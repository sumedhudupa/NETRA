import os
from pathlib import Path
from typing import List, Optional

from PIL import Image

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz  # type: ignore[no-redef]
    except ImportError as exc:
        raise ImportError(
            "PDF support requires PyMuPDF. Install it with 'python -m pip install PyMuPDF'."
        ) from exc

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
            with Image.open(path) as image:
                text, _ = self.ocr_service.extract_text_with_confidence(image)
                return text
        return ""

    def extract_ocr_from_camera_image(self, image_path: str, min_confidence: float = 0.0) -> Optional[str]:
        with Image.open(image_path) as image:
            text, confidence = self.ocr_service.extract_text_with_confidence(image)
        if confidence < min_confidence:
            return None
        return text

    def extract_ocr_chunks_from_camera_image(
        self,
        image_path: str,
        min_confidence: float = 0.0,
        lines_per_chunk: int = 2,
    ) -> Optional[List[str]]:
        image = Image.open(image_path)
        chunks_with_confidence = self.ocr_service.extract_text_chunks_with_confidence(
            image,
            lines_per_chunk=lines_per_chunk,
        )
        if not chunks_with_confidence:
            return None

        overall_confidence = sum(confidence for _, confidence in chunks_with_confidence) / len(chunks_with_confidence)
        if overall_confidence < min_confidence:
            return None

        return [text for text, _ in chunks_with_confidence if text.strip()]

    def extract_text_chunks(
        self,
        path: str,
        pdf_pages_per_chunk: int = 1,
        ocr_lines_per_chunk: int = 2,
    ) -> List[str]:
        suffix = Path(path).suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf_text_chunks(path, pdf_pages_per_chunk=pdf_pages_per_chunk)
        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
            with Image.open(path) as image:
                return [
                    text
                    for text, _ in self.ocr_service.extract_text_chunks_with_confidence(
                        image,
                        lines_per_chunk=ocr_lines_per_chunk,
                    )
                    if text.strip()
                ]
        return []

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

    def _extract_pdf_text_chunks(self, path: str, pdf_pages_per_chunk: int = 1) -> List[str]:
        doc = fitz.open(path)
        chunks: List[str] = []
        pending_pages: List[str] = []
        page_group_size = max(1, pdf_pages_per_chunk)

        try:
            for page in doc:
                text = page.get_text().strip()
                if not text:
                    continue
                pending_pages.append(text)
                if len(pending_pages) >= page_group_size:
                    chunks.append("\n\n".join(pending_pages))
                    pending_pages = []
        finally:
            doc.close()

        if pending_pages:
            chunks.append("\n\n".join(pending_pages))

        return chunks
