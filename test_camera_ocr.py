#!/usr/bin/env python3
from __future__ import annotations

"""
Standalone OCR test script optimized for Raspberry Pi.

Expected workflow:
1) Capture image separately (example):
   ffmpeg -f v4l2 -i /dev/video0 -frames:v 1 ~/photo_hq.jpg
2) Run this script to preprocess + OCR + print extracted text.
"""

import argparse
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from PIL import Image  # noqa: F401  # imported to validate Pillow presence
except ImportError:
    Image = None


def setup_logging(log_level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def validate_dependencies() -> None:
    missing = []
    if np is None:
        missing.append("numpy")
    if cv2 is None:
        missing.append("opencv-python-headless (cv2)")
    if pytesseract is None:
        missing.append("pytesseract")
    if Image is None:
        missing.append("Pillow")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "Missing Python dependency/dependencies: "
            f"{joined}. Install requirements before running OCR test."
        )


# ---------------------------------------------------------------------------
# Capture + Image IO
# ---------------------------------------------------------------------------

def capture_image(
    output_dir: Path,
    width: int,
    height: int,
    warmup_ms: int,
    quality: int,
    encoding: str,
    output_image: str | None = None,
) -> Path:
    """Capture one image using ffmpeg and return file path."""
    logger = logging.getLogger(__name__)
    output_dir.mkdir(parents=True, exist_ok=True)

    if output_image:
        image_path = Path(output_image).expanduser().resolve()
        image_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        suffix = "png" if encoding.lower() == "png" else "jpg"
        image_path = (output_dir / f"capture_{int(time.time())}.{suffix}").resolve()

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "v4l2",
        "-video_size", f"{width}x{height}",
        "-i", "/dev/video0",
        "-frames:v", "1",
        str(image_path),
    ]

    logger.info("Running capture: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed with exit code "
            f"{result.returncode}. stderr: {result.stderr.strip()}"
        )

    if not image_path.exists():
        raise RuntimeError(f"Capture completed but file not found: {image_path}")

    logger.info("Captured image: %s", image_path)
    return image_path


def load_input_image(image_path: Path) -> "np.ndarray":
    """Load image as OpenCV BGR ndarray."""
    logger = logging.getLogger(__name__)
    resolved = image_path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Input image not found: {resolved}")

    img = cv2.imread(str(resolved), cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f"OpenCV could not read: {resolved}")

    logger.info("Loaded image: %s (%dx%d)", resolved, img.shape[1], img.shape[0])
    return img


