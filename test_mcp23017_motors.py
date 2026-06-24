#!/usr/bin/env python3
"""
Test script for MCP23017 + ULN2003 + 28BYJ-48 stepper motors.

Run this directly on the Raspberry Pi to verify your wiring:
    python3 test_mcp23017_motors.py
"""

import smbus2
import time
import sys

# ─── MCP23017 Configuration ───────────────────────────────────────
I2C_BUS = 1
CHIP_ADDRESSES = [0x20, 0x21]  # Support both chips

IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13

# ─── Half-step sequence for 28BYJ-48 ──────────────────────────────
STEP_SEQUENCE = [
    0b0001, 0b0011, 0b0010, 0b0110,
    0b0100, 0b1100, 0b1000, 0b1001,
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

def init_chips(bus):
    """Initialize MCP23017: set pins as outputs, all LOW."""
    for addr in CHIP_ADDRESSES:
        safe_write(bus, addr, IODIRA, 0x00)  # Port A = all output
        safe_write(bus, addr, GPIOA, 0x00)   # Port A = all LOW
        safe_write(bus, addr, IODIRB, 0x00)  # Port B = all output
        safe_write(bus, addr, GPIOB, 0x00)   # Port B = all LOW
        print(f"✅ MCP23017 at 0x{addr:02X} initialized")

def step_motor(bus, addr, port_reg, bit_offset, step_idx, port_cache):
    pattern = STEP_SEQUENCE[step_idx % 8]
    key = (addr, port_reg)
    current = port_cache.get(key, 0x00)
    mask = 0x0F << bit_offset
    current = (current & ~mask) | ((pattern & 0x0F) << bit_offset)
    bus.write_byte_data(addr, port_reg, current)
    port_cache[key] = current

def interactive_mode(bus):
    print("\n=== Interactive Mode ===")
    print("Commands:")
    print("  1-8       → Spin that motor one full revolution")
    print("  scan      → Re-scan I2C bus")
    print("  quit / q  → Exit")
    print()

    port_cache = {}

    motors = {
        1: (0x20, GPIOA, 0),
        2: (0x20, GPIOA, 4),
        3: (0x20, GPIOB, 0),
        4: (0x20, GPIOB, 4),
        5: (0x21, GPIOA, 0),
        6: (0x21, GPIOA, 4),
        7: (0x21, GPIOB, 0),
        8: (0x21, GPIOB, 4),
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
        elif cmd.isdigit() and 1 <= int(cmd) <= 8:
            motor_num = int(cmd)
            addr, port_reg, bit_offset = motors[motor_num]
            print(f"Spinning Motor {motor_num} on 0x{addr:02X}...")

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
            print("Unknown command. Type 1-8, scan, or quit.")

    # Power off everything
    for addr in CHIP_ADDRESSES:
        bus.write_byte_data(addr, GPIOA, 0x00)
        bus.write_byte_data(addr, GPIOB, 0x00)

def main():
    print("=" * 50)
    print("MCP23017 + ULN2003 + 28BYJ-48 Test")
    print("=" * 50)

    bus = smbus2.SMBus(I2C_BUS)
    devices = scan_i2c(bus)

    for addr in CHIP_ADDRESSES:
        if addr not in devices:
            print(f"❌ MCP23017 not found at address 0x{addr:02X}")

    init_chips(bus)
    interactive_mode(bus)
    
    for addr in CHIP_ADDRESSES:
        safe_write(bus, addr, GPIOA, 0x00)
        safe_write(bus, addr, GPIOB, 0x00)
    bus.close()
    print("\n✅ Done. GPIO cleaned up.")

if __name__ == "__main__":
    main()
