import os
from pathlib import Path
from typing import List, Optional

import fitz
from PIL import Image

from netra.models.types import DocumentRef
from netra.services.ocr_service import OCRService


class DocumentService:
    SUPPORTED = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff")

    def __init__(self, docs_dir: str, ocr_service: OCRService) -> None:
        self.docs_dir = Path(docs_dir)
        self.ocr_service = ocr_service

    def scan_documents(self) -> List[DocumentRef]:
        if not self.docs_dir.exists():
            self.docs_dir = Path.cwd()

        refs: List[DocumentRef] = []
        for file_name in sorted(os.listdir(self.docs_dir)):
            if file_name.lower().endswith(self.SUPPORTED):
                refs.append(
                    DocumentRef(
                        name=file_name,
                        path=str((self.docs_dir / file_name).resolve()),
                    )
                )
        return refs

    def extract_text(self, path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf_text(path)
        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
            image = Image.open(path)
            text, _ = self.ocr_service.extract_text_with_confidence(image)
            return text
        return ""

    def extract_ocr_from_camera_image(self, image_path: str, min_confidence: float = 50.0) -> Optional[str]:
        image = Image.open(image_path)
        text, confidence = self.ocr_service.extract_text_with_confidence(image)
        if confidence < min_confidence:
            return None
        return text

    def _extract_pdf_text(self, path: str) -> str:
        doc = fitz.open(path)
        pages = []
        try:
            for page in doc:
                text = page.get_text().strip()
                if text:
                    pages.append(text)
        finally:
            doc.close()
        return "\n\n".join(pages)
