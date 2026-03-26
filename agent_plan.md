# Raspberry Pi 4B (8GB) Local Agent Architecture Plan for NETRA

## Goal

Build NETRA as a fully local, agent-based assistant on Raspberry Pi 4B (8GB), with quantized models and stable real-time behavior for blind-first voice + braille workflows.

## Scope

This plan covers:
- Agent and sub-agent architecture
- Quantized model strategy for local inference
- Deployment profile for Raspberry Pi 4B (8GB)
- System tuning and reliability best practices
- Validation checklist for performance and quality

## Success Criteria

A build is considered successful when:
- Common voice commands return in less than 2 seconds
- OCR to spoken response completes in less than 6 seconds for clean print pages
- Braille rendering never blocks TTS or STT pipeline
- System runs continuously for at least 60 minutes without crash or thermal throttle events
- Core features work fully offline

## Target Architecture

## 1) Orchestrator Agent

Responsibilities:
- Receive parsed user command
- Select plan route (deterministic path first)
- Dispatch to sub-agents
- Apply fallback and retries
- Merge outputs for TTS and braille

Inputs:
- user_text
- session_state
- active_document
- latest_note

Outputs:
- response_text
- braille_text
- action_status
- next_hint

## 2) Sub-Agents (Tool Workers)

1. Voice Agent
- Wake word, STT capture, confidence checks

2. Intent Agent
- Rule-first intent classification
- Quantized LLM fallback for ambiguous utterances

3. Document Agent
- Open, list, read, summarize, explain, translate

4. Vision Agent
- Camera capture and OCR pipeline
- Confidence scoring and recapture prompts

5. Notes Agent
- Save, append, read last, delete, list notes

6. Braille Agent
- Text normalization
- liblouis conversion
- chunking by cell width
- hardware display sequencing

7. System Agent
- Time, battery, diagnostics, health checks

## 3) Shared State Layer

Use SQLite + in-memory cache:
- session table: active doc, current mode, pending note
- action_log table: intent, status, latency, error
- notes and bookmarks table

Cache:
- last 3 responses
- last OCR text
- last generated braille pattern map

## Why This Works on Pi 4B 8GB

Agent routing logic is light CPU work.
Most heavy operations are single-task bursts (STT, OCR, LLM), not constant full-load if queued properly.

## Quantized Model Plan

## A) Model Strategy

Use a two-tier model strategy:

1. Tier-1 (Always available, low latency)
- Small quantized model (1B to 3B, Q4 or Q5)
- Purpose: intent cleanup, short reformulation, safety fallback

2. Tier-2 (Optional higher quality, still local)
- Medium quantized model (3B to 7B, Q4)
- Purpose: summarize/explain/translation for longer text
- Only invoked when user requests advanced reasoning

## B) Recommended Quantization Settings

- Prefer Q4_K_M for balanced speed and quality
- Use Q5 only if latency remains acceptable
- Avoid Q8 on Pi 4B unless workload is very light

## C) Runtime Policies

- Keep only one large model loaded at a time
- Warm small model at startup
- Load higher model lazily on demand
- Timebox model calls (hard timeout) and return graceful fallback

## D) Prompt and Token Budget Rules

- Intent fallback max context: 256 to 512 tokens
- Summarize/explain max input text per call: first 2000 to 4000 chars
- Chunk long documents and summarize incrementally
- Use concise response style for TTS friendliness

## E) Suggested Local-Only Routing Policy

1. Deterministic route (no LLM):
- open/list/read/save/delete/bookmark/time/battery/repeat/stop

2. Small model route:
- unclear user phrasing
- correction of transcription ambiguity

3. Medium model route:
- summarize
- explain in simple terms
- translation
- quiz generation

## Raspberry Pi 4B (8GB) System Tuning Plan

## 1) Active Cooling (Fan + Heatsink)

Actions:
- Install aluminum heatsinks on CPU/RAM
- Use PWM fan profile to keep CPU under 75 C
- Ensure unobstructed airflow in enclosure

Validation:
- Under load test, no sustained thermal throttling flag

## 2) Lightweight OS and Minimal Background Services

Actions:
- Use Raspberry Pi OS Lite (64-bit)
- Disable GUI and unnecessary daemons
- Disable auto-update jobs during active hours
- Keep only essential services enabled at boot

Validation:
- Idle RAM usage remains stable and low
- No background spikes during STT/OCR/LLM operations

## 3) Fast Storage (High-Endurance SD or SSD via USB)

Actions:
- Prefer USB 3 SSD for models and logs
- If SD card used, pick high-endurance A2 class
- Store temp files and caches on fast media
- Rotate logs to avoid write amplification

Validation:
- Model load and OCR temp writes complete without I/O stalls

## 4) zram/swap for Burst Handling

