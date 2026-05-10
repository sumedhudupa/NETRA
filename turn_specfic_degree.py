#!/usr/bin/env python3

# =====================================================
# MANUAL STEPPER MOTOR DEGREE CONTROL
# Motor 1 -> GPIO 17, 18, 27, 22
# Motor 2 -> GPIO 23, 24, 25, 4
#
# COMMANDS:
#   1 CW  45     -> Motor 1 clockwise 45 degrees
#   2 CCW 90     -> Motor 2 counter-clockwise 90 degrees
#   1 CW  45 50  -> Motor 1 CW 45 deg at speed 50 (1-100)
#   exit         -> quit
# =====================================================

import lgpio
import time

# ================= MOTOR PINS =================
MOTOR1_PINS = [17, 18, 27, 22]
MOTOR2_PINS = [23, 24, 25, 4]

# ================= SETTINGS =================
STEPS_PER_REVOLUTION = 4076.0          # 28BYJ-48 full revolution steps
DEGREES_PER_STEP     = 360.0 / STEPS_PER_REVOLUTION   # ~0.0883 deg/step
DEFAULT_STEP_DELAY   = 0.0009          # 900 us  (speed 50 baseline)

# ================= HALF STEP SEQUENCE =================
SEQ = [
    [1, 0, 0, 0],
    [1, 1, 0, 0],
    [0, 1, 0, 0],
    [0, 1, 1, 0],
    [0, 0, 1, 0],
    [0, 0, 1, 1],
    [0, 0, 0, 1],
    [1, 0, 0, 1],
]

# ================= STATE =================
step_index = {1: 0, 2: 0}
h = None

# =====================================================
# SETUP
# =====================================================

def setup_gpio():
    global h
    h = lgpio.gpiochip_open(0)
    for pin in MOTOR1_PINS + MOTOR2_PINS:
        lgpio.gpio_claim_output(h, pin, 0)

def power_off_coils():
    for pin in MOTOR1_PINS + MOTOR2_PINS:
        lgpio.gpio_write(h, pin, 0)

def cleanup():
    power_off_coils()
    if h is not None:
        lgpio.gpiochip_close(h)
    print("GPIO released.")

# =====================================================
# STEP MOTOR
# =====================================================

def step_motor(motor, direction):
    pins = MOTOR1_PINS if motor == 1 else MOTOR2_PINS

    step_index[motor] += direction
    if step_index[motor] > 7: step_index[motor] = 0
    if step_index[motor] < 0: step_index[motor] = 7

    for i in range(4):
        lgpio.gpio_write(h, pins[i], SEQ[step_index[motor]][i])

# =====================================================
# ROTATE BY DEGREES
# speed: 1 (slowest) to 100 (fastest)
# =====================================================

def rotate_degrees(motor, direction, degrees, speed=50):
    steps = int(round(degrees / DEGREES_PER_STEP))

    # Map speed 1-100 to delay range 3ms (slow) -> 0.5ms (fast)
    delay = 0.003 - ((speed - 1) / 99.0) * (0.003 - 0.0005)

    dir_int  = 1 if direction == "CW" else -1
    dir_label = "CW" if dir_int == 1 else "CCW"

    actual_degrees = steps * DEGREES_PER_STEP

    print(f"Motor {motor} | {dir_label} | {degrees}° requested "
          f"→ {steps} steps ({actual_degrees:.2f}° actual) | speed={speed}")

    for _ in range(steps):
        step_motor(motor, dir_int)
        time.sleep(delay)

    power_off_coils()
    print(f"Done.")

# =====================================================
# PARSE INPUT
# =====================================================

def parse_and_run(raw):
    parts = raw.strip().split()

    # Need at least: <motor> <dir> <degrees>
    if len(parts) < 3:
        print("Usage: <motor 1|2> <CW|CCW> <degrees> [speed 1-100]")
        return

    try:
        motor = int(parts[0])
        if motor not in (1, 2):
            raise ValueError

    except ValueError:
        print("Motor must be 1 or 2.")
        return

    direction = parts[1].upper()
    if direction not in ("CW", "CCW"):
        print("Direction must be CW or CCW.")
        return

    try:
        degrees = float(parts[2])
        if degrees <= 0:
            raise ValueError

    except ValueError:
        print("Degrees must be a positive number.")
        return

    speed = 50  # default
    if len(parts) >= 4:
        try:
            speed = int(parts[3])
            speed = max(1, min(100, speed))
        except ValueError:
            print("Speed must be an integer 1-100. Using default 50.")

    rotate_degrees(motor, direction, degrees, speed)

# =====================================================
# MAIN
# =====================================================

def main():
    setup_gpio()

    print("=========================================")
    print("  STEPPER MANUAL CONTROL")
    print("=========================================")
    print("  <motor> <CW|CCW> <degrees> [speed]")
    print("  Examples:")
    print("    1 CW  45        -> Motor 1, CW,  45 deg, speed 50")
    print("    2 CCW 90        -> Motor 2, CCW, 90 deg, speed 50")
    print("    1 CW  22.5 80   -> Motor 1, CW, 22.5 deg, speed 80")
    print("    2 CCW 360 20    -> Motor 2, full CCW rotation, slow")
    print("  exit / Ctrl+C    -> quit")
    print("=========================================")

    try:
        while True:
            raw = input(">> ").strip()
            if not raw:
                continue
            if raw.lower() == "exit":
                break
            parse_and_run(raw)

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        cleanup()

if __name__ == "__main__":
    main()
