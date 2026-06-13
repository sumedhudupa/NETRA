from pathlib import Path
import os
import inspect
import logging
import numpy as np
import time

import soundfile as sf
try:
    import whisper
except Exception:  # pragma: no cover
    whisper = None

try:
    from faster_whisper import WhisperModel as FasterWhisperModel
except Exception:  # pragma: no cover
    FasterWhisperModel = None

from netra.hardware.interfaces import HardwareAdapter

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None

try:
    from vosk import Model as VoskModel, KaldiRecognizer
    import json as vosk_json
except Exception:  # pragma: no cover
    VoskModel = None
    KaldiRecognizer = None
    vosk_json = None


import threading

class STTService:
    def __init__(
        self,
        whisper_model_name: str,
        vosk_model_path: str,
        sample_rate: int,
        wake_word: str,
        stt_engine: str = "vosk",
        stt_engine_wake_word: str = "vosk",
        stt_engine_command: str = "whisper",
        use_live_mic: bool = True,
        allow_typed_fallback: bool = False,
        stt_offline: bool = True,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.sample_rate = sample_rate
        self.wake_word = wake_word.lower()
        self.use_live_mic = use_live_mic
        self.allow_typed_fallback = allow_typed_fallback
        self.stt_offline = bool(stt_offline)
        self.stt_engine = stt_engine.lower()
        self.stt_engine_wake_word = stt_engine_wake_word.lower()
        self.stt_engine_command = stt_engine_command.lower()
        
        # Whisper model
        self.whisper_model = None
        self._whisper_backend = "none"
        needs_whisper = (
            self.stt_engine == "whisper"
            or self.stt_engine_wake_word == "whisper"
            or self.stt_engine_command == "whisper"
        )
        if needs_whisper:
            try:
                resolved_whisper_model = whisper_model_name
                # Convenience: if user config says "base" and a local folder exists, prefer it.
                local_fw_dir = Path("models") / f"faster-whisper-{whisper_model_name}"
                if not Path(resolved_whisper_model).exists() and local_fw_dir.exists():
                    resolved_whisper_model = str(local_fw_dir)

                if self.stt_offline:
                    # Prevent any accidental network access via HF Hub.
                    os.environ.setdefault("HF_HUB_OFFLINE", "1")
                    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

                if FasterWhisperModel is not None:
                    kwargs = {
                        "device": "cpu",
                        "compute_type": "int8",
                    }
                    # Newer faster-whisper supports local_files_only to avoid any downloads.
                    try:
                        params = inspect.signature(FasterWhisperModel).parameters
                        if self.stt_offline and "local_files_only" in params:
                            kwargs["local_files_only"] = True
                    except Exception:  # pragma: no cover
                        pass

                    self.whisper_model = FasterWhisperModel(resolved_whisper_model, **kwargs)
                    self._whisper_backend = "faster-whisper"
                    self.logger.info(
                        "Whisper model loaded (%s): %s", self._whisper_backend, resolved_whisper_model
                    )
                elif whisper is not None:
                    if self.stt_offline and not Path(resolved_whisper_model).exists():
                        raise RuntimeError(
                            "Offline STT enabled but Whisper model is not a local path. "
                            "Set whisper_model to a local .pt file path (openai-whisper) or "
                            "a local faster-whisper directory."
                        )
                    # openai-whisper will download weights if given a model name and not cached.
                    self.whisper_model = whisper.load_model(resolved_whisper_model)
                    self._whisper_backend = "openai-whisper"
                    self.logger.info(
                        "Whisper model loaded (%s): %s", self._whisper_backend, resolved_whisper_model
                    )
                else:
                    self.logger.info("Whisper libraries not installed; Whisper STT disabled")
            except Exception as exc:
                self.logger.warning("Whisper model unavailable (%s): %s", whisper_model_name, exc)
        
        # Vosk model
        self.vosk_model = None
        if VoskModel is not None:
            try:
                if Path(vosk_model_path).exists():
                    self.vosk_model = VoskModel(vosk_model_path)
                    self.logger.info("Vosk model loaded: %s", vosk_model_path)
                else:
                    self.logger.warning("Vosk model path does not exist: %s", vosk_model_path)
            except Exception as exc:
                self.logger.warning("Vosk model unavailable (%s): %s", vosk_model_path, exc)
        else:
            self.logger.warning("Vosk library not installed")

    def transcribe_wav(self, wav_path: str, engine: str = None) -> str:
        """Transcribe audio from WAV file using specified engine."""
        if engine is None:
            engine = self.stt_engine
        
        data, sample_rate = sf.read(wav_path, dtype="float32")
        if sample_rate != self.sample_rate:
            self.logger.warning("Sample rate %s differs from expected %s", sample_rate, self.sample_rate)
        
        if engine == "whisper":
            return self._transcribe_with_whisper(data)
        elif engine == "vosk":
            return self._transcribe_with_vosk(data)
        else:
            self.logger.error("Unknown STT engine: %s", engine)
            return ""
    
    def _transcribe_with_whisper(self, audio: np.ndarray) -> str:
        """Transcribe audio using Whisper model."""
        if self.whisper_model is None:
            self.logger.warning("Whisper model not available")
            return ""
        if self._whisper_backend == "faster-whisper":
            segments, _info = self.whisper_model.transcribe(audio, language="en")
            text = " ".join(segment.text.strip() for segment in segments if getattr(segment, "text", "").strip())
            text = text.strip().lower()
        else:
            result = self.whisper_model.transcribe(audio, language="en", fp16=False)
            text = result.get("text", "").strip().lower()
        self.logger.info("Whisper STT transcript: %s", text)
        return text
    
    def _transcribe_with_vosk(self, audio: np.ndarray) -> str:
        """Transcribe audio using Vosk model."""
        if self.vosk_model is None or KaldiRecognizer is None:
            self.logger.warning("Vosk model not available")
            return ""
        
        try:
            # Convert float32 to int16 for Vosk
            audio_int16 = (audio * 32767).astype(np.int16)
            
            recognizer = KaldiRecognizer(self.vosk_model, self.sample_rate)
            recognizer.AcceptWaveform(audio_int16.tobytes())
            result = vosk_json.loads(recognizer.FinalResult())
            text = result.get("text", "").strip().lower()
            self.logger.info("Vosk STT transcript: %s", text)
            return text
        except Exception as exc:
            self.logger.error("Vosk transcription failed: %s", exc)
            return ""

    def _record_microphone_audio(self, record_seconds: int) -> np.ndarray | None:
        if sd is None:
            self.logger.warning("sounddevice is unavailable; cannot record from live microphone")
            return None
        try:
            self.logger.info("Recording microphone for %s second(s)", record_seconds)
            recording = sd.rec(
                int(record_seconds * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=None  # Use system default microphone
            )
            sd.wait()
            # Software gain: boost quiet microphones
            return recording.flatten() * 3.0
        except Exception as exc:
            self.logger.warning("Microphone recording failed: %s", exc)
            return None

    def _transcribe_array(self, audio: np.ndarray, engine: str = None) -> str:
        """Transcribe audio array using specified engine."""
        if engine is None:
            engine = self.stt_engine
        
        if engine == "whisper":
            return self._transcribe_with_whisper(audio)
        elif engine == "vosk":
            return self._transcribe_with_vosk(audio)
        else:
            self.logger.error("Unknown STT engine: %s", engine)
            return ""

    def listen_for_command(self, hardware: HardwareAdapter, record_seconds: int) -> str:
        """Listen for command using configured command engine (Whisper by default for accuracy)."""
        engine = self.stt_engine_command
        
        # Always use hardware recording on RPi
        audio_path = hardware.record_audio(record_seconds)
        if audio_path and Path(audio_path).exists():
            return self.transcribe_wav(audio_path, engine=engine)

        # Fallback to live mic if hardware doesn't support recording
        if self.use_live_mic:
            # Check if the selected engine is available
            if engine == "whisper" and self.whisper_model is None:
                self.logger.warning("Whisper not available, falling back to Vosk")
                engine = "vosk"
            elif engine == "vosk" and self.vosk_model is None:
                self.logger.warning("Vosk not available, falling back to Whisper")
                engine = "whisper"
            
            audio = self._record_microphone_audio(record_seconds)
            if audio is not None:
                transcript = self._transcribe_array(audio, engine=engine)
                if transcript:
                    return transcript

        if self.allow_typed_fallback:
            self.logger.info("Falling back to typed command input")
            return input("[STT FALLBACK] Type command: ").strip().lower()

        self.logger.warning("No command transcribed from microphone")
        return ""

    def wait_for_wake(self, hardware: HardwareAdapter, record_seconds: int) -> None:
        """Wait for wake word using configured wake word engine (Vosk by default for speed)."""
        engine = self.stt_engine_wake_word
        
        # Always use hardware recording on RPi
        audio_path = hardware.record_audio(record_seconds)
        if audio_path and Path(audio_path).exists():
            transcript = self.transcribe_wav(audio_path, engine=engine)
            if self.wake_word in transcript:
                self.logger.info("Wake word detected from hardware recording")
                return
            self.logger.info("Wake word not detected in transcript: %s", transcript)
            return

        # Fallback to live mic if hardware doesn't support recording
        if self.use_live_mic:
            # Check if the selected engine is available
            if engine == "whisper" and self.whisper_model is None:
                self.logger.warning("Whisper not available for wake word, falling back to Vosk")
                engine = "vosk"
            elif engine == "vosk" and self.vosk_model is None:
                self.logger.warning("Vosk not available for wake word, falling back to Whisper")
                engine = "whisper"
            
            audio = self._record_microphone_audio(record_seconds)
            if audio is not None:
                transcript = self._transcribe_array(audio, engine=engine)
                if self.wake_word in transcript:
                    self.logger.info("Wake word detected from live microphone using %s", engine)
                    return
                self.logger.info("Wake word not detected from live microphone")
            return

        self.logger.info("Wake word simulation fallback enabled")
        input("[HW STUB] Press ENTER to simulate wake word... ")
