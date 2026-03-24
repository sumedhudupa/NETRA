from datetime import datetime
from pathlib import Path
from typing import List
import logging

from netra.models.types import CommandIntent, DocumentRef, SessionState
from netra.services.braille_service import BrailleService
from netra.services.document_service import DocumentService
from netra.services.ollama_service import OllamaService
from netra.services.store_service import StoreService
from netra.services.tts_service import TTSService
from netra.hardware.interfaces import HardwareAdapter


class ConversationAgent:
    """
    Basic command-first conversational entity.
    No history is maintained for this phase.
    """

    def __init__(
        self,
        state: SessionState,
        documents: List[DocumentRef],
        document_service: DocumentService,
        ollama: OllamaService,
        braille: BrailleService,
        tts: TTSService,
        store: StoreService,
        hardware: HardwareAdapter,
        braille_output_file: str,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        self.state = state
        self.documents = documents
        self.document_service = document_service
        self.ollama = ollama
        self.braille = braille
        self.tts = tts
        self.store = store
        self.hardware = hardware
        self.pending_note = ""
        self.braille_output_file = braille_output_file

    def handle_intent(self, intent: CommandIntent) -> None:
        action = intent.action
        self.logger.info("Handling intent action=%s value=%s", intent.action, intent.value)

        if action == "exit":
            self.state.running = False
            self._say("Shutting down NETRA.")
            return

        if action == "help":
            self._say(
                "You can speak naturally. For example: open my physics file, summarize this, explain this, "
                "take a note this is important, bookmark this, read this, or exit."
            )
            return

        if action == "close_document":
            self.state.current_doc_text = ""
            self.state.current_doc_name = ""
            self._say("Closed active document.")
            return

        if action == "repeat":
            if not self.state.last_output:
                self._say("No previous output available.")
                return
            self._render_text(self.state.last_output)
            return

        if action == "list_docs":
            if not self.documents:
                self._say("No documents found.")
                return
            names = ", ".join(doc.name for doc in self.documents)
            self._say(f"Available documents are: {names}")
            return

        if action == "open_by_index":
            self._open_by_index(intent.value)
            return

        if action == "open_by_name":
            self._open_by_name(intent.value or "")
            return

        if action == "camera_ocr":
            self._camera_capture_flow()
            return

        if action == "read_current":
            if not self.state.current_doc_text:
                self._say("No active document. Say open file first.")
                return
            self._render_text(self.state.current_doc_text)
            return

        if action == "summarize":
            self._llm_task("Summarize this in 4 short sentences", self.state.current_doc_text)
            return

        if action == "explain":
            self._llm_task("Explain this in simple language for a student", self.state.current_doc_text)
            return

        if action == "quiz":
            self._llm_task("Generate 5 oral quiz questions from this", self.state.current_doc_text)
            return

        if action == "define":
            query = intent.value or "Define the requested term from this text"
            self._llm_task(query, self.state.current_doc_text)
            return

        if action == "translate":
            target = "english"
            raw = intent.value or ""
            if "to" in raw:
                target = raw.split("to", 1)[1].strip() or target
            self._llm_task(f"Translate this to {target}", self.state.current_doc_text)
            return

        if action == "take_note":
            payload = (intent.value or "").strip()
            if not payload:
                self._say("Please say take a note followed by the note content.")
                return
            self.pending_note = payload
            self._say("Note captured. Say save note to store it.")
            return

        if action == "save_note":
            if not self.pending_note and self.state.current_doc_text:
                self.pending_note = self.state.current_doc_text[:500]
            if not self.pending_note:
                self._say("No note content available.")
                return
            name = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.store.save_note(name, self.pending_note)
            self.pending_note = ""
            self._say("Note saved.")
            return

        if action == "delete_note":
            note_name = (intent.value or "").strip()
            if not note_name:
                self._say("Please provide the note name to delete.")
                return
            ok = self.store.delete_note(note_name)
            if not ok:
                self._say("Note not found.")
                return
            self._say("Note deleted.")
            return

        if action == "read_last_note":
            note = self.store.get_last_note()
            if not note:
                self._say("No notes found.")
                return
            self._render_text(note[1])
            return

        if action == "bookmark":
            if not self.state.current_doc_name:
                self._say("No active document to bookmark.")
                return
            self.store.save_bookmark(self.state.current_doc_name, self.state.current_doc_index)
            self._say("Bookmark saved.")
            return

        if action == "go_bookmark":
            if not self.state.current_doc_name:
                self._say("No active document.")
                return
            position = self.store.get_latest_bookmark(self.state.current_doc_name)
            if position is None:
                self._say("No bookmark for this document.")
                return
            self.state.current_doc_index = max(0, min(position, len(self.documents) - 1))
            self._load_current_doc()
            return

        if action == "time":
            now = datetime.now().strftime("%I:%M %p")
            self._say(f"The time is {now}.")
            return

        if action == "battery":
            self._say("Battery sensor is not connected yet.")
            return

        if action == "start_over":
            self.state.current_doc_text = ""
            self.state.current_doc_name = ""
            self.pending_note = ""
            self._say("Session reset complete.")
            return

        if action == "general_query":
            query = (intent.value or "").strip()
            if not query:
                self._say("I did not catch that. Please say it again.")
                return
            if self.state.current_doc_text:
                self._llm_task(query, self.state.current_doc_text)
                return
            self._llm_general(query)
            return

        self._say("Command not understood.")

    def _open_by_index(self, value: str | None) -> None:
        if not value:
            self._say("Please provide a file number.")
            return
        try:
            idx = int(value) - 1
        except ValueError:
            self._say("Invalid file number.")
            return
        if idx < 0 or idx >= len(self.documents):
            self._say("File number out of range.")
            return
        self.state.current_doc_index = idx
        self._load_current_doc()

    def _open_by_name(self, value: str) -> None:
        for index, doc in enumerate(self.documents):
            if doc.name.lower() == value.lower():
                self.state.current_doc_index = index
                self._load_current_doc()
                return

        normalized = value.lower().replace("_", " ").replace("-", " ")
        for index, doc in enumerate(self.documents):
            stem = Path(doc.name).stem.lower().replace("_", " ").replace("-", " ")
            if normalized in stem:
                self.state.current_doc_index = index
                self._load_current_doc()
                return

        self._say("Could not find that document.")

    def _load_current_doc(self) -> None:
        if not self.documents:
            self._say("No documents available.")
            return

        doc = self.documents[self.state.current_doc_index]
        self.state.current_doc_name = doc.name
        self.state.current_doc_text = self.document_service.extract_text(doc.path)
        if not self.state.current_doc_text:
            self._say("Document loaded but no readable text found.")
            return

        self._say(f"Loaded {Path(doc.name).stem}. Say read this or summarize.")

    def _camera_capture_flow(self) -> None:
        self._say("Camera mode. Capture image now.")
        image_path = self.hardware.capture_image_path()
        if not image_path or not Path(image_path).exists():
            self._say("Image path invalid.")
            return

        text = self.document_service.extract_ocr_from_camera_image(image_path)
        if not text:
            self.logger.warning("OCR confidence too low for image %s", image_path)
            self._say("Low confidence OCR. Please recapture with better alignment.")
            return

        self.state.current_doc_text = text
        self.state.current_doc_name = "camera_capture"
        self.store.save_note(f"ocr_{datetime.now().strftime('%Y%m%d_%H%M%S')}", text)
        self._say("OCR complete.")
        self._render_text(text)

    def _llm_task(self, instruction: str, source_text: str) -> None:
        if not source_text:
            self._say("No active text. Open a document or capture image first.")
            return
        if not self.ollama.is_available():
            self._say("Ollama is not reachable right now.")
            return

        prompt = f"{instruction}. Keep response concise and voice-friendly.\\n\\nText:\\n{source_text[:8000]}"
        try:
            result = self.ollama.generate(prompt, timeout=90)
        except Exception:
            self._say("LLM request failed.")
            return
        self._render_text(result)

    def _llm_general(self, query: str) -> None:
        if not self.ollama.is_available():
            self._say("I cannot reach the local language model right now.")
            return

        prompt = (
            "You are NETRA, a concise voice assistant for blind users. "
            "Answer clearly and briefly in spoken style. "
            f"User query: {query}"
        )
        try:
            result = self.ollama.generate(prompt, timeout=60)
        except Exception:
            self._say("I could not process that request.")
            return
        self._render_text(result)

    def _render_text(self, text: str) -> None:
        if not text.strip():
            self._say("Nothing to read.")
            return

        self.state.last_output = text

        self.tts.speak(text, self.hardware)

        _, patterns = self.braille.text_to_patterns(text)
        unicode_braille = self.braille.export_unicode_braille(patterns, self.braille_output_file)
        preview = unicode_braille[:80].replace("\n", " ")
        self.logger.info("Braille unicode preview: %s", preview)
        chunks = self.braille.chunk_patterns(patterns)
        total = len(chunks)
        self.logger.info("Rendering %d braille chunk(s)", total)
        for idx, chunk in enumerate(chunks, start=1):
            self.hardware.display_braille_cells(chunk)
            if idx < total:
                self.hardware.wait_for_scroll()

    def _say(self, text: str) -> None:
        self.state.last_output = text
        self.tts.speak(text, self.hardware)
