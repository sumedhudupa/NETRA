import time
import logging
import sys
import os
import threading

# Insert the 'src' directory at the front of sys.path so it finds the 'netra' package 
# inside 'src' rather than the 'netra.py' file in the root directory.
sys.path.insert(0, os.path.abspath("src"))

# Configure logging to see the service output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from netra.services.llama_service import LlamaCppService
from netra.services.tts_service import TTSService
from netra.hardware.stub_adapter import StubHardwareAdapter

def measure_latency(func, *args, **kwargs):
    """Wrapper to measure execution time of a function."""
    start_time = time.perf_counter()
    result = func(*args, **kwargs)
    end_time = time.perf_counter()
    latency_ms = (end_time - start_time) * 1000
    return result, latency_ms

def test_pipeline_latency():
    print("=== NETRA Pipeline Latency Test ===")
    
    # 1. Initialize Components (Not measuring init time as it happens once)
    print("\n[1] Initializing components...")
    
    model_path = "models/Phi-3-mini-4k-instruct-q4.gguf" 
    piper_model_path = "models/en_US-lessac-medium.onnx"
    
    print("Loading LLM...")
    llama = LlamaCppService(model_path=model_path, n_threads=4, n_ctx=2048)
    
    print("Loading TTS...")
    tts = TTSService(model_path=piper_model_path)
    
    print("Initializing Stub Hardware Adapter...")
    hardware = StubHardwareAdapter()
    
    print(f"\n[1.5] Testing Model Load Time (Lazy Loading)")
    is_avail, load_latency = measure_latency(llama.is_available)
    print(f"Model Load Latency: {load_latency:.2f} ms")
    
    if not is_avail:
        print(f"Warning: LLM model not found at {model_path} or failed to load.")
    if not tts.voice:
        print(f"Warning: Piper TTS model not found at {piper_model_path} or failed to load.")
    
    test_prompt = "Explain why the sky is blue in three short sentences."
    
    # =========================================================================
    # [2] ORIGINAL (synchronous) pipeline
    # =========================================================================
    print(f"\n[2] Testing ORIGINAL (synchronous) LLM Latency for prompt: '{test_prompt}'")
    response_text, llm_latency = measure_latency(
        llama.generate, 
        prompt=test_prompt, 
        system="You are a helpful assistant.",
        max_tokens=100
    )
    print(f"\n--- LLM Result ---")
    print(f"Generated Text: {response_text}")
    print(f"LLM Latency: {llm_latency:.2f} ms")
    
    if not response_text or response_text == "Model not loaded" or response_text == "Generation error occurred":
        print("Skipping TTS test because LLM generation failed.")
        sys.exit(1)
        
    print(f"\n[3] Testing ORIGINAL TTS & Playback Latency for generated text")
    _, tts_latency = measure_latency(
        tts.speak,
        text=response_text,
        hardware=hardware
    )
    
    print(f"\n--- ORIGINAL TTS & Playback Result ---")
    print(f"TTS + Playback Total Time (Sync): {tts_latency:.2f} ms")
    
    original_total = llm_latency + tts_latency
    # Time-to-First-Audio in original = full LLM + TTS synthesis (~4-5s) + overhead (~0.5s)
    # We approximate TTS synthesis as tts_latency minus audio duration
    # But since stub doesn't actually play, tts_latency ≈ synthesis + silence_prepend
    original_ttfa = llm_latency + tts_latency
    
    print(f"\n[4] ORIGINAL Summary")
    print(f"Time-to-First-Audio (LLM + TTS synthesis + playback): {original_ttfa:.2f} ms")
    print(f"  (User hears NOTHING for {original_ttfa/1000:.1f}s)")
    
    # =========================================================================
    # [5] STREAMING pipeline with detailed stage timestamps
    # =========================================================================
    print(f"\n{'='*60}")
    print(f"[5] Testing STREAMING Pipeline (with parallelism proof)")
    print(f"{'='*60}")
    print(f"\nPrompt: '{test_prompt}'")
    
    # --- Timing hooks ---
    pipeline_start = time.perf_counter()
    timeline_events = []  # List of (elapsed_ms, stage, description)
    first_audio_enqueued = [None]  # When first PCM bytes are sent to speaker
    
    def log_event(stage, desc):
        elapsed = (time.perf_counter() - pipeline_start) * 1000
        timeline_events.append((elapsed, stage, desc))
    
    # Override enqueue to capture Time-to-First-Audio
    original_enqueue = None
    
    import queue as queue_module
    
    # We'll manually orchestrate to capture precise timings
    sentence_queue = queue_module.Queue(maxsize=20)
    llm_error = [None]
    
    def llm_producer():
        """LLM generator running in background thread."""
        try:
            sent_idx = 0
            for sentence in llama.generate_streaming(
                prompt=test_prompt,
                system="You are a helpful assistant.",
                max_tokens=100
            ):
                sent_idx += 1
                log_event("LLM", f"Sentence {sent_idx} ready: \"{sentence[:60]}...\"")
                sentence_queue.put(sentence)
            sentence_queue.put(None)
        except Exception as exc:
            llm_error[0] = exc
            sentence_queue.put(None)
    
    log_event("START", "Pipeline begins")
    
    # Start LLM in background thread
    llm_thread = threading.Thread(target=llm_producer, daemon=True)
    llm_thread.start()
    log_event("LLM", "Background thread started (generating tokens...)")
    
    # Import AudioStreamPlayer to play audio
    from netra.services.tts_service import AudioStreamPlayer
    player = AudioStreamPlayer(sample_rate=tts._sample_rate)
    player.start()
    
    sentences = []
    sent_count = 0
    
    try:
        while True:
            sentence = sentence_queue.get(timeout=120)
            if sentence is None:
                log_event("LLM", "Generation complete (all tokens produced)")
                break
            
            sentence = sentence.strip()
            if not sentence:
                continue
            
            sent_count += 1
            sentences.append(sentence)
            log_event("TTS", f"Synthesizing sentence {sent_count} ({len(sentence)} chars)...")
            
            # Time the TTS synthesis
            synth_start = time.perf_counter()
            pcm_bytes = tts._synthesize_raw_pcm(sentence)
            synth_ms = (time.perf_counter() - synth_start) * 1000
            log_event("TTS", f"Synthesis done ({synth_ms:.0f} ms, {len(pcm_bytes)} bytes PCM)")
            
            if pcm_bytes:
                player.enqueue(pcm_bytes)
                if first_audio_enqueued[0] is None:
                    first_audio_enqueued[0] = (time.perf_counter() - pipeline_start) * 1000
                log_event("AUDIO", f"Sentence {sent_count} enqueued for playback")
        
        log_event("AUDIO", "Draining (waiting for remaining audio to finish)")
        player.drain()
        log_event("AUDIO", "Playback complete")
    except Exception as exc:
        log_event("ERROR", str(exc))
    finally:
        player.close()
        llm_thread.join(timeout=5)
    
    pipeline_total = (time.perf_counter() - pipeline_start) * 1000
    
    # =========================================================================
    # [6] Timeline visualization (proof of parallelism)
    # =========================================================================
    print(f"\n{'='*60}")
    print(f"[6] TIMELINE (stage-by-stage proof of parallelism)")
    print(f"{'='*60}")
    print(f"{'Elapsed':>10}  {'Stage':>6}  Description")
    print(f"{'─'*10}  {'─'*6}  {'─'*45}")
    for elapsed, stage, desc in timeline_events:
        print(f"{elapsed:>9.0f}ms  [{stage:>5}]  {desc}")
    
    # =========================================================================
    # [7] Comparison Summary
    # =========================================================================
    print(f"\n{'='*60}")
    print(f"[7] COMPARISON SUMMARY")
    print(f"{'='*60}")
    
    streaming_ttfa = first_audio_enqueued[0] if first_audio_enqueued[0] else pipeline_total
    
    print(f"")
    print(f"  ORIGINAL Pipeline (fully sequential):")
    print(f"    LLM Generation (all tokens):  {llm_latency:>10.0f} ms")
    print(f"    TTS Synthesis + Playback:      {tts_latency:>10.0f} ms")
    print(f"    Time-to-First-Audio:           {original_ttfa:>10.0f} ms")
    print(f"")
    print(f"  STREAMING Pipeline (threaded, overlapped):")
    print(f"    Time-to-First-Audio:           {streaming_ttfa:>10.0f} ms")
    print(f"    Full Pipeline Time:            {pipeline_total:>10.0f} ms")
    print(f"    Sentences streamed:            {sent_count:>10}")
    print(f"")
    
    improvement = original_ttfa - streaming_ttfa
    improvement_pct = (improvement / original_ttfa) * 100 if original_ttfa > 0 else 0
    print(f"  ✅ Time-to-First-Audio: {original_ttfa/1000:.1f}s → {streaming_ttfa/1000:.1f}s")
    print(f"     Improved by: {improvement:.0f} ms ({improvement_pct:.1f}%)")
    print(f"     User hears audio {improvement/1000:.1f}s earlier!")
    print(f"")
    
    total_improvement = original_total - pipeline_total
    total_pct = (total_improvement / original_total) * 100 if original_total > 0 else 0
    print(f"  ✅ Total Pipeline: {original_total/1000:.1f}s → {pipeline_total/1000:.1f}s")
    print(f"     Saved: {total_improvement:.0f} ms ({total_pct:.1f}%)")
    print(f"")
    
    # Parallelism proof
    print(f"  📊 Parallelism Evidence:")
    # Find LLM events and TTS events to check overlap
    llm_events = [(e, d) for e, s, d in timeline_events if s == "LLM" and "ready" in d.lower()]
    tts_events = [(e, d) for e, s, d in timeline_events if s == "TTS" and "Synthesizing" in d]
    
    if len(llm_events) >= 2 and len(tts_events) >= 1:
        llm_sent2_time = llm_events[1][0] if len(llm_events) > 1 else None
        tts_sent1_time = tts_events[0][0]
        tts_done_events = [(e, d) for e, s, d in timeline_events if s == "TTS" and "done" in d.lower()]
        tts_sent1_done = tts_done_events[0][0] if tts_done_events else None
        
        if llm_sent2_time and tts_sent1_done:
            if llm_sent2_time < tts_sent1_done:
                print(f"     LLM produced sentence 2 at {llm_sent2_time:.0f}ms")
                print(f"     TTS finished sentence 1 at {tts_sent1_done:.0f}ms")
                print(f"     → LLM was generating DURING TTS synthesis! ✅ Parallel!")
            elif llm_sent2_time < tts_sent1_done + 2000:
                print(f"     LLM produced sentence 2 at {llm_sent2_time:.0f}ms")
                print(f"     TTS finished sentence 1 at {tts_sent1_done:.0f}ms")
                print(f"     → Stages ran nearly overlapped (LLM slightly behind) ✅")
            else:
                print(f"     LLM produced sentence 2 at {llm_sent2_time:.0f}ms")
                print(f"     TTS finished sentence 1 at {tts_sent1_done:.0f}ms")
                print(f"     → Sequential execution detected (LLM finished first)")
    
    if len(llm_events) == 1:
        print(f"     Only 1 sentence was generated (short response).")
        print(f"     Parallelism benefit increases with longer responses.")

if __name__ == "__main__":
    test_pipeline_latency()
