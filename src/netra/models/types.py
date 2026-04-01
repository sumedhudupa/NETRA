from dataclasses import dataclass
from typing import Optional


@dataclass
class CommandIntent:
    action: str
    value: Optional[str] = None


@dataclass
class DocumentRef:
    name: str
    path: str


@dataclass
class SessionState:
    current_doc_index: int = 0
    current_doc_text: str = ""
    current_doc_name: str = ""
    current_doc_path: str = ""
    running: bool = True
    last_output: str = ""
