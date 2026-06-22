#!/usr/bin/env python3
"""
Test script for MCP23017 + ULN2003 + 28BYJ-48 stepper motors.

Run this directly on the Raspberry Pi to verify your wiring:
    python3 test_mcp23017_motors.py

Prerequisites:
    sudo apt-get install -y i2c-tools python3-smbus
    pip install smbus2

Wiring:
    Raspberry Pi          MCP23017 Module
    ─────────────         ───────────────
    Pin 1 (3.3V)   →     VCC
    Pin 3 (GPIO2)  →     SDA
    Pin 5 (GPIO3)  →     SCL
    Pin 6 (GND)    →     GND

    MCP23017 Output       ULN2003 Driver
    ───────────────       ──────────────
    GPA0               →  Motor 1 IN1
    GPA1               →  Motor 1 IN2
    GPA2               →  Motor 1 IN3
    GPA3               →  Motor 1 IN4
    GPA4               →  Motor 2 IN1
    GPA5               →  Motor 2 IN2
    GPA6               →  Motor 2 IN3
    GPA7               →  Motor 2 IN4
    GPB0               →  Motor 3 IN1
    GPB1               →  Motor 3 IN2
    GPB2               →  Motor 3 IN3
    GPB3               →  Motor 3 IN4
    GPB4               →  Motor 4 IN1
    GPB5               →  Motor 4 IN2
    GPB6               →  Motor 4 IN3
    GPB7               →  Motor 4 IN4
"""

import smbus2
import time
import sys

# ─── MCP23017 Configuration ───────────────────────────────────────
I2C_BUS = 1
CHIP_ADDRESS = 0x20  # Change if your address jumpers are different

IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13

# ─── Half-step sequence for 28BYJ-48 ──────────────────────────────
STEP_SEQUENCE = [
    0b0001,
    0b0011,
    0b0010,
    0b0110,
    0b0100,
    0b1100,
    0b1000,
    0b1001,
]

STEPS_PER_REVOLUTION = 4076
STEP_DELAY = 0.001  # 1 millisecond between steps


def scan_i2c(bus):
    """Scan the I2C bus and print all detected device addresses."""
    print("\n=== I2C Bus Scan ===")
    found = []
    for addr in range(0x03, 0x78):
        try:
            bus.read_byte(addr)
            found.append(addr)
            print(f"  Device found at address: 0x{addr:02X}")
        except Exception:
            pass

    if not found:
        print("  ❌ No I2C devices found!")
        print("  Check:")
        print("    1. Is I2C enabled? (sudo raspi-config → Interface → I2C)")
        print("    2. Are SDA/SCL wires connected to the correct Pi pins?")
        print("    3. Is VCC/GND connected?")
    else:
        print(f"  ✅ Found {len(found)} device(s)")
    print()
    return found


def safe_write(bus, addr, reg, value, retries=3):
    """Write to MCP23017 register with retry logic and delay."""
    for attempt in range(retries):
        try:
            bus.write_byte_data(addr, reg, value)
            time.sleep(0.005)  # 5ms delay between I2C writes
            return True
        except OSError as e:
            print(f"  ⚠ I2C write failed (reg=0x{reg:02X}, attempt {attempt+1}/{retries}): {e}")
            time.sleep(0.05)  # longer delay before retry
    return False


def init_chip(bus, addr, port_b=False):
    """Initialize MCP23017: set pins as outputs, all LOW.
    
    Args:
        port_b: If False, only initialize Port A (8 pins / 2 motors).
                If True, initialize both Port A and Port B (16 pins / 4 motors).
    """
    safe_write(bus, addr, IODIRA, 0x00)  # Port A = all output
    safe_write(bus, addr, GPIOA, 0x00)   # Port A = all LOW
    print(f"  ✅ Port A initialized (GPA0-GPA7 = output, LOW)")

    if port_b:
        if safe_write(bus, addr, IODIRB, 0x00) and safe_write(bus, addr, GPIOB, 0x00):
            print(f"  ✅ Port B initialized (GPB0-GPB7 = output, LOW)")
        else:
            print(f"  ⚠ Port B failed — check wiring to GPB pins")

    print(f"✅ MCP23017 at 0x{addr:02X} initialized")


