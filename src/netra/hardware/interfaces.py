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
    def display_braille_cells(self, dot_patterns: List[int], chars: List[str] | None = None) -> None:
        """Display a group of braille cells.
        - `dot_patterns` is a list of integer dot bitmasks (one per visible cell)
        - `chars` is an optional list of original characters corresponding to the patterns
        """
        pass

    @abstractmethod
    def display_capacity_chars(self) -> int:
        """Return how many characters (braille cells) this hardware can display concurrently."""
        pass

    @abstractmethod
    def play_wav(self, wav_path: str) -> None:
        pass

    @abstractmethod
    def record_audio(self, seconds: int) -> str:
        """Record audio from microphone and return path to WAV (or "" on failure)."""
        pass

    @abstractmethod
    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        """
        Return path to wav file or empty string to use typed text fallback.
        """
        pass
