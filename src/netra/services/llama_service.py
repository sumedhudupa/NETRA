from typing import Optional, Generator
import logging
import re
from pathlib import Path


class LlamaCppService:
    """
    LLM service using llama.cpp Python bindings.
    Drop-in replacement for OllamaService with local GGUF model inference.
    """

    # Regex to split text at sentence boundaries (. ! ?) followed by whitespace
    _SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+')

    def __init__(self, model_path: str, n_threads: int = 4, n_ctx: int = 2048, temperature: float = 0.7) -> None:
        self.logger = logging.getLogger(__name__)
        self.model_path = model_path
        self.n_threads = n_threads
        self.n_ctx = n_ctx
        self.temperature = temperature
        self.llm = None
        self._model_load_attempted = False

    def _load_model(self) -> None:
        """Load the GGUF model file into memory."""
        if self._model_load_attempted and self.llm is None:
            return
        self._model_load_attempted = True

        if not Path(self.model_path).exists():
            self.logger.error("Model file not found at %s", self.model_path)
            return

        try:
            from llama_cpp import Llama
            
            self.logger.info("Loading llama.cpp model from %s", self.model_path)
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=0,  # CPU-only for Raspberry Pi
                verbose=False
            )
            self.logger.info("Model loaded successfully. Context size: %d, Threads: %d", self.n_ctx, self.n_threads)
        except ImportError:
            self.logger.error("llama-cpp-python not installed. Run: pip install llama-cpp-python")
        except Exception as exc:
            self.logger.error("Failed to load model: %s", exc)

    def is_available(self) -> bool:
        """Check if the model is loaded and ready for inference."""
        if self.llm is None and not self._model_load_attempted:
            self._load_model()
        return self.llm is not None

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        timeout: int = 60,
        temperature: Optional[float] = None,
        max_tokens: int = 512,
    ) -> str:
        """
        Generate text completion from prompt.
        
        Args:
            prompt: User prompt/question
            system: Optional system prompt for instruction-following models
            timeout: Not used (kept for API compatibility)
            
        Returns:
            Generated text response
        """
        if not self.is_available():
            self.logger.error("Model not available for generation")
            return "Model not loaded"

        try:
            # Build full prompt with system context if provided
            full_prompt = prompt
            if system:
                full_prompt = f"System: {system}\n\nUser: {prompt}\n\nAssistant:"
            
            # Generate response
            resolved_temperature = self.temperature if temperature is None else float(temperature)
            response = self.llm(
                full_prompt,
                max_tokens=max_tokens,  # Reasonable for voice assistant responses
                temperature=resolved_temperature,
                top_p=0.95,
                top_k=40,
                repeat_penalty=1.1,
                stop=["User:", "System:"],  # Stop tokens
                echo=False
            )
            
            # Extract generated text
            generated_text = response["choices"][0]["text"].strip()
            return generated_text
            
        except Exception as exc:
            self.logger.error("Generation failed: %s", exc)
            return "Generation error occurred"

    def generate_streaming(
        self,
        prompt: str,
        system: Optional[str] = None,
        timeout: int = 60,
        temperature: Optional[float] = None,
        max_tokens: int = 512,
    ) -> Generator[str, None, None]:
        """
        Stream text generation, yielding complete sentences as they form.

        Uses llama_cpp's native ``stream=True`` iterator so that each token is
        received as soon as it is produced.  Tokens are accumulated in a buffer
        and flushed as complete sentences whenever a sentence-ending punctuation
        mark (``.``, ``!``, ``?``) followed by whitespace (or end-of-stream) is
        detected.

        Yields:
            Each yielded string is one complete sentence (stripped).
        """
        if not self.is_available():
            self.logger.error("Model not available for streaming generation")
            return

        try:
            full_prompt = prompt
            if system:
                full_prompt = f"System: {system}\n\nUser: {prompt}\n\nAssistant:"

            resolved_temperature = self.temperature if temperature is None else float(temperature)

            stream = self.llm(
                full_prompt,
                max_tokens=max_tokens,
                temperature=resolved_temperature,
                top_p=0.95,
                top_k=40,
                repeat_penalty=1.1,
                stop=["User:", "System:"],
                echo=False,
                stream=True,
            )

            buffer = ""
            for chunk in stream:
                token_text = chunk["choices"][0]["text"]
                buffer += token_text

                # Check for sentence boundaries and yield complete sentences
                while True:
                    match = self._SENTENCE_BOUNDARY.search(buffer)
                    if not match:
                        break
                    sentence = buffer[:match.start()].strip()
                    buffer = buffer[match.end():]
                    if sentence:
                        self.logger.debug("Streaming sentence: %s", sentence[:60])
                        yield sentence

            # Flush any remaining text in the buffer
            remaining = buffer.strip()
            if remaining:
                self.logger.debug("Streaming final fragment: %s", remaining[:60])
                yield remaining

        except Exception as exc:
            self.logger.error("Streaming generation failed: %s", exc)
