# STT Accuracy Improvement Bugfix Design

## Overview

This bugfix upgrades the Netra AI assistant's speech-to-text (STT) system from Vosk-small (~15-20% WER) to OpenAI Whisper Base (~7-8% WER) for command recognition. The bug has two root causes: (1) the `openai-whisper` library is missing from `requirements.txt`, making Whisper completely unavailable, and (2) the `config.json` defaults to Vosk for command recognition even though Whisper would be more accurate. The fix adds Whisper to dependencies, changes the default STT engine configuration from Vosk to Whisper Base, and optionally adds `faster-whisper` for 4x performance improvement. This approach leverages the existing dual-engine architecture (Vosk for wake word detection where speed is critical, Whisper for command recognition where accuracy is critical) and requires dependency updates and configuration changes, with optional code enhancements to the STT service.

## Glossary

- **Bug_Condition (C)**: The condition that triggers poor transcription accuracy - when the system uses Vosk-small model for command recognition
- **Property (P)**: The desired behavior - accurate transcription with ~7-8% WER using Whisper Base model
- **Preservation**: Existing Vosk wake word detection, dual-engine architecture, and audio processing pipeline that must remain unchanged
- **WER (Word Error Rate)**: Percentage of words incorrectly transcribed (lower is better)
- **RTF (Real-Time Factor)**: Ratio of processing time to audio duration (0.23-0.41 means processing takes 23-41% of audio length)
- **STTService**: The service class in `src/netra/services/stt_service.py` that handles speech-to-text transcription
- **stt_engine_command**: Configuration parameter that determines which STT engine is used for command recognition
- **whisper_model**: Configuration parameter that specifies the Whisper model size (tiny/base/small)

## Bug Details

### Bug Condition

The bug manifests when a user speaks a voice command and the system attempts to use Whisper for transcription but the Whisper library is not installed. The `STTService.__init__` checks `if whisper is not None` but the import fails because `openai-whisper` is missing from `requirements.txt`. This causes the system to fall back to Vosk-small model (if configured) or have no STT capability at all. Even when Vosk is used as fallback, it has insufficient accuracy (~15-20% WER) for reliable command parsing, leading to frequent misrecognition of commands like "read and translate" or "summarize".

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type VoiceCommand
  OUTPUT: boolean
  
  RETURN input.isSpokenCommand == true
         AND (whisperLibraryNotInstalled() 
              OR (config.stt_engine_command == "vosk" 
                  AND voskModelIsSmall(config.vosk_model)))
         AND transcriptionAccuracy < 0.85  # WER > 15%
