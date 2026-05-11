"""Knowledge base search — delegates to the configured VectorStoreAdapter."""
from __future__ import annotations

import functools
import logging
import os
import time

from llama_index.embeddings.ollama import OllamaEmbedding

from tibco_agent.config import settings

log = logging.getLogger(__name__)

_embed_model = None  # lazy Ollama singleton; overridden by configure_llm()

_SEARCH_LIMIT = 20   # candidates fetched before reranking
_RERANK_TOP_K = 5    # top-K returned after reranking
_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_RERANKER_ENABLED = os.environ.get("RERANKER_ENABLED", "true").lower() not in {"false", "0", "no"}

_cross_encoder = None  # lazy-loaded on first use

# Product keywords → metadata tag for filtering
_PRODUCT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("flogo",  ["flogo", ".flogo"]),
    ("bw",     ["businessworks", "bwce", " bw6", " bw5", " bw ", "bwapp", ".bwp"]),
    ("ems",    ["tibco ems", " ems ", "enterprise message service", "tibemsd"]),
    ("ftl",    [" ftl ", "tibco ftl"]),
    ("eftl",   ["eftl", "tibco eftl"]),
]


def _detect_product(query: str) -> str | None:
    q = query.lower()
    for product, keywords in _PRODUCT_KEYWORDS:
        if any(kw in q for kw in keywords):
            return product
    return None


def _get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder(_RERANKER_MODEL)
    return _cross_encoder


def _rerank(query: str, objects: list[dict]) -> list[dict]:
    if not objects:
        return objects
    try:
        ce = _get_cross_encoder()
        pairs = [(query, obj.get("text", "")) for obj in objects]
        scores = ce.predict(pairs)
        ranked = sorted(zip(scores, objects), key=lambda x: x[0], reverse=True)
        return [obj for _, obj in ranked[:_RERANK_TOP_K]]
    except Exception:
        return objects[:_RERANK_TOP_K]


def _format_excerpts(objects: list[dict], numbered: bool = True) -> str:
    parts = []
    for i, obj in enumerate(objects, 1):
        source = obj.get("file_name", "unknown")
        product = obj.get("product", "")
        section = obj.get("section", "")
        base = f"{product} | {source}" if product else source
        label = f"{base} > {section}" if section else base
        prefix = f"[Excerpt {i} — {label}]" if numbered else f"[{label}]"
        parts.append(f"{prefix}\n{obj['text']}")
    return "\n\n---\n\n".join(parts)


def _get_embed_model():
    """Return the active embedding model, respecting configure_llm() provider."""
    from llama_index.core import Settings as LISettings
    if getattr(LISettings, "embed_model", None) is not None:
        return LISettings.embed_model
    global _embed_model
    if _embed_model is None:
        _embed_model = OllamaEmbedding(
            model_name=settings.embed_model,
            base_url=settings.ollama_base_url,
        )
    return _embed_model


@functools.lru_cache(maxsize=512)
def search_knowledge(
    query: str,
    collection_name: str = "",
    vector_db: str = "",
    vector_db_url: str = "",
    vector_db_api_key: str = "",
) -> str:
    """
    Query a knowledge base and return formatted excerpts.

    Falls back to global settings when per-agent overrides are empty.
    Results are LRU-cached per (query, collection_name, vector_db, url, key).
    Call invalidate_search_cache() after changing VectorDB config or re-ingesting.
    """
    t0 = time.perf_counter()
    try:
        from tibco_agent.vectorstore.factory import get_adapter

        db = vector_db or settings.vector_db
        url = vector_db_url  # blank is valid (e.g. embedded Chroma)
        key = vector_db_api_key
        col = collection_name or settings.collection_name

        adapter = get_adapter(db, url, key)
        if not adapter.collection_exists(col):
            return ""

        embed_model = _get_embed_model()
        query_vector = embed_model.get_text_embedding(query)
        product = _detect_product(query)

        objects = adapter.search(
            query=query,
            query_vector=query_vector,
            collection_name=col,
            limit=_SEARCH_LIMIT,
            product_filter=product,
        )
        if not objects:
            return ""
        if _RERANKER_ENABLED:
            objects = _rerank(query, objects)
        log.info(
            "search_knowledge: %d results in %.2fs (reranked=%s product=%s col=%s db=%s)",
            len(objects), time.perf_counter() - t0, _RERANKER_ENABLED, product, col, db,
        )
        return _format_excerpts(objects)
    except Exception as exc:
        log.warning("search_knowledge failed (returning empty): %s", exc)
        return ""


invalidate_search_cache = search_knowledge.cache_clear
