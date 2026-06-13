# LLM Hallucination Fix Bugfix Design

## Overview

This design addresses the critical hallucination issue in NETRA's document processing pipeline where TinyLlama-1.1B generates fictional content instead of processing actual PDF text. The fix involves replacing TinyLlama with Microsoft's Phi-3-mini (3.8B parameters), a more capable model that delivers significantly better reasoning and factual grounding while remaining viable for Raspberry Pi 4B (8GB RAM) deployment.

**Key Strategy:**
- Replace TinyLlama-1.1B-Q4_K_M with Phi-3-mini-4k-instruct-Q4_K_M
- Maintain the existing llama.cpp integration architecture (drop-in replacement)
- Preserve all existing functionality (intent parsing, document processing, general queries)
- Achieve ~2-4 tokens/sec inference speed on RPi 4B (acceptable for voice assistant use case)
- Improve MMLU benchmark score from 58.8% (TinyLlama) to 68.8% (Phi-3-mini), reducing hallucination risk

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when TinyLlama processes document text for translation or summarization and generates hallucinated content instead of using actual extracted text
- **Property (P)**: The desired behavior - the LLM SHALL process actual document text and produce factually grounded responses without hallucination
- **Preservation**: Existing functionality that must remain unchanged - intent parsing, document extraction, braille conversion, TTS, OCR, and all non-LLM commands
- **LlamaCppService**: The service class in `src/netra/services/llama_service.py` that wraps llama.cpp Python bindings for local GGUF model inference
- **ConversationAgent**: The agent class in `src/netra/core/conversation_agent.py` that orchestrates document processing and LLM task execution
- **IntentParser**: The parser class in `src/netra/core/intent_parser.py` that maps user natural language commands to system actions using LLM assistance
- **Hallucination**: When an LLM generates content that is not grounded in the provided input text, producing fictional or fabricated information
- **GGUF**: GPT-Generated Unified Format - a file format for storing quantized LLM weights for efficient inference with llama.cpp
- **Q4_K_M**: 4-bit quantization with K-quant medium precision - balances model size, memory usage, and inference quality
- **MMLU**: Massive Multitask Language Understanding - a benchmark measuring LLM reasoning and knowledge across 57 subjects

## Bug Details

### Bug Condition

The bug manifests when TinyLlama-1.1B processes document text for translation or summarization tasks. Instead of using the actual extracted PDF content (which PyMuPDF extracts correctly), TinyLlama intermittently generates completely fabricated responses such as unrelated website names, fictional braille content, or made-up summaries that do not reflect the source document.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type LLMTaskRequest
  OUTPUT: boolean
  
  RETURN input.action IN ['summarize', 'translate', 'explain', 'quiz', 'define']
         AND input.source_text IS NOT NULL
         AND input.source_text.length > 0
         AND LLM_generates_hallucinated_content(input.source_text)