END FUNCTION
```

### Examples

- **Example 1**: User says "read and translate" → Whisper library not installed → Falls back to Vosk → Vosk transcribes as "read and trans late" → Intent parser fails to recognize command → No action taken
- **Example 2**: User says "summarize document" → Whisper library not installed → Falls back to Vosk → Vosk transcribes as "some rice document" → Intent parser misinterprets → Wrong action executed
- **Example 3**: User says "open biology notes" → System configured with `stt_engine_command: "vosk"` → Vosk transcribes as "open by ology notes" → File matching fails → User must retry
- **Example 4**: User says "next" (short command) → Vosk transcribes correctly → Command works (short commands less affected by WER)
- **Example 5**: System starts with `stt_engine_command: "whisper"` → Whisper import fails (not in requirements.txt) → STTService logs warning "Whisper library not installed" → Falls back to Vosk or typed input

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Vosk must continue to be used for wake word detection (speed-critical path)
- Dual STT engine architecture (separate engines for wake word vs commands) must remain functional
- Audio recording and processing at 16kHz sample rate must continue to work
- Typed input fallback mechanism must continue to work when STT fails
- System must continue to operate on Raspberry Pi 4B (8GB RAM) without thermal throttling or memory exhaustion
- Existing Whisper model loading logic in STTService must continue to work
- Configuration file structure and parameter names must remain unchanged

**Scope:**
All inputs that do NOT involve spoken command recognition should be completely unaffected by this fix. This includes:
- Wake word detection (continues using Vosk)
- Typed command input (fallback mechanism)
- Audio file playback and TTS output
- Hardware button interactions

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is:

1. **Incorrect Default Configuration**: The `config.json` file sets `stt_engine_command: "vosk"` instead of `"whisper"`, causing the system to use the low-accuracy Vosk-small model for command recognition.

2. **Suboptimal Whisper Model Size**: The `config.json` specifies `whisper_model: "tiny"` (39M parameters, ~10% WER) instead of `"base"` (74M parameters, ~7-8% WER), which would provide better accuracy with acceptable performance on RPi 4B.

3. **Missing Whisper Dependencies**: The `requirements.txt` file does NOT include `openai-whisper` or `faster-whisper` packages, meaning Whisper STT is completely unavailable even if configured. The code has fallback logic (`if whisper is not None`) but the library is never installed.

4. **Missing Performance Optimization**: Even if Whisper were installed, the system would use the standard `openai-whisper` library instead of `faster-whisper`, which provides 4x speed improvement (RTF 0.23-0.41 vs 0.92-1.64) with identical accuracy through CTranslate2 optimization.

5. **Documentation Inconsistency**: The README.md shows `stt_engine_command: "whisper"` as the default in the config reference table, but the actual `config.json` file has `"vosk"`, creating confusion about the intended configuration.

## Correctness Properties

Property 1: Bug Condition - Whisper Library Availability

_For any_ system initialization where Whisper is configured as the STT engine, the system SHALL successfully import and load the Whisper library, enabling accurate command transcription instead of falling back to low-accuracy alternatives.

**Validates: Requirements 2.3**

Property 2: Bug Condition - Accurate Command Transcription

_For any_ spoken voice command where the user speaks a valid English phrase, the fixed STT system SHALL transcribe the command using Whisper Base model with Word Error Rate of approximately 7-8%, enabling reliable intent parsing and command execution.

**Validates: Requirements 2.1, 2.2, 2.4**

Property 3: Preservation - Wake Word Detection Speed

_For any_ wake word detection event where the user speaks the wake phrase, the fixed system SHALL continue to use the Vosk model for wake word processing, preserving the fast response time required for real-time wake word detection.

**Validates: Requirements 3.1, 3.2**

Property 4: Preservation - Audio Processing Pipeline

_For any_ audio input from hardware recording or live microphone, the fixed system SHALL continue to process audio at 16kHz sample rate and support typed input fallback, preserving all existing audio handling behaviors.

**Validates: Requirements 3.3, 3.4**

Property 5: Preservation - Resource Constraints

_For any_ operation on Raspberry Pi 4B (8GB RAM) hardware, the fixed system SHALL continue to operate without thermal throttling or memory exhaustion, maintaining acceptable performance within hardware constraints.

**Validates: Requirements 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File 1**: `requirements.txt`

**Changes**:
1. **Add Whisper Library**: Add `openai-whisper==20231117` to dependencies
   - This is the CRITICAL fix - Whisper is currently completely unavailable
   - Version 20231117 is stable and well-tested on Raspberry Pi 4B
   - Enables the Whisper STT functionality that the code already supports

2. **Add Performance Optimization**: Add `faster-whisper>=1.0.0` to dependencies
   - Provides 4x speed improvement over standard openai-whisper
   - Uses CTranslate2 for optimized inference on CPU
   - Maintains identical accuracy to openai-whisper
   - Reduces RTF from 0.92-1.64 to 0.23-0.41 on RPi 4B
   - This is HIGHLY RECOMMENDED but optional (system works without it)

**File 2**: `config.json`

**Changes**:
3. **Update Command Engine**: Change `"stt_engine_command": "vosk"` to `"stt_engine_command": "whisper"`
   - This switches command recognition from Vosk-small to Whisper
   - Wake word detection remains on Vosk (controlled by `stt_engine_wake_word`)
   - Only effective after Whisper library is installed (File 1, Change 1)

4. **Upgrade Whisper Model**: Change `"whisper_model": "tiny"` to `"whisper_model": "base"`
   - Upgrades from 39M parameter model (~10% WER) to 74M parameter model (~7-8% WER)
   - Base model has proven performance on RPi 4B: RTF 0.23-0.41, ~500MB RAM, no thermal issues
   - Provides optimal balance of accuracy and performance for RPi 4B hardware

**File 3**: `src/netra/services/stt_service.py` (Optional Enhancement)

**Changes**:
5. **Add Faster-Whisper Support** (Optional): Modify `__init__` to prefer faster-whisper over openai-whisper
   - Try importing `faster_whisper.WhisperModel` before falling back to `whisper.load_model`
   - Use `WhisperModel` from faster-whisper with same API
   - This is optional because the config changes alone fix the accuracy bug
   - Provides significant performance improvement if faster-whisper is installed

**File 4**: `README.md` (Documentation)

**Changes**:
6. **Update STT Documentation**: Add section explaining Whisper Base recommendation
   - Document WER comparison: Vosk-small (~15-20%) vs Whisper Base (~7-8%)
   - Document performance metrics: RTF 0.23-0.41, ~500MB RAM, no thermal issues
   - Clarify dual-engine architecture: Vosk for wake word, Whisper for commands

7. **Update Configuration Reference**: Update config table to show Whisper Base as default
   - Change `stt_engine_command` default from "vosk" to "whisper"
   - Change `whisper_model` default from "tiny" to "base"
   - Fix inconsistency between README table and actual config.json file

### Implementation Priority

**CRITICAL (Must Fix):**
- File 1, Change 1: Add `openai-whisper` to requirements.txt
- File 2, Change 3: Update `stt_engine_command` to "whisper"

**HIGH PRIORITY (Strongly Recommended):**
- File 1, Change 2: Add `faster-whisper` to requirements.txt
- File 2, Change 4: Upgrade `whisper_model` to "base"

**MEDIUM PRIORITY (Documentation):**
- File 4, Changes 6-7: Update README.md

**LOW PRIORITY (Optional Enhancement):**
- File 3, Change 5: Add faster-whisper support to STTService

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate poor transcription accuracy on unfixed code using Vosk-small, then verify the fix achieves target accuracy (~7-8% WER) and preserves existing behavior for wake word detection and audio processing.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the transcription accuracy bug BEFORE implementing the fix. Confirm that (1) Whisper library is missing from dependencies, and (2) Vosk-small produces ~15-20% WER on command recognition. If we observe significantly different behavior, we will need to re-hypothesize.

**Test Plan**: 
1. **Dependency Check**: Verify that `openai-whisper` is NOT in `requirements.txt` and cannot be imported
2. **Fallback Behavior**: Start system with `stt_engine_command: "whisper"` and observe fallback to Vosk or typed input
3. **Accuracy Test**: Create a test dataset of 50-100 common voice commands (e.g., "read and translate", "summarize document", "open file one", "next page"). Record these commands as WAV files at 16kHz. Run transcription using the UNFIXED configuration (Vosk-small) and calculate WER by comparing transcripts to ground truth. Observe failures and categorize error patterns.

**Test Cases**:
1. **Missing Dependency Test**: Try importing `whisper` module (will fail on unfixed code)
2. **Fallback Test**: Configure `stt_engine_command: "whisper"` and observe STTService logs "Whisper library not installed" (will occur on unfixed code)
3. **Multi-Word Commands**: Test "read and translate", "summarize document" (will show high WER on unfixed code with Vosk)
4. **File Navigation Commands**: Test "open biology notes", "next file", "previous page" (will show misrecognition on unfixed code)
5. **Short Commands**: Test "next", "back", "stop" (may work better but still show errors on unfixed code)
6. **Noisy Audio**: Test commands with background noise (will show even higher WER on unfixed code)

**Expected Counterexamples**:
- `import whisper` raises `ModuleNotFoundError` (confirming missing dependency)
- STTService logs "Whisper library not installed; Whisper STT disabled" when initialized
- Vosk-small transcribes "read and translate" as "read and trans late" or "reed and translate"
- Vosk-small transcribes "summarize" as "some rice" or "summer eyes"
- Vosk-small transcribes "biology" as "by ology" or "buy ology"
- Overall WER on test dataset: 15-20% (confirming root cause)

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (spoken commands), the fixed function produces the expected behavior (accurate transcription with ~7-8% WER).

**Pseudocode:**
```
FOR ALL voiceCommand WHERE isBugCondition(voiceCommand) DO
  transcript := stt_service_fixed.listen_for_command(voiceCommand)
  wer := calculateWER(transcript, groundTruth)
  ASSERT wer <= 0.08  # 8% WER threshold
  ASSERT intentParser.parse(transcript) == expectedIntent
