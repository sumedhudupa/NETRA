"""
StepperHardwareAdapter

Implements HardwareAdapter for ULN2003-driven 28BYJ-48 stepper motors using lgpio.
This adapts the logic from test_motor_rpi.py into a class suitable for NETRA.
Delegates audio/camera operations to an optional wrapped audio adapter.

Config expectations (from NetraConfig):
- rpi_stepper_enabled: bool
- rpi_stepper_motor_pins: list of lists, each inner list has 4 GPIO pins for that motor
- rpi_stepper_steps_per_revolution: float
- rpi_stepper_step_delay_sec: float
"""
from typing import List, Optional
import logging
import time
import threading

try:
    import lgpio
    LGPIO_AVAILABLE = True
except Exception:
    lgpio = None
    LGPIO_AVAILABLE = False

from .interfaces import HardwareAdapter


# Default braille mapping for letters -> (left_div, right_div)
# Motor 2 right_div values are negated (CCW) because Motor 2 is physically
# flipped (inserted from the opposite side). Negative divisions drive the
# motor counter-clockwise, reproducing the same physical dot patterns.
BRAILLE_MAP = {
    'a': (4,  0), 'b': (6,  0), 'c': (4, -4), 'd': (4, -6), 'e': (4, -2),
    'f': (6, -4), 'g': (6, -6), 'h': (6, -2), 'i': (2, -4), 'j': (2, -6),
    'k': (5,  0), 'l': (7,  0), 'm': (5, -4), 'n': (5, -6), 'o': (5, -2),
    'p': (7, -4), 'q': (7, -6), 'r': (7, -2), 's': (3, -4), 't': (3, -6),
    'u': (5, -1), 'v': (7, -1), 'w': (2, -7), 'x': (5, -5), 'y': (5, -7),
    'z': (5, -3), ' ': (0,  0),
}

# Half-step sequence
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


class StepperHardwareAdapter(HardwareAdapter):
    def __init__(
        self,
        motor_pins: Optional[List[List[int]]] = None,
        steps_per_rev: float = 4076.0,
        step_delay_sec: float = 0.0009,
        audio_adapter: Optional[HardwareAdapter] = None,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.motor_pins = motor_pins or []
        self.steps_per_rev = steps_per_rev
        self.step_delay = step_delay_sec
        self.audio_adapter = audio_adapter  # Wrap audio adapter for pass-through

        # internal state
        self._h = None
        self._step_index = {i + 1: 0 for i in range(len(self.motor_pins))}
        self._current_div = {i + 1: 0 for i in range(len(self.motor_pins))}
        self._home_div = 0

        if LGPIO_AVAILABLE:
            try:
                self._h = lgpio.gpiochip_open(0)
                # claim outputs
                for pins in self.motor_pins:
                    for p in pins:
                        lgpio.gpio_claim_output(self._h, p, 0)
                self.logger.info("Stepper motors claimed: %s", self.motor_pins)
            except Exception as exc:  # pragma: no cover - hardware
                self.logger.warning("lgpio init failed: %s", exc)
                self._h = None
        else:
            self.logger.info("lgpio not available - stepper adapter running in simulation mode")

    def capture_image_path(self) -> str:
        if self.audio_adapter:
            return self.audio_adapter.capture_image_path()
        return ""

    def wait_for_scroll(self) -> None:
        if self.audio_adapter:
            self.audio_adapter.wait_for_scroll()
        else:
            time.sleep(0.5)

    def display_capacity_chars(self) -> int:
        # Two motors per character (left + right columns)
        return max(1, len(self.motor_pins) // 2)

    def _step_motor(self, motor_idx: int, direction: int) -> None:
        idx = motor_idx
        self._step_index[idx] += direction
        if self._step_index[idx] > 7:
            self._step_index[idx] = 0
        if self._step_index[idx] < 0:
            self._step_index[idx] = 7

        pins = self.motor_pins[idx - 1]
        if self._h is not None:
            for i in range(4):
                lgpio.gpio_write(self._h, pins[i], SEQ[self._step_index[idx]][i])

    def _move_to_division(self, motor_idx: int, target_div: int) -> None:
        diff = target_div - self._current_div[motor_idx]
        direction = 1 if diff >= 0 else -1
        divisions = abs(diff)
        steps = int(divisions * (self.steps_per_rev / 8.0))

        self.logger.debug(
            "Motor %d moving %d divisions -> %d steps (%s)", motor_idx, divisions, steps, 'CW' if direction==1 else 'CCW'
        )

        for _ in range(steps):
            self._step_motor(motor_idx, direction)
            time.sleep(self.step_delay)

        self._current_div[motor_idx] = target_div

    def _move_pair_parallel(self, left_idx: int, right_idx: int, left_div: int, right_div: int) -> None:
        t1 = threading.Thread(target=self._move_to_division, args=(left_idx, left_div), daemon=True)
        t2 = threading.Thread(target=self._move_to_division, args=(right_idx, right_div), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    def _power_off_coils(self) -> None:
        if self._h is None:
            return
        for pins in self.motor_pins:
            for p in pins:
                lgpio.gpio_write(self._h, p, 0)

    def go_home(self) -> None:
        # move each motor to HOME division sequentially
        for idx in range(1, len(self.motor_pins) + 1):
            self._move_to_division(idx, self._home_div)
            time.sleep(0.05)
        self._power_off_coils()

    def display_braille_cells(self, dot_patterns: List[int], chars: List[str] | None = None) -> None:
        """Display multiple characters in parallel.
        Each pair of motors (motors 1&2, motors 3&4, etc.) handles one character.
        All pairs move simultaneously.
        """
        # Normalize inputs
        cap = self.display_capacity_chars()  # chars_per_batch = motors // 2
        char_list: List[str] = (chars or [])[:cap]
        while len(char_list) < cap:
            char_list.append(' ')

        # Build list of motor moves to execute in parallel
        move_threads = []
        for pair_idx in range(cap):
            char = char_list[pair_idx].lower() if char_list[pair_idx] else ' '
            left_div, right_div = BRAILLE_MAP.get(char, (0, 0))
            left_motor_idx = pair_idx * 2 + 1
            right_motor_idx = pair_idx * 2 + 2
            
            if right_motor_idx > len(self.motor_pins):
                self.logger.debug("Not enough motors for pair %d", pair_idx)
                continue
            
            self.logger.info("Char[%d]='%s' -> motors %d/%d divisions %d/%d",
                             pair_idx, char, left_motor_idx, right_motor_idx, left_div, right_div)
            
            # Create thread for this motor pair and add to list
            t = threading.Thread(
                target=self._move_pair_parallel,
                args=(left_motor_idx, right_motor_idx, left_div, right_div),
                daemon=True
            )
            move_threads.append(t)

        # Start all threads simultaneously
        for t in move_threads:
            t.start()
        
        # Wait for all to complete
        for t in move_threads:
            t.join()

        # Power off coils after all moves complete
        self._power_off_coils()
        self.logger.info("Display complete: all %d chars moved in parallel", len(move_threads))

    def play_wav(self, wav_path: str) -> None:
        if self.audio_adapter:
            self.audio_adapter.play_wav(wav_path)
        # Otherwise no-op (audio not supported without adapter)

    def record_audio(self, seconds: int) -> str:
        if self.audio_adapter:
            return self.audio_adapter.record_audio(seconds)
        return ""

    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        if self.audio_adapter:
            return self.audio_adapter.read_audio_path_or_text_mode(seconds)
        return ""

    def cleanup(self) -> None:
        self._power_off_coils()
        if self._h is not None:
            lgpio.gpiochip_close(self._h)
