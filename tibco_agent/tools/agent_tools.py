"""
Factory functions that create LlamaIndex tools from the domain analyzers.
Each function returns a BaseTool ready for registration in ToolRegistry.

To add a new tool:
1. Write a function build_<name>_tool() -> BaseTool
2. Register it in agent/core.py  build_agent()
"""

from __future__ import annotations

import functools
import os
import weaviate
from weaviate.classes.query import Filter, HybridFusion
from llama_index.core.tools import FunctionTool
from llama_index.embeddings.ollama import OllamaEmbedding

from tibco_agent.config import settings
from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
from tibco_agent.analyzers.log_analyzer import LogAnalyzer
from tibco_agent.analyzers.bw_analyzer import BWAnalyzer

# Module-level singletons — live for the process lifetime.
_weaviate_client: weaviate.WeaviateClient | None = None
_embed_model: OllamaEmbedding | None = None
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


def _get_embed_model() -> OllamaEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = OllamaEmbedding(
            model_name=settings.embed_model,
            base_url=settings.ollama_base_url,
        )
    return _embed_model


@functools.lru_cache(maxsize=256)
def search_knowledge(query: str) -> str:
    """
    Eagerly query the TIBCO knowledge base using hybrid search.
    Returns formatted excerpts with source citations, or empty string on failure.
    """
    try:
        client = _get_weaviate_client()
        class_name = settings.collection_name
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
        return _format_excerpts(objects)
    except Exception:
        return ""


invalidate_search_cache = search_knowledge.cache_clear


def build_knowledge_tool() -> FunctionTool:
    """
    Retrieval-only RAG tool — hybrid BM25 + vector search in Weaviate.
    Returns top-K chunks with source citations to the agent LLM.
    """
    client = _get_weaviate_client()
    class_name = settings.collection_name

    if not client.collections.exists(class_name):
        raise RuntimeError(
            f"Weaviate collection '{class_name}' not found. "
            "Run:  python ingest.py  to build the knowledge base first."
        )

    embed_model = _get_embed_model()

    def search_tibco_knowledge(query: str, product: str = "") -> str:
        """Search TIBCO Integration knowledge base and return relevant excerpts with citations."""
        vector = embed_model.get_text_embedding(query)
        product_filter = product.strip().lower() or _detect_product(query)
        objects = _hybrid_search(client, class_name, query, vector, product_filter)
        if not objects:
            return "No relevant information found in the knowledge base for this query."
        return _format_excerpts(objects)

    return FunctionTool.from_defaults(
        fn=search_tibco_knowledge,
        name="tibco_knowledge_search",
        description=(
            "Search the TIBCO Integration & Messaging knowledge base. "
            "Use for: best practices, error explanations, configuration patterns, "
            "JDBC/EMS/HTTP setup, Kubernetes deployment, performance tuning for BW and Flogo. "
            "Optional 'product' param to filter: flogo | bw | ems | ftl | eftl. "
            "Returns top-10 excerpts with source citations."
        ),
    )


def build_flogo_tool(analyzer: FlogoAnalyzer | None = None) -> FunctionTool:
    """Static analysis of .flogo application files."""
    _analyzer = analyzer or FlogoAnalyzer()

    def analyze_flogo_file(content: str) -> str:
        """Analyze a TIBCO Flogo .flogo JSON file and return a markdown findings report."""
        return _analyzer.analyze(content).to_markdown()

    return FunctionTool.from_defaults(
        fn=analyze_flogo_file,
        name="analyze_flogo_file",
        description=(
            "Analyze a TIBCO Flogo application (.flogo JSON content as string). "
            "Detects: missing error handlers, HTTP timeouts, disabled SSL, SELECT * queries, "
            "sensitive data logging, and high subflow complexity. "
            "Call this whenever the user provides or uploads a .flogo file."
        ),
    )


def build_bw_tool(analyzer: BWAnalyzer | None = None) -> FunctionTool:
    """Static analysis of TIBCO BusinessWorks 6 / BWCE .bwp XML process files."""
    _analyzer = analyzer or BWAnalyzer()

    def analyze_bw_process(xml_content: str) -> str:
        """Analyze a TIBCO BW6 process file (.bwp XML content as string) and return findings."""
        report = _analyzer.analyze(xml_content)
        return _analyzer._report_to_markdown(report)

    return FunctionTool.from_defaults(
        fn=analyze_bw_process,
        name="analyze_bw_process",
        description=(
            "Analyze a TIBCO BusinessWorks 6 or BWCE process file (.bwp XML as string). "
            "Detects: missing fault handlers, hardcoded URLs, plain-text passwords, "
            "HTTP activities without retry, SELECT * in JDBC queries, and oversized processes. "
            "Call this when the user provides or uploads a .bwp or BW process XML file."
        ),
    )


def build_log_tool(analyzer: LogAnalyzer | None = None) -> FunctionTool:
    """Pattern-based diagnosis of BW/Flogo Kubernetes pod logs."""
    _analyzer = analyzer or LogAnalyzer()

    def analyze_pod_log(log_text: str) -> str:
        """Analyze a Kubernetes pod log from a BW or Flogo container."""
        return _analyzer.analyze(log_text).to_markdown()

    return FunctionTool.from_defaults(
        fn=analyze_pod_log,
        name="analyze_pod_log",
        description=(
            "Analyze Kubernetes pod log text from a TIBCO BW or Flogo container. "
            "Matches against known error patterns: OOMKilled, CrashLoopBackOff, "
            "JDBC/EMS connection failures, NullPointerException, JVM OOM, "
            "substitution variable errors, readiness probe failures, and more. "
            "Call this whenever the user pastes or uploads pod logs."
        ),
    )
