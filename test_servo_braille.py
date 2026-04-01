#!/usr/bin/env python3
"""
Test script for braille-to-servo motor control.
Each braille character has 2 servo motors (one per column):
  - Left column motor: controls dots 1, 2, 3
  - Right column motor: controls dots 4, 5, 6

Usage:
    python test_servo_braille.py docs/sample.png
    python test_servo_braille.py "Hello World" --text
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List, Tuple

# Add src to path
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from netra.config import load_config
from netra.services.braille_service import BrailleService
from netra.services.document_service import DocumentService
from netra.services.ocr_service import OCRService

# Try to import RPi.GPIO for actual hardware control
try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    print("[WARNING] RPi.GPIO not available - running in simulation mode")


def pattern_to_bit_string(pattern: int) -> str:
    """
    Convert a braille pattern to a 6-bit string.
    Bit order: dots 1,2,3,4,5,6 → bits 0,1,2,3,4,5
    Example: dots [4,5] → pattern 0b011000 → "000110"
    """
    bits = []
    for dot in range(6):  # dots 1-6 correspond to bits 0-5
        if pattern & (1 << dot):
            bits.append('1')
        else:
            bits.append('0')
    return ''.join(bits)


def pattern_to_column_bits(pattern: int) -> Tuple[str, str]:
    """
    Split a braille pattern into left and right column bit strings.
    Left column: dots 1,2,3 (bits 0,1,2)
    Right column: dots 4,5,6 (bits 3,4,5)
    
    Returns: (left_bits, right_bits) e.g., ("010", "110")
    """
    left_bits = []
    right_bits = []
    
    # Left column: dots 1, 2, 3
    for dot in range(3):
        if pattern & (1 << dot):
            left_bits.append('1')
        else:
            left_bits.append('0')
    
    # Right column: dots 4, 5, 6
    for dot in range(3, 6):
        if pattern & (1 << dot):
            right_bits.append('1')
        else:
            right_bits.append('0')
    
    return (''.join(left_bits), ''.join(right_bits))


def calculate_servo_angles_for_column(column_bits: str) -> List[int]:
    """
    Calculate servo angles for a column based on which dots are active.
    Each column has 3 dots (positions 1, 2, 3).
    For each active dot, calculate angle: (dot_position * 45) mod 180
    
    Args:
        column_bits: 3-bit string representing dots (e.g., "101" means dots 1 and 3 active)
    
    Returns:
        List of angles in degrees for each active dot
    """
    angles = []
    for dot_position in range(3):  # 3 dots per column
        if column_bits[dot_position] == '1':
            # dot_position is 0,1,2 but we want 1,2,3 for calculation
            angle = ((dot_position + 1) * 45) % 180
            angles.append(angle)
    
    # If no dots active, return 0 degrees
    if not angles:
        angles.append(0)
    
    return angles


def duty_cycle_from_angle(angle: float) -> float:
    """
    Convert angle (0-180) to PWM duty cycle (2.5-12.5 for SG90 servo).
    
    Args:
        angle: servo angle in degrees (0-180)
    
    Returns:
        duty cycle percentage for 50Hz PWM
    """
    # SG90 servo: 0° = 2.5%, 90° = 7.5%, 180° = 12.5%
    return 2.5 + (angle / 180.0) * 10.0


class ServoController:
    """Controls servo motors for braille display."""
    
    def __init__(self, servo_pins: List[int], simulate: bool = False):
        """
        Initialize servo controller.
        
        Args:
            servo_pins: List of GPIO pins for servos (should be 8: 2 per cell for 4 cells)
            simulate: If True, simulate without hardware
        """
        self.servo_pins = servo_pins
        self.simulate = simulate or not HAS_GPIO
        self.pwm_objects = []
        
        if not self.simulate:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            
            for pin in servo_pins:
                GPIO.setup(pin, GPIO.OUT)
                pwm = GPIO.PWM(pin, 50)  # 50Hz for servo
                pwm.start(0)
                self.pwm_objects.append(pwm)
    
    def display_braille_cells(self, patterns: List[int], step_delay: float = 0.3) -> None:
        """
        Display braille patterns on servo motors.
        
        Args:
            patterns: List of braille patterns (up to 4 cells)
            step_delay: Delay between motor movements for the same column (seconds)
        """
        if len(patterns) > 4:
            print(f"[WARNING] Received {len(patterns)} cells, displaying first 4")
            patterns = patterns[:4]
        
        # Pad to 4 cells if needed
        while len(patterns) < 4:
            patterns.append(0)
        
        print("\n" + "=" * 70)
        print("BRAILLE → SERVO MOTOR CONTROL")
        print("=" * 70)
        
        for cell_idx, pattern in enumerate(patterns):
            # Get dot numbers for display
            dots = [str(dot + 1) for dot in range(6) if pattern & (1 << dot)]
            dots_str = ','.join(dots) if dots else 'empty'
            
            # Get 6-bit representation
            bit_string = pattern_to_bit_string(pattern)
            
            # Split into columns
            left_bits, right_bits = pattern_to_column_bits(pattern)
            
            # Calculate servo angles for each column based on active dots
            left_angles = calculate_servo_angles_for_column(left_bits)
            right_angles = calculate_servo_angles_for_column(right_bits)
            
            # Calculate motor indices (2 motors per cell)
            left_motor_idx = cell_idx * 2
            right_motor_idx = cell_idx * 2 + 1
            
            print(f"\nCell {cell_idx + 1}:")
            print(f"  Dots:         [{dots_str}]")
            print(f"  Bit pattern:  {bit_string}")
            print(f"  Left column:  {left_bits} (dots 1,2,3) → Motor {left_motor_idx + 1}")
            
            # Display left column angles
            left_dots_active = [i+1 for i, bit in enumerate(left_bits) if bit == '1']
            if left_dots_active:
                angle_info = [f"dot{d}→{a}°" for d, a in zip(left_dots_active, left_angles)]
                print(f"    Active dots: {left_dots_active} → Angles: {angle_info}")
            else:
                print(f"    No active dots → Angle: 0°")
            
            print(f"  Right column: {right_bits} (dots 4,5,6) → Motor {right_motor_idx + 1}")
            
            # Display right column angles
            right_dots_active = [i+4 for i, bit in enumerate(right_bits) if bit == '1']
            if right_dots_active:
                angle_info = [f"dot{d}→{a}°" for d, a in zip(right_dots_active, right_angles)]
                print(f"    Active dots: {right_dots_active} → Angles: {angle_info}")
            else:
                print(f"    No active dots → Angle: 0°")
            
            # Move servos to each angle position
            if not self.simulate and left_motor_idx < len(self.pwm_objects):
                # Move left column motor through its positions
                for angle in left_angles:
                    duty = duty_cycle_from_angle(angle)
                    self.pwm_objects[left_motor_idx].ChangeDutyCycle(duty)
                    print(f"  → Motor {left_motor_idx + 1} (left) moving to {angle}° (duty: {duty:.2f}%)")
                    if len(left_angles) > 1:
                        time.sleep(step_delay)
                
                # Move right column motor through its positions
                for angle in right_angles:
                    duty = duty_cycle_from_angle(angle)
                    self.pwm_objects[right_motor_idx].ChangeDutyCycle(duty)
                    print(f"  → Motor {right_motor_idx + 1} (right) moving to {angle}° (duty: {duty:.2f}%)")
                    if len(right_angles) > 1:
                        time.sleep(step_delay)
            else:
                print(f"  → [SIMULATED] Motor {left_motor_idx + 1} (left) would move to: {left_angles}")
                print(f"  → [SIMULATED] Motor {right_motor_idx + 1} (right) would move to: {right_angles}")
        
        print("=" * 70)
    
    def cleanup(self):
        """Clean up GPIO resources."""
        if not self.simulate:
            for pwm in self.pwm_objects:
                pwm.stop()
            GPIO.cleanup()
            print("\n[GPIO cleaned up]")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test braille-to-servo motor control.")
    parser.add_argument("input", help="Path to image/PDF file, or text if --text is used")
    parser.add_argument("--text", action="store_true", help="Process input as text instead of file")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between display steps (seconds)")
    parser.add_argument("--servo-pins", type=str, default=None, 
                        help="Comma-separated GPIO pins for 8 servos (default from config)")
    args = parser.parse_args()
    
    # Load config
    config = load_config(ROOT / "config.json")
    
    # Get servo pins
    if args.servo_pins:
        servo_pins = [int(p.strip()) for p in args.servo_pins.split(',')]
    else:
        # Get from config or use defaults
        pin_str = config.__dict__.get('rpi_gpio_servo_pins', '12,13,19,26')
        base_pins = [int(p.strip()) for p in pin_str.split(',')]
        
        # We need 8 servos (2 per cell for 4 cells)
        # If config only has 4, duplicate them or use sequential pins
        if len(base_pins) < 8:
            print(f"[INFO] Config has {len(base_pins)} servo pins, need 8 for 4 cells (2 motors each)")
            print(f"[INFO] Using pins: {base_pins} + sequential pins")
            servo_pins = base_pins + [base_pins[-1] + i + 1 for i in range(8 - len(base_pins))]
        else:
            servo_pins = base_pins[:8]
    
    print(f"[INFO] Using servo pins: {servo_pins}")
    
    # Initialize services
    braille = BrailleService(config.braille_table, config.braille_cells)
    servo = ServoController(servo_pins, simulate=not HAS_GPIO)
    
    try:
        # Get text to convert
        if args.text:
            text = args.input
            print(f"\n[INPUT TEXT] {text}")
        else:
            # Load from file
            target_path = Path(args.input).expanduser()
            if not target_path.is_absolute():
                target_path = (ROOT / target_path).resolve()
            
            if not target_path.exists():
                print(f"[ERROR] File not found: {target_path}")
                return 1
            
            print(f"\n[INPUT FILE] {target_path}")
            
            # Extract text using OCR/document service
            ocr = OCRService()
            docs = DocumentService(config.docs_dir, ocr)
            text_chunks = docs.extract_text_chunks(str(target_path), 
                                                   pdf_pages_per_chunk=1,
                                                   ocr_lines_per_chunk=2)
            text = ' '.join(chunk.strip() for chunk in text_chunks if chunk.strip())
            
            if not text:
                print("[ERROR] No text extracted from file")
                return 1
            
            print(f"[EXTRACTED TEXT] {text}")
        
        # Convert to braille
        contracted, patterns = braille.text_to_patterns(text)
        print(f"\n[BRAILLE] {len(patterns)} cells generated")
        print(f"[CONTRACTED] {contracted}")
        
        # Chunk into display groups (4 cells at a time)
        braille_chunks = braille.chunk_patterns(patterns)
        print(f"\n[DISPLAY] {len(braille_chunks)} group(s) of 4 cells")
        
        # Display each chunk
        for chunk_idx, chunk in enumerate(braille_chunks):
            print(f"\n{'=' * 70}")
            print(f"DISPLAYING GROUP {chunk_idx + 1}/{len(braille_chunks)}")
            print(f"{'=' * 70}")
            
            # Use 0.3s delay between positions for same motor
            servo.display_braille_cells(chunk, step_delay=0.3)
            
            # Wait before next chunk
            if chunk_idx < len(braille_chunks) - 1:
                print(f"\nWaiting {args.delay}s before next group...")
                time.sleep(args.delay)
        
        print("\n[SUCCESS] Test complete!")
        return 0
        
    except KeyboardInterrupt:
        print("\n\n[INTERRUPTED] Test stopped by user")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        servo.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
