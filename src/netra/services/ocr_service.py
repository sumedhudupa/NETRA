from typing import Dict, List, Tuple

import numpy as np
import pytesseract
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


class OCRService:
    def _extract_word_entries(self, image: Image.Image) -> List[Dict[str, object]]:
        processed = self.preprocess(image)
        data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)

        entries: List[Dict[str, object]] = []
        total = len(data.get("text", []))
        for index in range(total):
            text = (data["text"][index] or "").strip()
            if not text:
                continue
            try:
                score = float(data["conf"][index])
            except (TypeError, ValueError):
                continue
            if score < 0:
                continue

            entries.append(
                {
                    "text": text,
                    "conf": score,
                    "block_num": data.get("block_num", [0] * total)[index],
                    "par_num": data.get("par_num", [0] * total)[index],
                    "line_num": data.get("line_num", [0] * total)[index],
                }
            )

        return entries

    def preprocess(self, image: Image.Image) -> Image.Image:
        if cv2 is None:
            return image.convert("L")

        img_np = np.array(image)
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray)
        thresh = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        return Image.fromarray(thresh)

    def extract_text_with_confidence(self, image: Image.Image) -> Tuple[str, float]:
        entries = self._extract_word_entries(image)
        confidences = [float(entry["conf"]) for entry in entries]
        words = [str(entry["text"]) for entry in entries]

        if not words:
            return "", 0.0

        return " ".join(words), sum(confidences) / len(confidences)

    def extract_text_chunks_with_confidence(
        self,
        image: Image.Image,
        lines_per_chunk: int = 2,
    ) -> List[Tuple[str, float]]:
        entries = self._extract_word_entries(image)
        if not entries:
            return []

        lines: List[Tuple[str, float]] = []
        current_key = None
        current_words: List[str] = []
        current_confidences: List[float] = []

        for entry in entries:
            line_key = (entry["block_num"], entry["par_num"], entry["line_num"])
            if current_key is None:
                current_key = line_key
            if line_key != current_key and current_words:
                line_text = " ".join(current_words).strip()
                if line_text:
                    lines.append((line_text, sum(current_confidences) / len(current_confidences)))
                current_key = line_key
                current_words = []
                current_confidences = []

            current_words.append(str(entry["text"]))
            current_confidences.append(float(entry["conf"]))

        if current_words:
            line_text = " ".join(current_words).strip()
            if line_text:
                lines.append((line_text, sum(current_confidences) / len(current_confidences)))

        if not lines:
            return []

        chunks: List[Tuple[str, float]] = []
        chunk_lines: List[str] = []
        chunk_confidences: List[float] = []

        for line_text, line_confidence in lines:
            chunk_lines.append(line_text)
            chunk_confidences.append(line_confidence)

            if len(chunk_lines) >= max(1, lines_per_chunk):
                chunks.append(
                    ("\n".join(chunk_lines), sum(chunk_confidences) / len(chunk_confidences))
                )
                chunk_lines = []
                chunk_confidences = []

        if chunk_lines:
            chunks.append(
                ("\n".join(chunk_lines), sum(chunk_confidences) / len(chunk_confidences))
            )

        return chunks
