# Bugfix Requirements Document

## Introduction

This document addresses a critical reliability issue in the NETRA AI assistant where the TinyLlama LLM (tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf) intermittently hallucinates and generates fictional content instead of processing the actual document text when users request document translation or summarization. This bug undermines the core functionality of the assistant, which is designed to help visually impaired users access and understand document content accurately.

The bug manifests when users issue commands like "read and translate" or "summarize" on PDF documents. Instead of processing the actual extracted text from the PDF (which PyMuPDF extracts correctly), TinyLlama sometimes generates completely fabricated responses, such as unrelated website names or content about braille that does not exist in the source document.

The fix involves replacing TinyLlama with a more reliable LLM model that can run on Raspberry Pi 4B (8GB RAM) while providing accurate, hallucination-free intent parsing and document processing.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user says "read and translate" on a PDF document THEN the system intermittently generates completely fictional content (e.g., website names, unrelated braille information) that is not present in the source PDF

1.2 WHEN a user says "summarize" on a PDF document THEN the system intermittently generates made-up summaries that do not reflect the actual document content

1.3 WHEN TinyLlama processes document text for translation or summarization THEN it sometimes hallucinates and produces unreliable responses instead of processing the actual extracted text

1.4 WHEN the hallucination occurs THEN the user receives incorrect information, defeating the purpose of the assistive device for visually impaired users

### Expected Behavior (Correct)

2.1 WHEN a user says "read and translate" on a PDF document THEN the system SHALL reliably translate the actual extracted PDF content without generating fictional content

2.2 WHEN a user says "summarize" on a PDF document THEN the system SHALL generate an accurate summary based solely on the actual document content without hallucination

2.3 WHEN the LLM processes document text for any task (translation, summarization, explanation) THEN it SHALL consistently use the actual extracted text and produce reliable, factually grounded responses

2.4 WHEN processing any document command THEN the system SHALL provide accurate information that visually impaired users can trust

2.5 WHEN selecting a replacement LLM model THEN it SHALL be capable of running on Raspberry Pi 4B with 8GB RAM without requiring external servers

### Unchanged Behavior (Regression Prevention)

3.1 WHEN PyMuPDF extracts text from PDF documents THEN the system SHALL CONTINUE TO extract text correctly as it currently does

3.2 WHEN a user issues "read this" command (without LLM processing) THEN the system SHALL CONTINUE TO read the document using chunked streaming without LLM involvement

3.3 WHEN the LLM is used for intent parsing (mapping user commands to system actions) THEN the system SHALL CONTINUE TO parse user intents correctly

3.4 WHEN the LLM processes commands like "explain", "quiz", or "define" THEN the system SHALL CONTINUE TO provide these capabilities with improved reliability

3.5 WHEN the system performs OCR on camera-captured images THEN the system SHALL CONTINUE TO extract text correctly using Tesseract

3.6 WHEN the system converts text to braille THEN the system SHALL CONTINUE TO use liblouis for UEB Grade 2 translation correctly

3.7 WHEN the system performs text-to-speech THEN the system SHALL CONTINUE TO use Piper TTS for audio output correctly

3.8 WHEN a user issues non-LLM commands (open file, list docs, bookmark, take note, etc.) THEN the system SHALL CONTINUE TO execute these commands correctly

3.9 WHEN the system runs on Raspberry Pi 4B with 8GB RAM THEN the replacement LLM SHALL CONTINUE TO run locally without requiring external servers or internet connectivity
