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

# Module-level singletons — live for the process lifetime.
_weaviate_client: weaviate.Client | None = None
_embed_model: OllamaEmbedding | None = None


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


def build_knowledge_tool() -> FunctionTool:
    """
    Retrieval-only RAG tool — embeds the query with Ollama, runs a
    nearVector search in Weaviate, and returns raw chunks to the agent LLM.
    Avoids a second LLM synthesis call, halving inference time on local models.
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

    def search_tibco_knowledge(query: str) -> str:
        """Search TIBCO Integration knowledge base and return relevant excerpts."""
        vector = embed_model.get_text_embedding(query)
        result = (
            client.query
            .get(class_name, ["text", "file_name", "product"])
            .with_near_vector({"vector": vector})
            .with_limit(5)
            .do()
        )
        objects = result.get("data", {}).get("Get", {}).get(class_name, [])
        if not objects:
            return "No relevant information found in the knowledge base for this query."
        parts = []
        for i, obj in enumerate(objects, 1):
            source = obj.get("file_name", "unknown")
            parts.append(f"[Excerpt {i} from {source}]\n{obj['text']}")
        return "\n\n---\n\n".join(parts)

    return FunctionTool.from_defaults(
        fn=search_tibco_knowledge,
        name="tibco_knowledge_search",
        description=(
            "Search the TIBCO Integration knowledge base for relevant information. "
            "Use for: best practices, error explanations, patterns, JDBC/EMS/HTTP configuration, "
            "Kubernetes deployment tips, performance tuning for BusinessWorks and Flogo. "
            "Returns raw excerpts from the knowledge base."
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
