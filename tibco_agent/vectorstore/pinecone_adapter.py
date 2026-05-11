"""Pinecone adapter — cloud-hosted vector search."""
from __future__ import annotations

import logging
import re

from .base import VectorStoreAdapter

log = logging.getLogger(__name__)

_MAX_INDEX_NAME_LEN = 45


def _slugify(name: str) -> str:
    """Convert collection name to a valid Pinecone index name (lowercase, hyphens, ≤45 chars)."""
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:_MAX_INDEX_NAME_LEN]


class PineconeAdapter(VectorStoreAdapter):
    """
    Pinecone cloud vector store.

    vector_db_url  — Pinecone host URL shown in the console for your index
                     (e.g. https://my-index-xyz.svc.us-east1-gcp.pinecone.io).
                     Leave blank to let the adapter auto-discover it from the index name.
    vector_db_api_key — required Pinecone API key.
    """

    def __init__(self, url: str, api_key: str) -> None:
        if not api_key:
            raise ValueError(
                "Pinecone requires an API key. Set it in the agent's 'Vector DB API Key' field."
            )
        try:
            from pinecone import Pinecone
        except ImportError as exc:
            raise ImportError(
                "pinecone is required for the Pinecone adapter. "
                "Install it with: pip install 'pinecone>=3.0.0'"
            ) from exc

        from pinecone import Pinecone
        self._pc = Pinecone(api_key=api_key)
        self._host = url.rstrip("/") if url else ""

    def _get_index(self, collection_name: str):
        index_name = _slugify(collection_name)
        host = self._host or self._pc.describe_index(index_name).host
        return self._pc.Index(index_name, host=host)

    def ingest(self, chunks: list[dict], collection_name: str, reset: bool = True) -> int:
        if not chunks:
            return 0

        from pinecone import ServerlessSpec

        index_name = _slugify(collection_name)
        dim = len(chunks[0]["vector"])

        existing = [idx.name for idx in self._pc.list_indexes()]
        if index_name not in existing:
            self._pc.create_index(
                name=index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            log.info("Pinecone: created index '%s' (dim=%d).", index_name, dim)
        elif reset:
            idx = self._get_index(collection_name)
            idx.delete(delete_all=True)
            log.info("Pinecone: cleared index '%s'.", index_name)

        idx = self._get_index(collection_name)
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            idx.upsert(
                vectors=[
                    (
                        c.get("doc_id", "") or f"chunk-{i + j}",
                        c["vector"],
                        {
                            "text":        c["text"][:512],  # Pinecone metadata limit
                            "file_name":   c.get("file_name", ""),
                            "source_type": c.get("source_type", ""),
                            "product":     c.get("product", ""),
                            "section":     c.get("section", ""),
                        },
                    )
                    for j, c in enumerate(batch)
                ]
            )
        log.info("Pinecone: stored %d chunks in '%s'.", len(chunks), index_name)
        return len(chunks)

    def search(
        self,
        query: str,  # noqa: ARG002
        query_vector: list[float],
        collection_name: str,
        limit: int = 5,
        product_filter: str | None = None,
    ) -> list[dict]:
        try:
            idx = self._get_index(collection_name)
        except Exception:
            return []

        filt = {"product": {"$eq": product_filter}} if product_filter else None
        resp = idx.query(vector=query_vector, top_k=limit, filter=filt, include_metadata=True)

        if not resp.matches and product_filter:
            resp = idx.query(vector=query_vector, top_k=limit, include_metadata=True)

        return [
            {
                "text":      m.metadata.get("text", ""),
                "file_name": m.metadata.get("file_name", ""),
                "section":   m.metadata.get("section", ""),
                "product":   m.metadata.get("product", ""),
                "score":     m.score,
            }
            for m in resp.matches
        ]

    def delete_collection(self, collection_name: str) -> None:
        try:
            index_name = _slugify(collection_name)
            existing = [idx.name for idx in self._pc.list_indexes()]
            if index_name in existing:
                self._pc.delete_index(index_name)
                log.info("Pinecone: deleted index '%s'.", index_name)
        except Exception as exc:
            log.warning("Pinecone delete_collection failed: %s", exc)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            index_name = _slugify(collection_name)
            return index_name in [idx.name for idx in self._pc.list_indexes()]
        except Exception:
            return False
