"""
Raspberry Pi 4B Hardware Adapter for NETRA
Complete implementation for:
- Camera capture (Pi Camera / USB webcam)
- Audio recording (USB microphone)
- Audio playback (Speaker via 3.5mm jack or HDMI)
- Servo motor control for braille display
- GPIO button for scroll/navigation
"""

from typing import List
import logging
import subprocess
import time
from pathlib import Path

from .interfaces import HardwareAdapter

# Raspberry Pi specific imports - wrapped in try/except for development on non-Pi systems
try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    GPIO = None
    RPI_AVAILABLE = False

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    Picamera2 = None
    PICAMERA_AVAILABLE = False


class RaspberryPiHardwareAdapter(HardwareAdapter):
    """
    Complete Raspberry Pi 4B hardware adapter for NETRA braille reading assistant.
    
    Hardware Configuration:
    - GPIO 17: Scroll button (INPUT, PULL_UP)
    - GPIO 18: Status LED (OUTPUT)
    - 8 GPIO pins: Servo motors for 4 braille cells (2 per cell, left/right columns)
    - USB microphone: For voice input
    - 3.5mm audio jack: For speaker output
    - Pi Camera / USB webcam: For document capture
    
    Servo Configuration (per braille cell):
    Each braille cell has 6 dots controlled by solenoids/servos.
    Using cam-barrel mechanism with servo rotation.
    """
    
    # Default GPIO Pin Configuration
    DEFAULT_SCROLL_BUTTON_PIN = 17
    DEFAULT_STATUS_LED_PIN = 18
    DEFAULT_SERVO_PINS = [12, 13, 19, 26, 16, 20, 21, 6]
    
    # Audio Configuration
    AUDIO_SAMPLE_RATE = 16000   # 16kHz for STT compatibility
    AUDIO_CHANNELS = 1          # Mono recording
    AUDIO_DEVICE = None         # None = default device, or specify card number
    
    # Servo Configuration
    SERVO_FREQ = 50             # 50Hz PWM for standard servos
    SERVO_MIN_DUTY = 2.5        # Duty cycle for 0 degrees
    SERVO_MAX_DUTY = 12.5       # Duty cycle for 180 degrees
    
    def __init__(
        self,
        audio_device: int | str | None = None,
        audio_output_device: str | None = None,
        bt_speaker_mac: str | None = None,
        scroll_button_pin: int = DEFAULT_SCROLL_BUTTON_PIN,
        status_led_pin: int = DEFAULT_STATUS_LED_PIN,
        servo_pins: List[int] | None = None,
        usb_camera_device: str = "/dev/video0",
        usb_camera_width: int = 1920,
        usb_camera_height: int = 1080,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.audio_device = audio_device
        self.audio_output_device = audio_output_device
        self.bt_speaker_mac = bt_speaker_mac
        self.scroll_button_pin = scroll_button_pin
        self.status_led_pin = status_led_pin
        self.servo_pins = self._normalize_servo_pins(servo_pins)
        self.usb_camera_device = usb_camera_device
        self.usb_camera_width = usb_camera_width
        self.usb_camera_height = usb_camera_height
        self.camera = None
        self.servo_pwms = {}
        self._initialized = False
        
        self._initialize_hardware()

    def _normalize_servo_pins(self, servo_pins: List[int] | None) -> List[int]:
        pins = list(servo_pins or self.DEFAULT_SERVO_PINS)
        if len(pins) < 8:
            self.logger.warning(
                "Expected 8 servo GPIO pins for 4 braille cells, received %d. Falling back to defaults.",
                len(pins),
            )
            return list(self.DEFAULT_SERVO_PINS)
        return pins[:8]
    
    def _initialize_hardware(self) -> None:
        """Initialize all Raspberry Pi hardware components."""
        if not RPI_AVAILABLE:
            self.logger.warning("RPi.GPIO not available - running in simulation mode")
            return
        
        try:
            # Setup GPIO mode
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            # Setup scroll button with pull-up resistor
            GPIO.setup(self.scroll_button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self.logger.info("Scroll button configured on GPIO %d", self.scroll_button_pin)
            
            # Setup status LED
            GPIO.setup(self.status_led_pin, GPIO.OUT)
            GPIO.output(self.status_led_pin, GPIO.LOW)
            self.logger.info("Status LED configured on GPIO %d", self.status_led_pin)
            
            # Setup servos: N pins configured as PWM outputs
            for i, pin in enumerate(self.servo_pins):
                GPIO.setup(pin, GPIO.OUT)
                pwm = GPIO.PWM(pin, self.SERVO_FREQ)
                pwm.start(0)
                self.servo_pwms[i] = pwm
                self.logger.info("Servo %d configured on GPIO %d", i + 1, pin)
            
            self._initialized = True
            self.logger.info(
                "Raspberry Pi GPIO initialization complete with servo pins %s",
                self.servo_pins,
            )
            
        except Exception as exc:
            self.logger.error("GPIO initialization failed: %s", exc)
            self._initialized = False
    
    def _initialize_camera(self) -> bool:
        """Initialize camera on first use."""
        if self.camera is not None:
            return True
        
        # Check for USB webcam using v4l2
        try:
            result = subprocess.run(
                ["v4l2-ctl", "--list-devices"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and "/dev/video" in result.stdout:
                self.logger.info("USB webcam detected via v4l2")
                self.camera = "usb"
                return True
        except Exception as exc:
            self.logger.warning("No camera available: %s", exc)
        
        return False
    
    def capture_image_path(self) -> str:
        """
        Capture image from USB webcam using ffmpeg.
        Returns path to captured image file.
        """
        # Blink status LED to indicate capture
        self._blink_led(2, 0.1)
        
        output_dir = Path("/tmp/netra_captures")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        output_path = str(output_dir / f"capture_{timestamp}.jpg")
        
        # Use ffmpeg for USB camera capture
        try:
            command = [
                "ffmpeg",
                "-y",  # overwrite output files
                "-f", "v4l2",
                "-i", self.usb_camera_device,
                "-frames:v", "1",
                output_path
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and Path(output_path).exists():
                self.logger.info("Image captured with ffmpeg: %s", output_path)
                return output_path
            self.logger.debug(
                "ffmpeg failed with code %s: %s",
                result.returncode,
                (result.stderr or result.stdout or "").strip(),
            )
        except FileNotFoundError:
            self.logger.debug("ffmpeg not installed")
        except Exception as exc:
            self.logger.error("USB webcam capture failed: %s", exc)
        
        self.logger.error("Camera capture failed")
        return ""
    
    def wait_for_scroll(self) -> None:
        """
        Wait for scroll button press to advance braille display.
        Uses GPIO interrupt for efficient waiting.
        """
        if not RPI_AVAILABLE or not self._initialized:
            self.logger.info("Simulating scroll wait (2 seconds)")
            time.sleep(2)
            return
        
        self.logger.info("Waiting for scroll button press on GPIO %d", self.scroll_button_pin)
        
        try:
            # Wait for falling edge (button press with pull-up)
            GPIO.wait_for_edge(self.scroll_button_pin, GPIO.FALLING, timeout=30000)
            
            # Debounce
            time.sleep(0.05)
            
            # Verify button is still pressed
            if GPIO.input(self.scroll_button_pin) == GPIO.LOW:
                self.logger.info("Scroll button pressed")
                # Brief LED flash to confirm
                self._blink_led(1, 0.1)
                
                # Wait for button release
                while GPIO.input(self.scroll_button_pin) == GPIO.LOW:
                    time.sleep(0.01)
                    
        except Exception as exc:
            self.logger.warning("Scroll button wait error: %s", exc)
            time.sleep(1)
    
    def display_braille_cells(self, dot_patterns: List[int], chars: List[str] | None = None) -> None:
        """
        Display a group of braille cells using servos. Each cell uses two servos
        (left/right columns). `dot_patterns` is a list of patterns for visible
        cells; if fewer than configured cells are provided, we pad with blanks.
        """
        if not RPI_AVAILABLE or not self._initialized:
            # Fallback: print pattern representation
            rendered = []
            for idx, pattern in enumerate(dot_patterns, start=1):
                dots = [str(d + 1) for d in range(6) if pattern & (1 << d)]
                rendered.append(f"Cell{idx}:[{','.join(dots) or 'blank'}]")
            self.logger.info("Braille display (simulated): %s", " ".join(rendered))
            print(f"[BRAILLE] {' '.join(rendered)}")
            return
        
        # Normalize to configured number of cells
        patterns = list(dot_patterns[:len(self.servo_pins)//2])
        while len(patterns) < (len(self.servo_pins)//2):
            patterns.append(0)
        
        self.logger.info("Displaying braille patterns: %s", [bin(p) for p in patterns])
        
        for cell_idx, pattern in enumerate(patterns):
            left_motor_idx = cell_idx * 2
            right_motor_idx = left_motor_idx + 1
            left_bits, right_bits = self._pattern_to_column_bits(pattern)
            left_angles = self._calculate_servo_angles_for_column(left_bits)
            right_angles = self._calculate_servo_angles_for_column(right_bits)

            self._drive_servo_sequence(left_motor_idx, left_angles)
            self._drive_servo_sequence(right_motor_idx, right_angles)
        
        # Stop PWM to reduce jitter and power consumption
        for pwm in self.servo_pwms.values():
            pwm.ChangeDutyCycle(0)
        
        # Log rendered output
        rendered = []
        for idx, pattern in enumerate(patterns, start=1):
            dots = [str(d + 1) for d in range(6) if pattern & (1 << d)]
            rendered.append(f"Cell{idx}:[{','.join(dots) or 'blank'}]")
        self.logger.info("Braille cells updated: %s", " ".join(rendered))
    
    def display_capacity_chars(self) -> int:
        """Return how many braille cells this hardware can display concurrently.
        Each cell uses two servos (left/right columns), so capacity = servo_pins // 2.
        """
        return len(self.servo_pins) // 2

    def _pattern_to_column_bits(self, pattern: int) -> tuple[str, str]:
        left_bits = "".join("1" if pattern & (1 << dot) else "0" for dot in range(3))
        right_bits = "".join("1" if pattern & (1 << dot) else "0" for dot in range(3, 6))
        return left_bits, right_bits

    def _calculate_servo_angles_for_column(self, column_bits: str) -> List[int]:
        angles = [((dot_position + 1) * 45) % 180 for dot_position, bit in enumerate(column_bits) if bit == "1"]
        return angles or [0]

    def _drive_servo_sequence(self, servo_idx: int, angles: List[int], hold_seconds: float = 0.3) -> None:
        if servo_idx not in self.servo_pwms:
            return

        for angle in angles:
            self._set_servo_angle(servo_idx, angle)
            time.sleep(hold_seconds)
        self.servo_pwms[servo_idx].ChangeDutyCycle(0)
    
    def _set_servo_angle(self, servo_idx: int, angle: float) -> None:
        """Set servo to specific angle (0-180 degrees)."""
        if servo_idx not in self.servo_pwms:
            return
        
        # Clamp angle
        angle = max(0, min(180, angle))
        
        # Convert angle to duty cycle
        duty = self.SERVO_MIN_DUTY + (angle / 180.0) * (self.SERVO_MAX_DUTY - self.SERVO_MIN_DUTY)
        
        self.servo_pwms[servo_idx].ChangeDutyCycle(duty)
    
    def play_wav(self, wav_path: str) -> None:
        """Play audio file through speaker.

        Supports:
        - PipeWire/PulseAudio sinks via paplay --device=<sink>
        - ALSA devices via aplay -D <device>

        Bluetooth speaker handling (PipeWire):
        - If bt_speaker_mac is set, we try to force the BT card profile to A2DP first
          (a2dp-sink / a2dp_sink) and then discover the actual bluez_output sink via pactl.
        - If no sink appears (e.g., WirePlumber not running / negotiation still pending),
          we fall back to default playback (which may end up as auto_null).
        """
        if not Path(wav_path).exists():
            self.logger.error("Audio file not found: %s", wav_path)
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
                rc, _, err = pactl("set-card-profile", card, profile)
                if rc == 0:
                    self.logger.info("Bluetooth card %s set to profile %s", card, profile)
                    return
                self.logger.debug("pactl set-card-profile %s %s failed: %s", card, profile, (err or "").strip())

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

        # If configured for BT speaker, ensure A2DP and discover real sink name.
        if self.bt_speaker_mac:
            ensure_bt_a2dp(self.bt_speaker_mac)
            if not target:
                discovered = discover_bt_sink(self.bt_speaker_mac, timeout_s=10)
                if discovered:
                    target = discovered
                else:
                    # As a last guess, try the canonical pipewire-pulse sink name.
                    target = f"bluez_output.{normalize_mac(self.bt_speaker_mac)}.a2dp_sink"

        self.logger.info("Playing audio: %s (target=%s)", wav_path, target or "default")

        # Blink LED during playback
        if RPI_AVAILABLE and self._initialized:
            GPIO.output(self.status_led_pin, GPIO.HIGH)

        try:
            # 1) If a target is provided, try targeted playback first.
            if target:
                if looks_like_alsa_device(target):
                    result = subprocess.run(
                        ["aplay", "-q", "-D", target, wav_path],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if result.returncode == 0:
                        return
                    self.logger.warning("aplay -D failed: %s", (result.stderr or "").strip())
                else:
                    result = subprocess.run(
                        ["paplay", f"--device={target}", wav_path],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    if result.returncode == 0:
                        return
                    self.logger.warning("paplay --device failed: %s", (result.stderr or "").strip())

            # 2) Fallback: default paplay, then aplay.
            result = subprocess.run(
                ["paplay", wav_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                self.logger.warning("paplay failed: %s, trying aplay", (result.stderr or "").strip())
                subprocess.run(
                    ["aplay", "-q", wav_path],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

        except FileNotFoundError:
            self.logger.error("Audio player not found (paplay/aplay)")
        except subprocess.TimeoutExpired:
            self.logger.warning("Audio playback timed out")
        except Exception as exc:
            self.logger.error("Audio playback failed: %s", exc)
        finally:
            if RPI_AVAILABLE and self._initialized:
                GPIO.output(self.status_led_pin, GPIO.LOW)
    
    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        """
        Record audio from microphone - NO FALLBACK, always use audio.
        Returns path to recorded WAV file.
        """
        return ""  # Return empty to trigger live microphone recording in STT service
    
    def record_audio(self, seconds: int) -> str:
        """Record audio from the USB microphone and return a WAV path."""
        output_dir = Path("/tmp/netra_audio")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time() * 1000)
        output_path = str(output_dir / f"recording_{timestamp}.wav")

        seconds = max(1, int(seconds))

        # Visual feedback - LED on during recording
        if RPI_AVAILABLE and self._initialized:
            GPIO.output(self.status_led_pin, GPIO.HIGH)

        def resolve_alsa_device(dev: int | str | None) -> str | None:
            if dev is None:
                return None
            if isinstance(dev, str) and dev.isdigit():
                dev = int(dev)
            if isinstance(dev, int):
                return f"plughw:{dev},0"
            return str(dev)

        try:
            alsa_device = resolve_alsa_device(self.audio_device)
            if alsa_device is None:
                # Sensible default for the common "USB mic shows up as card1" case.
                alsa_device = "plughw:1,0"

            self.logger.info("Recording %d seconds from ALSA device %s using arecord", seconds, alsa_device)

            cmd = [
                "arecord",
                "-q",
                "-D",
                alsa_device,
                "-f",
                "S16_LE",
                "-c",
                str(self.AUDIO_CHANNELS),
                "-r",
                str(self.AUDIO_SAMPLE_RATE),
                "-d",
                str(seconds),
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=seconds + 10)
            if result.returncode != 0:
                self.logger.error("arecord failed: %s", (result.stderr or "").strip())
                return ""

            if Path(output_path).exists():
                self.logger.info("Audio recorded successfully: %s", output_path)
                return output_path

            self.logger.error("Recording file was not created")
            return ""

        except FileNotFoundError:
            self.logger.error("arecord not found; install alsa-utils")
            return ""
        except subprocess.TimeoutExpired:
            self.logger.error("Audio recording timed out")
            return ""
        except Exception as exc:
            self.logger.error("Audio recording failed: %s", exc)
            return ""
        finally:
            if RPI_AVAILABLE and self._initialized:
                GPIO.output(self.status_led_pin, GPIO.LOW)
    
    def _blink_led(self, times: int, duration: float) -> None:
        """Blink status LED for visual feedback."""
        if not RPI_AVAILABLE or not self._initialized:
            return
        
        for _ in range(times):
            GPIO.output(self.status_led_pin, GPIO.HIGH)
            time.sleep(duration)
            GPIO.output(self.status_led_pin, GPIO.LOW)
            time.sleep(duration)
    
    def set_status_led(self, on: bool) -> None:
        """Set status LED state."""
        if RPI_AVAILABLE and self._initialized:
            GPIO.output(self.status_led_pin, GPIO.HIGH if on else GPIO.LOW)
    
    def cleanup(self) -> None:
        """Clean up GPIO and hardware resources."""
        self.logger.info("Cleaning up Raspberry Pi hardware")
        
        # Stop all servos
        for pwm in self.servo_pwms.values():
            pwm.stop()
        
        # Turn off LED
        if RPI_AVAILABLE and self._initialized:
            GPIO.output(self.status_led_pin, GPIO.LOW)
            GPIO.cleanup()
        
        # Close camera
        if self.camera is not None:
            try:
                self.camera.close()
            except:
                pass
        
        self._initialized = False
        self.logger.info("Hardware cleanup complete")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()

