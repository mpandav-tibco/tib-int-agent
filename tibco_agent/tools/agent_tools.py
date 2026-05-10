"""Weaviate search utilities used by build_prompt() for KB retrieval."""
from __future__ import annotations

import functools
import logging
import os
import threading
import time
import weaviate
from weaviate.classes.query import Filter
from llama_index.embeddings.ollama import OllamaEmbedding

from tibco_agent.config import settings

log = logging.getLogger(__name__)

# Module-level singletons — live for the process lifetime.
_weaviate_client: weaviate.WeaviateClient | None = None
_weaviate_lock = threading.Lock()  # guards reconnect across concurrent sessions
_embed_model = None   # may be OllamaEmbedding or OpenAIEmbedding depending on provider
_cross_encoder = None  # lazy-loaded on first use

# Hybrid search alpha: 0 = pure BM25, 1 = pure vector. 0.75 weights toward semantic.
_HYBRID_ALPHA = 0.75
_SEARCH_LIMIT = 20   # fetch more candidates for reranker
_RERANK_TOP_K = 5    # return top-K after reranking
_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_RERANKER_ENABLED = os.environ.get("RERANKER_ENABLED", "true").lower() not in {"false", "0", "no"}

# Product keywords → Weaviate product tag for metadata filtering
_PRODUCT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("flogo",  ["flogo", ".flogo"]),
    ("bw",     ["businessworks", "bwce", " bw6", " bw5", " bw ", "bwapp", ".bwp"]),
    ("ems",    ["tibco ems", " ems ", "enterprise message service", "tibemsd"]),
    ("ftl",    [" ftl ", "tibco ftl"]),
    ("eftl",   ["eftl", "tibco eftl"]),
]


def _detect_product(query: str) -> str | None:
    """Return a product tag if the query clearly targets one product, else None."""
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
    """Score (query, passage) pairs with a cross-encoder and return top-K results."""
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


def _hybrid_search(
    client: weaviate.WeaviateClient,
    class_name: str,
    query: str,
    vector: list[float],
    product_filter: str | None = None,
) -> list[dict]:
    """Run hybrid (BM25 + vector) search, optionally filtered by product tag."""
    return_props = ["text", "file_name", "product", "source_type", "section"]
    collection = client.collections.get(class_name)

    filt = Filter.by_property("product").equal(product_filter) if product_filter else None
    result = collection.query.hybrid(
        query=query,
        vector=vector,
        alpha=_HYBRID_ALPHA,
        limit=_SEARCH_LIMIT,
        filters=filt,
        return_properties=return_props,
    )
    objects = [o.properties for o in result.objects]

    # If product filter returned nothing, retry without it
    if not objects and product_filter:
        result = collection.query.hybrid(
            query=query,
            vector=vector,
            alpha=_HYBRID_ALPHA,
            limit=_SEARCH_LIMIT,
            return_properties=return_props,
        )
        objects = [o.properties for o in result.objects]
    return objects


def _connect_weaviate() -> weaviate.WeaviateClient:
    url = settings.weaviate_url
    bare = url.removeprefix("https://").removeprefix("http://")
    host, _, port_str = bare.partition(":")
    port = int(port_str) if port_str.isdigit() else 8080
    return weaviate.connect_to_custom(
        http_host=host or "localhost",
        http_port=port,
        http_secure=url.startswith("https://"),
        grpc_host=host or "localhost",
        grpc_port=50051,
        grpc_secure=False,
    )


def _get_weaviate_client() -> weaviate.WeaviateClient:
    global _weaviate_client
    with _weaviate_lock:
        # Reconnect if the singleton is stale (Weaviate restart, network blip, etc.)
        if _weaviate_client is not None and not _weaviate_client.is_connected():
            try:
                _weaviate_client.close()
            except Exception:
                pass
            _weaviate_client = None
        if _weaviate_client is None:
            _weaviate_client = _connect_weaviate()
        return _weaviate_client


def _get_embed_model():
    """Return the active embedding model.

    Respects configure_llm() provider selection: if Settings.embed_model has been
    set (e.g. OpenAIEmbedding for openai provider), use it; otherwise fall back to
    the module-level Ollama singleton so the first call before configure_llm() works.
    """
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
def search_knowledge(query: str, collection_name: str = "") -> str:
    """
    Query a knowledge base using hybrid BM25 + vector search.

    collection_name: target Weaviate collection; falls back to settings.collection_name
    when empty so existing single-agent callers need no changes.

    Results are LRU-cached per (query, collection_name) pair — call
    invalidate_search_cache() after changing Weaviate config or collection contents.
    """
    t0 = time.perf_counter()
    try:
        client = _get_weaviate_client()
        class_name = collection_name or settings.collection_name
        if not client.collections.exists(class_name):
            return ""
        embed_model = _get_embed_model()
        vector = embed_model.get_text_embedding(query)
        product = _detect_product(query)
        objects = _hybrid_search(client, class_name, query, vector, product)
        if not objects:
            return ""
        if _RERANKER_ENABLED:
            objects = _rerank(query, objects)
        log.info("search_knowledge: %d results in %.2fs (reranked=%s product=%s col=%s)",
                 len(objects), time.perf_counter() - t0, _RERANKER_ENABLED, product, class_name)
        return _format_excerpts(objects)
    except Exception as exc:
        log.warning("search_knowledge failed (returning empty): %s", exc)
        return ""


invalidate_search_cache = search_knowledge.cache_clear