def step_motor(bus, addr, port_reg, bit_offset, step_idx, port_cache):
    """
    Write one step to a motor.

    Args:
        bus:         smbus2.SMBus instance
        addr:        MCP23017 I2C address
        port_reg:    GPIOA or GPIOB
        bit_offset:  0 for lower nibble (motor on bits 0-3),
                     4 for upper nibble (motor on bits 4-7)
        step_idx:    current step index (0-7)
        port_cache:  dict to cache port state so two motors share a port safely
    """
    pattern = STEP_SEQUENCE[step_idx % 8]

    key = (addr, port_reg)
    current = port_cache.get(key, 0x00)
    mask = 0x0F << bit_offset
    current = (current & ~mask) | ((pattern & 0x0F) << bit_offset)

    bus.write_byte_data(addr, port_reg, current)
    port_cache[key] = current


def move_motor(bus, addr, port_reg, bit_offset, steps, port_cache, direction=1):
    """Move a motor a given number of steps."""
    for i in range(steps):
        step_idx = i if direction == 1 else (7 - (i % 8))
        step_motor(bus, addr, port_reg, bit_offset, i * direction, port_cache)
        time.sleep(STEP_DELAY)

    # Power off coils for this motor after movement
    key = (addr, port_reg)
    current = port_cache.get(key, 0x00)
    mask = 0x0F << bit_offset
    current = current & ~mask
    bus.write_byte_data(addr, port_reg, current)
    port_cache[key] = current


def test_single_motor(bus, addr):
    """Test: Spin Motor 1 (Port A, lower nibble) one full revolution."""
    print("\n=== Test 1: Single Motor (Motor 1 on Port A, bits 0-3) ===")
    print(f"Spinning Motor 1 one full revolution ({STEPS_PER_REVOLUTION} steps)...")

    port_cache = {}
    step_idx = 0

    for _ in range(STEPS_PER_REVOLUTION):
        step_motor(bus, addr, GPIOA, 0, step_idx, port_cache)
        step_idx += 1
        time.sleep(STEP_DELAY)

    # Power off
    bus.write_byte_data(addr, GPIOA, 0x00)
    port_cache[(addr, GPIOA)] = 0x00
    print("✅ Motor 1 completed one revolution")


def test_two_motors_same_port(bus, addr):
    """Test: Spin Motor 1 and Motor 2 (both on Port A) simultaneously."""
    print("\n=== Test 2: Two Motors on Same Port (Port A) ===")
    print("Motor 1 (bits 0-3) and Motor 2 (bits 4-7) spinning together...")

    port_cache = {}
    steps = STEPS_PER_REVOLUTION // 2  # Half revolution each

    for i in range(steps):
        pattern_m1 = STEP_SEQUENCE[i % 8]            # lower nibble
        pattern_m2 = STEP_SEQUENCE[i % 8] << 4        # upper nibble
        combined = pattern_m1 | pattern_m2

        bus.write_byte_data(addr, GPIOA, combined)
        port_cache[(addr, GPIOA)] = combined
        time.sleep(STEP_DELAY)

    # Power off
    bus.write_byte_data(addr, GPIOA, 0x00)
    print("✅ Both motors completed half revolution")


def test_all_four_motors(bus, addr):
    """Test: Spin all 4 motors on one MCP23017 chip simultaneously."""
    print("\n=== Test 3: All 4 Motors on One Chip ===")
    print("Motors 1-4 spinning together (half revolution)...")

    steps = STEPS_PER_REVOLUTION // 4  # Quarter revolution

    for i in range(steps):
        pattern = STEP_SEQUENCE[i % 8]

        # Port A: Motor 1 (bits 0-3) + Motor 2 (bits 4-7)
        port_a_value = pattern | (pattern << 4)
        bus.write_byte_data(addr, GPIOA, port_a_value)

        # Port B: Motor 3 (bits 0-3) + Motor 4 (bits 4-7)
        port_b_value = pattern | (pattern << 4)
        bus.write_byte_data(addr, GPIOB, port_b_value)

        time.sleep(STEP_DELAY)

    # Power off all
    bus.write_byte_data(addr, GPIOA, 0x00)
    bus.write_byte_data(addr, GPIOB, 0x00)
    print("✅ All 4 motors completed quarter revolution")


