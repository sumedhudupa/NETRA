# NETRA — Refreshable Braille Reading Assistant

> **Status:** Phase 2 — Software pipeline functional (Docker/emulation stage). Hardware integration in progress.

NETRA is a low-cost, fully standalone refreshable braille reading assistant for visually impaired users. It runs entirely on a Raspberry Pi 4B/5 with no paired PC or external server required.

---

## Features (Current Stage)

- **PDF input** — extract and display text from PDF files stored on SD card
- **Camera input** — capture images of printed text and OCR them (Tesseract)
- **Braille output** — UEB Grade 2 translation via liblouis, displayed as 4-cell dot patterns
- **TTS output** — simultaneous audio output via Piper TTS (`en_US-lessac-medium`)
- **LLM integration** — llama.cpp with Phi-3-mini for grounded summarization + natural language commands
- **Dual STT engines** — Vosk (fast, for wake word detection) + Whisper (accurate, for command recognition), fully configurable
- **4-cell scroll** — braille text displayed in chunks of 4 cells, advanced by button press

---

## Architecture

```
Input Layer
├── PDF file (PyMuPDF)         → structured text
└── Camera capture (Tesseract) → raw text
          ↓
Processing Core
├── LLM (llama.cpp + Phi-3-mini)       → summarization / natural language parsing
├── liblouis (UEB G2)          → braille dot patterns
└── Piper TTS                  → audio synthesis
          ↓
Output Layer
├── Braille display (4-cell, solenoid-driven)
└── Speaker (WAV audio)
```

---

## Tech Stack

| Component           | Library / Tool                    | Version      |
| ------------------- | --------------------------------- | ------------ |
| PDF extraction      | PyMuPDF (`fitz`)                  | 1.27.2       |
| OCR                 | Tesseract + pytesseract           | 5.x / 0.3.13 |
| Braille translation | liblouis + python3-louis          | 3.29.0       |
| TTS                 | piper-tts (`lessac-medium`)       | 1.4.1        |
| STT (accuracy)      | openai-whisper (base)             | 20231117     |
| STT (speed)         | Vosk                              | 0.3.45       |
| LLM                 | llama.cpp + Phi-3-mini (Q4)       | 0.2.90       |
| Runtime             | Python 3.12                       | —            |
| Target hardware     | Raspberry Pi 4B (8GB) / RPi 5     | —            |

---

## Repository Structure

```
netra/
├── netra.py                  # Compatibility launcher (entrypoint)
├── config.json               # Runtime configuration
├── requirements.txt
├── src/netra/app.py          # Modular runtime orchestrator
├── src/netra/core/           # Conversation agent + command parser
├── src/netra/services/       # OCR/PDF/Braille/STT/TTS/Llama/Store services
├── src/netra/hardware/       # Hardware interface + adapters
├── models/                   # Model files (GGUF LLM, Vosk, Piper)
├── Dockerfile
└── README.md
```

---

## Prerequisites

### 1. Docker (for dev/testing on x86 laptop)

- Docker Desktop with `buildx` and QEMU ARM64 support
- For Windows: Docker Desktop ≥ 4.x

### 2. LLM Model Setup

Download the recommended grounded model for Raspberry Pi 4B:

**Phi-3-mini-4k-instruct (Q4 quantization)**

```bash
# Create models directory
mkdir -p models

# Download the model (approximately ~2.2GB)
cd models
wget https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf
cd ..
```

**Alternative models (if you need different speed/quality):**

- **Qwen 2.5 1.5B Instruct (Q4_K_M)**: smaller + faster, but less grounded than Phi-3-mini

> The model runs directly within your Python application - no separate server needed!

---

## Setup

### Step 1 — Clone the repo

```bash
git clone https://github.com/sumedhudupa/NETRA.git
cd netra
```

### Step 2 — Install Python dependencies

