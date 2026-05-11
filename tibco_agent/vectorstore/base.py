"""Abstract base class for all vector store adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod


class VectorStoreAdapter(ABC):
    """
    Pluggable vector store interface used by IngestionPipeline and search_knowledge().

    Embedding is done OUTSIDE the adapter — callers pre-compute vectors and pass them in.
    This keeps the embed model decoupled from the store backend.

    Chunk dict schema for ingest():
        {text, vector, file_name, source_type, product, doc_id, section}

    Result dict schema returned by search():
        {text, file_name, section, product, score}
    """

    @abstractmethod
    def ingest(
        self,
        chunks: list[dict],
        collection_name: str,
        reset: bool = True,
    ) -> int:
        """Store chunks (with pre-computed vectors) in the collection.

        Returns the number of chunks successfully stored.
        When reset=True, drop existing data before inserting.
        """

    @abstractmethod
    def search(
        self,
        query: str,
        query_vector: list[float],
        collection_name: str,
        limit: int = 5,
        product_filter: str | None = None,
    ) -> list[dict]:
        """Retrieve the top-limit most relevant chunks.

        query is the raw text (used for BM25/keyword search where supported).
        query_vector is the pre-computed dense embedding.
        product_filter is an optional metadata equality filter on the 'product' field.
        Falls back to no filter when product_filter returns no results.
        """

    @abstractmethod
    def delete_collection(self, collection_name: str) -> None:
        """Drop the collection and all its data. No-op if it does not exist."""

    def collection_exists(self, collection_name: str) -> bool:  # noqa: ARG002
        """Return True if the collection exists. Adapters may override for efficiency."""
        return True
