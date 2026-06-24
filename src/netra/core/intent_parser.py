import re
import json
from difflib import get_close_matches
from typing import List

from netra.models.types import CommandIntent
from netra.services.llama_service import LlamaCppService


class IntentParser:
    def __init__(self, llama: LlamaCppService) -> None:
        self.llama = llama

    def parse(self, command: str, doc_names: List[str]) -> CommandIntent:
        text = command.strip().lower()
        if text.startswith("and "):
            text = text[4:].strip()
            
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
        # Common combined command: user wants the current text translated (usually to English)
        # while also implying they want it read aloud.
        if "read and translate" in text or "translate and read" in text:
            return CommandIntent("translate", "to english")
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

        if self._is_generic_open_request(text):
            if len(doc_names) == 1:
                return CommandIntent("open_by_name", doc_names[0])
            if doc_names:
                return CommandIntent("list_docs")

        match = re.search(r"open\s+(?:file\s+)?(\d+)", text)
        if match:
            return CommandIntent("open_by_index", match.group(1))

        if text.startswith("open "):
            query = text.replace("open ", "", 1).strip()

            cleaned_query = self._normalize_open_query(query)
            if cleaned_query in {"", "file", "document"}:
                if len(doc_names) == 1:
                    return CommandIntent("open_by_name", doc_names[0])
                if doc_names:
                    return CommandIntent("list_docs")
            if query:
                closest = self._closest_doc_name(cleaned_query or query, doc_names)
                if closest:
                    return CommandIntent("open_by_name", closest)
                if len(doc_names) == 1 and self._looks_like_stt_open_error(cleaned_query or query):
                    return CommandIntent("open_by_name", doc_names[0])
                return CommandIntent("open_not_found", cleaned_query or query)

        llm_intent = self._llm_parse(text, doc_names)
        return llm_intent if llm_intent.action != "unknown" else CommandIntent("general_query", text)

    def _closest_doc_name(self, query: str, doc_names: List[str]) -> str:
        stems = [name.rsplit(".", 1)[0].lower().replace("_", " ") for name in doc_names]
        matched = get_close_matches(query, stems, n=1, cutoff=0.4)
        if not matched:
            return ""
        index = stems.index(matched[0])
        return doc_names[index]

    def _is_generic_open_request(self, text: str) -> bool:
        generic_phrases = {
            "open file",
            "open the file",
            "open document",
            "open the document",
            "open my document",
            "open my file",
        }
        return text in generic_phrases

    def _normalize_open_query(self, query: str) -> str:
        normalized = query.strip().lower()
        prefixes = (
            "the ",
            "my ",
            "a ",
            "an ",
        )
        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if normalized.startswith(prefix):
                    normalized = normalized[len(prefix):].strip()
                    changed = True
        return normalized

    def _looks_like_stt_open_error(self, query: str) -> bool:
        tokens = [token for token in re.split(r"\s+", query.strip().lower()) if token]
        if not tokens:
            return False
        noise_tokens = {
            "file", "document", "one", "won", "find", "fine", "by", "it", "watched",
        }
        return all(token in noise_tokens for token in tokens)

    def _llm_parse(self, command: str, doc_names: List[str]) -> CommandIntent:
        if not self.llama.is_available():
            return CommandIntent("unknown")

        docs_text = ", ".join(doc_names[:30]) if doc_names else "none"
        prompt = (
            "You are NETRA, an intelligent voice assistant for the blind.\n"
            "Map the user's text to exactly ONE action.\n"
            "\nAllowed actions:\n"
            "- open_by_name (value: document name)\n"
            "- open_by_index (value: 1-based index as string)\n"
            "- list_docs (value: empty)\n"
            "- read_current (value: empty)\n"
            "- camera_ocr (value: empty)\n"
            "- summarize | explain | quiz (value: empty)\n"
            "- translate (value: target language, e.g. 'spanish')\n"
            "- define (value: term or question)\n"
            "- take_note (value: note content)\n"
            "- save_note | read_last_note (value: empty)\n"
            "- delete_note (value: note name)\n"
            "- bookmark | go_bookmark | close_document | repeat | start_over | time | battery (value: empty)\n"
            "- general_query (value: user text)\n"
            "\nRules:\n"
            "1. Output MUST be strict JSON with keys action and value ONLY. No markdown.\n"
            "2. If unsure, use general_query.\n"
            "3. 'open file 2' => open_by_index with value '2'.\n"
            "4. 'translate to spanish' => translate with value 'spanish'.\n"
            "\nExamples:\n"
            "User: open file 1\nOutput: {\"action\":\"open_by_index\",\"value\":\"1\"}\n"
            "User: read this\nOutput: {\"action\":\"read_current\",\"value\":\"\"}\n"
            "User: summarize\nOutput: {\"action\":\"summarize\",\"value\":\"\"}\n"
            "User: translate to spanish\nOutput: {\"action\":\"translate\",\"value\":\"spanish\"}\n"
            "\n"
            f"Available documents: {docs_text}\n"
            f"User: {command}\n"
            "Output:"
        )
        try:
            raw = self.llama.generate(prompt, timeout=30).strip()
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