On your Raspberry Pi 4B or development machine:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (includes llama-cpp-python with CPU support)
pip install -r requirements.txt
```

**Note:** `llama-cpp-python` will compile from source on first install for ARM64. This takes 5-10 minutes on RPi 4B.

### Step 3 — Download the model

Place your downloaded GGUF model in the `models/` directory:

```bash
models/Phi-3-mini-4k-instruct-q4.gguf
```

### Step 4 — Configure and run

The `config.json` is already updated for llama.cpp. Just run:

```bash
python netra.py
```

---

## Docker Setup (for dev/testing on x86 laptop)

### Build the ARM64 image

This emulates the RPi environment:

```bash
docker buildx build --platform linux/arm64 -t netra-rpi:v1 .
```

> First build takes ~20–30 minutes due to compilation under QEMU emulation. Subsequent builds use cache and are faster.

### Run the container

```bash
docker run --platform linux/arm64 --memory=8g --cpus=4 -v $(pwd)/models:/app/models -it --name rpi-sim netra-rpi:v1
```

The `-v $(pwd)/models:/app/models` flag mounts your local models directory inside the container so the model file is accessible.

---

## Running

### On Raspberry Pi 4B

```bash
python netra.py
```

### In Docker container

```bash
# Inside the container
python3 /root/netra.py
```

---

## Configuration

Edit `config.json` to customize settings:

```json
{
  "llama_model_path": "models/Phi-3-mini-4k-instruct-q4.gguf",
  "llama_threads": 4,
  "llama_context_size": 4096,
  "llama_temperature": 0.7,
  "piper_model": "models/en_US-lessac-medium.onnx",
  "docs_dir": "docs",
  "braille_table": "en-ueb-g2.ctb",
  "braille_cells": 4,
  "whisper_model": "base",
  "stt_offline": true,
  "vosk_model": "models/vosk-model-small-en-us-0.15",
  "stt_engine": "vosk",
  "stt_engine_wake_word": "vosk",
  "stt_engine_command": "whisper",
  "wake_word": "hey netra",
  "enable_wake_word": false,
  "conversational_mode": true
}
```

**Key settings:**

- `llama_threads`: Set to 4 for RPi 4B (use all cores)
- `llama_context_size`: 4096 tokens is recommended for Phi-3-mini
- `llama_temperature`: 0.7 for balanced creativity/consistency

---

## Usage (Docker / Stub Mode)

Since the container has no physical buttons, microphone, or display, all hardware interactions use text stubs. Follow this interaction flow:

### Wake word

```
[HW STUB] Enter path to 3s audio .wav file (or ENTER to type text):
>> [ENTER]
[HW STUB] Press ENTER to simulate wake word detection... [ENTER]
```

### Mode selection

```
[HW STUB] Press button — type 'pdf' or 'camera': pdf
```

### File selection (PDF mode)

```
[HW STUB] Enter path to 5s audio .wav file (or ENTER to type text):
>> [ENTER]
[STT FALLBACK] Type spoken input: open file 1
```

Supported navigation commands:

- `open file 1` — open by index
- `open biology notes` — open by filename (fuzzy matched, then LLM confirmed)
- `next` — next file
- `previous` — previous file

### Summarization

```
[HW STUB] Summarize button pressed? (y/n): y   ← triggers LLM summarization
                                           n   ← reads full document
