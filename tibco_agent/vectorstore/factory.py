"""Factory for VectorStoreAdapter instances — one singleton per (type, url, api_key)."""
from __future__ import annotations

import logging
import threading

from .base import VectorStoreAdapter

log = logging.getLogger(__name__)

_registry: dict[tuple, VectorStoreAdapter] = {}
_lock = threading.Lock()

_SUPPORTED = {"weaviate", "chroma", "qdrant", "pinecone", "pgvector", "activespaces"}


def get_adapter(
    vector_db: str,
    url: str = "",
    api_key: str = "",
) -> VectorStoreAdapter:
    """Return (and cache) a VectorStoreAdapter for the given (type, url, api_key) triple.

    Adapters are singletons per unique (vector_db, url, api_key) combination so
    connection objects are reused across multiple search_knowledge() calls.
    """
    db = (vector_db or "weaviate").lower().strip()
    key = (db, url, api_key)

    with _lock:
        if key not in _registry:
            _registry[key] = _build(db, url, api_key)
        return _registry[key]


def _build(db: str, url: str, api_key: str) -> VectorStoreAdapter:
    if db == "weaviate":
        from .weaviate_adapter import WeaviateAdapter
        from tibco_agent.config import settings
        return WeaviateAdapter(url=url or settings.vector_db_url)

    if db == "chroma":
        from .chroma_adapter import ChromaAdapter
        return ChromaAdapter(url=url)

    if db == "qdrant":
        from .qdrant_adapter import QdrantAdapter
        return QdrantAdapter(url=url, api_key=api_key)

    if db == "pinecone":
        from .pinecone_adapter import PineconeAdapter
        return PineconeAdapter(url=url, api_key=api_key)

    if db == "pgvector":
        from .pgvector_adapter import PgvectorAdapter
        return PgvectorAdapter(url=url)

    if db == "activespaces":
        from .activespaces_adapter import ActiveSpacesAdapter
        return ActiveSpacesAdapter(url=url, api_key=api_key)

    raise ValueError(
        f"Unknown vector_db type '{db}'. Supported: {', '.join(sorted(_SUPPORTED))}"
    )
