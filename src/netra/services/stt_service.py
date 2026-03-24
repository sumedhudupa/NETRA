from pathlib import Path
import logging
import numpy as np

import soundfile as sf
import whisper

from netra.hardware.interfaces import HardwareAdapter

try:
    import sounddevice as sd
except Exception:  # pragma: no cover
    sd = None


class STTService:
    def __init__(
        self,
        whisper_model_name: str,
        sample_rate: int,
        wake_word: str,
        use_live_mic: bool = True,
        allow_typed_fallback: bool = False,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.sample_rate = sample_rate
        self.wake_word = wake_word.lower()
        self.use_live_mic = use_live_mic
        self.allow_typed_fallback = allow_typed_fallback
        self.model = None
        try:
            self.model = whisper.load_model(whisper_model_name)
            self.logger.info("Whisper model loaded: %s", whisper_model_name)
        except Exception as exc:
            self.logger.warning("Whisper model unavailable (%s): %s", whisper_model_name, exc)

    def transcribe_wav(self, wav_path: str) -> str:
        if self.model is None:
            return ""
        data, sample_rate = sf.read(wav_path, dtype="float32")
        if sample_rate != self.sample_rate:
            self.logger.warning("Sample rate %s differs from expected %s", sample_rate, self.sample_rate)
        result = self.model.transcribe(data, language="en", fp16=False)
        text = result.get("text", "").strip().lower()
        self.logger.info("STT transcript from wav: %s", text)
        return text

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
            )
            sd.wait()
            return recording.flatten()
        except Exception as exc:
            self.logger.warning("Microphone recording failed: %s", exc)
            return None

    def _transcribe_array(self, audio: np.ndarray) -> str:
        if self.model is None:
            return ""
        result = self.model.transcribe(audio, language="en", fp16=False)
        text = result.get("text", "").strip().lower()
        self.logger.info("STT transcript from live mic: %s", text)
        return text

    def listen_for_command(self, hardware: HardwareAdapter, record_seconds: int) -> str:
        source = hardware.read_audio_path_or_text_mode(record_seconds)
        if source and Path(source).exists():
            return self.transcribe_wav(source)

        if self.use_live_mic and self.model is not None:
            audio = self._record_microphone_audio(record_seconds)
            if audio is not None:
                transcript = self._transcribe_array(audio)
                if transcript:
                    return transcript

        if self.allow_typed_fallback:
            self.logger.info("Falling back to typed command input")
            return input("[STT FALLBACK] Type command: ").strip().lower()

        self.logger.warning("No command transcribed from microphone")
        return ""

    def wait_for_wake(self, hardware: HardwareAdapter, record_seconds: int) -> None:
        source = hardware.read_audio_path_or_text_mode(record_seconds)
        if source and Path(source).exists():
            transcript = self.transcribe_wav(source)
            if self.wake_word in transcript:
                self.logger.info("Wake word detected from wav input")
                return
            self.logger.info("Wake word not detected in wav transcript: %s", transcript)
            return

        if self.use_live_mic and self.model is not None:
            audio = self._record_microphone_audio(record_seconds)
            if audio is not None:
                transcript = self._transcribe_array(audio)
                if self.wake_word in transcript:
                    self.logger.info("Wake word detected from live microphone")
                    return
                self.logger.info("Wake word not detected from live microphone")
            return

        self.logger.info("Wake word simulation fallback enabled")
        input("[HW STUB] Press ENTER to simulate wake word... ")
