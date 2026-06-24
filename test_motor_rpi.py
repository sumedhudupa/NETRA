#!/usr/bin/env python3

# =====================================================
# BRAILLE SYSTEM - MCP23017 I2C Port (8 motors / 4 cells)
# Uses smbus2 + 2x MCP23017 I/O expander (no direct GPIO)
#
# Wiring:
# Chip 1 (0x20):
#   GPA0-GPA3  →  Motor 1 IN1-IN4 (Cell 1, left column)
#   GPA4-GPA7  →  Motor 2 IN1-IN4 (Cell 1, right column)
#   GPB0-GPB3  →  Motor 3 IN1-IN4 (Cell 2, left column)
#   GPB4-GPB7  →  Motor 4 IN1-IN4 (Cell 2, right column)
#
# Chip 2 (0x21):
#   GPA0-GPA3  →  Motor 5 IN1-IN4 (Cell 3, left column)
#   GPA4-GPA7  →  Motor 6 IN1-IN4 (Cell 3, right column)
#   GPB0-GPB3  →  Motor 7 IN1-IN4 (Cell 4, left column)
#   GPB4-GPB7  →  Motor 8 IN1-IN4 (Cell 4, right column)
#
# Input a word → displayed 4 characters per frame across 8 motors.
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
step_index  = {m: 0 for m in range(1, 9)}
current_div = {m: 0 for m in range(1, 9)}
HOME_DIV    = 0
bus         = None
port_cache  = {}

# ================= BRAILLE MAPPING =================
# Right-column motors (2, 4, 6, 8) have negated divisions because
# they are physically flipped. Negative divisions drive CCW.
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

    for addr in CHIP_ADDRESSES:
        if addr not in found:
            print(f"❌ MCP23017 not found at 0x{addr:02X}!")
            if found:
                print(f"   Devices found: {['0x%02X' % a for a in found]}")
            bus.close()
            sys.exit(1)

        print(f"✅ MCP23017 found at 0x{addr:02X}")
        # Port A
        bus.write_byte_data(addr, IODIRA, 0x00); time.sleep(0.005)
        bus.write_byte_data(addr, GPIOA,  0x00); time.sleep(0.005)
        port_cache[(addr, GPIOA)] = 0x00

        # Port B
        bus.write_byte_data(addr, IODIRB, 0x00); time.sleep(0.005)
        bus.write_byte_data(addr, GPIOB,  0x00); time.sleep(0.005)
        port_cache[(addr, GPIOB)] = 0x00

    print("================================")
    print("BRAILLE SYSTEM READY (8 motors)")
    print("================================")
    print("Type a word, or HO / HOME to go home")


# =====================================================
# MOVE EIGHT MOTORS SIMULTANEOUSLY
# =====================================================
def move_eight_motors(divs):
    """divs is a list or tuple of exactly 8 division targets."""
    def _prep(motor, target):
        diff = target - current_div[motor]
        return (1 if diff >= 0 else -1), int(abs(diff) * (STEPS_PER_REVOLUTION / 8))

    dirs = {}
    rems = {}
    for m in range(1, 9):
        dirs[m], rems[m] = _prep(m, divs[m-1])

    print("Motors:")
    print(f" Cell1 → M1:{rems[1]} steps, M2:{rems[2]} steps")
    print(f" Cell2 → M3:{rems[3]} steps, M4:{rems[4]} steps")
    print(f" Cell3 → M5:{rems[5]} steps, M6:{rems[6]} steps")
    print(f" Cell4 → M7:{rems[7]} steps, M8:{rems[8]} steps")

    def _advance(motor, direction, remaining):
        if remaining > 0:
            step_index[motor] += direction
            if step_index[motor] > 7: step_index[motor] = 0
            if step_index[motor] < 0: step_index[motor] = 7
            return STEP_SEQUENCE[step_index[motor]], remaining - 1
        return 0x00, 0

    while any(r > 0 for r in rems.values()):
        p = {}
        for m in range(1, 9):
            p[m], rems[m] = _advance(m, dirs[m], rems[m])

        # Write to Chip 0x20
        bus.write_byte_data(0x20, GPIOA, ((p[2] & 0x0F) << 4) | (p[1] & 0x0F))
        bus.write_byte_data(0x20, GPIOB, ((p[4] & 0x0F) << 4) | (p[3] & 0x0F))
        
        # Write to Chip 0x21
        bus.write_byte_data(0x21, GPIOA, ((p[6] & 0x0F) << 4) | (p[5] & 0x0F))
        bus.write_byte_data(0x21, GPIOB, ((p[8] & 0x0F) << 4) | (p[7] & 0x0F))
        
        time.sleep(STEP_DELAY)

    power_off_coils()

    for m in range(1, 9):
        current_div[m] = divs[m-1]

    print(f"Done → M1@{current_div[1]} M2@{current_div[2]} M3@{current_div[3]} M4@{current_div[4]} "
          f"M5@{current_div[5]} M6@{current_div[6]} M7@{current_div[7]} M8@{current_div[8]}")


