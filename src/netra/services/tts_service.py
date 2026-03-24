import os
import tempfile
import wave
import logging

from piper.voice import PiperVoice

from netra.hardware.interfaces import HardwareAdapter


class TTSService:
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
            hardware.play_wav(wav_path)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)
                self.logger.debug("Deleted temporary wav file %s", wav_path)
