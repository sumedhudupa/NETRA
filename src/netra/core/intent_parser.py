import re
import json
from difflib import get_close_matches
from typing import List

from netra.models.types import CommandIntent
from netra.services.ollama_service import OllamaService


class IntentParser:
    def __init__(self, ollama: OllamaService) -> None:
        self.ollama = ollama

    def parse(self, command: str, doc_names: List[str]) -> CommandIntent:
        text = command.strip().lower()
        if not text:
            return CommandIntent("unknown")

        # Minimal always-available controls.
        if text in {"exit", "quit", "shutdown"}:
            return CommandIntent("exit")
        if "help" in text:
            return CommandIntent("help")
        if "list" in text and ("doc" in text or "file" in text):
            return CommandIntent("list_docs")
        if "read this" in text or text == "read" or "read document" in text or "read it" in text:
            return CommandIntent("read_current")
        if "camera" in text or "capture" in text:
            return CommandIntent("camera_ocr")
        if "take a note" in text or text.startswith("note this"):
            payload = text.replace("take a note", "", 1).replace("note this", "", 1).strip()
            return CommandIntent("take_note", payload)
        if "save note" in text:
            return CommandIntent("save_note")
        if "read my last note" in text or "last note" in text:
            return CommandIntent("read_last_note")
        if text.startswith("delete note "):
            return CommandIntent("delete_note", text.replace("delete note ", "", 1).strip())
        if "bookmark" in text and "go" not in text:
            return CommandIntent("bookmark")
        if "go to my bookmark" in text or "go bookmark" in text:
            return CommandIntent("go_bookmark")
        if "close document" in text or text == "close":
            return CommandIntent("close_document")
        if "repeat" in text:
            return CommandIntent("repeat")
        if text == "stop":
            return CommandIntent("stop")
        if text == "start over":
            return CommandIntent("start_over")
        if "battery" in text:
            return CommandIntent("battery")
        if "time" in text:
            return CommandIntent("time")

        match = re.search(r"open\s+(?:file\s+)?(\d+)", text)
        if match:
            return CommandIntent("open_by_index", match.group(1))

        if text.startswith("open "):
            query = text.replace("open ", "", 1).strip()
            if query:
                closest = self._closest_doc_name(query, doc_names)
                if closest:
                    return CommandIntent("open_by_name", closest)
                return CommandIntent("open_by_name", query)

        llm_intent = self._llm_parse(text, doc_names)
        return llm_intent if llm_intent.action != "unknown" else CommandIntent("general_query", text)

    def _closest_doc_name(self, query: str, doc_names: List[str]) -> str:
        stems = [name.rsplit(".", 1)[0].lower().replace("_", " ") for name in doc_names]
        matched = get_close_matches(query, stems, n=1, cutoff=0.4)
        if not matched:
            return ""
        index = stems.index(matched[0])
        return doc_names[index]

    def _llm_parse(self, command: str, doc_names: List[str]) -> CommandIntent:
        if not self.ollama.is_available():
            return CommandIntent("unknown")

        docs_text = ", ".join(doc_names[:30]) if doc_names else "none"
        prompt = (
            "You are NETRA, an intelligent voice assistant for the blind. "
            "Your goal is to map user natural language to specific system actions. "
            "Actions: open_by_name, read_current, camera_ocr, summarize, explain, quiz, translate, list_docs, general_query. "
            "\n"
            "Rules:\n"
            "1. If user mentions 'braille', 'convert', 'translate', map to translate action.\n"
            "2. If user mentions 'read', 'listen', 'hear', map to read_current action for open doc.\n"
            "3. If user says 'tell me about' or 'what is in', map to summarize if doc is open, camera_ocr if not.\n"
            "4. If doc is already open, assume actions like 'braille' or 'read' refer to that doc.\n"
            "5. Social cues map to general_query.\n"
            "\n"
            "Return ONLY strict JSON: {\"action\":\"...\",\"value\":\"...\"}\n"
            f"Available documents: {docs_text}\n"
            f"User says: \"{command}\""
        )
        try:
            raw = self.ollama.generate(prompt, timeout=30).strip()
            # Clean possible markdown
            if "{" in raw:
                raw = raw[raw.find("{"):raw.rfind("}")+1]
            data = json.loads(raw)
            action = str(data.get("action", "unknown")).strip().lower()
            value = data.get("value")
            
            allowed = {
                "open_by_name", "open_by_index", "camera_ocr", "read_current",
                "summarize", "explain", "quiz", "define", "translate",
                "take_note", "save_note", "read_last_note", "delete_note",
                "bookmark", "go_bookmark", "close_document", "repeat",
                "start_over", "time", "battery", "list_docs", "general_query", "unknown"
            }
            
            if action in allowed:
                return CommandIntent(action, str(value) if value is not None else None)
            return CommandIntent("unknown")
        except Exception:
            return CommandIntent("unknown")
