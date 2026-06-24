#!/usr/bin/env python3

# =====================================================
# BRAILLE SYSTEM - MCP23017 I2C Port  (4 motors / 2 cells)
# Uses smbus2 + MCP23017 I/O expander (no direct GPIO)
#
# Wiring (MCP23017 at 0x20):
#   GPA0-GPA3  →  Motor 1 IN1-IN4  (ULN2003)  ← Cell 1, left column
#   GPA4-GPA7  →  Motor 2 IN1-IN4  (ULN2003)  ← Cell 1, right column
#   GPB0-GPB3  →  Motor 3 IN1-IN4  (ULN2003)  ← Cell 2, left column
#   GPB4-GPB7  →  Motor 4 IN1-IN4  (ULN2003)  ← Cell 2, right column
#
# Each character needs 2 motors (left + right column).
# Two characters are displayed simultaneously across the 4 motors.
# Input a word → displayed 2 characters per frame.
# Type HO or HOME to return all motors to home position.
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
    1: (GPIOA, 0),   # Motor 1: GPA bits 0-3  (Cell 1, left column)
    2: (GPIOA, 4),   # Motor 2: GPA bits 4-7  (Cell 1, right column)
    3: (GPIOB, 0),   # Motor 3: GPB bits 0-3  (Cell 2, left column)
    4: (GPIOB, 4),   # Motor 4: GPB bits 4-7  (Cell 2, right column)
}

# ================= SETTINGS =================
STEPS_PER_REVOLUTION = 4076.0
STEP_DELAY = 0.001    # 1 ms between steps

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
step_index  = {1: 0, 2: 0, 3: 0, 4: 0}
current_div = {1: 0, 2: 0, 3: 0, 4: 0}
HOME_DIV    = 0
bus         = None   # smbus2.SMBus instance
port_cache  = {}     # (addr, port_reg) → current 8-bit value

# ================= BRAILLE MAPPING =================
# (left_div, right_div) per Braille cell.
# Right-column motors (Motor 2, Motor 4) have negated divisions because
# they are physically flipped (shafts pointing inward). Negative divisions
# drive those motors CCW, reproducing the same physical dot patterns.
BRAILLE_MAP = {
    'a': (4,  0), 'b': (6,  0), 'c': (4, -4), 'd': (4, -6), 'e': (4, -2),
    'f': (6, -4), 'g': (6, -6), 'h': (6, -2), 'i': (2, -4), 'j': (2, -6),
    'k': (5,  0), 'l': (7,  0), 'm': (5, -4), 'n': (5, -6), 'o': (5, -2),
    'p': (7, -4), 'q': (7, -6), 'r': (7, -2), 's': (3, -4), 't': (3, -6),
    'u': (5, -1), 'v': (7, -1), 'w': (2, -7), 'x': (5, -5), 'y': (5, -7),
    'z': (5, -3), ' ': (0,  0),
}

# =====================================================
# I2C / MCP23017 SETUP
# =====================================================

def setup_mcp23017():
    """Open I2C bus, scan for MCP23017, and configure Port A and Port B as outputs."""
    global bus
    bus = smbus2.SMBus(I2C_BUS)

    print("================================")
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

    # Port A (motors 1 & 2 — Cell 1): all outputs, all LOW
    bus.write_byte_data(CHIP_ADDRESS, IODIRA, 0x00); time.sleep(0.005)
    bus.write_byte_data(CHIP_ADDRESS, GPIOA,  0x00); time.sleep(0.005)
    port_cache[(CHIP_ADDRESS, GPIOA)] = 0x00

    # Port B (motors 3 & 4 — Cell 2): all outputs, all LOW
    bus.write_byte_data(CHIP_ADDRESS, IODIRB, 0x00); time.sleep(0.005)
    bus.write_byte_data(CHIP_ADDRESS, GPIOB,  0x00); time.sleep(0.005)
    port_cache[(CHIP_ADDRESS, GPIOB)] = 0x00

    print("================================")
    print("BRAILLE SYSTEM READY  (4 motors)")
    print("================================")
    print("Type a word, or HO / HOME to go home")

# =====================================================
# STEP MOTOR  (single motor — used by go_home sequential fallback)
# =====================================================

def step_motor(motor, direction):
    """Advance one motor by one half-step in the given direction (+1 or -1)."""
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
# MOVE TO DIVISION  (single motor — used by go_home)
# =====================================================

def move_to_division(motor, target_div):
    """Move a single motor sequentially to target division."""
    diff      = target_div - current_div[motor]
    direction = 1 if diff >= 0 else -1
    divisions = abs(diff)
    steps     = int(divisions * (STEPS_PER_REVOLUTION / 8))

    print(f"Motor {motor} Moving {'CW' if direction == 1 else 'CCW'} "
          f"({divisions} div, {steps} steps)")

    for _ in range(steps):
        step_motor(motor, direction)
        time.sleep(STEP_DELAY)

    current_div[motor] = target_div
    print(f"Motor {motor} @ Division {current_div[motor]}")

# =====================================================
# MOVE FOUR MOTORS SIMULTANEOUSLY
#
# 2 I2C writes per step cycle (one per port):
#   GPIOA write → steps Motor 1 (bits 0-3) + Motor 2 (bits 4-7)  [Cell 1]
#   GPIOB write → steps Motor 3 (bits 0-3) + Motor 4 (bits 4-7)  [Cell 2]
#
# Each motor steps once per loop iteration. Motors with fewer steps
# finish early (coils set to 0x00); others continue until done.
# =====================================================

