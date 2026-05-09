from __future__ import annotations

import weaviate
from llama_index.core import Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

from tibco_agent.config import settings
from .sources.base import KnowledgeSource

# Weaviate schema for the knowledge collection.
_WEAVIATE_SCHEMA = {
    "class": None,  # filled at runtime from settings.collection_name
    "vectorizer": "none",  # we supply our own vectors from Ollama
    "properties": [
        {"name": "text",        "dataType": ["text"]},
        {"name": "file_name",   "dataType": ["text"]},
        {"name": "source_type", "dataType": ["text"]},
        {"name": "product",     "dataType": ["text"]},
        {"name": "doc_id",      "dataType": ["text"]},
    ],
}


def _open_client() -> weaviate.Client:
    return weaviate.Client(settings.weaviate_url)


class IngestionPipeline:
    """
    Orchestrates loading from multiple KnowledgeSource instances,
    chunking, embedding (via Ollama), and storing into Weaviate v3.

    Usage:
        pipeline = IngestionPipeline()
        pipeline.add_source(FileSource("./data/knowledge"))
        pipeline.add_source(WebSource(urls=[...], product_tag="flogo"))
        chunks = pipeline.run()
    """

    def __init__(self, chunk_size: int = 300, chunk_overlap: int = 50) -> None:
        self._sources: list[KnowledgeSource] = []
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

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
            print(f"\nLoading: {source}")
            loaded = source.load()
            raw_docs.extend(loaded)
            print(f"  -> {len(loaded)} document(s)")

        if not raw_docs:
            print("No documents loaded.")
            return 0

        llama_docs = [
            Document(text=d.content, metadata=d.metadata, id_=d.source)
            for d in raw_docs
        ]

        splitter = SentenceSplitter(chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap)
        nodes = splitter.get_nodes_from_documents(llama_docs)
        print(f"\nTotal: {len(nodes)} chunks from {len(raw_docs)} document(s)")

        client = _open_client()
        class_name = settings.collection_name

        # ── Schema management ──────────────────────────────────────────────────
        existing = client.schema.get()
        class_names = {c["class"] for c in existing.get("classes", [])}

        if class_name in class_names:
            if reset:
                client.schema.delete_class(class_name)
                print(f"Dropped existing class '{class_name}'.")
                class_names.discard(class_name)
            # else: append mode — schema already exists, keep it

        if class_name not in class_names:
            schema = dict(_WEAVIATE_SCHEMA)
            schema["class"] = class_name
            client.schema.create_class(schema)
            print(f"Created Weaviate class '{class_name}'.")

        # ── Embed + store ──────────────────────────────────────────────────────
        print("Embedding and indexing (this takes a minute on first run)...")
        embed_model = Settings.embed_model
        stored = 0

        with client.batch as batch:
            batch.batch_size = 50
            for node in nodes:
                text = node.get_content()
                vector = embed_model.get_text_embedding(text)
                batch.add_data_object(
                    data_object={
                        "text": text,
                        "file_name": node.metadata.get("file_name", ""),
                        "source_type": node.metadata.get("source_type", ""),
                        "product": node.metadata.get("product", ""),
                        "doc_id": node.node_id,
                    },
                    class_name=class_name,
                    vector=vector,
                )
                stored += 1

        print(f"Done. {stored} chunks stored in Weaviate '{class_name}'.")
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
