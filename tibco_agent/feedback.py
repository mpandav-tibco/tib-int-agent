from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

_DB_PATH = Path(
    os.environ.get("FEEDBACK_DB_PATH")
    or str(Path(__file__).resolve().parent.parent / "data" / "feedback.db")
)

# Module-level singleton — opened once, reused across all sessions.
# WAL mode allows concurrent readers; busy_timeout avoids "database is locked" under load.
_db_conn: sqlite3.Connection | None = None
_db_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    global _db_conn
    with _db_lock:
        if _db_conn is None:
            _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _db_conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
            _db_conn.execute("PRAGMA journal_mode=WAL")
            _db_conn.execute("PRAGMA busy_timeout=5000")
            _db_conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts        REAL    NOT NULL,
                    msg_idx   INTEGER NOT NULL,
                    rating    TEXT    NOT NULL,
                    question  TEXT,
                    response  TEXT
                )
            """)
            _db_conn.commit()
        return _db_conn


def record(msg_idx: int, rating: str, question: str = "", response: str = "") -> None:
    """Persist a thumbs-up or thumbs-down rating for a TARA response."""
    with _get_conn() as con:
        con.execute(
            "INSERT INTO feedback (ts, msg_idx, rating, question, response) VALUES (?,?,?,?,?)",
            (time.time(), msg_idx, rating, question[:1000], response[:2000]),
        )


def summary() -> dict:
    """Return total up/down counts for display."""
    with _get_conn() as con:
        row = con.execute(
            "SELECT rating, COUNT(*) FROM feedback GROUP BY rating"
        ).fetchall()
    return {r: c for r, c in row}
