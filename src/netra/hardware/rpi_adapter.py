from typing import List

from .interfaces import HardwareAdapter


class RaspberryPiHardwareAdapter(HardwareAdapter):
    """
    Placeholder adapter for Raspberry Pi GPIO/I2C integration.
    Replace each method body with actual hardware code.
    """

    def capture_image_path(self) -> str:
        raise NotImplementedError("Implement with picamera2 capture and temp file path")

    def wait_for_scroll(self) -> None:
        raise NotImplementedError("Implement with GPIO.wait_for_edge")

    def display_braille_cells(self, dot_patterns: List[int]) -> None:
        raise NotImplementedError("Implement I2C/UART write to braille controller")

    def play_wav(self, wav_path: str) -> None:
        raise NotImplementedError("Implement speaker playback, e.g., aplay")

    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        raise NotImplementedError("Implement microphone capture to wav")
