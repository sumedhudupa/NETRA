import os
import tempfile
import wave
import logging

from piper.voice import PiperVoice

from netra.hardware.interfaces import HardwareAdapter


class TTSService:
    PLAYBACK_LEADIN_MS = 250

    def __init__(self, model_path: str) -> None:
        self.logger = logging.getLogger(__name__)
        self.voice = None
        try:
            self.voice = PiperVoice.load(model_path)
            self.logger.info("Piper model loaded: %s", model_path)
        except Exception as exc:
            self.logger.warning("Piper model not available (%s): %s", model_path, exc)

    def speak(self, text: str, hardware: HardwareAdapter) -> None:
        self.logger.info("TTS speak request length=%d", len(text))
        print(f"[TTS] {text}")
        if self.voice is None:
            self.logger.info("TTS audio skipped because Piper model is unavailable")
            return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            wav_path = handle.name

        try:
            with wave.open(wav_path, "w") as wav_file:
                self.voice.synthesize_wav(text, wav_file)
            self.logger.info("Synthesized wav at %s", wav_path)
            self._prepend_silence(wav_path, self.PLAYBACK_LEADIN_MS)
            self.logger.info("Prepended %d ms silence to wav", self.PLAYBACK_LEADIN_MS)
            hardware.play_wav(wav_path)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)
                self.logger.debug("Deleted temporary wav file %s", wav_path)

    def _prepend_silence(self, wav_path: str, silence_ms: int) -> None:
        if silence_ms <= 0:
            return

        padded_path = f"{wav_path}.padded"

        try:
            with wave.open(wav_path, "rb") as source_wav:
                params = source_wav.getparams()
                frame_rate = source_wav.getframerate()
                channels = source_wav.getnchannels()
                sample_width = source_wav.getsampwidth()

                silence_frames = max(1, int(frame_rate * silence_ms / 1000.0))
                silence_frame = b"\x00" * sample_width * channels

                with wave.open(padded_path, "wb") as padded_wav:
                    padded_wav.setparams(params)
                    for _ in range(silence_frames):
                        padded_wav.writeframesraw(silence_frame)

                    while True:
                        chunk = source_wav.readframes(4096)
                        if not chunk:
                            break
                        padded_wav.writeframesraw(chunk)

            os.replace(padded_path, wav_path)
        except Exception as exc:
            self.logger.warning("Failed to prepend silence to wav: %s", exc)
            if os.path.exists(padded_path):
                os.unlink(padded_path)