def interactive_mode(bus, addr):
    """Interactive mode to manually test individual motors."""
    print("\n=== Interactive Mode ===")
    print("Commands:")
    print("  1-4       → Spin that motor one full revolution")
    print("  all       → Spin all 4 motors simultaneously")
    print("  scan      → Re-scan I2C bus")
    print("  quit / q  → Exit")
    print()

    port_cache = {}

    # Motor definitions: motor_number → (port_register, bit_offset)
    motors = {
        1: (GPIOA, 0),
        2: (GPIOA, 4),
        3: (GPIOB, 0),
        4: (GPIOB, 4),
    }

    while True:
        try:
            cmd = input(">> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            break

        if cmd in ("q", "quit", "exit"):
            break
        elif cmd == "scan":
            scan_i2c(bus)
        elif cmd == "all":
            test_all_four_motors(bus, addr)
        elif cmd in ("1", "2", "3", "4"):
            motor_num = int(cmd)
            port_reg, bit_offset = motors[motor_num]
            print(f"Spinning Motor {motor_num}...")

            step_idx = 0
            for _ in range(STEPS_PER_REVOLUTION):
                step_motor(bus, addr, port_reg, bit_offset, step_idx, port_cache)
                step_idx += 1
                time.sleep(STEP_DELAY)

            # Power off this motor
            key = (addr, port_reg)
            current = port_cache.get(key, 0x00)
            mask = 0x0F << bit_offset
            port_cache[key] = current & ~mask
            bus.write_byte_data(addr, port_reg, port_cache[key])
            print(f"✅ Motor {motor_num} done")
        else:
            print("Unknown command. Type 1-4, all, scan, or quit.")

    # Power off everything
    bus.write_byte_data(addr, GPIOA, 0x00)
    bus.write_byte_data(addr, GPIOB, 0x00)


def main():
    print("=" * 50)
    print("MCP23017 + ULN2003 + 28BYJ-48 Test")
    print("=" * 50)

    bus = smbus2.SMBus(I2C_BUS)

    # Step 1: Scan for devices
    devices = scan_i2c(bus)

    if CHIP_ADDRESS not in devices:
        print(f"❌ MCP23017 not found at address 0x{CHIP_ADDRESS:02X}")
        if devices:
            print(f"   But found devices at: {['0x%02X' % d for d in devices]}")
            print(f"   Update CHIP_ADDRESS in this script if needed.")
        bus.close()
        sys.exit(1)

    # Step 2: Initialize chip (Port A only since only 8 pins connected)
    init_chip(bus, CHIP_ADDRESS, port_b=False)

    # Step 3: Run tests
    print("\nWhich test would you like to run?")
    print("  1 → Single motor test (Motor 1, Port A bits 0-3)")
    print("  2 → Two motors on Port A (Motor 1 & 2)")
    print("  3 → Interactive mode (type motor numbers)")
    print("  4 → Run all Port A tests sequentially")
    print()

    try:
        choice = input("Select (1-4): ").strip()
    except (KeyboardInterrupt, EOFError):
        choice = ""

    if choice == "1":
        test_single_motor(bus, CHIP_ADDRESS)
    elif choice == "2":
        test_two_motors_same_port(bus, CHIP_ADDRESS)
    elif choice == "3":
        interactive_mode(bus, CHIP_ADDRESS)
    elif choice == "4":
        test_single_motor(bus, CHIP_ADDRESS)
        time.sleep(1)
        test_two_motors_same_port(bus, CHIP_ADDRESS)
    else:
        print("No test selected.")

    # Cleanup - Port A only
    safe_write(bus, CHIP_ADDRESS, GPIOA, 0x00)
    bus.close()
    print("\n✅ Done. GPIO cleaned up.")


if __name__ == "__main__":
    main()
