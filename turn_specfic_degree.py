#!/usr/bin/env python3

# =====================================================
# MANUAL STEPPER MOTOR DEGREE CONTROL  (4 motors)
# Uses MCP23017 I2C expander (no direct GPIO)
#
# Wiring (MCP23017 at 0x20):
#   GPA0-GPA3  →  Motor 1 IN1-IN4  (ULN2003)
#   GPA4-GPA7  →  Motor 2 IN1-IN4  (ULN2003)
#   GPB0-GPB3  →  Motor 3 IN1-IN4  (ULN2003)
#   GPB4-GPB7  →  Motor 4 IN1-IN4  (ULN2003)
#
# COMMANDS:
#   1 CW  45     -> Motor 1 clockwise 45 degrees
#   3 CCW 90     -> Motor 3 counter-clockwise 90 degrees
#   2 CW  45 50  -> Motor 2 CW 45 deg at speed 50 (1-100)
#   exit         -> quit
# =====================================================

import smbus2
import time
import sys

# ================= MCP23017 CONFIG =================
I2C_BUS      = 1
CHIP_ADDRESS = 0x20   # Change if A0/A1/A2 jumpers differ

IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13

# ================= MOTOR LAYOUT ON MCP23017 =================
# motor_number → (port_register, bit_offset)
MOTOR_MAP = {
    1: (GPIOA, 0),   # Motor 1: GPA bits 0-3
    2: (GPIOA, 4),   # Motor 2: GPA bits 4-7
    3: (GPIOB, 0),   # Motor 3: GPB bits 0-3
    4: (GPIOB, 4),   # Motor 4: GPB bits 4-7
}

# ================= SETTINGS =================
STEPS_PER_REVOLUTION = 4076.0
DEGREES_PER_STEP     = 360.0 / STEPS_PER_REVOLUTION   # ~0.0883 deg/step
DEFAULT_STEP_DELAY   = 0.0009                           # 900 us baseline

# ================= HALF-STEP SEQUENCE (4-bit patterns) =================
STEP_SEQUENCE = [
    0b0001,   # Step 0
    0b0011,   # Step 1
    0b0010,   # Step 2
    0b0110,   # Step 3
    0b0100,   # Step 4
    0b1100,   # Step 5
    0b1000,   # Step 6
    0b1001,   # Step 7
]

# ================= STATE =================
step_index = {1: 0, 2: 0, 3: 0, 4: 0}
bus        = None          # smbus2.SMBus instance
port_cache = {}            # (addr, port_reg) → current 8-bit value

# =====================================================
# SETUP
# =====================================================

def setup_mcp23017():
    global bus
    bus = smbus2.SMBus(I2C_BUS)

    print("Scanning I2C bus...")
    found = []
    for addr in range(0x03, 0x78):
        try:
            bus.read_byte(addr)
            found.append(addr)
        except Exception:
            pass

    if CHIP_ADDRESS not in found:
        print(f"❌ MCP23017 not found at 0x{CHIP_ADDRESS:02X}!")
        if found:
            print(f"   Devices found: {['0x%02X' % a for a in found]}")
        bus.close()
        sys.exit(1)

    print(f"✅ MCP23017 found at 0x{CHIP_ADDRESS:02X}")

    # Port A (motors 1 & 2): all outputs, all LOW
    bus.write_byte_data(CHIP_ADDRESS, IODIRA, 0x00)
    time.sleep(0.005)
    bus.write_byte_data(CHIP_ADDRESS, GPIOA, 0x00)
    time.sleep(0.005)
    port_cache[(CHIP_ADDRESS, GPIOA)] = 0x00

    # Port B (motors 3 & 4): all outputs, all LOW
    bus.write_byte_data(CHIP_ADDRESS, IODIRB, 0x00)
    time.sleep(0.005)
    bus.write_byte_data(CHIP_ADDRESS, GPIOB, 0x00)
    time.sleep(0.005)
    port_cache[(CHIP_ADDRESS, GPIOB)] = 0x00


def power_off_coils():
    """Set all motor pins LOW on both ports."""
    bus.write_byte_data(CHIP_ADDRESS, GPIOA, 0x00)
    bus.write_byte_data(CHIP_ADDRESS, GPIOB, 0x00)
    port_cache[(CHIP_ADDRESS, GPIOA)] = 0x00
    port_cache[(CHIP_ADDRESS, GPIOB)] = 0x00


def cleanup():
    power_off_coils()
    if bus is not None:
        bus.close()
    print("I2C bus closed.")

# =====================================================
# STEP MOTOR  (MCP23017 version)
# =====================================================

def step_motor(motor, direction):
    step_index[motor] += direction
    if step_index[motor] > 7: step_index[motor] = 0
    if step_index[motor] < 0: step_index[motor] = 7

    port_reg, bit_offset = MOTOR_MAP[motor]
    pattern = STEP_SEQUENCE[step_index[motor]]

    key = (CHIP_ADDRESS, port_reg)
    current = port_cache.get(key, 0x00)
    mask = 0x0F << bit_offset
    current = (current & ~mask) | ((pattern & 0x0F) << bit_offset)
    bus.write_byte_data(CHIP_ADDRESS, port_reg, current)
    port_cache[key] = current

# =====================================================
# ROTATE BY DEGREES
# speed: 1 (slowest) to 100 (fastest)
# =====================================================

def rotate_degrees(motor, direction, degrees, speed=50):
    steps = int(round(degrees / DEGREES_PER_STEP))

    # Map speed 1-100 to delay range 3ms (slow) -> 0.5ms (fast)
    delay = 0.003 - ((speed - 1) / 99.0) * (0.003 - 0.0005)

    dir_int   = 1 if direction == "CW" else -1
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
        print("Usage: <motor 1-4> <CW|CCW> <degrees> [speed 1-100]")
        return

    try:
        motor = int(parts[0])
        if motor not in (1, 2, 3, 4):
            raise ValueError
    except ValueError:
        print("Motor must be 1, 2, 3, or 4.")
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
    setup_mcp23017()

    print("=========================================")
    print("  STEPPER MANUAL CONTROL  (4 motors)")
    print("=========================================")
    print("  <motor 1-4> <CW|CCW> <degrees> [speed]")
    print("  Examples:")
    print("    1 CW  45        -> Motor 1, CW,  45 deg, speed 50")
    print("    2 CCW 90        -> Motor 2, CCW, 90 deg, speed 50")
    print("    3 CW  22.5 80   -> Motor 3, CW, 22.5 deg, speed 80")
    print("    4 CCW 360 20    -> Motor 4, full CCW rotation, slow")
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
