"""PostgreSQL + pgvector adapter — vector similarity search via SQL."""
from __future__ import annotations

import logging
import threading

from .base import VectorStoreAdapter

log = logging.getLogger(__name__)

_conns: dict[str, object] = {}
_lock = threading.Lock()


def _safe_table(name: str) -> str:
    """Sanitize collection name for use as a SQL table identifier."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name).lower()


class PgvectorAdapter(VectorStoreAdapter):
    """
    Stores and searches vectors using PostgreSQL with the pgvector extension.

    vector_db_url must be a PostgreSQL DSN:
      postgresql://user:password@host:5432/dbname

    Requirements (install separately):
      pip install psycopg2-binary pgvector
    """

    def __init__(self, url: str) -> None:
        if not url:
            raise ValueError(
                "pgvector requires a PostgreSQL connection string in 'Vector DB URL'. "
                "Format: postgresql://user:password@host:5432/dbname"
            )
        try:
            import psycopg2  # noqa: F401
            import pgvector  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "psycopg2-binary and pgvector are required for the pgvector adapter. "
                "Install them with: pip install psycopg2-binary pgvector"
            ) from exc
        self._dsn = url

    def _get_conn(self):
        import psycopg2
        from pgvector.psycopg2 import register_vector
        with _lock:
            conn = _conns.get(self._dsn)
            if conn is None or conn.closed:
                conn = psycopg2.connect(self._dsn)
                conn.autocommit = False
                register_vector(conn)
                conn.cursor().execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
                _conns[self._dsn] = conn
            return conn

    def _ensure_table(self, conn, table: str, dim: int) -> None:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id          TEXT PRIMARY KEY,
                    text        TEXT NOT NULL,
                    embedding   vector({dim}),
                    file_name   TEXT DEFAULT '',
                    source_type TEXT DEFAULT '',
                    product     TEXT DEFAULT '',
                    section     TEXT DEFAULT ''
                )
            """)
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {table}_vec_idx "
                f"ON {table} USING ivfflat (embedding vector_cosine_ops)"
            )
        conn.commit()

    def ingest(self, chunks: list[dict], collection_name: str, reset: bool = True) -> int:
        import numpy as np

        if not chunks:
            return 0

        table = _safe_table(collection_name)
        dim = len(chunks[0]["vector"])
        conn = self._get_conn()

        if reset:
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()
            log.info("pgvector: dropped table '%s'.", table)

        self._ensure_table(conn, table, dim)

        with conn.cursor() as cur:
            for c in chunks:
                cur.execute(
                    f"INSERT INTO {table} (id, text, embedding, file_name, source_type, product, section) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET "
                    "text=EXCLUDED.text, embedding=EXCLUDED.embedding, "
                    "file_name=EXCLUDED.file_name, source_type=EXCLUDED.source_type, "
                    "product=EXCLUDED.product, section=EXCLUDED.section",
                    (
                        c.get("doc_id", ""),
                        c["text"],
                        np.array(c["vector"]),
                        c.get("file_name", ""),
                        c.get("source_type", ""),
                        c.get("product", ""),
                        c.get("section", ""),
                    ),
                )
        conn.commit()
        log.info("pgvector: stored %d chunks in '%s'.", len(chunks), table)
        return len(chunks)

    def search(
        self,
        query: str,  # noqa: ARG002
        query_vector: list[float],
        collection_name: str,
        limit: int = 5,
        product_filter: str | None = None,
    ) -> list[dict]:
        import numpy as np

        table = _safe_table(collection_name)
        conn = self._get_conn()

        def _run(filt):
            with conn.cursor() as cur:
                where = "WHERE product = %s" if filt else ""
                params = [np.array(query_vector), limit]
                if filt:
                    params.insert(1, filt)
                cur.execute(
                    f"SELECT text, file_name, section, product, "
                    f"1 - (embedding <=> %s::vector) AS score "
                    f"FROM {table} {where} "
                    f"ORDER BY embedding <=> %s::vector LIMIT %s",
                    [np.array(query_vector)] + ([filt] if filt else []) + [np.array(query_vector), limit],
                )
                return cur.fetchall()

        try:
            rows = _run(product_filter)
            if not rows and product_filter:
                rows = _run(None)
        except Exception as exc:
            log.warning("pgvector search failed: %s", exc)
            return []

        return [
            {"text": r[0], "file_name": r[1], "section": r[2], "product": r[3], "score": float(r[4])}
            for r in rows
        ]

    def delete_collection(self, collection_name: str) -> None:
        try:
            table = _safe_table(collection_name)
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()
            log.info("pgvector: dropped table '%s'.", table)
        except Exception as exc:
            log.warning("pgvector delete_collection failed: %s", exc)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            table = _safe_table(collection_name)
            conn = self._get_conn()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
                    (table,),
                )
                return cur.fetchone()[0]
        except Exception:
            return False
