from __future__ import annotations

import bisect
import logging
import re

import weaviate
from llama_index.core import Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from weaviate.classes.config import DataType, Property

from tibco_agent.config import settings
from .sources.base import KnowledgeSource

log = logging.getLogger(__name__)

# Property definitions for the Weaviate v4 collection schema.
_COLLECTION_PROPERTIES = [
    Property(name="text",        data_type=DataType.TEXT),
    Property(name="file_name",   data_type=DataType.TEXT),
    Property(name="source_type", data_type=DataType.TEXT),
    Property(name="product",     data_type=DataType.TEXT),
    Property(name="doc_id",      data_type=DataType.TEXT),
    Property(name="section",     data_type=DataType.TEXT),
]

_MD_HEADER_RE   = re.compile(r"^#{1,4}\s+(.+)", re.MULTILINE)
_HTML_HEADER_RE = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_RE    = re.compile(r"<[^>]+>")
# Heuristic for plain text: short line, starts uppercase, no trailing punctuation
_TEXT_HEADING_RE = re.compile(r"^[A-Z][^\n]{0,78}(?<![.,;:!?])\s*$", re.MULTILINE)


def _extract_sections(text: str, filename: str) -> list[tuple[int, str]]:
    """Return [(char_offset, section_title), ...] sorted by offset."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    sections: list[tuple[int, str]] = []

    if ext == "md":
        for m in _MD_HEADER_RE.finditer(text):
            sections.append((m.start(), m.group(1).strip()))
    elif ext in {"html", "htm"}:
        for m in _HTML_HEADER_RE.finditer(text):
            title = _HTML_TAG_RE.sub("", m.group(1)).strip()
            if title:
                sections.append((m.start(), title))
    else:
        for m in _TEXT_HEADING_RE.finditer(text):
            line = m.group(0).strip()
            if 4 <= len(line) <= 80:
                sections.append((m.start(), line))

    sections.sort(key=lambda x: x[0])
    return sections


def _section_for_offset(sections: list[tuple[int, str]], offset: int) -> str:
    """Return the most recent section heading that starts before `offset`."""
    if not sections:
        return ""
    keys = [s[0] for s in sections]
    idx = bisect.bisect_right(keys, offset) - 1
    return sections[idx][1] if idx >= 0 else ""


def _open_client(weaviate_url: str | None = None) -> weaviate.WeaviateClient:
    url = weaviate_url or settings.weaviate_url
    # Strip scheme for connect_to_custom (it takes host + port separately)
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


class IngestionPipeline:
    """
    Orchestrates loading from multiple KnowledgeSource instances,
    chunking, embedding (via Ollama), and storing into Weaviate v4.

    Usage:
        pipeline = IngestionPipeline()
        pipeline.add_source(FileSource("./data/knowledge"))
        pipeline.add_source(WebSource(urls=[...], product_tag="flogo"))
        chunks = pipeline.run()
    """

    def __init__(
        self,
        chunk_size: int = 300,
        chunk_overlap: int = 50,
        collection_name: str = "",
        weaviate_url: str = "",
    ) -> None:
        self._sources: list[KnowledgeSource] = []
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        # Per-pipeline overrides — fall back to global settings when empty
        self._collection_name = collection_name
        self._weaviate_url = weaviate_url

    def add_source(self, source: KnowledgeSource) -> "IngestionPipeline":
        self._sources.append(source)
        return self

    def run(self, reset: bool = True) -> int:
        """Load, chunk, embed, and store. Returns number of chunks stored."""
        if not self._sources:
            raise ValueError("No sources registered. Call add_source() first.")

        self._configure_llama()

        raw_docs: list = []
        for source in self._sources:
            log.info("Loading: %s", source)
            loaded = source.load()
            raw_docs.extend(loaded)
            log.info("  -> %d document(s)", len(loaded))

        if not raw_docs:
            log.warning("No documents loaded.")
            return 0

        llama_docs = [
            Document(text=d.content, metadata=d.metadata, id_=d.source)
            for d in raw_docs
        ]

        splitter = SentenceSplitter(chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap)
        nodes = splitter.get_nodes_from_documents(llama_docs)

        # Pre-compute section maps per source document for citation enrichment
        _section_maps: dict[str, list[tuple[int, str]]] = {
            d.source: _extract_sections(d.content, d.source)
            for d in raw_docs
        }
        for node in nodes:
            source_id = node.ref_doc_id or ""
            sections = _section_maps.get(source_id, [])
            offset = node.start_char_idx or 0
            node.metadata["section"] = _section_for_offset(sections, offset)
        log.info("Total: %d chunks from %d document(s)", len(nodes), len(raw_docs))

        client = _open_client(self._weaviate_url or None)
        class_name = self._collection_name or settings.collection_name

        # ── Schema management (Weaviate v4) ────────────────────────────────────
        with client:
            if client.collections.exists(class_name):
                if reset:
                    client.collections.delete(class_name)
                    log.info("Dropped existing collection '%s'.", class_name)
                # else: append mode — collection already exists

            if not client.collections.exists(class_name):
                client.collections.create(
                    name=class_name,
                    properties=_COLLECTION_PROPERTIES,
                )
                log.info("Created Weaviate collection '%s'.", class_name)

            # ── Embed + store ──────────────────────────────────────────────────
            log.info("Embedding and indexing (this takes a minute on first run)...")
            embed_model = Settings.embed_model
            collection = client.collections.get(class_name)
            stored = 0

            with collection.batch.dynamic() as batch:
                for node in nodes:
                    text = node.get_content()
                    vector = embed_model.get_text_embedding(text)
                    batch.add_object(
                        properties={
                            "text": text,
                            "file_name": node.metadata.get("file_name", ""),
                            "source_type": node.metadata.get("source_type", ""),
                            "product": node.metadata.get("product", ""),
                            "doc_id": node.node_id,
                            "section": node.metadata.get("section", ""),
                        },
                        vector=vector,
                    )
                    stored += 1

        log.info("Done. %d chunks stored in Weaviate '%s'.", stored, class_name)
        return stored

    def _configure_llama(self) -> None:
        Settings.llm = Ollama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            request_timeout=settings.request_timeout,
        )
        Settings.embed_model = OllamaEmbedding(
            model_name=settings.embed_model,
            base_url=settings.ollama_base_url,
        )
