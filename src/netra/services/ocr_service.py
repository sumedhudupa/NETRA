from typing import Tuple

import numpy as np
import pytesseract
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


class OCRService:
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
        processed = self.preprocess(image)
        data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT)

        confidences = []
        words = []
        for word, conf in zip(data.get("text", []), data.get("conf", [])):
            text = (word or "").strip()
            if not text:
                continue
            try:
                score = float(conf)
            except (TypeError, ValueError):
                continue
            if score >= 0:
                confidences.append(score)
                words.append(text)

        if not words:
            return "", 0.0

        return " ".join(words), sum(confidences) / len(confidences)
