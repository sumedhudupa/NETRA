#!/usr/bin/env python3
"""
Simple two-servo sweep test for Raspberry Pi GPIO 12 and GPIO 13.

This script uses BCM numbering:
  - Servo 1 signal -> BCM GPIO 12 (physical pin 32)
  - Servo 2 signal -> BCM GPIO 13 (physical pin 33)

Power guidance:
  - Servo VCC -> 5V
  - Servo GND -> GND
  - Raspberry Pi GND must be common with servo ground

Run:
    sudo /path/to/venv/bin/python test_two_servos_board.py
"""

import sys
import time

try:
    import RPi.GPIO as GPIO
except ImportError:
    print("RPi.GPIO is not installed. Run this on a Raspberry Pi with RPi.GPIO available.")
    raise SystemExit(1)


SERVO_PINS = [12, 13]  # BCM GPIO pins.
FREQUENCY_HZ = 50


def duty_cycle_from_angle(angle: float) -> float:
    """Convert 0-180 degrees to SG90-style duty cycle."""
    return 2.5 + (angle / 180.0) * 10.0


def move_servo(pwm: GPIO.PWM, angle: float, hold_seconds: float = 1.0) -> None:
    duty = duty_cycle_from_angle(angle)
    print(f"  angle={angle:>5.1f} duty={duty:>4.1f}%")
    pwm.ChangeDutyCycle(duty)
    time.sleep(hold_seconds)
    pwm.ChangeDutyCycle(0)
    time.sleep(0.2)


def main() -> int:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    pwm_objects = []

    try:
        for pin in SERVO_PINS:
            GPIO.setup(pin, GPIO.OUT)
            pwm = GPIO.PWM(pin, FREQUENCY_HZ)
            pwm.start(0)
            pwm_objects.append(pwm)

        print("Two-servo sweep test starting")
        print(f"Using BCM GPIO pins: {SERVO_PINS}")
        print("Expected sequence: 0° -> 90° -> 180° -> 90°")

        for index, pwm in enumerate(pwm_objects, start=1):
            print(f"\nTesting servo {index} on BCM GPIO {SERVO_PINS[index - 1]}")
            for angle in (0, 90, 180, 90):
                move_servo(pwm, angle)

        print("\nTesting both servos together")
        for angle in (0, 90, 180, 90):
            duty = duty_cycle_from_angle(angle)
            print(f"  both -> angle={angle:>5.1f} duty={duty:>4.1f}%")
            for pwm in pwm_objects:
                pwm.ChangeDutyCycle(duty)
            time.sleep(1.0)
            for pwm in pwm_objects:
                pwm.ChangeDutyCycle(0)
            time.sleep(0.2)

        print("\nServo test complete")
        return 0
    except KeyboardInterrupt:
        print("\nStopped by user")
        return 1
    finally:
        for pwm in pwm_objects:
            pwm.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
