#!/usr/bin/env python3
"""
Continuous audio recording and playback test script.
Records 5 seconds of audio and plays it back in a loop until Ctrl+C.
"""

import subprocess
import time
import os
import signal
import sys

# Audio configuration (matching your successful test)
DEVICE = "3"
CHANNELS = "1"
RATE = "16000"
FORMAT = "s16le"
DURATION = 5  # seconds
TEMP_FILE = "test_recording.wav"

# Flag for graceful shutdown
running = True

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully."""
    global running
    print("\n\n🛑 Stopping audio test...")
    running = False

def record_audio(duration=5):
    """Record audio for specified duration."""
    print(f"🎤 Recording for {duration} seconds...")
    
    # Use parecord to capture audio
    cmd = [
        "parecord",
        f"--device={DEVICE}",
        f"--channels={CHANNELS}",
        f"--rate={RATE}",
        f"--format={FORMAT}",
        TEMP_FILE
    ]
    
    try:
        # Start recording process
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait for specified duration
        time.sleep(duration)
        
        # Stop recording
        proc.terminate()
        proc.wait(timeout=2)
        
        print("✅ Recording complete")
        return True
        
    except subprocess.TimeoutExpired:
        proc.kill()
        print("⚠️  Recording process killed (timeout)")
        return False
    except Exception as e:
        print(f"❌ Recording error: {e}")
        return False

def play_audio():
    """Play back the recorded audio."""
    if not os.path.exists(TEMP_FILE):
        print("❌ No recording file found!")
        return False
    
    print("🔊 Playing back audio...")
    
    # Use paplay to play audio
    cmd = ["paplay", TEMP_FILE]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Playback complete")
            return True
        else:
            print(f"⚠️  Playback returned code {result.returncode}")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Playback timeout")
        return False
    except Exception as e:
        print(f"❌ Playback error: {e}")
        return False

def cleanup():
    """Remove temporary files."""
    if os.path.exists(TEMP_FILE):
        try:
            os.remove(TEMP_FILE)
            print(f"🧹 Cleaned up {TEMP_FILE}")
        except Exception as e:
            print(f"⚠️  Could not remove temp file: {e}")

def main():
    """Main test loop."""
    global running
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    print("=" * 60)
    print("🎧 AUDIO DEVICE TEST - Record & Playback Loop")
    print("=" * 60)
    print(f"Device: {DEVICE}")
    print(f"Channels: {CHANNELS}")
    print(f"Sample Rate: {RATE} Hz")
    print(f"Format: {FORMAT}")
    print(f"Duration: {DURATION} seconds")
    print("=" * 60)
    print("\nPress Ctrl+C to stop\n")
    
    cycle = 0
    
    try:
        while running:
            cycle += 1
            print(f"\n{'='*60}")
            print(f"Cycle #{cycle}")
            print(f"{'='*60}")
            
            # Record audio
            if not record_audio(DURATION):
                print("⚠️  Recording failed, retrying in 2 seconds...")
                time.sleep(2)
                continue
            
            # Small delay between record and playback
            time.sleep(0.5)
            
            # Play back audio
            if not play_audio():
                print("⚠️  Playback failed, continuing anyway...")
            
            # Small delay before next cycle
            if running:
                print("\n⏳ Waiting 1 second before next cycle...")
                time.sleep(1)
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    
    finally:
        # Cleanup
        print("\n" + "=" * 60)
        print(f"📊 Test completed: {cycle} cycle(s)")
        cleanup()
        print("=" * 60)
        print("Goodbye! 👋\n")

if __name__ == "__main__":
    main()
