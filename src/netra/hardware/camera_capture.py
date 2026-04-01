from __future__ import annotations

import logging
import time
from pathlib import Path

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def _open_camera(device_index: int):
    if cv2 is None:
        return None

    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(cv2.CAP_DSHOW)
    if hasattr(cv2, "CAP_MSMF"):
        backends.append(cv2.CAP_MSMF)
    backends.append(None)

    for backend in backends:
        camera = cv2.VideoCapture(device_index, backend) if backend is not None else cv2.VideoCapture(device_index)
        if camera is not None and camera.isOpened():
            return camera
        if camera is not None:
            camera.release()

    return None


def capture_frame_with_opencv(
    output_dir: str | Path,
    device_index: int = 0,
    width: int = 2560,
    height: int = 1440,
    warmup_frames: int = 30,
    logger: logging.Logger | None = None,
) -> str:
    if cv2 is None:
        if logger:
            logger.warning("OpenCV is not installed, cannot capture from USB camera")
        return ""

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"capture_{int(time.time() * 1000)}.jpg"

    camera = _open_camera(device_index)
    if camera is None:
        if logger:
            logger.warning("No camera could be opened on device index %d", device_index)
        return ""

    try:
        if hasattr(cv2, "VideoWriter_fourcc"):
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if hasattr(cv2, "CAP_PROP_AUTOFOCUS"):
            camera.set(cv2.CAP_PROP_AUTOFOCUS, 1)

        frame = None
        best_frame = None
        best_sharpness = -1.0
        for _ in range(max(1, warmup_frames)):
            ok, grabbed = camera.read()
            if ok:
                frame = grabbed
                gray = cv2.cvtColor(grabbed, cv2.COLOR_BGR2GRAY)
                sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
                if sharpness > best_sharpness:
                    best_sharpness = sharpness
                    best_frame = grabbed.copy()
            time.sleep(0.05)

        if best_frame is not None:
            frame = best_frame

        if frame is None:
            if logger:
                logger.warning("Camera opened but no frame was captured")
            return ""

        saved = cv2.imwrite(str(output_path), frame)
        if not saved:
            if logger:
                logger.error("Failed to write captured frame to %s", output_path)
            return ""

        if logger:
            logger.info("Captured image from camera index %d to %s", device_index, output_path)
        return str(output_path)
    finally:
        camera.release()


def probe_camera_indices(max_index: int = 4) -> list[int]:
    available: list[int] = []
    if cv2 is None:
        return available

    for index in range(max_index + 1):
        camera = _open_camera(index)
        if camera is None:
            continue
        available.append(index)
        camera.release()

    return available
