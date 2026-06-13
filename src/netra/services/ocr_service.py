from typing import Dict, List, Tuple
import logging
import re

import numpy as np
import pytesseract
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


class OCRService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"[^\w\s.,:/()-]", " ", text)
        text = re.sub(r"[_=-]{3,}", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def preprocess_variants(self, image: Image.Image, fast_mode: bool = False) -> Dict[str, np.ndarray]:
        """Build a small set of OCR-friendly variants."""
        if cv2 is None:
            # Fallback if cv2 is missing
            return {"otsu": np.array(image.convert("L"))}

        bgr = np.array(image.convert("RGB"))
        # Ensure BGR format as cv2 expects
        bgr = cv2.cvtColor(bgr, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        denoised = cv2.medianBlur(clahe, 3)
        deskewed = self._deskew(denoised)

        otsu = cv2.threshold(deskewed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        variants: Dict[str, np.ndarray] = {
            "otsu": otsu,
        }

        if not fast_mode:
            adaptive = cv2.adaptiveThreshold(
                deskewed,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                9,
            )
            variants["adaptive"] = adaptive
            variants["gray"] = deskewed

        return variants

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        if cv2 is None:
            return image

        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

        if lines is None:
            return image

        angles = []
        for line in lines:
            rho, theta = line[0]
            angle = np.degrees(theta) - 90
            if -45 < angle < 45:
                angles.append(angle)

        if not angles:
            return image

        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.5:
            return image

        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        return cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _image_to_words(self, image: np.ndarray, lang: str = "eng", psm: int = 6, oem: int = 1) -> Tuple[List[str], List[float]]:
        config = f"--oem {oem} --psm {psm}"
        # Convert numpy array to PIL for pytesseract if needed, but pytesseract accepts numpy arrays.
        data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)

        words: List[str] = []
        confidences: List[float] = []

        for raw_text, raw_conf in zip(data.get("text", []), data.get("conf", [])):
            text = (raw_text or "").strip()
            if not text:
                continue
            try:
                conf = float(raw_conf)
            except (TypeError, ValueError):
                continue
            if conf < 60:
                continue
            words.append(text)
            confidences.append(conf)

        return words, confidences

    def run_best_ocr(self, variants: Dict[str, np.ndarray], lang: str = "eng") -> Dict:
        attempts = [("otsu", 6), ("adaptive", 6), ("gray", 11)]
        attempts = [a for a in attempts if a[0] in variants]

        best = {
            "text": "",
            "confidence": 0.0,
            "variant": "",
            "psm": -1,
            "word_count": 0,
            "words": [],
            "confidences": []
        }

        for variant_name, psm in attempts:
            words, confs = self._image_to_words(variants[variant_name], lang=lang, psm=psm)
            if not words:
                continue

            text = self._clean_text(" ".join(words))
            avg_conf = float(sum(confs) / len(confs))

            if avg_conf > best["confidence"]:
                best.update(
                    {
                        "text": text,
                        "confidence": avg_conf,
                        "variant": variant_name,
                        "psm": psm,
                        "word_count": len(words),
                        "words": words,
                        "confidences": confs
                    }
                )

        return best

    def extract_text_with_confidence(self, image: Image.Image, fast_mode: bool = False) -> Tuple[str, float]:
        variants = self.preprocess_variants(image, fast_mode=fast_mode)
        best = self.run_best_ocr(variants)
        return best["text"], best["confidence"]

    def extract_text_chunks_with_confidence(
        self,
        image: Image.Image,
        lines_per_chunk: int = 2,
        fast_mode: bool = False
    ) -> List[Tuple[str, float]]:
        """Return chunks directly from best run to minimize memory usage."""
        variants = self.preprocess_variants(image, fast_mode=fast_mode)
        best = self.run_best_ocr(variants)
        
        words = best["words"]
        confs = best["confidences"]
        
        if not words:
            return []

        # Simple chunking: we have words, let's group them loosely into chunks.
        # Approximating a "line" as roughly 8 words for chunking purposes 
        # (since we don't track full bounding boxes in the fast path to save RAM)
        words_per_line = 8
        words_per_chunk = max(1, lines_per_chunk * words_per_line)
        
        chunks: List[Tuple[str, float]] = []
        for i in range(0, len(words), words_per_chunk):
            chunk_words = words[i:i + words_per_chunk]
            chunk_confs = confs[i:i + words_per_chunk]
            if chunk_words:
                text = " ".join(chunk_words)
                conf = sum(chunk_confs) / len(chunk_confs)
                chunks.append((text, conf))
                
        return chunks
