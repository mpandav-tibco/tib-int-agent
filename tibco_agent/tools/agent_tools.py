"""
Factory functions that create LlamaIndex tools from the domain analyzers.
Each function returns a BaseTool ready for registration in ToolRegistry.

To add a new tool:
1. Write a function build_<name>_tool() -> BaseTool
2. Register it in agent/core.py  build_agent()
"""

from __future__ import annotations

import weaviate
from llama_index.core.tools import FunctionTool
from llama_index.embeddings.ollama import OllamaEmbedding

from tibco_agent.config import settings
from tibco_agent.analyzers.flogo_analyzer import FlogoAnalyzer
from tibco_agent.analyzers.log_analyzer import LogAnalyzer
from tibco_agent.analyzers.bw_analyzer import BWAnalyzer

# Module-level singletons — live for the process lifetime.
_weaviate_client: weaviate.Client | None = None
_embed_model: OllamaEmbedding | None = None

# Hybrid search alpha: 0 = pure BM25, 1 = pure vector. 0.75 weights toward semantic.
_HYBRID_ALPHA = 0.75
_SEARCH_LIMIT = 10

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


def _format_excerpts(objects: list[dict], numbered: bool = True) -> str:
    parts = []
    for i, obj in enumerate(objects, 1):
        source = obj.get("file_name", "unknown")
        product = obj.get("product", "")
        label = f"{product} | {source}" if product else source
        prefix = f"[Excerpt {i} — {label}]" if numbered else f"[{label}]"
        parts.append(f"{prefix}\n{obj['text']}")
    return "\n\n---\n\n".join(parts)


def _hybrid_search(
    client: weaviate.Client,
    class_name: str,
    query: str,
    vector: list[float],
    product_filter: str | None = None,
) -> list[dict]:
    """Run hybrid (BM25 + vector) search, optionally filtered by product tag."""
    fields = ["text", "file_name", "product", "source_type"]
    q = (
        client.query
        .get(class_name, fields)
        .with_hybrid(query=query, vector=vector, alpha=_HYBRID_ALPHA)
        .with_limit(_SEARCH_LIMIT)
    )
    if product_filter:
        q = q.with_where({
            "path": ["product"],
            "operator": "Equal",
            "valueText": product_filter,
        })
    result = q.do()
    objects = result.get("data", {}).get("Get", {}).get(class_name, [])

    # If product filter returned nothing, retry without it
    if not objects and product_filter:
        result = (
            client.query
            .get(class_name, fields)
            .with_hybrid(query=query, vector=vector, alpha=_HYBRID_ALPHA)
            .with_limit(_SEARCH_LIMIT)
            .do()
        )
        objects = result.get("data", {}).get("Get", {}).get(class_name, [])
    return objects


def _get_weaviate_client() -> weaviate.Client:
    global _weaviate_client
    if _weaviate_client is None:
        _weaviate_client = weaviate.Client(settings.weaviate_url)
    return _weaviate_client


def _get_embed_model() -> OllamaEmbedding:
    global _embed_model
    if _embed_model is None:
        _embed_model = OllamaEmbedding(
            model_name=settings.embed_model,
            base_url=settings.ollama_base_url,
        )
    return _embed_model


def search_knowledge(query: str) -> str:
    """
    Eagerly query the TIBCO knowledge base using hybrid search.
    Returns formatted excerpts with source citations, or empty string on failure.
    """
    try:
        client = _get_weaviate_client()
        class_name = settings.collection_name
        existing = client.schema.get()
        class_names = {c["class"] for c in existing.get("classes", [])}
        if class_name not in class_names:
            return ""
        embed_model = _get_embed_model()
        vector = embed_model.get_text_embedding(query)
        product = _detect_product(query)
        objects = _hybrid_search(client, class_name, query, vector, product)
        if not objects:
            return ""
        return _format_excerpts(objects)
    except Exception:
        return ""


def build_knowledge_tool() -> FunctionTool:
    """
    Retrieval-only RAG tool — hybrid BM25 + vector search in Weaviate.
    Returns top-10 chunks with source citations to the agent LLM.
    """
    client = _get_weaviate_client()
    class_name = settings.collection_name

    existing = client.schema.get()
    class_names = {c["class"] for c in existing.get("classes", [])}
    if class_name not in class_names:
        raise RuntimeError(
            f"Weaviate class '{class_name}' not found. "
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
