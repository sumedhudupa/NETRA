import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NetraConfig:
    llama_model_path: str = "models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
    llama_threads: int = 4
    llama_context_size: int = 2048
    llama_temperature: float = 0.7
    piper_model: str = "models/en_US-lessac-medium.onnx"
    docs_dir: str = "docs"
    braille_table: str = "en-ueb-g2.ctb"
    braille_cells: int = 4
    whisper_model: str = "tiny"
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
    rpi_audio_device: int = None  # None = default, or ALSA card number
    rpi_gpio_scroll_button: int = 17
    rpi_gpio_status_led: int = 18
    rpi_gpio_servo_pins: str = "12,13,19,26"  # Comma-separated GPIO pins for 4 servos


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
