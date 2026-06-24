#!/usr/bin/env python3
"""
Standalone test script for chunked OCR/PDF-to-braille streaming.

Usage:
    python test_ocr_braille_stream.py docs/sample.jpg
    python test_ocr_braille_stream.py docs/sample.pdf --pdf-pages-per-chunk 1
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from netra.config import load_config
from netra.hardware.stub_adapter import StubHardwareAdapter
from netra.services.braille_service import BrailleService
from netra.services.document_service import DocumentService
from netra.services.ocr_service import OCRService


def render_braille_stream(
    text_chunks: list[str],
    braille: BrailleService,
    hardware: StubHardwareAdapter,
    delay_seconds: float,
) -> None:
    for chunk_index, text_chunk in enumerate(text_chunks, start=1):
        cleaned = text_chunk.strip()
        if not cleaned:
            continue

        print()
        print(f"[TEXT CHUNK {chunk_index}]")
        print(cleaned)

        _, patterns = braille.text_to_patterns(cleaned)
        braille_chunks = braille.chunk_patterns(patterns)
        print(f"[BRAILLE CHUNK {chunk_index}] {len(braille_chunks)} display step(s)")

        for display_index, display_chunk in enumerate(braille_chunks, start=1):
            print(f"  Step {display_index}/{len(braille_chunks)}")
            hardware.display_braille_cells(display_chunk)
            if display_index < len(braille_chunks):
                time.sleep(delay_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test chunked OCR/PDF braille streaming.")
    parser.add_argument("path", help="Path to a PDF or image file.")
    parser.add_argument(
        "--ocr-lines-per-chunk",
        type=int,
        default=2,
        help="Number of OCR text lines to group into one streamed chunk.",
    )
    parser.add_argument(
        "--pdf-pages-per-chunk",
        type=int,
        default=1,
        help="Number of PDF pages to group into one streamed chunk.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay between 4-cell braille display steps.",
    )
    args = parser.parse_args()

    target_path = Path(args.path).expanduser()
    if not target_path.is_absolute():
        target_path = (ROOT / target_path).resolve()

    if not target_path.exists():
        print(f"File not found: {target_path}")
        return 1

    config = load_config(ROOT / "config.json")
    ocr = OCRService()
    docs = DocumentService(config.docs_dir, ocr)
    braille = BrailleService(config.braille_table, config.braille_cells)
    hardware = StubHardwareAdapter()

    text_chunks = docs.extract_text_chunks(
        str(target_path),
        pdf_pages_per_chunk=args.pdf_pages_per_chunk,
        ocr_lines_per_chunk=args.ocr_lines_per_chunk,
    )
    text_chunks = [chunk for chunk in text_chunks if chunk.strip()]

    if not text_chunks:
        print("No readable text found.")
        return 1

    print("=" * 60)
    print("NETRA Chunked OCR/Braille Stream Test")
    print("=" * 60)
    print(f"Source: {target_path}")
    print(f"Text chunks: {len(text_chunks)}")
    print(f"Braille cells per display step: {config.braille_cells}")

    render_braille_stream(text_chunks, braille, hardware, args.delay)

    print()
    print("Streaming test complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