Actions:
- Enable zram with conservative compression ratio
- Keep swap small to moderate to avoid slow swap storms
- Prioritize preventing OOM during occasional spikes

Validation:
- No OOM kills during long summarize/explain tasks
- Swap activity present only in bursts, not constant

## 5) CPU Governor Pinning

Actions:
- Use performance governor during active assistant session
- Revert to ondemand/powersave when idle if battery critical
- Apply governor change through startup script and service hooks

Validation:
- Reduced response jitter for STT and model inference

## Process and Concurrency Best Practices

1. Single action queue for heavy tasks
- Prevent STT, OCR, and LLM from overloading CPU simultaneously

2. Non-blocking audio path
- TTS must run async and support interruption (stop command)

3. Circuit breakers per sub-agent
- Timeout and fallback message for each failing component

4. Graceful degradation ladder
- If medium model fails, fallback to small model
- If small model fails, fallback to deterministic template response

5. Structured telemetry
- Track: intent, route type, latency, CPU temp, memory, error code

## Security and Reliability Basics

- Run assistant service as non-root user
- Restrict file permissions for notes/db/logs
- Validate all external inputs before file operations
- Keep watchdog service to auto-restart on crash
- Add startup self-test: mic, speaker, camera, braille bus, db

## Phased Implementation Plan

## Phase 0 - Baseline and Instrumentation (1 to 2 days)

Deliverables:
- Latency baseline for current script architecture
- CPU, RAM, temp, and response time logs
- Existing failure map (top 10 frequent errors)

## Phase 1 - Agent Skeleton (2 to 3 days)

Deliverables:
- Orchestrator module with typed task contracts
- Sub-agent interfaces and response schema
- Deterministic routing for core commands

## Phase 2 - Quantized Inference Integration (2 to 4 days)

Deliverables:
- Small quantized model integrated for ambiguity fallback
- Medium quantized model integrated for heavy reasoning
- Token and timeout guards implemented

## Phase 3 - Voice + OCR + Braille Pipeline Hardening (2 to 4 days)

Deliverables:
- Queue-based execution for heavy tasks
- Async TTS with interrupt support
- Braille rendering decoupled from generation

## Phase 4 - Pi Tuning and Soak Testing (3 to 5 days)

Deliverables:
- Cooling, governor, zram, and storage tuning completed
- 60-minute soak test without failures
- Final tuned config profiles saved

## Validation Checklist

Functional:
- [ ] open/list/read docs
- [ ] capture and OCR via camera
- [ ] save/read/delete notes
- [ ] convert note to braille
- [ ] summarize/explain/translate locally

Performance:
- [ ] median intent-to-response under 2 seconds for deterministic actions
- [ ] summarize under acceptable latency target
- [ ] no major jitter in TTS playback

Stability:
- [ ] no crash in 60-minute continuous run
- [ ] no thermal throttle under normal session load
- [ ] no OOM kill events in logs

Accessibility:
- [ ] short spoken confirmations at every step
- [ ] clear retry prompts on low confidence OCR or STT
- [ ] stop/repeat commands always available

## Suggested Repo Structure Changes

- src/netra/agents/orchestrator.py
- src/netra/agents/contracts.py
- src/netra/agents/voice_agent.py
- src/netra/agents/intent_agent.py
- src/netra/agents/document_agent.py
- src/netra/agents/vision_agent.py
- src/netra/agents/notes_agent.py
- src/netra/agents/braille_agent.py
- src/netra/agents/system_agent.py
- src/netra/runtime/task_queue.py
- src/netra/runtime/health_monitor.py

## Risk Register and Mitigations

1. Risk: Slow local reasoning for long prompts
- Mitigation: chunking, strict token budgets, two-tier model routing

2. Risk: Thermal throttling during continuous usage
- Mitigation: active cooling, performance profile checks, queue limits

3. Risk: Memory pressure from model + OCR + TTS overlap
- Mitigation: serialized heavy tasks, zram burst support, one model loaded policy

4. Risk: Poor STT in noisy environments
- Mitigation: wake beep cue, confidence threshold, quick repeat prompts

## Operational Best Practices (Day-2 Ops)

- Keep a daily health log (temp, free RAM, crashes, latency)
- Rotate logs weekly and archive snapshots
- Re-test model latency after every package update
- Freeze dependency versions in requirements.txt for reproducibility
- Maintain two startup profiles: performance and battery-safe

## Final Recommendation

For Raspberry Pi 4B (8GB), fully local agent architecture is feasible if:
- routing is deterministic-first,
- quantized models are kept small to medium,
- heavy tasks are queued,
- and hardware/system tuning is treated as part of the software architecture.

This plan provides a practical path to stable, fully offline NETRA operation with accessible response behavior.
