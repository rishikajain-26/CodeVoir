"""SQLite-backed session persistence with in-memory cache."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sessions.db"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA synchronous=NORMAL")
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        _conn.commit()
    return _conn


def save_session(session: dict[str, Any]) -> None:
    session_id = session.get("session_id", "")
    if not session_id:
        return
    blob = json.dumps(session, default=str, ensure_ascii=False)
    with _lock:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO sessions (session_id, data, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, updated_at=datetime('now')""",
            (session_id, blob, session.get("created_at", "")),
        )
        conn.commit()


def load_session(session_id: str) -> dict[str, Any] | None:
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT data FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def load_all_sessions() -> dict[str, dict[str, Any]]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute("SELECT session_id, data FROM sessions").fetchall()
    result: dict[str, dict[str, Any]] = {}
    for session_id, data in rows:
        try:
            result[session_id] = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return result


def delete_session(session_id: str) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()


def session_count() -> int:
    with _lock:
        conn = _get_conn()
        row = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
    return row[0] if row else 0
