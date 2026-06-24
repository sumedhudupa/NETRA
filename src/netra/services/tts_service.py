import os
import tempfile
import wave
import logging
import threading
import queue
import struct
from typing import Optional, Callable

from piper.voice import PiperVoice

from netra.hardware.interfaces import HardwareAdapter

# Optional: sounddevice for in-memory audio streaming (avoids disk I/O + subprocess)
try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except (ImportError, OSError):
    sd = None
    _SD_AVAILABLE = False


class AudioStreamPlayer:
    """
    In-memory PCM audio player using sounddevice.

    Accepts raw int16 PCM bytes and plays them through the system default
    audio output (which is the BT speaker if already connected via PulseAudio).

    Usage::

        player = AudioStreamPlayer(sample_rate=22050)
        player.start()
        player.enqueue(pcm_bytes_sentence_1)
        player.enqueue(pcm_bytes_sentence_2)
        player.drain()   # blocks until all audio finishes playing
        player.close()
    """

    def __init__(self, sample_rate: int = 22050, channels: int = 1, block_size: int = 1024) -> None:
        self.logger = logging.getLogger(__name__)
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=200)
        self._stream = None
        self._leftover = b""
        self._finished = threading.Event()

    def start(self) -> None:
        """Open the audio output stream."""
        if not _SD_AVAILABLE:
            self.logger.warning("sounddevice not available; AudioStreamPlayer will not produce audio")
            return

        bytes_per_frame = 2 * self.channels  # int16
        self._stream = sd.RawOutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.block_size,
            callback=self._audio_callback,
            finished_callback=self._on_stream_finished,
        )
        self._stream.start()
        self.logger.debug("AudioStreamPlayer started (rate=%d)", self.sample_rate)

    def _audio_callback(self, outdata, frames, time_info, status):
        """
        sounddevice callback – fills the output buffer from the queue.
        Runs in a separate audio thread.
        """
        if status:
            self.logger.debug("Audio stream status: %s", status)

        bytes_needed = frames * 2 * self.channels  # int16 = 2 bytes per sample
        data = self._leftover

        while len(data) < bytes_needed:
            try:
                chunk = self._queue.get_nowait()
            except queue.Empty:
                break
            if chunk is None:
                # Sentinel: no more data coming.  Pad with silence and signal done.
                data += b"\x00" * (bytes_needed - len(data))
                outdata[:] = data[:bytes_needed]
                self._leftover = b""
                raise sd.CallbackStop
            data += chunk

        if len(data) >= bytes_needed:
            outdata[:] = data[:bytes_needed]
            self._leftover = data[bytes_needed:]
        else:
            # Underrun – fill what we have, pad the rest with silence
            outdata[:len(data)] = data
            outdata[len(data):] = b"\x00" * (bytes_needed - len(data))
            self._leftover = b""

    def _on_stream_finished(self):
        """Called by sounddevice when the stream stops."""
        self._finished.set()

    def enqueue(self, pcm_bytes: bytes) -> None:
        """Add raw PCM bytes to the playback queue."""
        if not self._stream:
            return
        # Break large buffers into manageable chunks for responsive callback
        chunk_size = self.block_size * 2 * self.channels
        for i in range(0, len(pcm_bytes), chunk_size):
            self._queue.put(pcm_bytes[i:i + chunk_size])

    def drain(self) -> None:
        """Block until all enqueued audio has been played."""
        if not self._stream:
            return
        self._queue.put(None)  # Sentinel
        self._finished.wait(timeout=120)

    def close(self) -> None:
        """Stop and close the audio stream."""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

# Optional: sounddevice for in-memory audio streaming (avoids disk I/O + subprocess)
try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except (ImportError, OSError):
    sd = None
    _SD_AVAILABLE = False


