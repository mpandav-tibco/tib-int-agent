from __future__ import annotations

import sqlite3
import time
from pathlib import Path

_DB_PATH = Path("./data/feedback.db")


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        REAL    NOT NULL,
            msg_idx   INTEGER NOT NULL,
            rating    TEXT    NOT NULL,
            question  TEXT,
            response  TEXT
        )
    """)
    con.commit()
    return con


def record(msg_idx: int, rating: str, question: str = "", response: str = "") -> None:
    """Persist a thumbs-up or thumbs-down rating for a TARA response."""
    with _conn() as con:
        con.execute(
            "INSERT INTO feedback (ts, msg_idx, rating, question, response) VALUES (?,?,?,?,?)",
            (time.time(), msg_idx, rating, question[:1000], response[:2000]),
        )


def summary() -> dict:
    """Return total up/down counts for display."""
    with _conn() as con:
        row = con.execute(
            "SELECT rating, COUNT(*) FROM feedback GROUP BY rating"
        ).fetchall()
    return {r: c for r, c in row}
