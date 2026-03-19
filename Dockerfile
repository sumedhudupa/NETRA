# NETRA - Refreshable Braille Reading Assistant
# Base: ARM64 Python 3.12 slim (matches Raspberry Pi 5 target)
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
    # Braille (pip stub not needed — python3-louis installed via apt above)
    # TTS
    piper-tts==1.4.1 \
    pathvalidate==3.3.1 \
    # STT / wake word
    openai-whisper==20250625 \
    # Audio / math
    soundfile==0.13.1 \
    numpy==2.4.3 \
    # Summarization
    sumy==0.12.0 \
    # Networking (for Ollama API calls)
    requests==2.32.5

# ── Piper TTS model (en_US lessac medium — best quality/performance tradeoff) ──
RUN mkdir -p /root/piper-models && \
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
        -O /root/piper-models/en_US-lessac-medium.onnx && \
    wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
        -O /root/piper-models/en_US-lessac-medium.onnx.json

# ── Whisper model pre-download (tiny — ~150MB, CPU viable on RPi 5) ────────────
RUN python3 -c "import whisper; whisper.load_model('tiny')"

WORKDIR /root

CMD ["/bin/bash"]