END FUNCTION
```

**Root Cause Analysis:**
TinyLlama-1.1B (1.1 billion parameters, MMLU score 58.8%) lacks sufficient reasoning capacity and factual grounding for reliable document processing tasks. The model's limited parameter count and training data result in:
1. **Insufficient context adherence**: The model fails to consistently ground responses in the provided document text
2. **Weak instruction following**: The model does not reliably follow prompts like "Summarize this in 4 short sentences" when processing long documents
3. **Low reasoning capability**: MMLU score of 58.8% indicates poor performance on knowledge and reasoning tasks compared to larger models

### Examples

**Example 1: Translation Hallucination**
- **User Command**: "read and translate" on a PDF containing physics notes
- **Expected Behavior**: Translate the actual physics content from the PDF
- **Actual Behavior (Bug)**: Generates fictional website names and unrelated braille information not present in the source PDF

**Example 2: Summarization Hallucination**
- **User Command**: "summarize" on a PDF containing biology lecture notes
- **Expected Behavior**: Generate a 4-sentence summary of the actual biology content
- **Actual Behavior (Bug)**: Produces a made-up summary about topics not mentioned in the source document

**Example 3: Explanation Hallucination**
- **User Command**: "explain this in simple language" on a PDF containing mathematical concepts
- **Expected Behavior**: Explain the actual mathematical concepts from the PDF in simple terms
- **Actual Behavior (Bug)**: Generates fictional explanations unrelated to the source content

**Example 4: Edge Case - Short Document**
- **User Command**: "summarize" on a PDF with only 2 paragraphs
- **Expected Behavior**: Summarize the 2 paragraphs accurately
- **Actual Behavior (Bug)**: May work correctly for very short documents but still risks hallucination

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- PyMuPDF text extraction from PDF documents must continue to work correctly
- Direct document reading via "read this" command (without LLM processing) must continue using chunked streaming
- Intent parsing for mapping user commands to system actions must continue to work correctly
- OCR text extraction from camera-captured images using Tesseract must continue to work correctly
- Braille conversion using liblouis (UEB Grade 2) must continue to work correctly
- Text-to-speech using Piper TTS must continue to work correctly
- All non-LLM commands (open file, list docs, bookmark, take note, save note, delete note, read last note, close document, repeat, time, battery, start over) must continue to work correctly
- Local execution on Raspberry Pi 4B (8GB RAM) without external servers or internet connectivity must be preserved

**Scope:**
All inputs that do NOT involve LLM document processing (summarize, translate, explain, quiz, define) should be completely unaffected by this fix. This includes:
- Document extraction and reading operations
- Camera capture and OCR operations
- Braille and TTS output operations
- File management and navigation commands
- Note-taking and bookmarking operations

## Hypothesized Root Cause

Based on the bug description and model analysis, the most likely issues are:

1. **Insufficient Model Capacity**: TinyLlama-1.1B has only 1.1 billion parameters, which is insufficient for reliable document understanding and summarization tasks
   - MMLU benchmark score of 58.8% indicates weak reasoning and knowledge capabilities
   - Limited parameter count restricts the model's ability to maintain context and follow complex instructions

2. **Poor Instruction Following**: TinyLlama struggles to adhere to specific prompts when processing long document text
   - The model does not consistently ground responses in the provided source text
   - Prompts like "Summarize this in 4 short sentences" are not reliably followed

3. **Training Data Quality**: TinyLlama's training focused on speed and efficiency rather than factual accuracy
   - The model was trained on 3 trillion tokens but optimized for fast inference rather than reasoning quality
   - Insufficient exposure to document summarization and translation tasks during training

4. **Context Window Limitations**: While TinyLlama supports 2048 tokens, it may struggle to effectively utilize the full context
   - Long documents (8000 characters truncated in `_llm_task`) may exceed the model's effective reasoning window
   - The model may "forget" earlier parts of the document when generating responses

## Correctness Properties

Property 1: Bug Condition - Accurate Document Processing Without Hallucination

_For any_ document processing request where the user issues a command (summarize, translate, explain, quiz, define) on extracted document text, the fixed LLM (Phi-3-mini) SHALL process the actual document content and generate responses that are factually grounded in the source text, without producing hallucinated or fictional content.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - Non-LLM Functionality Unchanged

_For any_ operation that does NOT involve LLM document processing (document extraction, direct reading, OCR, braille conversion, TTS, file management, note-taking), the fixed system SHALL produce exactly the same behavior as the original system, preserving all existing functionality for non-LLM operations.

**Validates: Requirements 3.1, 3.2, 3.5, 3.6, 3.7, 3.8**

Property 3: Preservation - Intent Parsing Functionality

_For any_ user command that requires intent parsing (mapping natural language to system actions), the fixed system with Phi-3-mini SHALL continue to parse user intents correctly, maintaining or improving the accuracy of command recognition compared to the original TinyLlama implementation.

**Validates: Requirements 3.3, 3.4**

Property 4: Preservation - Resource Constraints

_For any_ LLM inference operation on Raspberry Pi 4B with 8GB RAM, the fixed system with Phi-3-mini SHALL run locally without requiring external servers or internet connectivity, maintaining the standalone nature of the NETRA device.

**Validates: Requirements 2.5, 3.9**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct (TinyLlama lacks sufficient capacity for reliable document processing):

**File**: `config.json`

**Configuration Update**:

**Specific Changes**:
1. **Model Path Update**: Change the model path to point to Phi-3-mini GGUF file
   - Old: `"llama_model_path": "models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"`
   - New: `"llama_model_path": "models/phi-3-mini-4k-instruct-q4.gguf"`

2. **Context Size Adjustment**: Increase context size to leverage Phi-3-mini's 4K context window
   - Old: `"llama_context_size": 2048`
   - New: `"llama_context_size": 4096`

3. **Thread Configuration**: Keep thread count at 4 for optimal RPi 4B performance
   - Unchanged: `"llama_threads": 4`

4. **Temperature Setting**: Keep temperature at 0.7 for balanced output
   - Unchanged: `"llama_temperature": 0.7`

**File**: `src/netra/services/llama_service.py`

**No Code Changes Required** - The existing `LlamaCppService` class is model-agnostic and works with any GGUF model. The llama.cpp Python bindings automatically handle model loading and inference for Phi-3-mini.

**File**: `src/netra/core/conversation_agent.py`

**Prompt Engineering Improvements** (Optional but Recommended):

**Specific Changes**:
1. **Enhanced System Prompts**: Update system prompts in `_llm_task` and `_llm_general` to leverage Phi-3-mini's improved instruction-following capabilities
   - Add explicit grounding instructions: "Base your response ONLY on the provided text. Do not add information not present in the source."
   - Emphasize conciseness for voice output: "Keep response under 100 words and optimized for text-to-speech."

2. **Improved Context Truncation**: Increase document text limit from 8000 to 12000 characters to leverage the larger 4K context window
   - Old: `prompt = f"{instruction}...\\n\\nText:\\n{source_text[:8000]}"`
   - New: `prompt = f"{instruction}...\\n\\nText:\\n{source_text[:12000]}"`

**File**: `src/netra/core/intent_parser.py`

**Prompt Engineering Improvements** (Optional but Recommended):

**Specific Changes**:
1. **Clearer Intent Parsing Instructions**: Update the LLM prompt in `_llm_parse` to provide more structured examples
   - Add few-shot examples of correct intent mappings
   - Emphasize strict JSON output format to reduce parsing errors

**File**: `README.md`

**Documentation Updates**:

**Specific Changes**:
1. **Model Recommendation Update**: Replace TinyLlama recommendation with Phi-3-mini
   - Update download instructions with Phi-3-mini Hugging Face link
   - Update performance expectations (2-4 tokens/sec on RPi 4B)
   - Update model size information (~2.2GB for Q4_K_M quantization)

2. **Benchmark Information**: Add MMLU scores and quality comparison
   - Document the improvement from 58.8% (TinyLlama) to 68.8% (Phi-3-mini)
   - Explain the reduced hallucination risk with the more capable model

### Model Download Instructions

**Download Phi-3-mini-4k-instruct (Q4_K_M quantization)**:

```bash
# Create models directory if it doesn't exist
mkdir -p models

