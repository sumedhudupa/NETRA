from abc import ABC, abstractmethod
from typing import List


class HardwareAdapter(ABC):
    @abstractmethod
    def capture_image_path(self) -> str:
        pass

    @abstractmethod
    def wait_for_scroll(self) -> None:
        pass

    @abstractmethod
    def display_braille_cells(self, dot_patterns: List[int]) -> None:
        pass

    @abstractmethod
    def play_wav(self, wav_path: str) -> None:
        pass

    @abstractmethod
    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        """
        Return path to wav file or empty string to use typed text fallback.
        """
        pass
