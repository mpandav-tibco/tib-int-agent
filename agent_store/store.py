"""SQLite-backed store for AgentForge agent configurations."""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .models import Agent

_DB_PATH = Path(
    os.environ.get("AGENTS_DB_PATH")
    or str(Path(__file__).resolve().parent.parent / "data" / "agents.db")
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    title           TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    system_prompt   TEXT NOT NULL DEFAULT '',
    collection_name TEXT NOT NULL,
    llm_provider    TEXT NOT NULL DEFAULT 'ollama',
    llm_model       TEXT NOT NULL DEFAULT '',
    llm_api_key     TEXT NOT NULL DEFAULT '',
    llm_api_base    TEXT NOT NULL DEFAULT '',
    embed_model     TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'draft'
)
"""

_COLUMNS = [
    "id", "name", "title", "description", "system_prompt", "collection_name",
    "llm_provider", "llm_model", "llm_api_key", "llm_api_base", "embed_model",
    "created_at", "updated_at", "status",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_agent(row: tuple) -> Agent:
    return Agent(**dict(zip(_COLUMNS, row)))


class AgentStore:
    """Thread-safe SQLite store for Agent configs. One instance per process."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _DB_PATH
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA busy_timeout=5000")
                self._conn.execute(_CREATE_TABLE)
                self._conn.commit()
            return self._conn

    # ── write ops ─────────────────────────────────────────────────────────────

    def create(
        self,
        name: str,
        title: str = "",
        description: str = "",
        system_prompt: str = "",
        llm_provider: str = "ollama",
        llm_model: str = "",
        llm_api_key: str = "",
        llm_api_base: str = "",
        embed_model: str = "",
    ) -> Agent:
        agent_id = uuid.uuid4().hex
        collection_name = f"Agent_{agent_id[:8].capitalize()}"
        now = _now()
        agent = Agent(
            id=agent_id,
            name=name,
            title=title,
            description=description,
            system_prompt=system_prompt,
            collection_name=collection_name,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            llm_api_base=llm_api_base,
            embed_model=embed_model,
            created_at=now,
            updated_at=now,
            status="draft",
        )
        cols = ", ".join(_COLUMNS)
        placeholders = ", ".join("?" * len(_COLUMNS))
        with self._get_conn() as con:
            con.execute(
                f"INSERT INTO agents ({cols}) VALUES ({placeholders})",
                tuple(getattr(agent, c) for c in _COLUMNS),
            )
        return agent

    def update(self, agent_id: str, **fields) -> Agent:
        """Update arbitrary fields on an existing agent. Returns the updated Agent."""
        allowed = set(_COLUMNS) - {"id", "created_at", "collection_name"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Cannot update read-only fields: {bad}")
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k}=?" for k in fields)
        values = list(fields.values()) + [agent_id]
        with self._get_conn() as con:
            cur = con.execute(f"UPDATE agents SET {set_clause} WHERE id=?", values)
            if cur.rowcount == 0:
                raise KeyError(agent_id)
        return self.get(agent_id)  # type: ignore[return-value]

    def set_status(self, agent_id: str, status: str) -> None:
        with self._get_conn() as con:
            con.execute(
                "UPDATE agents SET status=?, updated_at=? WHERE id=?",
                (status, _now(), agent_id),
            )

    def delete(self, agent_id: str) -> None:
        with self._get_conn() as con:
            con.execute("DELETE FROM agents WHERE id=?", (agent_id,))

    # ── read ops ──────────────────────────────────────────────────────────────

    def get(self, agent_id: str) -> Agent | None:
        cols = ", ".join(_COLUMNS)
        con = self._get_conn()
        row = con.execute(f"SELECT {cols} FROM agents WHERE id=?", (agent_id,)).fetchone()
        return _row_to_agent(row) if row else None

    def list_all(self) -> list[Agent]:
        cols = ", ".join(_COLUMNS)
        con = self._get_conn()
        rows = con.execute(f"SELECT {cols} FROM agents ORDER BY created_at DESC").fetchall()
        return [_row_to_agent(r) for r in rows]


# Module-level singleton used by the FastAPI router and Chainlit app.
store = AgentStore()
