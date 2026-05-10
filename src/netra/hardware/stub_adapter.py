from typing import List
import logging
import platform
import time
import tempfile
import subprocess
from pathlib import Path

if platform.system() == "Windows":
    import winsound

from .interfaces import HardwareAdapter


def _resolve_alsa_device(audio_device: int | str | None) -> str | None:
    if audio_device is None:
        return None
    if isinstance(audio_device, str) and audio_device.isdigit():
        audio_device = int(audio_device)
    if isinstance(audio_device, int):
        return f"plughw:{audio_device},0"
    return str(audio_device)


class StubHardwareAdapter(HardwareAdapter):
    def __init__(
        self,
        audio_device: int | str | None = None,
        sample_rate: int = 16000,
        audio_output_device: str | None = None,
        bt_speaker_mac: str | None = None,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.audio_device = audio_device
        self.sample_rate = sample_rate
        self.audio_output_device = audio_output_device
        self.bt_speaker_mac = bt_speaker_mac

    def capture_image_path(self) -> str:
        docs_dir = Path.cwd() / "docs"
        candidates = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff"):
            candidates.extend(docs_dir.glob(ext))

        if not candidates:
            self.logger.warning("No image found in docs folder for camera stub")
            return ""

        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        self.logger.info("Camera stub selected image %s", latest)
        return str(latest)

    def wait_for_scroll(self) -> None:
        time.sleep(0.8)

    def display_braille_cells(self, dot_patterns: List[int]) -> None:
        rendered = []
        for index, pattern in enumerate(dot_patterns, start=1):
            dots = [str(dot + 1) for dot in range(6) if pattern & (1 << dot)]
            rendered.append(f"Cell{index}:[{','.join(dots)}]")
        print("[HW STUB] Braille:", " ".join(rendered))

    def play_wav(self, wav_path: str) -> None:
        print(f"[HW STUB] Playing audio: {wav_path}")
        if platform.system() == "Windows":
            try:
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                self.logger.info("Played wav on Windows: %s", wav_path)
                return
            except Exception as exc:
                self.logger.warning("Windows audio playback failed: %s", exc)
            self.logger.info("Audio playback stub fallback used")
            return

        def normalize_mac(mac: str) -> str:
            return mac.strip().upper().replace(":", "_")

        def bt_card_name(mac: str) -> str:
            return f"bluez_card.{normalize_mac(mac)}"

        def looks_like_alsa_device(dev: str) -> bool:
            return dev.startswith(("hw:", "plughw:", "sysdefault:", "dmix:", "default:"))

        def pactl(*args: str) -> tuple[int, str, str]:
            try:
                proc = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5)
                return proc.returncode, proc.stdout or "", proc.stderr or ""
            except FileNotFoundError:
                return 127, "", "pactl not found"
            except Exception as exc:
                return 1, "", str(exc)

        def ensure_bt_a2dp(mac: str) -> None:
            card = bt_card_name(mac)
            for profile in ("a2dp-sink", "a2dp_sink"):
                rc, _, _ = pactl("set-card-profile", card, profile)
                if rc == 0:
                    return

        def discover_bt_sink(mac: str, timeout_s: int = 10) -> str | None:
            needle = normalize_mac(mac)
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                rc, out, _ = pactl("list", "short", "sinks")
                if rc == 0:
                    for line in out.splitlines():
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            sink_name = parts[1]
                            if sink_name.startswith("bluez_output.") and needle in sink_name.upper():
                                return sink_name
                time.sleep(1)
            return None

        target = self.audio_output_device

        if self.bt_speaker_mac:
            ensure_bt_a2dp(self.bt_speaker_mac)
            if not target:
                target = discover_bt_sink(self.bt_speaker_mac, timeout_s=10)
                if not target:
                    target = f"bluez_output.{normalize_mac(self.bt_speaker_mac)}.a2dp_sink"

        # Try Pulse/PipeWire first (typical on RPi), then ALSA.
        try:
            if target and not looks_like_alsa_device(target):
                result = subprocess.run(
                    ["paplay", f"--device={target}", wav_path],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    return
                self.logger.warning("paplay --device failed: %s", (result.stderr or "").strip())

            result = subprocess.run(
                ["paplay", wav_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                return

            if target and looks_like_alsa_device(target):
                result = subprocess.run(
                    ["aplay", "-q", "-D", target, wav_path],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    return
                self.logger.warning("aplay -D failed: %s", (result.stderr or "").strip())

            subprocess.run(
                ["aplay", "-q", wav_path],
                capture_output=True,
                text=True,
                timeout=120,
            )

        except FileNotFoundError:
            self.logger.warning("Audio player not found (paplay/aplay)")
        except subprocess.TimeoutExpired:
            self.logger.warning("Audio playback timed out")
        except Exception as exc:
            self.logger.warning("Audio playback failed: %s", exc)

    def record_audio(self, seconds: int) -> str:
        """Record audio even in stub mode (useful on RPi when running with hardware_mode=stub)."""
        seconds = max(1, int(seconds))
        out_dir = Path(tempfile.gettempdir()) / "netra_audio"
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"recording_{int(time.time() * 1000)}.wav")

        alsa_device = _resolve_alsa_device(self.audio_device) or "plughw:1,0"

        # Prefer ALSA arecord on Linux/RPi since it can target plughw:card,device directly.
        if platform.system() != "Windows":
            cmd = [
                "arecord",
                "-q",
                "-f",
                "S16_LE",
                "-c",
                "1",
                "-r",
                str(self.sample_rate),
                "-d",
                str(seconds),
                "-D",
                alsa_device,
                output_path,
            ]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds + 10)
                if result.returncode == 0 and Path(output_path).exists():
                    return output_path
                self.logger.warning("arecord failed (%s): %s", result.returncode, (result.stderr or "").strip())
            except FileNotFoundError:
                self.logger.warning("arecord not found; cannot capture via ALSA")
            except Exception as exc:
                self.logger.warning("Microphone recording failed: %s", exc)

        # No recording support available in stub
        return ""

    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        return ""
