import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class NetraConfig:
    llama_model_path: str = "models/Phi-3-mini-4k-instruct-q4.gguf"
    llama_threads: int = 4
    llama_context_size: int = 2048
    llama_temperature: float = 0.7
    piper_model: str = "models/en_US-lessac-medium.onnx"
    docs_dir: str = "docs"
    braille_table: str = "en-ueb-g2.ctb"
    braille_cells: int = 4
    whisper_model: str = "base"
    # When true, STT will not download models from the internet.
    # Provide local model paths (or ensure models are already cached) to use Whisper.
    stt_offline: bool = True
    vosk_model: str = "models/vosk-model-small-en-us-0.15"
    stt_engine: str = "vosk"
    stt_engine_wake_word: str = "vosk"
    stt_engine_command: str = "vosk"
    wake_word: str = "hey netra"
    audio_sample_rate: int = 16000
    record_seconds: int = 5
    db_path: str = "netra_store.db"
    enable_wake_word: bool = False
    stt_use_live_mic: bool = True
    stt_allow_typed_fallback: bool = False
    conversational_mode: bool = True
    log_level: str = "INFO"
    logs_dir: str = "logs"
    braille_output_file: str = "logs/last_output.brl"
    # Raspberry Pi Hardware Settings
    hardware_mode: str = "auto"  # "auto", "rpi", or "stub"

    # Microphone / capture:
    rpi_audio_device: int | str | None = None

    # Speaker / playback:
    rpi_audio_output_device: str | None = None
    rpi_bt_speaker_mac: str | None = None

    rpi_gpio_scroll_button: int = 17
    rpi_gpio_status_led: int = 18
    rpi_gpio_servo_pins: str = "12,13,19,26,16,20,21,6"  # Comma-separated GPIO pins for 8 servos

    # Stepper motor support (lgpio-driven stepper/ULN2003)
    rpi_stepper_enabled: bool = False
    rpi_stepper_motor_pins: Optional[List[List[int]]] = None
    rpi_stepper_steps_per_revolution: float = 4076.0
    rpi_stepper_step_delay_sec: float = 0.0009

    # MCP23017 I2C I/O expander stepper motor support
    mcp23017_enabled: bool = False
    mcp23017_addresses: Optional[List[int]] = None  # e.g. [0x20, 0x21, 0x22]
    mcp23017_total_motors: int = 10

    usb_camera_device: str = "/dev/video0"
    usb_camera_width: int = 1920
    usb_camera_height: int = 1080
    # OCR/PDF Chunking Settings
    ocr_lines_per_chunk: int = 2
    pdf_pages_per_chunk: int = 1
    braille_display_delay: float = 3.0  # Delay between braille slides in seconds


DEFAULT_CONFIG = NetraConfig()


def load_config(config_path: Path) -> NetraConfig:
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        merged = {**DEFAULT_CONFIG.__dict__, **payload}
        return NetraConfig(**merged)

    config_path.write_text(
        json.dumps(DEFAULT_CONFIG.__dict__, indent=2),
        encoding="utf-8",
    )
    return DEFAULT_CONFIG
