# NETRA — Refreshable Braille Reading Assistant

> **Status:** Phase 2 — Software pipeline functional (Docker/emulation stage). Hardware integration in progress.

NETRA is a low-cost, fully standalone refreshable braille reading assistant for visually impaired users. It runs entirely on a Raspberry Pi 5 with no paired PC or external server required.

---

## Features (Current Stage)

- **PDF input** — extract and display text from PDF files stored on SD card
- **Camera input** — capture images of printed text and OCR them (Tesseract)
- **Braille output** — UEB Grade 2 translation via liblouis, displayed as 4-cell dot patterns
- **TTS output** — simultaneous audio output via Piper TTS (`en_US-lessac-medium`)
- **LLM integration** — Ollama + gemma2:2b for document summarization and file navigation by name/index
- **STT** — Whisper tiny for voice commands and wake word detection ("hey netra")
- **4-cell scroll** — braille text displayed in chunks of 4 cells, advanced by button press

---

## Architecture

```
Input Layer
├── PDF file (PyMuPDF)         → structured text
└── Camera capture (Tesseract) → raw text
          ↓
Processing Core
├── LLM (Ollama + gemma2:2b)   → summarization / file navigation intent
├── liblouis (UEB G2)          → braille dot patterns
└── Piper TTS                  → audio synthesis
          ↓
Output Layer
├── Braille display (4-cell, solenoid-driven)
└── Speaker (WAV audio)
```

---

## Tech Stack

| Component | Library / Tool | Version |
|---|---|---|
| PDF extraction | PyMuPDF (`fitz`) | 1.27.2 |
| OCR | Tesseract + pytesseract | 5.x / 0.3.13 |
| Braille translation | liblouis + python3-louis | 3.29.0 |
| TTS | piper-tts (`lessac-medium`) | 1.4.1 |
| STT / wake word | openai-whisper (tiny) | 20250625 |
| LLM | Ollama + gemma2:2b | — |
| Runtime | Python 3.12 | — |
| Target hardware | Raspberry Pi 4 (4GB) | — |

---

## Repository Structure

```
netra/
├── netra.py          # Main integration script
├── config.json       # Runtime configuration (edit before running)
├── Dockerfile        # ARM64 container for dev/testing
└── README.md
```

---

## Prerequisites

### 1. Docker (for dev/testing on x86 laptop)
- Docker Desktop with `buildx` and QEMU ARM64 support
- For Windows: Docker Desktop ≥ 4.x

### 2. Ollama (runs natively on your machine, NOT inside the container)
- Download from [https://ollama.com/download](https://ollama.com/download)
- Required model: `gemma2:2b`

> On the real RPi 5, Ollama runs locally on the device. The container setup uses your laptop as a stand-in.

---

## Setup

### Step 1 — Clone the repo

```bash
git clone https://github.com/<your-username>/netra.git
cd netra
```

### Step 2 — Build the Docker image

This builds an ARM64 image that emulates the RPi 5 environment.

```bash
docker buildx build --platform linux/arm64 -t netra-rpi:v1 .
```

> First build takes ~20–30 minutes due to `torch` compilation under QEMU emulation. Subsequent builds use cache and are faster.

### Step 3 — Start the container

```bash
docker run --platform linux/arm64 --memory=8g --cpus=4 -it --name rpi-sim netra-rpi:v1
```

### Step 4 — Set up Ollama on your host machine

**Windows:**
```powershell
# Set model directory if models are stored in a custom path
$env:OLLAMA_MODELS="D:\Ollama\Models"     # skip if using default path

# Expose Ollama to Docker network
$env:OLLAMA_HOST="0.0.0.0"
ollama serve
```

**Linux/Mac:**
```bash
OLLAMA_HOST=0.0.0.0 ollama serve
```

In a separate terminal, pull the model:
```bash
ollama pull gemma2:2b
```

### Step 5 — Find the Docker-to-host IP

Inside the container:
```bash
# Install iproute2 if needed
apt-get install -y iproute2

# Get host IP
ip route | grep default | awk '{print $3}'
```

On Windows with Docker Desktop, also check:
```powershell
ipconfig
# Look for: "Ethernet adapter vEthernet (WSL)" → IPv4 Address
```

Use whichever IP successfully reaches Ollama:
```bash
curl http://<IP>:11434/api/tags
# Should return: {"models":[{"name":"gemma2:2b",...}]}
```

### Step 6 — Edit config.json

```json
{
  "ollama_host": "<IP from Step 5>",
  "ollama_port": 11434,
  "ollama_model": "gemma2:2b",
  "piper_model": "/root/piper-models/en_US-lessac-medium.onnx",
  "docs_dir": "/media/sdcard/docs",
  "braille_table": "en-ueb-g2.ctb",
  "braille_cells": 4,
  "whisper_model": "tiny",
  "wake_word": "hey netra",
  "audio_sample_rate": 16000,
  "record_seconds": 5
}
```

> On real RPi 4, set `ollama_host` to `127.0.0.1`.

### Step 7 — Add test documents

```bash
# Inside container
mkdir -p /media/sdcard/docs

# From your laptop (outside container)
docker cp yourfile.pdf rpi-sim:/media/sdcard/docs/yourfile.pdf
```

---

## Running

```bash
# Inside the container
python3 /root/netra.py
```

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

| Stub function | RPi replacement |
|---|---|
| `hw_read_mode_button()` | GPIO input on two pins (one per mode) |
| `hw_read_scroll_button()` | `GPIO.wait_for_edge(SCROLL_PIN, GPIO.RISING)` |
| `hw_read_summarize_button()` | `GPIO.input(SUMMARIZE_PIN)` |
| `hw_capture_image()` | `picamera2` library |
| `hw_display_braille_cells(patterns)` | Serial to Arduino/STM32 or direct GPIO solenoids |
| `hw_record_audio(seconds)` | `sounddevice.rec()` |
| `hw_play_audio(wav_path)` | `subprocess.run(["aplay", wav_path])` |

---

## Config Reference

| Key | Default | Description |
|---|---|---|
| `ollama_host` | `127.0.0.1` | Ollama server IP. Use `127.0.0.1` on RPi, Docker gateway IP on laptop |
| `ollama_port` | `11434` | Ollama server port |
| `ollama_model` | `gemma2:2b` | LLM model name (must be pulled in Ollama) |
| `piper_model` | `/root/piper-models/...` | Path to Piper `.onnx` model file |
| `docs_dir` | `/media/sdcard/docs` | Directory scanned for PDF and image files |
| `braille_table` | `en-ueb-g2.ctb` | liblouis translation table. Use `en-ueb-g1.ctb` for Grade 1 |
| `braille_cells` | `4` | Number of physical braille cells on the display |
| `whisper_model` | `tiny` | Whisper model size (`tiny`, `base`, `small`) |
| `wake_word` | `hey netra` | Wake word phrase (lowercase) |
| `record_seconds` | `5` | Duration to record after wake word |

---

## Known Limitations (Current Stage)

- **No real hardware connected yet** — all I/O via keyboard stubs
- **Emulated performance is not representative** — ARM64 under QEMU is ~5-10x slower than real RPi 5
- **Ollama runs on host machine** — not yet on-device; standalone deployment pending RPi hardware
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