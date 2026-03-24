from typing import List
import logging
import platform
import time
from pathlib import Path

if platform.system() == "Windows":
    import winsound

from .interfaces import HardwareAdapter


class StubHardwareAdapter(HardwareAdapter):
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def capture_image_path(self) -> str:
        docs_dir = Path.cwd() / "docs"
        candidates = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff"):
            candidates.extend(docs_dir.glob(ext))

        if not candidates:
            self.logger.warning("No image found in docs folder for camera stub")
            return ""

        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        self.logger.info("Camera stub selected image %s", latest)
        return str(latest)

    def wait_for_scroll(self) -> None:
        time.sleep(0.8)

    def display_braille_cells(self, dot_patterns: List[int]) -> None:
        rendered = []
        for index, pattern in enumerate(dot_patterns, start=1):
            dots = [str(dot + 1) for dot in range(6) if pattern & (1 << dot)]
            rendered.append(f"Cell{index}:[{','.join(dots)}]")
        print("[HW STUB] Braille:", " ".join(rendered))

    def play_wav(self, wav_path: str) -> None:
        print(f"[HW STUB] Playing audio: {wav_path}")
        if platform.system() == "Windows":
            try:
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                self.logger.info("Played wav on Windows: %s", wav_path)
                return
            except Exception as exc:
                self.logger.warning("Windows audio playback failed: %s", exc)
        self.logger.info("Audio playback stub fallback used")

    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        return ""
