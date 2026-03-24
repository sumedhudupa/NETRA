import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NetraConfig:
    ollama_host: str = "127.0.0.1"
    ollama_port: int = 11434
    ollama_model: str = "qwen2.5-coder:3b"
    piper_model: str = "models/en_US-lessac-medium.onnx"
    docs_dir: str = "docs"
    braille_table: str = "en-ueb-g2.ctb"
    braille_cells: int = 4
    whisper_model: str = "tiny"
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
