"""
NETRA — Refreshable Braille Reading Assistant
Main integration script

Pipeline:
  Input (PDF / Camera) → Text Extraction → LLM (summarize / navigate)
                       → liblouis (braille dot patterns) + Piper TTS (audio)
                       → Braille Display (4-cell scroll) + Speaker

Hardware stubs are clearly marked. Replace with real GPIO code on RPi.
Config is loaded from config.json (set ollama_host to 127.0.0.1 on RPi).
"""

import os
import sys
import json
import time
import wave
import tempfile
import difflib
import threading
import struct
import requests
import numpy as np
import soundfile as sf
import fitz                          # PyMuPDF
import louis                         # liblouis
import whisper
from PIL import Image
import pytesseract
from piper.voice import PiperVoice

# ── CONFIG ─────────────────────────────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    "ollama_host": "127.0.0.1",      # Change to 127.0.0.1 on RPi (Ollama runs locally)
    "ollama_port": 11434,
    "ollama_model": "gemma2:2b",
    "piper_model": "/root/piper-models/en_US-lessac-medium.onnx",
    "docs_dir": "/media/sdcard/docs", # SD card mount point on RPi
    "braille_table": "en-ueb-g2.ctb",
    "braille_cells": 4,               # Physical display cell count
    "whisper_model": "tiny",
    "wake_word": "hey netra",
    "audio_sample_rate": 16000,
    "record_seconds": 5               # Duration to record after wake word
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
        # Merge with defaults so missing keys always have a value
        return {**DEFAULT_CONFIG, **cfg}
    else:
        # Write defaults on first run
        with open(CONFIG_PATH, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        print(f"[NETRA] config.json created at {CONFIG_PATH}. Edit ollama_host if needed.")
        return DEFAULT_CONFIG.copy()

CFG = load_config()
OLLAMA_URL = f"http://{CFG['ollama_host']}:{CFG['ollama_port']}/api/generate"


# ══════════════════════════════════════════════════════════════════════════════
# HARDWARE ABSTRACTION LAYER
# All functions in this section are STUBS for Docker/dev testing.
# Replace each stub body with real GPIO / camera code on RPi.
# ══════════════════════════════════════════════════════════════════════════════

def hw_read_mode_button():
    """
    STUB — Returns 'pdf' or 'camera' based on which button is pressed.
    RPi: Read two GPIO input pins (one per button). Return whichever fires first.
    """
    choice = input("\n[HW STUB] Press button — type 'pdf' or 'camera': ").strip().lower()
    return choice if choice in ("pdf", "camera") else "pdf"


def hw_read_scroll_button():
    """
    STUB — Blocks until the scroll/next button is pressed.
    RPi: Block on GPIO.wait_for_edge(SCROLL_PIN, GPIO.RISING)
    """
    input("[HW STUB] Press ENTER to scroll to next braille chunk...")


def hw_read_summarize_button():
    """
    STUB — Non-blocking check if summarize button is pressed.
    RPi: Return GPIO.input(SUMMARIZE_PIN) == GPIO.HIGH
    """
    val = input("[HW STUB] Summarize button pressed? (y/n): ").strip().lower()
    return val == "y"


def hw_capture_image():
    """
    STUB — Captures an image from the camera and returns a PIL Image.
    RPi: Use picamera2 library:
         from picamera2 import Picamera2
         cam = Picamera2()
         cam.start()
         frame = cam.capture_array()
         cam.stop()
         return Image.fromarray(frame)
    """
    path = input("[HW STUB] Enter path to test image file: ").strip()
    return Image.open(path)


def hw_display_braille_cells(dot_patterns):
    """
    STUB — Sends 4 bytes (one per cell) to solenoid driver.
    dot_patterns: list of up to 4 integers (8-bit, one per braille cell)
                  bit0=dot1 ... bit5=dot6 (standard 6-dot UEB)

    RPi (Arduino/STM32 as GPIO buffer via UART):
         import serial
         ser = serial.Serial('/dev/ttyUSB0', 9600)
         ser.write(bytes(dot_patterns))

    RPi (direct GPIO solenoids — 4 cells × 6 dots = 24 pins):
         for cell_idx, pattern in enumerate(dot_patterns):
             for dot in range(6):
                 pin = CELL_PIN_MAP[cell_idx][dot]
                 GPIO.output(pin, bool(pattern & (1 << dot)))
    """
    cell_str = ""
    for i, pat in enumerate(dot_patterns):
        dots = [d+1 for d in range(6) if pat & (1 << d)]
        cell_str += f"  Cell{i+1}:{dots}"
    print(f"[HW STUB] Braille display:{cell_str}")


def hw_record_audio(seconds):
    """
    STUB — Records audio from microphone and returns numpy float32 array at 16kHz.
    RPi: Use sounddevice or pyaudio:
         import sounddevice as sd
         audio = sd.rec(int(seconds * 16000), samplerate=16000,
                        channels=1, dtype='float32')
         sd.wait()
         return audio.flatten()

    In Docker (no mic): reads from a .wav file path provided by user.
    """
    print(f"\n[HW STUB] Enter path to {seconds}s audio .wav file (or ENTER to type text): ", flush=True)
    path = input(">> ").strip()
    if path and os.path.exists(path):
        data, sr = sf.read(path, dtype="float32")
        if sr != CFG["audio_sample_rate"]:
            print(f"[WARN] Audio sample rate {sr} != {CFG['audio_sample_rate']}. Results may vary.")
        return data
    return None  # Signals to use text input fallback


def hw_play_audio(wav_path):
    """
    STUB — Plays a .wav file through the speaker.
    RPi: Use aplay (subprocess) or pygame:
         import subprocess
         subprocess.run(["aplay", wav_path])
    """
    print(f"[HW STUB] Playing audio: {wav_path}")
    # On RPi uncomment:
    # import subprocess
    # subprocess.run(["aplay", wav_path])


# ══════════════════════════════════════════════════════════════════════════════
# MODEL LOADING
# ══════════════════════════════════════════════════════════════════════════════

print("[NETRA] Loading models...")

print("  → Whisper tiny...")
_whisper_model = whisper.load_model(CFG["whisper_model"])

print("  → Piper TTS...")
_piper_voice = PiperVoice.load(CFG["piper_model"])

print("  → Checking Ollama connection...")
try:
    r = requests.get(f"http://{CFG['ollama_host']}:{CFG['ollama_port']}/api/tags", timeout=5)
    models = [m["name"] for m in r.json().get("models", [])]
    if CFG["ollama_model"] not in models:
        print(f"  [WARN] Model '{CFG['ollama_model']}' not found in Ollama. Available: {models}")
    else:
        print(f"  → Ollama OK ({CFG['ollama_model']})")
except Exception as e:
    print(f"  [WARN] Ollama not reachable: {e}. LLM features will be disabled.")

print("[NETRA] All models loaded.\n")


# ══════════════════════════════════════════════════════════════════════════════
# TTS
# ══════════════════════════════════════════════════════════════════════════════

def speak(text):
    """Synthesize text to speech and play it."""
    print(f"[TTS] {text}")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name

    with wave.open(wav_path, "w") as wav_file:
        _piper_voice.synthesize_wav(text, wav_file)

    hw_play_audio(wav_path)
    os.unlink(wav_path)


# ══════════════════════════════════════════════════════════════════════════════
# STT / WAKE WORD
# ══════════════════════════════════════════════════════════════════════════════

def transcribe(audio_array):
    """Transcribe numpy audio array to text using Whisper."""
    if audio_array is None:
        # Docker fallback: type text directly
        return input("[STT FALLBACK] Type spoken input: ").strip().lower()
    result = _whisper_model.transcribe(audio_array, language="en", fp16=False)
    return result["text"].strip().lower()


def wait_for_wake_word():
    """
    Continuously listen for wake word. Returns when detected.
    In Docker: just press ENTER to simulate wake word.
    """
    print(f"[NETRA] Listening for wake word: '{CFG['wake_word']}'...")
    while True:
        audio = hw_record_audio(3)
        if audio is None:
            # Docker stub — ENTER simulates wake word
            input("[HW STUB] Press ENTER to simulate wake word detection...")
            return
        transcript = transcribe(audio)
        print(f"[STT] Heard: {transcript!r}")
        if CFG["wake_word"] in transcript:
            print("[NETRA] Wake word detected.")
            return


def listen_for_command():
    """Record and transcribe a user command."""
    speak("Listening.")
    audio = hw_record_audio(CFG["record_seconds"])
    cmd = transcribe(audio)
    # If empty, re-prompt explicitly
    while not cmd.strip():
        print("[STT] Got empty input. Please type your command:")
        cmd = input(">> ").strip().lower()
    return cmd


# ══════════════════════════════════════════════════════════════════════════════
# FILE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def scan_docs():
    """Scan docs directory. Returns list of filenames (PDF + images)."""
    supported = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff")
    docs_dir = CFG["docs_dir"]
    if not os.path.exists(docs_dir):
        print(f"[WARN] Docs directory not found: {docs_dir}. Using current directory.")
        docs_dir = os.getcwd()
    files = sorted([
        f for f in os.listdir(docs_dir)
        if f.lower().endswith(supported)
    ])
    return files, docs_dir


def fuzzy_match_filename(query, filenames):
    """
    Match a spoken filename query to the closest actual filename.
    Returns (matched_filename, confidence_score).
    """
    # Strip extensions for matching
    stems = [os.path.splitext(f)[0].lower().replace("_", " ").replace("-", " ")
             for f in filenames]
    matches = difflib.get_close_matches(query.lower(), stems, n=3, cutoff=0.3)
    if not matches:
        return None, 0.0
    best = matches[0]
    idx = stems.index(best)
    score = difflib.SequenceMatcher(None, query.lower(), best).ratio()
    return filenames[idx], score


def resolve_file_intent(command, filenames, current_idx):
    """
    Use LLM to parse navigation intent from a voice command.
    Returns (action, value) where action is one of:
      'open_index'  → value = int index
      'open_name'   → value = str filename
      'next'        → value = None
      'previous'    → value = None
      'unknown'     → value = None
    """
    file_list_str = "\n".join([f"{i+1}. {f}" for i, f in enumerate(filenames)])
    prompt = f"""You are a file navigation assistant for a braille reader device.
Available files:
{file_list_str}

Current file index (1-based): {current_idx + 1}
User command: "{command}"

Reply with ONLY a JSON object, no explanation:
- To open by index: {{"action": "open_index", "value": <number>}}
- To open by name: {{"action": "open_name", "value": "<filename>"}}
- To go to next file: {{"action": "next"}}
- To go to previous file: {{"action": "previous"}}
- If unclear: {{"action": "unknown"}}"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": CFG["ollama_model"],
            "prompt": prompt,
            "stream": False
        }, timeout=30)
        raw = resp.json()["response"].strip()
        # Strip markdown fences if present
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[LLM] Navigation parse failed: {e}")
        return {"action": "unknown"}


# ══════════════════════════════════════════════════════════════════════════════
# TEXT EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_pdf(filepath):
    """Extract text from a PDF file using PyMuPDF."""
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text.strip()


def extract_text_image(image):
    """Extract text from a PIL Image using Tesseract OCR."""
    return pytesseract.image_to_string(image).strip()


# ══════════════════════════════════════════════════════════════════════════════
# LLM — SUMMARIZATION
# ══════════════════════════════════════════════════════════════════════════════

def summarize_text(text):
    """Summarize document text using Ollama LLM."""
    # Truncate to avoid exceeding context window (~6000 chars safe for gemma2:2b)
    if len(text) > 6000:
        text = text[:6000] + "..."

    prompt = f"""Summarize the following document in 3-4 sentences. 
Be concise. The summary will be read aloud to a visually impaired user.

Document:
{text}

Summary:"""

    try:
        speak("Summarizing. Please wait.")
        resp = requests.post(OLLAMA_URL, json={
            "model": CFG["ollama_model"],
            "prompt": prompt,
            "stream": False
        }, timeout=60)
        return resp.json()["response"].strip()
    except Exception as e:
        print(f"[LLM] Summarization failed: {e}")
        return "Summarization unavailable."


# ══════════════════════════════════════════════════════════════════════════════
# BRAILLE DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def text_to_dot_patterns(text):
    """Convert text to list of 8-bit dot pattern integers via liblouis UEB G2."""
    contracted = louis.translateString([CFG["braille_table"]], text)
    patterns = []
    for char in contracted:
        dots_char = louis.charToDots([CFG["braille_table"]], char, mode=louis.dotsIO)
        patterns.append(ord(dots_char) & 0xFF)
    return contracted, patterns


def display_and_read(text):
    """
    Main reading loop:
    - Converts text to braille dot patterns
    - Plays TTS audio
    - Displays braille in 4-cell chunks
    - Waits for scroll button between chunks
    - Checks for summarize button press during reading
    """
    if not text:
        speak("No text found in document.")
        return

    contracted, dot_patterns = text_to_dot_patterns(text)
    cell_size = CFG["braille_cells"]
    chunks = [dot_patterns[i:i+cell_size] for i in range(0, len(dot_patterns), cell_size)]
    total = len(chunks)

    print(f"[NETRA] {len(dot_patterns)} braille cells, {total} chunks of {cell_size}.")

    # Start TTS in a background thread so braille + audio run simultaneously
    tts_thread = threading.Thread(target=speak, args=(text,), daemon=True)
    tts_thread.start()

    for idx, chunk in enumerate(chunks):
        # Pad last chunk with empty cells if needed
        padded = chunk + [0x00] * (cell_size - len(chunk))
        hw_display_braille_cells(padded)
        print(f"[BRAILLE] Chunk {idx+1}/{total}")

        if idx < total - 1:
            hw_read_scroll_button()
        else:
            speak("End of document.")

    tts_thread.join()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN STATE MACHINE
# ══════════════════════════════════════════════════════════════════════════════

def main():
    speak("NETRA is ready.")
    filenames, docs_dir = scan_docs()

    if not filenames:
        speak("No documents found in storage. Please add files and restart.")
        sys.exit(1)

    print(f"[NETRA] Found {len(filenames)} document(s) in {docs_dir}:")
    for i, f in enumerate(filenames):
        print(f"  {i+1}. {f}")

    current_idx = 0
    current_text = None

    while True:
        # ── Wait for wake word or button ──────────────────────────────────────
        wait_for_wake_word()
        speak("Ready. Press PDF or Camera button.")

        mode = hw_read_mode_button()

        # ── PDF MODE ──────────────────────────────────────────────────────────
        if mode == "pdf":
            speak(f"PDF mode. {len(filenames)} files available. Say a file name or number.")
            command = listen_for_command()
            print(f"[STT] Command: {command!r}")

            intent = resolve_file_intent(command, filenames, current_idx)
            action = intent.get("action", "unknown")

            if action == "open_index":
                idx = int(intent.get("value", 1)) - 1
                if 0 <= idx < len(filenames):
                    current_idx = idx
                else:
                    speak("File number out of range.")
                    continue

            elif action == "open_name":
                name_query = intent.get("value", "")
                matched, score = fuzzy_match_filename(name_query, filenames)
                if matched:
                    speak(f"Opening {os.path.splitext(matched)[0]}.")
                    current_idx = filenames.index(matched)
                else:
                    speak("File not found.")
                    continue

            elif action == "next":
                if current_idx < len(filenames) - 1:
                    current_idx += 1
                else:
                    speak("Already at last file.")
                    continue

            elif action == "previous":
                if current_idx > 0:
                    current_idx -= 1
                else:
                    speak("Already at first file.")
                    continue

            else:
                speak("Command not understood. Please try again.")
                continue

            filepath = os.path.join(docs_dir, filenames[current_idx])
            speak(f"Loading {os.path.splitext(filenames[current_idx])[0]}.")
            current_text = extract_text_pdf(filepath)
            print(f"[PDF] Extracted {len(current_text)} characters.")

        # ── CAMERA MODE ───────────────────────────────────────────────────────
        elif mode == "camera":
            speak("Camera mode. Point camera at text and press the capture button.")
            hw_read_scroll_button()  # reuse scroll button as capture trigger
            speak("Capturing.")
            image = hw_capture_image()
            speak("Running OCR. Please wait.")
            current_text = extract_text_image(image)
            print(f"[OCR] Extracted {len(current_text)} characters.")

            if not current_text:
                speak("No text detected. Please try again.")
                continue

        # ── SUMMARIZE CHECK ───────────────────────────────────────────────────
        if current_text:
            speak("Document loaded. Press summarize button or say hey NETRA to summarize. Press scroll to read.")

            if hw_read_summarize_button():
                summary = summarize_text(current_text)
                print(f"[LLM] Summary: {summary}")
                display_and_read(summary)
            else:
                # Check voice summarize command
                wait_for_wake_word()
                command = listen_for_command()
                if "summar" in command:
                    summary = summarize_text(current_text)
                    display_and_read(summary)
                else:
                    # Read full document
                    display_and_read(current_text)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[NETRA] Shutting down.")
        sys.exit(0)