# Download the model (approximately 2.2GB)
cd models
wget https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf
cd ..
```

**Alternative Download Method (using Hugging Face CLI)**:

```bash
pip install huggingface-hub
huggingface-cli download microsoft/Phi-3-mini-4k-instruct-gguf Phi-3-mini-4k-instruct-q4.gguf --local-dir models
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code (TinyLlama), then verify the fix works correctly (Phi-3-mini) and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the hallucination bug BEFORE implementing the fix. Confirm or refute the root cause analysis (insufficient model capacity). If we refute, we will need to re-hypothesize.

**Test Plan**: Create a test suite that processes known PDF documents with specific content and captures the LLM's output for summarization and translation tasks. Run these tests on the UNFIXED code (TinyLlama) to observe hallucination failures and document the specific types of hallucinated content generated.

**Test Cases**:
1. **Physics PDF Summarization Test**: Process a physics PDF and request summarization (will fail on unfixed code - expect hallucinated content)
   - Input: PDF with physics formulas and concepts
   - Command: "summarize"
   - Expected Failure: TinyLlama generates summary unrelated to physics content

2. **Biology PDF Translation Test**: Process a biology PDF and request translation (will fail on unfixed code - expect fictional website names or braille content)
   - Input: PDF with biology lecture notes
   - Command: "translate to Spanish"
   - Expected Failure: TinyLlama generates fictional content instead of translating actual biology text

3. **Math PDF Explanation Test**: Process a math PDF and request simple explanation (will fail on unfixed code - expect fabricated explanations)
   - Input: PDF with mathematical proofs
   - Command: "explain this in simple language"
   - Expected Failure: TinyLlama generates explanations unrelated to the actual math content

4. **Short Document Edge Case**: Process a very short PDF (2 paragraphs) and request summarization (may pass or fail on unfixed code)
   - Input: PDF with 2 short paragraphs
   - Command: "summarize"
   - Expected Behavior: May work correctly due to short length, but still at risk of hallucination