class AudioStreamPlayer:
    """
    In-memory PCM audio player using sounddevice.

    Accepts raw int16 PCM bytes and plays them through the system default
    audio output (which is the BT speaker if already connected via PulseAudio).

    Usage::

        player = AudioStreamPlayer(sample_rate=22050)
        player.start()
        player.enqueue(pcm_bytes_sentence_1)
        player.enqueue(pcm_bytes_sentence_2)
        player.drain()   # blocks until all audio finishes playing
        player.close()
    """

    def __init__(self, sample_rate: int = 22050, channels: int = 1, block_size: int = 1024) -> None:
        self.logger = logging.getLogger(__name__)
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_size = block_size
        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=200)
        self._stream = None
        self._leftover = b""
        self._finished = threading.Event()

    def start(self) -> None:
        """Open the audio output stream."""
        if not _SD_AVAILABLE:
            self.logger.warning("sounddevice not available; AudioStreamPlayer will not produce audio")
            return

        bytes_per_frame = 2 * self.channels  # int16
        self._stream = sd.RawOutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.block_size,
            callback=self._audio_callback,
            finished_callback=self._on_stream_finished,
        )
        self._stream.start()
        self.logger.debug("AudioStreamPlayer started (rate=%d)", self.sample_rate)

    def _audio_callback(self, outdata, frames, time_info, status):
        """
        sounddevice callback – fills the output buffer from the queue.
        Runs in a separate audio thread.
        """
        if status:
            self.logger.debug("Audio stream status: %s", status)

        bytes_needed = frames * 2 * self.channels  # int16 = 2 bytes per sample
        data = self._leftover

        while len(data) < bytes_needed:
            try:
                chunk = self._queue.get_nowait()
            except queue.Empty:
                break
            if chunk is None:
                # Sentinel: no more data coming.  Pad with silence and signal done.
                data += b"\x00" * (bytes_needed - len(data))
                outdata[:] = data[:bytes_needed]
                self._leftover = b""
                raise sd.CallbackStop
            data += chunk

        if len(data) >= bytes_needed:
            outdata[:] = data[:bytes_needed]
            self._leftover = data[bytes_needed:]
        else:
            # Underrun – fill what we have, pad the rest with silence
            outdata[:len(data)] = data
            outdata[len(data):] = b"\x00" * (bytes_needed - len(data))
            self._leftover = b""

    def _on_stream_finished(self):
        """Called by sounddevice when the stream stops."""
        self._finished.set()

    def enqueue(self, pcm_bytes: bytes) -> None:
        """Add raw PCM bytes to the playback queue."""
        if not self._stream:
            return
        # Break large buffers into manageable chunks for responsive callback
        chunk_size = self.block_size * 2 * self.channels
        for i in range(0, len(pcm_bytes), chunk_size):
            self._queue.put(pcm_bytes[i:i + chunk_size])

    def drain(self) -> None:
        """Block until all enqueued audio has been played."""
        if not self._stream:
            return
        self._queue.put(None)  # Sentinel
        self._finished.wait(timeout=120)

    def close(self) -> None:
        """Stop and close the audio stream."""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class TTSService:
    PLAYBACK_LEADIN_MS = 250

    def __init__(self, model_path: str) -> None:
        self.logger = logging.getLogger(__name__)
        self.voice = None
        self._sample_rate = 22050  # Piper default sample rate
        self._sample_rate = 22050  # Piper default sample rate
        try:
            self.voice = PiperVoice.load(model_path)
            self.logger.info("Piper model loaded: %s", model_path)
            # Try to read the actual sample rate from the loaded voice
            if hasattr(self.voice, 'config') and hasattr(self.voice.config, 'sample_rate'):
                self._sample_rate = self.voice.config.sample_rate
            # Try to read the actual sample rate from the loaded voice
            if hasattr(self.voice, 'config') and hasattr(self.voice.config, 'sample_rate'):
                self._sample_rate = self.voice.config.sample_rate
        except Exception as exc:
            self.logger.warning("Piper model not available (%s): %s", model_path, exc)

    def speak(self, text: str, hardware: HardwareAdapter) -> None:
        self.logger.info("TTS speak request length=%d", len(text))
        print(f"[TTS] {text}")
        if self.voice is None:
            self.logger.info("TTS audio skipped because Piper model is unavailable")
            return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            wav_path = handle.name

        try:
            with wave.open(wav_path, "w") as wav_file:
                self.voice.synthesize_wav(text, wav_file)
            self.logger.info("Synthesized wav at %s", wav_path)
            self._prepend_silence(wav_path, self.PLAYBACK_LEADIN_MS)
            self.logger.info("Prepended %d ms silence to wav", self.PLAYBACK_LEADIN_MS)
            hardware.play_wav(wav_path)
        finally:
            if os.path.exists(wav_path):
                os.unlink(wav_path)
                self.logger.debug("Deleted temporary wav file %s", wav_path)

    def speak_streaming(
        self, 
        sentence_iterator, 
        hardware: HardwareAdapter,
        on_sentence: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Stream sentences to audio as they arrive from the LLM.

        Runs the *sentence_iterator* (LLM) in a **background thread** so that
        token generation continues while the main thread synthesizes audio.
        Three stages overlap concurrently:

        - **Thread 1 (background):** LLM generates tokens → yields sentences
        - **Main thread:** TTS synthesizes each sentence → enqueues PCM
        - **Audio thread (sounddevice):** Plays PCM from the queue

        If ``sounddevice`` is not available, falls back to collecting all
        sentences and using the regular ``speak()`` method.

        Args:
            sentence_iterator: An iterable yielding sentence strings.
            hardware: The hardware adapter (used only for fallback path).
            on_sentence: Optional callback fired when a sentence is about to play.

        Returns:
            The full concatenated text of all sentences (for braille/state).
        """
        sentences = []

        if not _SD_AVAILABLE or self.voice is None:
            # Fallback: collect everything and use synchronous speak()
            self.logger.info("Streaming TTS fallback: sounddevice=%s, voice=%s",
                             _SD_AVAILABLE, self.voice is not None)
            for sentence in sentence_iterator:
                sentences.append(sentence)
                if on_sentence:
                    on_sentence(sentence)
            full_text = " ".join(sentences)
            if full_text.strip():
                self.speak(full_text, hardware)
            return full_text

        # Queue to decouple LLM generation (background) from TTS synthesis (main)
        sentence_queue: queue.Queue[str | None] = queue.Queue(maxsize=20)
        llm_error = [None]  # mutable container for thread error

        def _llm_producer():
            """Run the LLM generator in a background thread."""
            try:
                for sentence in sentence_iterator:
                    sentence_queue.put(sentence)
                sentence_queue.put(None)  # Sentinel: generation complete
            except Exception as exc:
                llm_error[0] = exc
                sentence_queue.put(None)

        # Start LLM generation in background thread
        llm_thread = threading.Thread(target=_llm_producer, daemon=True)
        llm_thread.start()

        player = AudioStreamPlayer(sample_rate=self._sample_rate)
        player.start()

        try:
            while True:
                # Block until next sentence arrives (LLM thread is generating concurrently)
                sentence = sentence_queue.get(timeout=120)
                if sentence is None:
                    break  # LLM finished

                sentence = sentence.strip()
                if not sentence:
                    continue
                sentences.append(sentence)
                self.logger.info("TTS streaming sentence length=%d", len(sentence))
                print(f"[TTS STREAM] {sentence}")

                # Synthesize raw PCM audio for this sentence
                # While this runs, the LLM thread continues generating the next sentence
                pcm_bytes = self._synthesize_raw_pcm(sentence)
                if pcm_bytes:
                    if on_sentence:
                        on_sentence(sentence)
                    player.enqueue(pcm_bytes)

            player.drain()
        except Exception as exc:
            self.logger.error("Streaming TTS failed: %s", exc)
        finally:
            player.close()
            llm_thread.join(timeout=5)

        if llm_error[0]:
            self.logger.error("LLM producer thread error: %s", llm_error[0])

        return " ".join(sentences)

    def _synthesize_raw_pcm(self, text: str) -> bytes:
        """
        Synthesize text to raw int16 PCM bytes using Piper.

        Tries ``synthesize_stream_raw()`` first (yields raw PCM chunks),
        then falls back to ``synthesize_wav()`` into an in-memory buffer
        and extracts the raw frames — still zero disk I/O.
        """
        if self.voice is None:
            return b""

        try:
            # Preferred: synthesize_stream_raw yields raw int16 audio chunks
            if hasattr(self.voice, 'synthesize_stream_raw'):
                pcm_parts = []
                for audio_bytes in self.voice.synthesize_stream_raw(text):
                    if isinstance(audio_bytes, bytes):
                        pcm_parts.append(audio_bytes)
                    elif hasattr(audio_bytes, 'tobytes'):
                        # numpy array
                        pcm_parts.append(audio_bytes.tobytes())
                result = b"".join(pcm_parts)
                if result:
                    self.logger.debug("synthesize_stream_raw produced %d bytes", len(result))
                    return result
                self.logger.debug("synthesize_stream_raw returned empty, falling back to WAV method")

            # Fallback: use synthesize_wav() with in-memory buffer (proven API)
            import io
            mem_wav = io.BytesIO()
            with wave.open(mem_wav, "wb") as wf:
                self.voice.synthesize_wav(text, wf)
            mem_wav.seek(0)

            # Extract raw PCM frames from the in-memory WAV
            with wave.open(mem_wav, "rb") as wf:
                raw_frames = wf.readframes(wf.getnframes())
            self.logger.debug("WAV fallback produced %d PCM bytes", len(raw_frames))
            return raw_frames

        except Exception as exc:
            self.logger.error("Raw PCM synthesis failed for text (len=%d): %s", len(text), exc)
            return b""

    def _prepend_silence(self, wav_path: str, silence_ms: int) -> None:
        if silence_ms <= 0:
            return

        padded_path = f"{wav_path}.padded"

        try:
            with wave.open(wav_path, "rb") as source_wav:
                params = source_wav.getparams()
                frame_rate = source_wav.getframerate()
                channels = source_wav.getnchannels()
                sample_width = source_wav.getsampwidth()

                silence_frames = max(1, int(frame_rate * silence_ms / 1000.0))
                silence_frame = b"\x00" * sample_width * channels

                with wave.open(padded_path, "wb") as padded_wav:
                    padded_wav.setparams(params)
                    for _ in range(silence_frames):
                        padded_wav.writeframesraw(silence_frame)

                    while True:
                        chunk = source_wav.readframes(4096)
                        if not chunk:
                            break
                        padded_wav.writeframesraw(chunk)

            os.replace(padded_path, wav_path)
        except Exception as exc:
            self.logger.warning("Failed to prepend silence to wav: %s", exc)
            if os.path.exists(padded_path):
                os.unlink(padded_path)