def clean_text(text: str) -> str:
    text = re.sub(r"[^\w\s.,:/()-]", " ", text)
    text = re.sub(r"[_=-]{3,}", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def preprocess_variants(bgr: "np.ndarray", fast_mode: bool = False) -> "dict[str, np.ndarray]":
    """
    Build a small set of OCR-friendly variants.

    Designed for Raspberry Pi: good quality with moderate CPU usage.
    """
    logger = logging.getLogger(__name__)

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # CLAHE improves local contrast on uneven lighting.
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)

    # Median blur is cheaper than heavy denoisers on Pi and works well for text.
    denoised = cv2.medianBlur(clahe, 3)

    deskewed = _deskew(denoised)

    otsu = cv2.threshold(deskewed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    variants: dict[str, np.ndarray] = {
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

        # Keep a grayscale candidate for difficult low-contrast text.
        variants["gray"] = deskewed

    logger.info("Prepared %d preprocessing variant(s)", len(variants))
    return variants


def _deskew(image: "np.ndarray") -> "np.ndarray":
    """Rotate image to correct text skew using Hough line detection."""
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
    rotated = cv2.warpAffine(
        image, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def _image_to_words(image: "np.ndarray", lang: str, psm: int, oem: int = 1) -> "tuple[list[str], list[float]]":
    """Run Tesseract and return filtered words with confidences."""
    config = f"--oem {oem} --psm {psm}"
    data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)

    words: list[str] = []
    confidences: list[float] = []

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


def run_best_ocr(variants: "dict[str, np.ndarray]", lang: str, forced_psm: int | None = None) -> dict:
    """Try a few low-cost OCR passes and keep the best result by confidence."""
    logger = logging.getLogger(__name__)

    attempts: list[tuple[str, int]] = []
    if forced_psm is not None:
        for name in variants:
            attempts.append((name, forced_psm))
    else:
        # PSM 6: block of text, PSM 11: sparse text.
        attempts = [("otsu", 6), ("adaptive", 6), ("gray", 11)]
        attempts = [a for a in attempts if a[0] in variants]

    best = {
        "text": "",
        "confidence": 0.0,
        "variant": "",
        "psm": -1,
        "word_count": 0,
    }

    for variant_name, psm in attempts:
        words, confs = _image_to_words(variants[variant_name], lang=lang, psm=psm)
        if not words:
            logger.info("OCR attempt variant=%s psm=%d -> no text", variant_name, psm)
            continue

        text = clean_text(" ".join(words))
        avg_conf = float(sum(confs) / len(confs))
        logger.info(
            "OCR attempt variant=%s psm=%d -> words=%d conf=%.2f",
            variant_name,
            psm,
            len(words),
            avg_conf,
        )

        if avg_conf > best["confidence"]:
            best.update(
                {
                    "text": text,
                    "confidence": avg_conf,
                    "variant": variant_name,
                    "psm": psm,
                    "word_count": len(words),
                }
            )

    return best


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def test_capture_and_ocr(
    use_existing: bool = False,
    input_image: str = "~/NETRA/photo_hq.jpg",
    output_dir: str = "test_output",
    width: int = 2592,
    height: int = 1944,
    warmup_ms: int = 3000,
    quality: int = 100,
    encoding: str = "jpg",
    lang: str = "eng",
    fast_mode: bool = False,
    forced_psm: int | None = None,
    save_preprocessed: bool = False,
) -> dict:
    """
    Pipeline: capture image -> preprocess -> OCR.

    Returns:
        dict with OCR results and metadata.
    """
    logger = logging.getLogger(__name__)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    input_path = Path(input_image).expanduser().resolve()

    results = {
        "image_path": str(input_path),
        "best_variant": "",
        "psm": -1,
        "word_count": 0,
        "extracted_text": "",
        "confidence": 0.0,
        "success": False,
    }

    try:
        if use_existing:
            logger.info("Step 1/3 - Using existing image")
        else:
            logger.info("Step 1/3 - Capturing image")
            input_path = capture_image(
                output_dir=output_path,
                width=width,
                height=height,
                warmup_ms=warmup_ms,
                quality=quality,
                encoding=encoding,
                output_image=input_image,
            )
            results["image_path"] = str(input_path)

        logger.info("Step 1/3 - Loading image")
        bgr = load_input_image(input_path)

        logger.info("Step 2/3 - Preprocessing for OCR")
        variants = preprocess_variants(bgr, fast_mode=fast_mode)

        if save_preprocessed:
            for name, image in variants.items():
                out_file = output_path / f"preprocessed_{input_path.stem}_{name}.png"
                cv2.imwrite(str(out_file), image)
                logger.info("Saved: %s", out_file)

        logger.info("Step 3/3 - Running OCR")
        best = run_best_ocr(variants, lang=lang, forced_psm=forced_psm)

        results["extracted_text"] = clean_text(best["text"])
        results["confidence"] = best["confidence"]
        results["best_variant"] = best["variant"]
        results["psm"] = best["psm"]
        results["word_count"] = best["word_count"]
        results["success"] = True

        logger.info("Selected variant: %s", best["variant"])
        logger.info("PSM: %s", best["psm"])
        logger.info("Words: %d", best["word_count"])
        logger.info("Confidence: %.2f", best["confidence"])

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Capture image on Raspberry Pi and run OCR"
    )
    parser.add_argument("--input-image", default="~/NETRA/photo_hq.jpg",
                        help="Output image path for capture (or existing image path with --use-existing)")
    parser.add_argument("--use-existing", action="store_true",
                        help="Skip capture and run OCR on --input-image")
    parser.add_argument("--width", type=int, default=2592,
                        help="Capture width (default: 2592)")
    parser.add_argument("--height", type=int, default=1944,
                        help="Capture height (default: 1944)")
    parser.add_argument("--warmup-ms", type=int, default=3000,
                        help="Sensor warmup timeout in ms (default: 3000)")
    parser.add_argument("--quality", type=int, default=100,
                        help="Capture quality (default: 100)")
    parser.add_argument("--encoding", default="jpg", choices=["png", "jpg"],
                        help="Capture encoding (default: jpg)")
    parser.add_argument("--lang", default="eng",
                        help="Tesseract language (default: eng)")
    parser.add_argument("--psm", type=int, default=None,
                        help="Force Tesseract page segmentation mode")
    parser.add_argument("--fast", action="store_true",
                        help="Use fewer OCR attempts for faster runtime on Pi")
    parser.add_argument("--output-dir", default="test_output",
                        help="Output directory for optional preprocessed images")
    parser.add_argument("--save-preprocessed", action="store_true",
                        help="Save intermediate preprocessed images")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()
    setup_logging(args.log_level)
    validate_dependencies()

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("NETRA - Capture + OCR Test (Raspberry Pi)")
    logger.info("=" * 60)

    results = test_capture_and_ocr(
        use_existing=args.use_existing,
        input_image=args.input_image,
        output_dir=args.output_dir,
        width=args.width,
        height=args.height,
        warmup_ms=args.warmup_ms,
        quality=args.quality,
        encoding=args.encoding,
        lang=args.lang,
        fast_mode=args.fast,
        forced_psm=args.psm,
        save_preprocessed=args.save_preprocessed,
    )

    print("\n" + "=" * 72)
    print("RESULTS")
    print("=" * 72)

    if results["success"]:
        print(f"Image           : {results['image_path']}")
        print(f"Best variant    : {results['best_variant']}")
        print(f"PSM             : {results['psm']}")
        print(f"Words detected  : {results['word_count']}")
        print(f"Confidence      : {results['confidence']:.2f}")
        print(f"\nExtracted Text:\n{'-' * 72}")
        print(results["extracted_text"] if results["extracted_text"] else "(No text detected)")
        print("-" * 72)
    else:
        print("Test failed. Check logs above for details.")
        return 1

    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())