# =====================================================
# POWER OFF COILS
# =====================================================
def power_off_coils():
    """Set all motor pins LOW on all ports to prevent heating."""
    for addr in CHIP_ADDRESSES:
        bus.write_byte_data(addr, GPIOA, 0x00)
        bus.write_byte_data(addr, GPIOB, 0x00)
        port_cache[(addr, GPIOA)] = 0x00
        port_cache[(addr, GPIOB)] = 0x00


# =====================================================
# GO HOME
# =====================================================
def go_home():
    print("Going HOME...")
    move_eight_motors([HOME_DIV] * 8)
    print("HOME REACHED")


# =====================================================
# DISPLAY FOUR CHARS
# =====================================================
def transform_mapping(left_div, right_div):
    left_div_new = ((left_div & 1) << 2) | (left_div & 2) | ((left_div & 4) >> 2)
    right_div_new = abs(right_div)
    return left_div_new, right_div_new

def display_four_chars(c1, c2, c3, c4):
    """Display 4 characters simultaneously across 4 cells (8 motors)."""
    m1, m2 = transform_mapping(*BRAILLE_MAP.get(c1.lower(), (0, 0)))
    m3, m4 = transform_mapping(*BRAILLE_MAP.get(c2.lower(), (0, 0)))
    m5, m6 = transform_mapping(*BRAILLE_MAP.get(c3.lower(), (0, 0)))
    m7, m8 = transform_mapping(*BRAILLE_MAP.get(c4.lower(), (0, 0)))

    print("======================")
    print(f"Cell1: '{c1}' → M1={m1} M2={m2}")
    print(f"Cell2: '{c2}' → M3={m3} M4={m4}")
    print(f"Cell3: '{c3}' → M5={m5} M6={m6}")
    print(f"Cell4: '{c4}' → M7={m7} M8={m8}")

    move_eight_motors([m1, m2, m3, m4, m5, m6, m7, m8])
    print("======================")


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
                chars = [c for c in user_input if c.isalpha() or c == ' ']
                if not chars:
                    print("No valid characters.")
                    continue

                # Pad to multiple of 4
                while len(chars) % 4 != 0:
                    chars.append(' ')

                frames = [tuple(chars[i:i+4]) for i in range(0, len(chars), 4)]
                print(f"Displaying {len(chars)} chars in {len(frames)} frame(s).")

                for idx, frame in enumerate(frames):
                    print(f"\n[Frame {idx+1}/{len(frames)}]")
                    display_four_chars(*frame)
                    time.sleep(2.0)

                print("Input processed.")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        power_off_coils()
        if bus is not None:
            bus.close()
        print("I2C bus closed. Bye.")


if __name__ == "__main__":
    main()