**Expected Counterexamples**:
- TinyLlama generates fictional website names when asked to translate document content
- TinyLlama produces summaries about topics not mentioned in the source PDF
- TinyLlama fabricates explanations unrelated to the actual document text
- Possible causes: insufficient model capacity (1.1B parameters), poor instruction following, weak factual grounding

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (document processing tasks), the fixed function (Phi-3-mini) produces the expected behavior (accurate, grounded responses without hallucination).

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := LlamaCppService_with_Phi3Mini.generate(input.prompt, input.source_text)
  ASSERT result_is_grounded_in_source_text(result, input.source_text)
  ASSERT NOT contains_hallucinated_content(result)
  ASSERT result_follows_instruction(result, input.instruction)
END FOR
```

**Test Plan**: Run the same test cases from exploratory checking on the FIXED code (Phi-3-mini) and verify that:
1. Summaries accurately reflect the actual document content
2. Translations use the actual source text without fabrication
3. Explanations are grounded in the provided document text
4. No fictional content (website names, unrelated topics) is generated

**Validation Criteria**:
- **Factual Grounding**: Use keyword matching to verify that key terms from the source document appear in the LLM output
- **No Hallucination**: Manually review outputs to confirm no fictional content is present
- **Instruction Following**: Verify that summaries are concise (4 sentences as requested), translations are in the target language, and explanations are simplified

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (non-LLM operations and intent parsing), the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT system_with_TinyLlama(input) = system_with_Phi3Mini(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-LLM operations, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Document Extraction Preservation**: Verify that PyMuPDF text extraction produces identical output before and after the fix
   - Test with multiple PDF files of varying complexity
   - Assert that extracted text is byte-for-byte identical

2. **Direct Reading Preservation**: Verify that "read this" command (without LLM processing) produces identical chunked streaming behavior
   - Test with PDF and OCR-captured documents
   - Assert that braille output and TTS audio are identical

3. **Intent Parsing Preservation**: Verify that intent parsing continues to work correctly (or improves) with Phi-3-mini
   - Test with a corpus of 50+ user commands covering all action types
   - Assert that parsed intents match expected actions
   - Allow for improvements (Phi-3-mini may parse intents MORE accurately)

4. **OCR Preservation**: Verify that camera capture and Tesseract OCR produce identical text extraction
   - Test with sample images of printed text
   - Assert that OCR output is identical before and after the fix

5. **Braille Conversion Preservation**: Verify that liblouis braille translation produces identical dot patterns
   - Test with various text inputs
   - Assert that braille patterns are identical before and after the fix

6. **TTS Preservation**: Verify that Piper TTS produces identical audio output
   - Test with various text inputs
   - Assert that generated WAV files are identical (or functionally equivalent)

7. **File Management Preservation**: Verify that all file operations (open, list, close, bookmark) work identically
   - Test with various document collections
   - Assert that file navigation and bookmarking behavior is unchanged

8. **Note-Taking Preservation**: Verify that note capture, save, read, and delete operations work identically
   - Test with various note content
   - Assert that database operations produce identical results

### Unit Tests

- Test Phi-3-mini model loading with correct configuration (4K context, 4 threads, Q4_K_M quantization)
- Test LLM generation with various prompt lengths (short, medium, long up to 12000 characters)
- Test summarization task with known PDF content and verify output contains key terms from source
- Test translation task with known PDF content and verify output is in target language and grounded in source
- Test explanation task with known PDF content and verify output simplifies concepts from source
- Test intent parsing with Phi-3-mini and verify correct action mapping for all command types
- Test edge cases (empty document, very long document, special characters in document)
- Test error handling (model file not found, out of memory, generation timeout)

### Property-Based Tests

- Generate random PDF documents with known content and verify that summarization outputs contain keywords from the source (no hallucination)
- Generate random user commands and verify that intent parsing produces valid action types from the allowed set
- Generate random document text of varying lengths (100 to 12000 characters) and verify that LLM processing completes without errors
- Test that all non-LLM operations (document extraction, OCR, braille, TTS) produce identical outputs across many random inputs before and after the fix

### Integration Tests

- Test full document processing flow: open PDF → extract text → summarize with Phi-3-mini → convert to braille → output via TTS
- Test full camera capture flow: capture image → OCR with Tesseract → explain with Phi-3-mini → convert to braille → output via TTS
- Test full intent parsing flow: user command → Phi-3-mini intent parsing → action execution → output
- Test switching between different document processing tasks (summarize → translate → explain) on the same document
- Test that visual feedback (braille display, TTS audio) occurs correctly after LLM processing
- Test performance on Raspberry Pi 4B: measure inference speed (target 2-4 tokens/sec), memory usage (target <6GB), and end-to-end latency (target <10 seconds for summarization)
