#!/usr/bin/env python3
"""
NETRA Hardware Test Script for Raspberry Pi 4B
Tests all hardware components individually.
"""

import sys
import time
from pathlib import Path

print("=" * 60)
print("NETRA Hardware Test Suite")
print("Raspberry Pi 4B")
print("=" * 60)
print()

# Track test results
results = {}

# ==============================================================================
# Test 1: GPIO / RPi.GPIO
# ==============================================================================
print("[1/7] Testing GPIO...")
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    # Test LED on GPIO 18
    GPIO.setup(18, GPIO.OUT)
    print("  - GPIO initialized successfully")
    print("  - Blinking LED on GPIO 18...")
    for _ in range(3):
        GPIO.output(18, GPIO.HIGH)
        time.sleep(0.3)
        GPIO.output(18, GPIO.LOW)
        time.sleep(0.3)
    print("  ✓ LED test passed (did you see it blink?)")
    
    # Test button on GPIO 17
    GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print("  - Button configured on GPIO 17 (pull-up)")
    print("  - Press the button within 5 seconds...")
    
    button_pressed = False
    start = time.time()
    while time.time() - start < 5:
        if GPIO.input(17) == GPIO.LOW:
            button_pressed = True
            print("  ✓ Button press detected!")
            break
        time.sleep(0.1)
    
    if not button_pressed:
        print("  ⚠ No button press detected (timeout)")
    
    results['GPIO'] = True
    GPIO.cleanup()
    
except ImportError:
    print("  ✗ RPi.GPIO not installed")
    print("    Run: pip install RPi.GPIO")
    results['GPIO'] = False
except Exception as e:
    print(f"  ✗ GPIO test failed: {e}")
    results['GPIO'] = False

print()

# ==============================================================================
# Test 2: Audio Recording (Microphone)
# ==============================================================================
print("[2/7] Testing Microphone...")
try:
    import sounddevice as sd
    import numpy as np
    import soundfile as sf
    
    # List audio devices
    print("  Available input devices:")
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            print(f"    [{i}] {d['name']} ({d['max_input_channels']} ch)")
    
    # Try recording
    print("  - Recording 3 seconds... Speak now!")
    recording = sd.rec(
        int(3 * 16000),
        samplerate=16000,
        channels=1,
        dtype='float32',
        device=None  # Default device
    )
    sd.wait()
    
    # Check audio level
    max_amp = np.max(np.abs(recording))
    print(f"  - Max amplitude: {max_amp:.4f}")
    
    if max_amp > 0.01:
        print("  ✓ Microphone test passed (audio detected)")
        results['Microphone'] = True
    else:
        print("  ⚠ Very low audio level - check microphone")
        results['Microphone'] = False
    
    # Save test recording
    sf.write('/tmp/netra_mic_test.wav', recording, 16000)
    print("  - Test recording saved to /tmp/netra_mic_test.wav")
    
except ImportError as e:
    print(f"  ✗ Audio library not installed: {e}")
    results['Microphone'] = False
except Exception as e:
    print(f"  ✗ Microphone test failed: {e}")
    results['Microphone'] = False

print()

# ==============================================================================
# Test 3: Audio Playback (Speaker)
# ==============================================================================
print("[3/7] Testing Speaker...")
try:
    import subprocess
    
    # Generate test tone
    print("  - Generating test tone...")
    import numpy as np
    import soundfile as sf
    
    duration = 1.0
    freq = 440  # A4 note
    sample_rate = 16000
    t = np.linspace(0, duration, int(sample_rate * duration))
    tone = 0.3 * np.sin(2 * np.pi * freq * t)
    sf.write('/tmp/netra_speaker_test.wav', tone.astype(np.float32), sample_rate)
    
    print("  - Playing test tone (you should hear a beep)...")
    result = subprocess.run(
        ['aplay', '-q', '/tmp/netra_speaker_test.wav'],
        capture_output=True,
        timeout=10
    )
    
    if result.returncode == 0:
        print("  ✓ Speaker test completed (did you hear the tone?)")
        results['Speaker'] = True
    else:
        print(f"  ⚠ aplay returned error: {result.stderr.decode()}")
        results['Speaker'] = False
        
except Exception as e:
    print(f"  ✗ Speaker test failed: {e}")
    results['Speaker'] = False

print()

# ==============================================================================
# Test 4: Camera
# ==============================================================================
print("[4/7] Testing Camera...")
try:
    import subprocess
    
    # Try libcamera-still first (Pi Camera)
    print("  - Trying Pi Camera (libcamera)...")
    result = subprocess.run(
        ['libcamera-still', '-o', '/tmp/netra_camera_test.jpg', '-t', '1000', '-n'],
        capture_output=True,
        timeout=15
    )
    
    if result.returncode == 0 and Path('/tmp/netra_camera_test.jpg').exists():
        print("  ✓ Pi Camera test passed")
        print("  - Image saved to /tmp/netra_camera_test.jpg")
        results['Camera'] = True
    else:
        # Try fswebcam (USB webcam)
        print("  - Pi Camera failed, trying USB webcam (fswebcam)...")
        result = subprocess.run(
            ['fswebcam', '-r', '640x480', '--no-banner', '/tmp/netra_camera_test.jpg'],
            capture_output=True,
            timeout=15
        )
        
        if result.returncode == 0 and Path('/tmp/netra_camera_test.jpg').exists():
            print("  ✓ USB Webcam test passed")
            print("  - Image saved to /tmp/netra_camera_test.jpg")
            results['Camera'] = True
        else:
            print("  ✗ No camera detected")
            results['Camera'] = False
            
