from __future__ import annotations
import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".clawlite" / "memory.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL)")
    return conn


def add_note(text: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO notes(text) VALUES (?)", (text,))


def search_notes(query: str, limit: int = 10) -> list[str]:
    like = f"%{query}%"
    with _conn() as c:
        rows = c.execute("SELECT text FROM notes WHERE text LIKE ? ORDER BY id DESC LIMIT ?", (like, limit)).fetchall()
    return [r[0] for r in rows]
