# NETRA - Refreshable Braille Reading Assistant
# Base: ARM64 Python 3.12 slim (matches Raspberry Pi 4B target)
FROM arm64v8/python:3.12-slim

# ── System packages ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    # Braille translation (liblouis C library + UEB tables + Python bindings)
    liblouis20 \
    liblouis-data \
    python3-louis \
    # OCR
    tesseract-ocr \
    tesseract-ocr-eng \
    # Audio (required by whisper + piper)
    ffmpeg \
    libsndfile1 \
    libportaudio2 \
    portaudio19-dev \
    alsa-utils \
    pulseaudio-utils \
    # Build tools for llama-cpp-python
    build-essential \
    cmake \
    # Utilities
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Python packages ────────────────────────────────────────────────────────────
RUN pip install --break-system-packages \
    # PDF extraction
    PyMuPDF==1.27.2 \
    # OCR
    pytesseract==0.3.13 \
    pillow==12.1.1 \
    opencv-python-headless==4.12.0.88 \
    # Braille (pip stub not needed — python3-louis installed via apt above)
    # TTS
    piper-tts==1.4.1 \
    pathvalidate==3.3.1 \
    # STT / wake word
    openai-whisper==20250625 \
    vosk==0.3.45 \
    sounddevice==0.5.2 \
    # Audio / math
    soundfile==0.13.1 \
    numpy==2.2.6 \
    # LLM (llama.cpp Python bindings with CPU-only support)
    llama-cpp-python==0.2.90

# ── Piper TTS model (en_US lessac medium — best quality/performance tradeoff) ──
RUN mkdir -p /root/piper-models && \
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
        -O /root/piper-models/en_US-lessac-medium.onnx && \
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
        -O /root/piper-models/en_US-lessac-medium.onnx.json

# ── Whisper model pre-download (tiny — ~150MB, CPU viable on RPi 4B) ────────────
RUN python3 -c "import whisper; whisper.load_model('tiny')"

# ── Download TinyLlama model for llama.cpp ──────────────────────────────────────
RUN mkdir -p /root/models && \
    wget -q "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf" \
        -O /root/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf

WORKDIR /root

CMD ["/bin/bash"]
