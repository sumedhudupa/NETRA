#!/usr/bin/env python3

# =====================================================
# BRAILLE SYSTEM - Raspberry Pi Port
# Uses lgpio (compatible with Pi 4 and Pi 5)
#
# Motor 1 -> GPIO 17, 18, 27, 22
# Motor 2 -> GPIO 23, 24, 25, 4
# =====================================================

import lgpio
import time
import threading

# ================= MOTOR PINS =================
MOTOR1_PINS = [17, 18, 27, 22]
MOTOR2_PINS = [23, 24, 25, 4]

# ================= SETTINGS =================
STEPS_PER_REVOLUTION = 4076.0
STEP_DELAY = 0.0009   # 900 microseconds

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
step_index  = {1: 0, 2: 0}
current_div = {1: 0, 2: 0}
HOME_DIV    = 0
h           = None   # lgpio chip handle

# ================= BRAILLE MAPPING =================
BRAILLE_MAP = {
    'a': (4, 0), 'b': (6, 0), 'c': (4, 4), 'd': (4, 6), 'e': (4, 2),
    'f': (6, 4), 'g': (6, 6), 'h': (6, 2), 'i': (2, 4), 'j': (2, 6),
    'k': (5, 0), 'l': (7, 0), 'm': (5, 4), 'n': (5, 6), 'o': (5, 2),
    'p': (7, 4), 'q': (7, 6), 'r': (7, 2), 's': (3, 4), 't': (3, 6),
    'u': (5, 1), 'v': (7, 1), 'w': (2, 7), 'x': (5, 5), 'y': (5, 7),
    'z': (5, 3), ' ': (0, 0),
}

# =====================================================
# GPIO SETUP
# =====================================================

def setup_gpio():
    global h
    h = lgpio.gpiochip_open(0)   # opens /dev/gpiochip0

    for pin in MOTOR1_PINS + MOTOR2_PINS:
        lgpio.gpio_claim_output(h, pin, 0)   # claim as output, default LOW

    print("================================")
    print("BRAILLE SYSTEM READY  (lgpio)")
    print("================================")
    print("Type a letter A-Z or type HOME")

# =====================================================
# STEP MOTOR
# =====================================================

def step_motor(motor, direction):
    pins = MOTOR1_PINS if motor == 1 else MOTOR2_PINS

    step_index[motor] += direction

    if step_index[motor] > 7:
        step_index[motor] = 0
    if step_index[motor] < 0:
        step_index[motor] = 7

    for i in range(4):
        lgpio.gpio_write(h, pins[i], SEQ[step_index[motor]][i])

# =====================================================
# MOVE TO DIVISION
# =====================================================

def move_to_division(motor, target_div):
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


def move_both_to_divisions(left_div, right_div):
    """Move motor1 and motor2 in parallel to the target divisions."""
    t1 = threading.Thread(target=move_to_division, args=(1, left_div), daemon=True)
    t2 = threading.Thread(target=move_to_division, args=(2, right_div), daemon=True)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

# =====================================================
# POWER OFF COILS  (prevents overheating when idle)
# =====================================================

def power_off_coils():
    for pin in MOTOR1_PINS + MOTOR2_PINS:
        lgpio.gpio_write(h, pin, 0)

# =====================================================
# GO HOME
# =====================================================

def go_home():
    print("Going HOME...")
    move_to_division(1, HOME_DIV)
    time.sleep(0.2)
    move_to_division(2, HOME_DIV)
    time.sleep(0.2)
    power_off_coils()
    print("HOME REACHED")

# =====================================================
# DISPLAY CHARACTER
# =====================================================

def display_character(c):
    # NOTE: No automatic goHome here; caller should decide when to go home.
    m1, m2 = BRAILLE_MAP.get(c.lower(), (0, 0))

    print("======================")
    print(f"Character: {c.upper()}  ->  Motor1={m1}  Motor2={m2}")

    # Move both motors in parallel to target divisions
    move_both_to_divisions(m1, m2)

    # small pause after movement
    time.sleep(0.1)

    # optionally power off coils to avoid heating between moves
    power_off_coils()

    print(f"Final -> Motor1 Div: {current_div[1]}  Motor2 Div: {current_div[2]}")
    print("======================")

# =====================================================
# CLEANUP
# =====================================================

def cleanup():
    power_off_coils()
    if h is not None:
        lgpio.gpiochip_close(h)
    print("GPIO released. Bye.")

# =====================================================
# MAIN
# =====================================================

def main():
    setup_gpio()

    try:
        while True:
            user_input = input(">> ").strip()

            if not user_input:
                continue

            print(f"Input: {user_input}")

            if user_input.upper() == "HOME":
                go_home()

            else:
                # Process by words: go HOME once per word, then move per-character
                words = user_input.split(' ')
                pos = 0
                for widx, word in enumerate(words):
                    if word == '':
                        # consecutive spaces
                        pos += 1
                        continue

                    print(f"Word {widx+1}/{len(words)}: '{word}' - going HOME before word")
                    go_home()

                    for i, c in enumerate(word):
                        pos += 1
                        if c.isalpha():
                            print(f"[{pos}] Character: {c.upper()} - moving motors")
                            display_character(c)
                            time.sleep(2.0)
                        else:
                            print(f"[{pos}] '{c}' skipped (not a letter)")

                    # after finishing the word, return to HOME
                    print(f"Word '{word}' complete - returning HOME")
                    go_home()

                print("Input processed.")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    finally:
        cleanup()

if __name__ == "__main__":
    main()
