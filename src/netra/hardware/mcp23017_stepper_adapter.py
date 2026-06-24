"""
MCP23017 Stepper Hardware Adapter

Drives 28BYJ-48 stepper motors through ULN2003 drivers connected to
MCP23017 I2C I/O expander chips instead of direct Raspberry Pi GPIO pins.

Each MCP23017 provides 16 output pins (Port A: GPA0-7, Port B: GPB0-7),
enough for 4 motors (4 pins each). Multiple chips can share the same
I2C bus (SDA/SCL), using only 2 GPIO pins total.

Pin mapping per chip:
  GPA0-3 → Motor 1 (IN1-IN4)
  GPA4-7 → Motor 2 (IN1-IN4)
  GPB0-3 → Motor 3 (IN1-IN4)
  GPB4-7 → Motor 4 (IN1-IN4)

Chip addressing (set via A0, A1, A2 pins on the MCP23017):
  Chip 1: A2=0 A1=0 A0=0 → address 0x20 → Motors 1-4
  Chip 2: A2=0 A1=0 A0=1 → address 0x21 → Motors 5-8
  Chip 3: A2=0 A1=1 A0=0 → address 0x22 → Motors 9-12

Config expectations (from NetraConfig):
- mcp23017_enabled: bool
- mcp23017_addresses: list of I2C addresses, e.g. [0x20, 0x21, 0x22]
- mcp23017_total_motors: int (default 10)
- rpi_stepper_steps_per_revolution: float (default 4076.0)
- rpi_stepper_step_delay_sec: float (default 0.0009)
"""

from typing import List, Optional, Dict, Tuple
import logging
import time
import threading

try:
    import smbus2
    SMBUS_AVAILABLE = True
except ImportError:
    smbus2 = None
    SMBUS_AVAILABLE = False

from .interfaces import HardwareAdapter

# ─── MCP23017 Register Addresses ───────────────────────────────────
IODIRA = 0x00   # I/O Direction Register for Port A (1=input, 0=output)
IODIRB = 0x01   # I/O Direction Register for Port B
GPIOA  = 0x12   # GPIO Port A register (read/write pin states)
GPIOB  = 0x13   # GPIO Port B register

# ─── Half-step sequence for 28BYJ-48 ──────────────────────────────
# Each value is a 4-bit pattern for IN1-IN4
STEP_SEQUENCE = [
    0b0001,  # Step 0
    0b0011,  # Step 1
    0b0010,  # Step 2
    0b0110,  # Step 3
    0b0100,  # Step 4
    0b1100,  # Step 5
    0b1000,  # Step 6
    0b1001,  # Step 7
]

# ─── Braille mapping: letter → (left_division, right_division) ─────
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


