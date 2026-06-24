#!/usr/bin/env python3

# =====================================================
# MANUAL STEPPER MOTOR DEGREE CONTROL (8 motors)
# Uses smbus2 + 2x MCP23017 I/O expander
#
# Wiring:
# Chip 1 (0x20):
#   GPA0-GPA3  →  Motor 1 IN1-IN4
#   GPA4-GPA7  →  Motor 2 IN1-IN4
#   GPB0-GPB3  →  Motor 3 IN1-IN4
#   GPB4-GPB7  →  Motor 4 IN1-IN4
#
# Chip 2 (0x21):
#   GPA0-GPA3  →  Motor 5 IN1-IN4
#   GPA4-GPA7  →  Motor 6 IN1-IN4
#   GPB0-GPB3  →  Motor 7 IN1-IN4
#   GPB4-GPB7  →  Motor 8 IN1-IN4
#
# COMMANDS:
#   1 CW  45     -> Motor 1 clockwise 45 degrees
#   8 CCW 90     -> Motor 8 counter-clockwise 90 degrees
#   2 CW  45 50  -> Motor 2 CW 45 deg at speed 50 (1-100)
#   exit         -> quit
# =====================================================

import smbus2
import time
import sys

# ================= MCP23017 CONFIG =================
I2C_BUS      = 1
CHIP_ADDRESSES = [0x20, 0x21]

IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13

# motor_number → (chip_addr, port_register, bit_offset)
MOTOR_MAP = {
    1: (0x20, GPIOA, 0),
    2: (0x20, GPIOA, 4),
    3: (0x20, GPIOB, 0),
    4: (0x20, GPIOB, 4),
    5: (0x21, GPIOA, 0),
    6: (0x21, GPIOA, 4),
    7: (0x21, GPIOB, 0),
    8: (0x21, GPIOB, 4),
}

# ================= SETTINGS =================
STEPS_PER_REVOLUTION = 4076.0
DEGREES_PER_STEP     = 360.0 / STEPS_PER_REVOLUTION
DEFAULT_STEP_DELAY   = 0.0009

# ================= HALF-STEP SEQUENCE =================
STEP_SEQUENCE = [
    0b0001, 0b0011, 0b0010, 0b0110,
    0b0100, 0b1100, 0b1000, 0b1001,
]

# ================= STATE =================
step_index = {m: 0 for m in range(1, 9)}
bus        = None
port_cache = {}

# ================= SETUP =================
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

    for addr in CHIP_ADDRESSES:
        if addr not in found:
            print(f"❌ MCP23017 not found at 0x{addr:02X}!")
            if found:
                print(f"   Devices found: {['0x%02X' % a for a in found]}")
            bus.close()
            sys.exit(1)
        
        print(f"✅ MCP23017 found at 0x{addr:02X}")
        
        bus.write_byte_data(addr, IODIRA, 0x00); time.sleep(0.005)
        bus.write_byte_data(addr, GPIOA, 0x00); time.sleep(0.005)
        port_cache[(addr, GPIOA)] = 0x00
        
        bus.write_byte_data(addr, IODIRB, 0x00); time.sleep(0.005)
        bus.write_byte_data(addr, GPIOB, 0x00); time.sleep(0.005)
        port_cache[(addr, GPIOB)] = 0x00


def power_off_coils():
    for addr in CHIP_ADDRESSES:
        bus.write_byte_data(addr, GPIOA, 0x00)
        bus.write_byte_data(addr, GPIOB, 0x00)
        port_cache[(addr, GPIOA)] = 0x00
        port_cache[(addr, GPIOB)] = 0x00


def cleanup():
    power_off_coils()
    if bus is not None:
        bus.close()
    print("I2C bus closed.")

# =====================================================
# STEP MOTOR (MCP23017 version)
# =====================================================
def step_motor(motor, direction):
    step_index[motor] += direction
    if step_index[motor] > 7: step_index[motor] = 0
    if step_index[motor] < 0: step_index[motor] = 7

    chip_addr, port_reg, bit_offset = MOTOR_MAP[motor]
    pattern = STEP_SEQUENCE[step_index[motor]]

    key = (chip_addr, port_reg)
    current = port_cache.get(key, 0x00)
    mask = 0x0F << bit_offset
    current = (current & ~mask) | ((pattern & 0x0F) << bit_offset)
    bus.write_byte_data(chip_addr, port_reg, current)
    port_cache[key] = current

# =====================================================
# ROTATE BY DEGREES
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

    if len(parts) < 3:
        print("Usage: <motor 1-8> <CW|CCW> <degrees> [speed 1-100]")
        return

    try:
        motor = int(parts[0])
        if motor not in range(1, 9):
            raise ValueError
    except ValueError:
        print("Motor must be between 1 and 8.")
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

    speed = 50
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
    print("  STEPPER MANUAL CONTROL  (8 motors)")
    print("=========================================")
    print("  <motor 1-8> <CW|CCW> <degrees> [speed]")
    print("  Examples:")
    print("    1 CW  45        -> Motor 1, CW,  45 deg, speed 50")
    print("    8 CCW 90        -> Motor 8, CCW, 90 deg, speed 50")
    print("    3 CW  22.5 80   -> Motor 3, CW, 22.5 deg, speed 80")
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
