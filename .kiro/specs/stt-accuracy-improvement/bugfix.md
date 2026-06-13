# Bugfix Requirements Document

## Introduction

The Netra AI assistant currently uses the Vosk-small model (`vosk-model-small-en-us-0.15`) for speech-to-text (STT) transcription. This model exhibits poor transcription accuracy (~15-20% Word Error Rate), leading to frequent command misrecognition and unreliable voice interactions for visually impaired users. This bugfix upgrades the STT system from Vosk-small to OpenAI Whisper Base model to achieve significantly better accuracy (~7-8% WER) while maintaining acceptable performance on Raspberry Pi 4B (8GB RAM) hardware.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user speaks a voice command THEN the system transcribes with ~15-20% Word Error Rate using Vosk-small model

1.2 WHEN a user speaks commands like "read and translate" or "summarize" THEN the system frequently misrecognizes the command due to poor transcription accuracy

1.3 WHEN the STT engine is configured as "vosk" THEN the system uses the Vosk-small model which has insufficient accuracy for reliable command recognition

1.4 WHEN transcription errors occur THEN the intent parser receives incorrect text input leading to wrong command execution or no action

### Expected Behavior (Correct)

2.1 WHEN a user speaks a voice command THEN the system SHALL transcribe with ~7-8% Word Error Rate using Whisper Base model

2.2 WHEN a user speaks commands like "read and translate" or "summarize" THEN the system SHALL accurately recognize and transcribe the command for correct intent parsing

2.3 WHEN the STT engine is configured to use Whisper Base THEN the system SHALL load and use the Whisper Base model with acceptable latency (RTF 0.23-0.41) on Raspberry Pi 4B

2.4 WHEN transcription completes THEN the intent parser SHALL receive accurate text input enabling reliable command execution

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the system is configured to use Vosk for wake word detection THEN the system SHALL CONTINUE TO use Vosk for fast wake word processing

3.2 WHEN the system uses dual STT engines (Vosk for wake word, Whisper for commands) THEN the system SHALL CONTINUE TO support this configuration pattern

3.3 WHEN audio is recorded from hardware or live microphone THEN the system SHALL CONTINUE TO process audio at 16kHz sample rate

3.4 WHEN STT transcription fails or is unavailable THEN the system SHALL CONTINUE TO fall back to typed input if configured

3.5 WHEN the system runs on Raspberry Pi 4B with 8GB RAM THEN the system SHALL CONTINUE TO operate without thermal throttling or memory exhaustion

3.6 WHEN Whisper model is already loaded for command recognition THEN the system SHALL CONTINUE TO use the existing Whisper model instance

3.7 WHEN the configuration specifies a Whisper model size (tiny/base/small) THEN the system SHALL CONTINUE TO respect this configuration parameter
