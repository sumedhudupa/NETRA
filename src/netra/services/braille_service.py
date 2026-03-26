from typing import List, Tuple
from pathlib import Path
import logging

try:
    import louis
except Exception:  # pragma: no cover
    louis = None


class BrailleService:
    def __init__(self, table: str, cells: int) -> None:
        self.table = table
        self.cells = cells
        self.logger = logging.getLogger(__name__)

    def text_to_patterns(self, text: str) -> Tuple[str, List[int]]:
        # Normalize: basic cleanup for fallback or liblouis
        text = text.replace("\n", " ").replace("\r", " ")
        
        if louis is None:
            contracted = text.lower()
            basic_map = {
                "a": 0b000001, "b": 0b000011, "c": 0b001001, "d": 0b011001, "e": 0b010001,
                "f": 0b001011, "g": 0b011011, "h": 0b010011, "i": 0b001010, "j": 0b011010,
                "k": 0b000101, "l": 0b000111, "m": 0b001101, "n": 0b011101, "o": 0b010101,
                "p": 0b001111, "q": 0b011111, "r": 0b010111, "s": 0b001110, "t": 0b011110,
                "u": 0b100101, "v": 0b100111, "w": 0b111010, "x": 0b101101, "y": 0b111101,
                "z": 0b110101, " ": 0b000000, ",": 0b000010, ".": 0b010110, "?": 0b010010,
                "!": 0b010111, "-": 0b100100, "'": 0b000100, "1": 0b000001, "2": 0b000011,
                "3": 0b001001, "4": 0b011001, "5": 0b010001, "6": 0b001011, "7": 0b011011,
                "8": 0b010011, "9": 0b001010, "0": 0b011010
            }
            patterns = [basic_map.get(ch, 0b000000) for ch in contracted]
            self.logger.warning("liblouis unavailable; using basic fallback braille mapping")
            return contracted, patterns

        contracted = louis.translateString([self.table], text)
        patterns: List[int] = []
        for char in contracted:
            dots_char = louis.charToDots([self.table], char, mode=louis.dotsIO)
            patterns.append(ord(dots_char) & 0xFF)
        self.logger.info("Braille conversion complete: input=%d chars output=%d cells", len(text), len(patterns))
        return contracted, patterns

    def patterns_to_unicode(self, patterns: List[int]) -> str:
        braille_chars = []
        for pattern in patterns:
            braille_chars.append(chr(0x2800 + (pattern & 0xFF)))
        return "".join(braille_chars)

    def export_unicode_braille(self, patterns: List[int], output_file: str) -> str:
        unicode_braille = self.patterns_to_unicode(patterns)
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unicode_braille, encoding="utf-8")
        self.logger.info("Braille unicode exported to %s", path)
        return unicode_braille

    def chunk_patterns(self, patterns: List[int]) -> List[List[int]]:
        chunks: List[List[int]] = []
        for index in range(0, len(patterns), self.cells):
            chunk = patterns[index:index + self.cells]
            if len(chunk) < self.cells:
                chunk = chunk + [0] * (self.cells - len(chunk))
            chunks.append(chunk)
        return chunks
