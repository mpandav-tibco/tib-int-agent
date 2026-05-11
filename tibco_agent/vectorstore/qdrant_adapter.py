"""Qdrant adapter — vector search (cosine similarity)."""
from __future__ import annotations

import logging
import uuid

from .base import VectorStoreAdapter

log = logging.getLogger(__name__)


class QdrantAdapter(VectorStoreAdapter):
    """
    Connects to a Qdrant instance. url="" uses in-memory mode (dev/test only).

    url examples:
      "http://localhost:6333"   — local Qdrant
      "https://xyz.qdrant.tech" — Qdrant Cloud (provide api_key)
    """

    def __init__(self, url: str, api_key: str = "") -> None:
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise ImportError(
                "qdrant-client is required for the Qdrant adapter. "
                "Install it with: pip install 'qdrant-client>=1.9.0'"
            ) from exc

        from qdrant_client import QdrantClient
        if url:
            self._client = QdrantClient(url=url, api_key=api_key or None)
            log.info("Qdrant: connecting to %s", url)
        else:
            self._client = QdrantClient(":memory:")
            log.info("Qdrant: using in-memory mode (data not persisted)")

    def ingest(self, chunks: list[dict], collection_name: str, reset: bool = True) -> int:
        from qdrant_client.models import Distance, PointStruct, VectorParams

        if not chunks:
            return 0

        dim = len(chunks[0]["vector"])

        if reset and self._client.collection_exists(collection_name):
            self._client.delete_collection(collection_name)
            log.info("Qdrant: dropped collection '%s'.", collection_name)

        if not self._client.collection_exists(collection_name):
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            log.info("Qdrant: created collection '%s' (dim=%d).", collection_name, dim)

        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, c.get("doc_id", "") or str(i))),
                vector=c["vector"],
                payload={
                    "text":        c["text"],
                    "file_name":   c.get("file_name", ""),
                    "source_type": c.get("source_type", ""),
                    "product":     c.get("product", ""),
                    "section":     c.get("section", ""),
                },
            )
            for i, c in enumerate(chunks)
        ]
        self._client.upsert(collection_name=collection_name, points=points)
        log.info("Qdrant: stored %d chunks in '%s'.", len(chunks), collection_name)
        return len(chunks)

    def search(
        self,
        query: str,  # noqa: ARG002 — Qdrant sparse search not enabled here
        query_vector: list[float],
        collection_name: str,
        limit: int = 5,
        product_filter: str | None = None,
    ) -> list[dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        if not self._client.collection_exists(collection_name):
            return []

        filt = None
        if product_filter:
            filt = Filter(
                must=[FieldCondition(key="product", match=MatchValue(value=product_filter))]
            )

        hits = self._client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=filt,
        )

        if not hits and product_filter:
            hits = self._client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
            )

        return [
            {
                "text":      h.payload.get("text", ""),
                "file_name": h.payload.get("file_name", ""),
                "section":   h.payload.get("section", ""),
                "product":   h.payload.get("product", ""),
                "score":     h.score,
            }
            for h in hits
        ]

    def delete_collection(self, collection_name: str) -> None:
        try:
            if self._client.collection_exists(collection_name):
                self._client.delete_collection(collection_name)
                log.info("Qdrant: dropped collection '%s'.", collection_name)
        except Exception as exc:
            log.warning("Qdrant delete_collection failed: %s", exc)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            return self._client.collection_exists(collection_name)
        except Exception:
            return False