except FileNotFoundError:
    print("  ✗ Camera tools not installed (libcamera-still, fswebcam)")
    results['Camera'] = False
except Exception as e:
    print(f"  ✗ Camera test failed: {e}")
    results['Camera'] = False

print()

# ==============================================================================
# Test 5: Servo Motors
# ==============================================================================
print("[5/7] Testing Servo Motors...")
try:
    import RPi.GPIO as GPIO
    
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    
    servo_pins = [12, 13, 19, 26]
    
    for i, pin in enumerate(servo_pins):
        print(f"  - Testing Servo {i+1} on GPIO {pin}...")
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, 50)  # 50Hz for servo
        pwm.start(0)
        
        # Sweep from 0 to 180 degrees
        for duty in [2.5, 7.5, 12.5]:  # 0°, 90°, 180°
            pwm.ChangeDutyCycle(duty)
            time.sleep(0.3)
        
        pwm.ChangeDutyCycle(7.5)  # Return to center
        time.sleep(0.2)
        pwm.stop()
    
    print("  ✓ Servo test completed (did all servos move?)")
    results['Servos'] = True
    GPIO.cleanup()
    
except ImportError:
    print("  ✗ RPi.GPIO not available")
    results['Servos'] = False
except Exception as e:
    print(f"  ✗ Servo test failed: {e}")
    results['Servos'] = False

print()

# ==============================================================================
# Test 6: Vosk STT
# ==============================================================================
print("[6/7] Testing Vosk STT...")
try:
    from vosk import Model, KaldiRecognizer
    import json
    
    model_path = Path("models/vosk-model-small-en-us-0.15")
    if not model_path.exists():
        model_path = Path.home() / "NETRA" / "models" / "vosk-model-small-en-us-0.15"
    
    if model_path.exists():
        print(f"  - Loading Vosk model from {model_path}...")
        model = Model(str(model_path))
        print("  ✓ Vosk model loaded successfully")
        results['Vosk'] = True
    else:
        print(f"  ✗ Vosk model not found at {model_path}")
        print("    Download with: wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip")
        results['Vosk'] = False
        
except ImportError:
    print("  ✗ Vosk not installed")
    print("    Run: pip install vosk")
    results['Vosk'] = False
except Exception as e:
    print(f"  ✗ Vosk test failed: {e}")
    results['Vosk'] = False

print()

# ==============================================================================
# Test 7: LLM (llama.cpp)
# ==============================================================================
print("[7/7] Testing LLM (llama.cpp)...")
try:
    model_path = Path("models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
    if not model_path.exists():
        model_path = Path.home() / "NETRA" / "models" / "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
    
    if model_path.exists():
        print(f"  - Model file found: {model_path}")
        print(f"  - Size: {model_path.stat().st_size / 1024 / 1024:.1f} MB")
        
        from llama_cpp import Llama
        print("  - Loading model (this may take a few seconds)...")
        llm = Llama(
            model_path=str(model_path),
            n_ctx=512,
            n_threads=4,
            verbose=False
        )
        print("  ✓ LLM model loaded successfully")
        
        # Quick inference test
        print("  - Testing inference...")
        response = llm("Hello, I am NETRA.", max_tokens=20)
        print(f"  - Response: {response['choices'][0]['text'][:50]}...")
        results['LLM'] = True
        
    else:
        print(f"  ✗ LLM model not found at {model_path}")
        print("    Download with: wget https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
        results['LLM'] = False
        
except ImportError:
    print("  ✗ llama-cpp-python not installed")
    print("    Run: pip install llama-cpp-python")
    results['LLM'] = False
except Exception as e:
    print(f"  ✗ LLM test failed: {e}")
    results['LLM'] = False

print()

# ==============================================================================
# Summary
# ==============================================================================
print("=" * 60)
print("TEST SUMMARY")
print("=" * 60)

passed = 0
failed = 0

for component, status in results.items():
    symbol = "✓" if status else "✗"
    status_text = "PASSED" if status else "FAILED"
    print(f"  {symbol} {component}: {status_text}")
    if status:
        passed += 1
    else:
        failed += 1

print()
print(f"Results: {passed} passed, {failed} failed")
print()

if failed == 0:
    print("🎉 All tests passed! NETRA is ready to run.")
    print("   Start with: python netra.py")
else:
    print("⚠ Some tests failed. Please check the components above.")
    print("   Refer to docs/RASPBERRY_PI_WIRING.md for troubleshooting.")

print()