```

### Braille scrolling

```
[HW STUB] Press ENTER to scroll to next braille chunk... [ENTER]
```

Each ENTER advances by 4 braille cells. Dot patterns are printed as:

```
[HW STUB] Braille display:  Cell1:[1,2,5]  Cell2:[1,5]  Cell3:[1,2,3]  Cell4:[1,2,3]
```

### Camera mode

```
[HW STUB] Press button — type 'pdf' or 'camera': camera
[HW STUB] Press ENTER to simulate button press... [ENTER]   ← capture trigger
[HW STUB] Enter path to test image file: /root/test_image.png
```

---

## Hardware Stubs — RPi Replacement Guide

All hardware stubs are in the `HARDWARE ABSTRACTION LAYER` section of `netra.py`. Each function contains the RPi replacement code as a comment.

| Stub function                        | RPi replacement                                  |
| ------------------------------------ | ------------------------------------------------ |
| `hw_read_mode_button()`              | GPIO input on two pins (one per mode)            |
| `hw_read_scroll_button()`            | `GPIO.wait_for_edge(SCROLL_PIN, GPIO.RISING)`    |
| `hw_read_summarize_button()`         | `GPIO.input(SUMMARIZE_PIN)`                      |
| `hw_capture_image()`                 | `picamera2` library                              |
| `hw_display_braille_cells(patterns)` | Serial to Arduino/STM32 or direct GPIO solenoids |
| `hw_record_audio(seconds)`           | `sounddevice.rec()`                              |
| `hw_play_audio(wav_path)`            | `subprocess.run(["aplay", wav_path])`            |

---

## Config Reference

| Key                    | Default                    | Description                                                       |
| ---------------------- | -------------------------- | ----------------------------------------------------------------- |
| `llama_model_path`     | `models/Phi-3-mini-...gguf` | Path to GGUF model file for llama.cpp                            |
| `llama_threads`        | `4`                        | Number of CPU threads (4 for RPi 4B quad-core)                    |
| `llama_context_size`   | `4096`                     | Maximum context window in tokens                                  |
| `llama_temperature`    | `0.7`                      | Sampling temperature (0.1=focused, 1.0=creative)                  |
| `piper_model`          | `models/en_US-lessac-...`  | Path to Piper `.onnx` model file                                  |
| `docs_dir`             | `docs`                     | Directory scanned for PDF and image files                         |
| `braille_table`        | `en-ueb-g2.ctb`            | liblouis translation table. Use `en-ueb-g1.ctb` for Grade 1       |
| `braille_cells`        | `4`                        | Number of physical braille cells on the display                   |
| `whisper_model`        | `base`                     | Whisper model name (`tiny`, `base`, `small`) or local model path   |
| `stt_offline`          | `true`                     | If true, prevents STT from downloading models (offline-only)      |
| `vosk_model`           | `models/vosk-model-...`    | Path to Vosk model directory                                      |
| `stt_engine`           | `vosk`                     | Default STT engine (`vosk` or `whisper`)                          |
| `stt_engine_wake_word` | `vosk`                     | Engine for wake word detection (Vosk recommended for speed)       |
| `stt_engine_command`   | `whisper`                  | Engine for command recognition (Whisper recommended for accuracy) |
| `wake_word`            | `hey netra`                | Wake word phrase (lowercase)                                      |
| `record_seconds`       | `5`                        | Duration to record after wake word                                |

---

## Known Limitations (Current Stage)

- **No real hardware connected yet** — all I/O via keyboard stubs
- **Emulated performance is not representative** — ARM64 under QEMU is ~5-10x slower than real RPi 4B
- **LLM inference on RPi 4B** — Phi-3-mini is heavier than TinyLlama; expect slower but more grounded responses on CPU-only Raspberry Pi
- **No Porcupine wake word** — using Whisper for wake detection (less efficient than a dedicated wake word engine); Porcupine integration planned once AccessKey is available
- **Audio playback stubbed** — WAV files are generated correctly but not played inside the container (no audio device)
- **Single flat directory** — no nested folder navigation supported by design

---

## Roadmap

- [ ] Phase 2 (mid-May): RPi 4 hardware integration — GPIO buttons, solenoid display, camera, speaker
- [ ] Phase 2: 4-cell braille mechanism (cam-barrel design, OpenSCAD modeled)
- [ ] Phase 2: Arduino Nano / STM32 as GPIO buffer for solenoid current protection
- [ ] Phase 3 (late June): Porcupine wake word, performance benchmarking on real hardware
- [ ] Phase 3: Indic language support (extension scope)

---

## Team

Interdisciplinary Project (IDP) — 2 CS + 2 EC students  
Target device: Raspberry Pi 4 (4GB RAM), standalone, no PC dependency