def move_four_motors(div1, div2, div3, div4):
    """Move all 4 motors simultaneously using 2 I2C writes per step cycle."""

    def _prep(motor, target):
        diff = target - current_div[motor]
        return (1 if diff >= 0 else -1), int(abs(diff) * (STEPS_PER_REVOLUTION / 8))

    dir1, rem1 = _prep(1, div1)
    dir2, rem2 = _prep(2, div2)
    dir3, rem3 = _prep(3, div3)
    dir4, rem4 = _prep(4, div4)

    print(f"Cell1 → M1({'CW' if dir1==1 else 'CCW'},{rem1}steps) "
          f"M2({'CW' if dir2==1 else 'CCW'},{rem2}steps)")
    print(f"Cell2 → M3({'CW' if dir3==1 else 'CCW'},{rem3}steps) "
          f"M4({'CW' if dir4==1 else 'CCW'},{rem4}steps)")

    def _advance(motor, direction, remaining):
        """Return (4-bit pattern, remaining-1) or (0x00, 0) if done."""
        if remaining > 0:
            step_index[motor] += direction
            if step_index[motor] > 7: step_index[motor] = 0
            if step_index[motor] < 0: step_index[motor] = 7
            return STEP_SEQUENCE[step_index[motor]], remaining - 1
        return 0x00, 0  # motor done — coils off

    while rem1 > 0 or rem2 > 0 or rem3 > 0 or rem4 > 0:
        p1, rem1 = _advance(1, dir1, rem1)
        p2, rem2 = _advance(2, dir2, rem2)
        p3, rem3 = _advance(3, dir3, rem3)
        p4, rem4 = _advance(4, dir4, rem4)

        # Port A: Motor 1 in lower nibble, Motor 2 in upper nibble
        bus.write_byte_data(CHIP_ADDRESS, GPIOA, ((p2 & 0x0F) << 4) | (p1 & 0x0F))
        # Port B: Motor 3 in lower nibble, Motor 4 in upper nibble
        bus.write_byte_data(CHIP_ADDRESS, GPIOB, ((p4 & 0x0F) << 4) | (p3 & 0x0F))
        time.sleep(STEP_DELAY)

    # All done — power off all coils
    bus.write_byte_data(CHIP_ADDRESS, GPIOA, 0x00)
    bus.write_byte_data(CHIP_ADDRESS, GPIOB, 0x00)
    port_cache[(CHIP_ADDRESS, GPIOA)] = 0x00
    port_cache[(CHIP_ADDRESS, GPIOB)] = 0x00

    current_div[1] = div1;  current_div[2] = div2
    current_div[3] = div3;  current_div[4] = div4
    print(f"Done → M1@{div1} M2@{div2} | M3@{div3} M4@{div4}")

# =====================================================
# POWER OFF COILS
# =====================================================

def power_off_coils():
    """Set all motor pins LOW on both ports."""
    bus.write_byte_data(CHIP_ADDRESS, GPIOA, 0x00)
    bus.write_byte_data(CHIP_ADDRESS, GPIOB, 0x00)
    port_cache[(CHIP_ADDRESS, GPIOA)] = 0x00
    port_cache[(CHIP_ADDRESS, GPIOB)] = 0x00

# =====================================================
# GO HOME  (all 4 motors back to division 0)
# =====================================================

def go_home():
    print("Going HOME...")
    move_four_motors(HOME_DIV, HOME_DIV, HOME_DIV, HOME_DIV)
    print("HOME REACHED")

# =====================================================
# DISPLAY TWO CHARS  (one per Braille cell, all 4 motors together)
# =====================================================

def display_two_chars(c1, c2):
    """Display two characters simultaneously.
    Cell 1 (motors 1 & 2) shows c1.
    Cell 2 (motors 3 & 4) shows c2.
    """
    m1, m2 = BRAILLE_MAP.get(c1.lower(), (0, 0))
    m3, m4 = BRAILLE_MAP.get(c2.lower(), (0, 0))

    print("======================")
    print(f"Cell1: '{c1.upper()}' → M1={m1} M2={m2}")
    print(f"Cell2: '{c2.upper()}' → M3={m3} M4={m4}")

    move_four_motors(m1, m2, m3, m4)

    print(f"Final → M1@{current_div[1]} M2@{current_div[2]} | "
          f"M3@{current_div[3]} M4@{current_div[4]}")
    print("======================")

# =====================================================
# CLEANUP
# =====================================================

def cleanup():
    power_off_coils()
    if bus is not None:
        bus.close()
    print("I2C bus closed. Bye.")

# =====================================================
# MAIN
# =====================================================

def main():
    setup_mcp23017()

    try:
        while True:
            user_input = input(">> ").strip()

            if not user_input:
                continue

            print(f"Input: {user_input}")

            if user_input.upper() in ("HOME", "HO"):
                go_home()

            else:
                # Keep only letters and spaces; drop everything else
                chars = [c for c in user_input if c.isalpha() or c == ' ']
                if not chars:
                    print("No valid characters.")
                    continue

                # Pad to an even length so every frame has exactly 2 chars
                if len(chars) % 2 != 0:
                    chars.append(' ')

                frames = [(chars[i], chars[i + 1]) for i in range(0, len(chars), 2)]
                print(f"Displaying {len(chars)} chars in {len(frames)} frame(s).")

                for idx, (c1, c2) in enumerate(frames):
                    print(f"\n[Frame {idx+1}/{len(frames)}]")
                    display_two_chars(c1, c2)
                    time.sleep(2.0)

                print("Input processed.")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        cleanup()

if __name__ == "__main__":
    main()