END FOR
```

**Test Plan**: Run the same test dataset through the FIXED configuration (Whisper Base installed and configured). Calculate WER and verify it meets the 7-8% target. Verify that intent parser successfully recognizes commands from the improved transcripts. Verify that Whisper library is successfully imported and loaded.

**Test Cases**:
1. **Dependency Verification**: Verify `openai-whisper` is in requirements.txt and can be imported successfully
2. **Model Loading**: Verify STTService logs "Whisper model loaded: base" during initialization
3. **Multi-Word Commands**: Verify "read and translate" transcribes correctly with Whisper Base
4. **File Navigation Commands**: Verify "open biology notes" transcribes correctly with Whisper Base
5. **Short Commands**: Verify "next", "back", "stop" continue to work correctly
6. **Noisy Audio**: Verify Whisper Base handles background noise better than Vosk-small
7. **Performance Validation**: Measure RTF on Raspberry Pi 4B and verify it stays within 0.23-0.41 range (with faster-whisper) or 0.92-1.64 range (with openai-whisper)
8. **Memory Validation**: Monitor RAM usage and verify it stays within ~500MB for Whisper Base model
9. **Intent Parsing**: Verify that improved transcripts lead to correct intent recognition and command execution

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (wake word detection, typed input, audio processing), the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT stt_service_original(input) = stt_service_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-command inputs

**Test Plan**: Observe behavior on UNFIXED code first for wake word detection, typed input fallback, and audio processing, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Wake Word Detection Preservation**: Observe that Vosk wake word detection works on unfixed code, then verify it continues to use Vosk (not Whisper) after fix
2. **Typed Input Fallback Preservation**: Observe that typed input fallback works when STT fails on unfixed code, then verify this continues after fix
3. **Audio Sample Rate Preservation**: Observe that audio is processed at 16kHz on unfixed code, then verify this continues after fix
4. **Dual Engine Architecture Preservation**: Observe that separate engines can be configured for wake word vs commands on unfixed code, then verify this continues after fix
5. **Resource Usage Preservation**: Observe memory and CPU usage on unfixed code, then verify the fixed code does not exceed these baselines (accounting for larger Whisper Base model)

### Unit Tests

- Test that `openai-whisper` package is installed and importable
- Test STTService initialization with Whisper Base model configuration
- Test that Whisper model loads successfully (not None) when configured
- Test `listen_for_command()` with Whisper engine returns accurate transcripts
- Test `wait_for_wake()` continues to use Vosk engine (not affected by command engine change)
- Test WER calculation on sample command dataset (verify <8% threshold)
- Test fallback behavior when Whisper model unavailable (should fall back to Vosk or typed input)
- Test configuration loading with new default values
- Test that faster-whisper is used if available, otherwise falls back to openai-whisper

### Property-Based Tests

- Generate random voice commands from vocabulary and verify WER stays below 8% threshold across many samples
- Generate random wake word audio samples and verify Vosk engine is always used (never Whisper)
- Generate random audio configurations (sample rates, durations) and verify audio processing pipeline continues to work
- Test that all non-command STT paths (wake word, typed fallback) produce identical behavior before and after fix

### Integration Tests

- Test full voice interaction flow: wake word detection (Vosk) → command recognition (Whisper Base) → intent parsing → action execution
- Test switching between wake word detection and command recognition engines within single session
- Test performance on actual Raspberry Pi 4B hardware: measure RTF, RAM usage, CPU temperature
- Test with real user voice samples: verify improved accuracy translates to better user experience
- Test edge cases: very short commands, very long commands, commands with background noise, accented speech
