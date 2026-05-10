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
                    response  TEXT,
                    agent_id  TEXT
                )
            """)
            # Add agent_id column to existing DBs that predate this schema version
            try:
                _db_conn.execute("ALTER TABLE feedback ADD COLUMN agent_id TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            _db_conn.commit()
        return _db_conn


def record(
    msg_idx: int,
    rating: str,
    question: str = "",
    response: str = "",
    agent_id: str = "",
) -> None:
    """Persist a thumbs-up or thumbs-down rating for an agent response."""
    with _get_conn() as con:
        con.execute(
            "INSERT INTO feedback (ts, msg_idx, rating, question, response, agent_id)"
            " VALUES (?,?,?,?,?,?)",
            (time.time(), msg_idx, rating, question[:1000], response[:2000], agent_id or None),
        )


def summary(agent_id: str = "") -> dict:
    """Return total up/down counts. Optionally scoped to a specific agent."""
    with _get_conn() as con:
        if agent_id:
            rows = con.execute(
                "SELECT rating, COUNT(*) FROM feedback WHERE agent_id=? GROUP BY rating",
                (agent_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT rating, COUNT(*) FROM feedback GROUP BY rating"
            ).fetchall()
    return {r: c for r, c in rows}
