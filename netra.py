#!/usr/bin/env python3
"""Compatibility launcher for NETRA modular runtime."""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from netra.app import run, _create_hardware_adapter
from netra.config import load_config
from netra.services.braille_service import BrailleService
from netra.services.document_service import DocumentService
from netra.services.ocr_service import OCRService


def render_braille_stream(
    text_chunks: list[str],
    braille: BrailleService,
    hardware,
    delay_seconds: float,
) -> None:
    """Render text chunks as braille patterns with display streaming."""
    for chunk_index, text_chunk in enumerate(text_chunks, start=1):
        cleaned = text_chunk.strip()
        if not cleaned:
            continue

        print()
        print(f"[TEXT CHUNK {chunk_index}]")
        print(cleaned)

        contracted, patterns = braille.text_to_patterns(cleaned)
        
        # Get hardware capacity and chunk by characters
        try:
            cap = max(1, int(hardware.display_capacity_chars()))
        except Exception:
            cap = braille.cells
        
        # Build character-aligned chunks
        chars = list(contracted)
        chunks = []
        for i in range(0, len(patterns), cap):
            pchunk = patterns[i:i+cap]
            cchunk = chars[i:i+cap]
            # Pad to capacity
            if len(pchunk) < cap:
                pchunk = pchunk + [0] * (cap - len(pchunk))
                cchunk = cchunk + [' '] * (cap - len(cchunk))
            chunks.append((pchunk, cchunk))
        
        print(f"[BRAILLE CHUNK {chunk_index}] {len(chunks)} display step(s)")

        for display_index, (pattern_chunk, char_chunk) in enumerate(chunks, start=1):
            print(f"  Step {display_index}/{len(chunks)}")
            hardware.display_braille_cells(pattern_chunk, char_chunk)
            if display_index < len(chunks):
                time.sleep(delay_seconds)


def view_document(args: argparse.Namespace) -> int:
    """Run document viewing mode with OCR/braille streaming."""
    config = load_config(ROOT / "config.json")
    
    target_path = Path(args.document).expanduser()
    if not target_path.is_absolute():
        target_path = (ROOT / target_path).resolve()

    if not target_path.exists():
        print(f"Error: File not found: {target_path}")
        return 1

    # Initialize services
    ocr = OCRService()
    docs = DocumentService(config.docs_dir, ocr)
    braille = BrailleService(config.braille_table, config.braille_cells)
    
    # Use configured hardware adapter (stepper, RPi, or stub)
    hardware = _create_hardware_adapter(config)

    # Extract text chunks using config values
    text_chunks = docs.extract_text_chunks(
        str(target_path),
        pdf_pages_per_chunk=config.pdf_pages_per_chunk,
        ocr_lines_per_chunk=config.ocr_lines_per_chunk,
    )
    text_chunks = [chunk for chunk in text_chunks if chunk.strip()]

    if not text_chunks:
        print("Error: No readable text found in document.")
        return 1

    # Display document information
    print("=" * 60)
    print("NETRA Document Viewer - OCR/Braille Stream")
    print("=" * 60)
    print(f"Source: {target_path}")
    print(f"Text chunks: {len(text_chunks)}")
    print(f"Braille cells per display step: {config.braille_cells}")
    print(f"OCR lines per chunk: {config.ocr_lines_per_chunk}")
    print(f"PDF pages per chunk: {config.pdf_pages_per_chunk}")

    # Render braille stream
    render_braille_stream(text_chunks, braille, hardware, config.braille_display_delay)

    print()
    print("Document viewing complete.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="NETRA - AI-powered assistive device for visually impaired users"
    )
    parser.add_argument(
        "--view",
        dest="document",
        metavar="FILE",
        help="View a document with OCR/braille streaming (PDF or image file)",
    )
    
    args = parser.parse_args()
    
    if args.document:
        # Document viewing mode
        sys.exit(view_document(args))
    else:
        # Normal interactive mode
        run()