class MCP23017StepperAdapter(HardwareAdapter):
    """
    Hardware adapter that controls 28BYJ-48 stepper motors via MCP23017
    I2C I/O expander chips.

    Usage:
        adapter = MCP23017StepperAdapter(
            chip_addresses=[0x20, 0x21, 0x22],  # 3 chips = 12 motors max
            motors_per_chip=4,
            total_motors=10,
        )
    """

    def __init__(
        self,
        chip_addresses: Optional[List[int]] = None,
        motors_per_chip: int = 4,
        total_motors: int = 10,
        steps_per_rev: float = 4076.0,
        step_delay_sec: float = 0.0009,
        i2c_bus_number: int = 1,
        audio_adapter: Optional[HardwareAdapter] = None,
    ) -> None:
        self.logger = logging.getLogger(__name__)

        # Configuration
        self.chip_addresses = chip_addresses or [0x20, 0x21, 0x22]
        self.motors_per_chip = motors_per_chip
        self.total_motors = total_motors
        self.steps_per_rev = steps_per_rev
        self.step_delay = step_delay_sec
        self.i2c_bus_number = i2c_bus_number
        self.audio_adapter = audio_adapter

        # Internal state per motor
        self._step_index: Dict[int, int] = {m: 0 for m in range(1, total_motors + 1)}
        self._current_div: Dict[int, int] = {m: 0 for m in range(1, total_motors + 1)}
        self._home_div = 0

        # Port state cache: (chip_address, port_register) → current 8-bit value
        # This is essential so that when we update one motor's 4 bits on a port,
        # we don't accidentally overwrite the other motor's 4 bits on the same port.
        self._port_state: Dict[Tuple[int, int], int] = {}

        # Thread lock for I2C bus access — two motors on the same port
        # must not write simultaneously or data gets corrupted.
        self._i2c_lock = threading.Lock()

        # I2C bus handle
        self._bus = None

        self._initialize_hardware()

    # ─── Safe I2C write with retry ─────────────────────────────────
    def _safe_write(self, addr: int, reg: int, value: int, retries: int = 3) -> bool:
        """Write to MCP23017 register with retry logic and delay."""
        if self._bus is None:
            return False
        for attempt in range(retries):
            try:
                self._bus.write_byte_data(addr, reg, value)
                time.sleep(0.001)  # 1ms settling delay between I2C writes
                return True
            except OSError as exc:
                self.logger.warning(
                    "I2C write failed (addr=0x%02X reg=0x%02X attempt=%d/%d): %s",
                    addr, reg, attempt + 1, retries, exc,
                )
                time.sleep(0.01)  # 10ms before retry
        return False

    # ─── Motor-to-chip/port mapping ────────────────────────────────
    def _motor_location(self, motor_idx: int) -> Tuple[int, int, int]:
        """
        Given a 1-based motor index, return:
          (chip_address, port_register, bit_offset)

        Each chip has 2 ports (A and B), each port holds 2 motors (lower 4 bits
        and upper 4 bits).

        Motor layout per chip:
          Motor 1 → Port A, bits 0-3   (bit_offset=0)
          Motor 2 → Port A, bits 4-7   (bit_offset=4)
          Motor 3 → Port B, bits 0-3   (bit_offset=0)
          Motor 4 → Port B, bits 4-7   (bit_offset=4)
        """
        zero_idx = motor_idx - 1
        chip_idx = zero_idx // self.motors_per_chip
        motor_on_chip = zero_idx % self.motors_per_chip

        chip_addr = self.chip_addresses[chip_idx]

        if motor_on_chip < 2:
            port_reg = GPIOA
            bit_offset = motor_on_chip * 4  # 0 or 4
        else:
            port_reg = GPIOB
            bit_offset = (motor_on_chip - 2) * 4  # 0 or 4

        return chip_addr, port_reg, bit_offset

    # ─── Hardware initialization ───────────────────────────────────
    def _initialize_hardware(self) -> None:
        """Open the I2C bus and configure all MCP23017 chips as outputs."""
        if not SMBUS_AVAILABLE:
            self.logger.info(
                "smbus2 not available — MCP23017 adapter running in simulation mode"
            )
            return

        try:
            self._bus = smbus2.SMBus(self.i2c_bus_number)

            # Determine how many chips we actually need
            chips_needed = (self.total_motors + self.motors_per_chip - 1) // self.motors_per_chip
            active_chips = self.chip_addresses[:chips_needed]

            for addr in active_chips:
                # Determine how many motors are on this chip
                chip_idx = self.chip_addresses.index(addr)
                first_motor = chip_idx * self.motors_per_chip + 1
                last_motor = min(first_motor + self.motors_per_chip - 1, self.total_motors)
                motors_on_this_chip = last_motor - first_motor + 1

                # Port A is always needed (motors 1-2 on this chip)
                if not self._safe_write(addr, IODIRA, 0x00):
                    self.logger.error("Failed to init Port A direction on 0x%02X", addr)
                    continue
                self._safe_write(addr, GPIOA, 0x00)
                self._port_state[(addr, GPIOA)] = 0x00
                self.logger.info("MCP23017 0x%02X Port A initialized", addr)

                # Port B only needed if this chip has motors 3-4
                if motors_on_this_chip > 2:
                    if self._safe_write(addr, IODIRB, 0x00):
                        self._safe_write(addr, GPIOB, 0x00)
                        self._port_state[(addr, GPIOB)] = 0x00
                        self.logger.info("MCP23017 0x%02X Port B initialized", addr)
                    else:
                        self.logger.warning(
                            "MCP23017 0x%02X Port B init failed — "
                            "motors 3-4 on this chip will not work. Check wiring.",
                            addr,
                        )

            self.logger.info(
                "MCP23017 stepper adapter ready: %d chips, %d motors",
                len(active_chips),
                self.total_motors,
            )

        except Exception as exc:
            self.logger.error("MCP23017 initialization failed: %s", exc)
            self._bus = None

    # ─── Low-level I2C pin writing ─────────────────────────────────
    def _write_motor_pins(self, motor_idx: int, four_bit_pattern: int) -> None:
        """
        Write a 4-bit pattern (IN1-IN4) for a specific motor.

        This method reads the cached port state, masks in the new 4-bit pattern
        at the correct offset, and writes the full 8-bit value to the port.
        This ensures that two motors sharing the same port don't interfere.

        Thread-safe: uses a lock so concurrent motor threads don't corrupt
        the shared port state.
        """
        chip_addr, port_reg, bit_offset = self._motor_location(motor_idx)

        with self._i2c_lock:
            # Read current cached state of the 8-bit port
            port_key = (chip_addr, port_reg)
            current = self._port_state.get(port_key, 0x00)

            # Clear the 4 bits for this motor, then set the new pattern
            mask = 0x0F << bit_offset          # e.g., 0b00001111 or 0b11110000
            current = current & ~mask          # clear the motor's bits
            current = current | ((four_bit_pattern & 0x0F) << bit_offset)  # set new bits

            # Write to the chip and update cache
            if self._bus is not None:
                try:
                    self._bus.write_byte_data(chip_addr, port_reg, current)
                except OSError:
                    # Retry once on transient I2C error
                    time.sleep(0.005)
                    try:
                        self._bus.write_byte_data(chip_addr, port_reg, current)
                    except OSError as exc:
                        self.logger.warning(
                            "I2C write failed for motor %d: %s", motor_idx, exc
                        )
            self._port_state[port_key] = current

    # ─── Stepping logic ────────────────────────────────────────────
    def _step_motor(self, motor_idx: int, direction: int) -> None:
        """Advance motor by one half-step in the given direction (+1 or -1)."""
        self._step_index[motor_idx] += direction

        if self._step_index[motor_idx] > 7:
            self._step_index[motor_idx] = 0
        if self._step_index[motor_idx] < 0:
            self._step_index[motor_idx] = 7

        pattern = STEP_SEQUENCE[self._step_index[motor_idx]]
        self._write_motor_pins(motor_idx, pattern)

    def _move_to_division(self, motor_idx: int, target_div: int) -> None:
        """Move a motor from its current division to the target division."""
        diff = target_div - self._current_div[motor_idx]
        direction = 1 if diff >= 0 else -1
        divisions = abs(diff)
        steps = int(divisions * (self.steps_per_rev / 8.0))

        self.logger.debug(
            "Motor %d moving %d divisions → %d steps (%s)",
            motor_idx, divisions, steps, "CW" if direction == 1 else "CCW",
        )

        for _ in range(steps):
            self._step_motor(motor_idx, direction)
            time.sleep(self.step_delay)

        self._current_div[motor_idx] = target_div

    def _move_pair_parallel(
        self, left_idx: int, right_idx: int, left_div: int, right_div: int
    ) -> None:
        """Move two motors (a left/right pair) simultaneously using threads."""
        t1 = threading.Thread(
            target=self._move_to_division, args=(left_idx, left_div), daemon=True
        )
        t2 = threading.Thread(
            target=self._move_to_division, args=(right_idx, right_div), daemon=True
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    # ─── Power off all coils ───────────────────────────────────────
    def _power_off_coils(self) -> None:
        """Set all motor pins to LOW to prevent overheating when idle."""
        if self._bus is None:
            return

        with self._i2c_lock:
            chips_needed = (self.total_motors + self.motors_per_chip - 1) // self.motors_per_chip
            for addr in self.chip_addresses[:chips_needed]:
                # Always try Port A
                self._safe_write(addr, GPIOA, 0x00)
                self._port_state[(addr, GPIOA)] = 0x00

                # Port B — may not be connected, handle gracefully
                if (addr, GPIOB) in self._port_state:
                    self._safe_write(addr, GPIOB, 0x00)
                    self._port_state[(addr, GPIOB)] = 0x00

    # ─── HardwareAdapter interface ─────────────────────────────────

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
        """Two motors per braille character (left + right columns)."""
        return max(1, self.total_motors // 2)

    def go_home(self) -> None:
        """Move all motors back to the home division (0)."""
        threads = []
        for idx in range(1, self.total_motors + 1):
            t = threading.Thread(
                target=self._move_to_division, args=(idx, self._home_div), daemon=True
            )
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self._power_off_coils()
        self.logger.info("All motors returned to HOME")

    def display_braille_cells(
        self, dot_patterns: List[int], chars: List[str] | None = None
    ) -> None:
        """
        Display multiple braille characters simultaneously.
        Each pair of motors (motors 1&2, 3&4, etc.) represents one character.
        All pairs move at the same time via threading.
        """
        cap = self.display_capacity_chars()
        char_list: List[str] = (chars or [])[:cap]
        while len(char_list) < cap:
            char_list.append(" ")

        move_threads = []
        for pair_idx in range(cap):
            char = char_list[pair_idx].lower() if char_list[pair_idx] else " "
            left_div, right_div = BRAILLE_MAP.get(char, (0, 0))
            
            # Motor 2 (right) maps to absolute positive value
            right_div = abs(right_div)
            # Motor 1 (left) uses 3-bit binary reversal
            left_div = ((left_div & 1) << 2) | (left_div & 2) | ((left_div & 4) >> 2)

            left_motor = pair_idx * 2 + 1
            right_motor = pair_idx * 2 + 2

            if right_motor > self.total_motors:
                self.logger.debug("Not enough motors for pair %d", pair_idx)
                continue

            self.logger.info(
                "Char[%d]='%s' → motors %d/%d divisions %d/%d",
                pair_idx, char, left_motor, right_motor, left_div, right_div,
            )

            t = threading.Thread(
                target=self._move_pair_parallel,
                args=(left_motor, right_motor, left_div, right_div),
                daemon=True,
            )
            move_threads.append(t)

        for t in move_threads:
            t.start()
        for t in move_threads:
            t.join()

        self._power_off_coils()
        self.logger.info(
            "Display complete: %d chars rendered via MCP23017", len(move_threads)
        )

    def play_wav(self, wav_path: str) -> None:
        if self.audio_adapter:
            self.audio_adapter.play_wav(wav_path)

    def record_audio(self, seconds: int) -> str:
        if self.audio_adapter:
            return self.audio_adapter.record_audio(seconds)
        return ""

    def read_audio_path_or_text_mode(self, seconds: int) -> str:
        if self.audio_adapter:
            return self.audio_adapter.read_audio_path_or_text_mode(seconds)
        return ""

    def cleanup(self) -> None:
        """Power off all coils and close the I2C bus."""
        self._power_off_coils()
        if self._bus is not None:
            self._bus.close()
            self._bus = None
        self.logger.info("MCP23017 stepper adapter cleaned up")
