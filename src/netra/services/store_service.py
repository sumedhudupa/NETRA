import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple


class StoreService:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_name TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def save_note(self, name: str, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO notes (name, content) VALUES (?, ?)",
                (name, content),
            )
            conn.commit()

    def get_last_note(self) -> Optional[Tuple[str, str]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, content FROM notes ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return row if row else None

    def get_note(self, name: str) -> Optional[Tuple[str, str]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, content FROM notes WHERE name = ? ORDER BY id DESC LIMIT 1",
                (name,),
            ).fetchone()
            return row if row else None

    def append_note(self, name: str, content_suffix: str) -> bool:
        existing = self.get_note(name)
        if not existing:
            return False

        updated = f"{existing[1]}\n{content_suffix}".strip()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO notes (name, content) VALUES (?, ?)",
                (name, updated),
            )
            conn.commit()
        return True

    def delete_note(self, name: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM notes WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

    def list_notes(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name FROM notes ORDER BY id DESC").fetchall()
            return [row[0] for row in rows]

    def save_bookmark(self, doc_name: str, position: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO bookmarks (doc_name, position) VALUES (?, ?)",
                (doc_name, position),
            )
            conn.commit()

    def get_latest_bookmark(self, doc_name: str) -> Optional[int]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT position FROM bookmarks WHERE doc_name = ? ORDER BY id DESC LIMIT 1",
                (doc_name,),
            ).fetchone()
            return int(row[0]) if row else None
