"""ChromaDB adapter — vector-only search (no BM25 hybrid)."""
from __future__ import annotations

import logging

from .base import VectorStoreAdapter

log = logging.getLogger(__name__)


class ChromaAdapter(VectorStoreAdapter):
    """
    Supports two modes:
    - url=""   → embedded PersistentClient stored in data/chroma/
    - url=str  → HttpClient connecting to a running Chroma server
    """

    def __init__(self, url: str) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for the ChromaDB adapter. "
                "Install it with: pip install 'chromadb>=0.5.0'"
            ) from exc

        if url:
            # Parse host and port from url like "http://localhost:8000"
            bare = url.removeprefix("https://").removeprefix("http://")
            host, _, port_str = bare.rstrip("/").partition(":")
            port = int(port_str) if port_str.isdigit() else 8000
            self._client = chromadb.HttpClient(host=host or "localhost", port=port)
            log.info("ChromaDB: connecting to server at %s", url)
        else:
            self._client = chromadb.PersistentClient(path="data/chroma")
            log.info("ChromaDB: using embedded storage at data/chroma/")

    def ingest(self, chunks: list[dict], collection_name: str, reset: bool = True) -> int:
        if reset:
            try:
                self._client.delete_collection(collection_name)
            except Exception:
                pass

        col = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        if not chunks:
            return 0

        col.upsert(
            ids=[c["doc_id"] for c in chunks],
            embeddings=[c["vector"] for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[
                {
                    "file_name":   c.get("file_name", ""),
                    "source_type": c.get("source_type", ""),
                    "product":     c.get("product", ""),
                    "section":     c.get("section", ""),
                }
                for c in chunks
            ],
        )
        log.info("ChromaDB: stored %d chunks in '%s'.", len(chunks), collection_name)
        return len(chunks)

    def search(
        self,
        query: str,  # noqa: ARG002 — ChromaDB doesn't support keyword search
        query_vector: list[float],
        collection_name: str,
        limit: int = 5,
        product_filter: str | None = None,
    ) -> list[dict]:
        try:
            col = self._client.get_collection(collection_name)
        except Exception:
            return []

        where = {"product": product_filter} if product_filter else None
        try:
            results = col.query(
                query_embeddings=[query_vector],
                n_results=min(limit, col.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        if not results["documents"] or not results["documents"][0]:
            if product_filter:
                # Retry without product filter
                try:
                    results = col.query(
                        query_embeddings=[query_vector],
                        n_results=min(limit, col.count()),
                        include=["documents", "metadatas", "distances"],
                    )
                except Exception:
                    return []
            else:
                return []

        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]
        return [
            {
                "text":      d,
                "file_name": m.get("file_name", ""),
                "section":   m.get("section", ""),
                "product":   m.get("product", ""),
                "score":     1.0 / (1.0 + dist),
            }
            for d, m, dist in zip(docs, metas, dists)
        ]

    def delete_collection(self, collection_name: str) -> None:
        try:
            self._client.delete_collection(collection_name)
            log.info("ChromaDB: dropped collection '%s'.", collection_name)
        except Exception as exc:
            log.warning("ChromaDB delete_collection failed: %s", exc)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            self._client.get_collection(collection_name)
            return True
        except Exception:
            return False
