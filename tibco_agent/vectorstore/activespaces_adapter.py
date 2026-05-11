"""TIBCO ActiveSpaces adapter stub.

TIBCO ActiveSpaces (AS) 5.x supports vector similarity search via its Space API.
This adapter requires the TIBCO ActiveSpaces Python client SDK, which is distributed
separately as part of the TIBCO ActiveSpaces product.

Installation:
  1. Obtain the ActiveSpaces Python SDK from your TIBCO/Cloud Software Group distribution.
  2. Install: pip install <path-to-sdk>/as_python_client-*.whl
  3. Ensure the native AS libraries are on LD_LIBRARY_PATH / PATH.

Connection URL format:  tibcosub://hostname:port
"""
from __future__ import annotations

import logging

from .base import VectorStoreAdapter

log = logging.getLogger(__name__)

_INSTALL_MSG = (
    "TIBCO ActiveSpaces Python SDK is required for the ActiveSpaces adapter. "
    "Obtain it from your TIBCO / Cloud Software Group distribution and install with:\n"
    "  pip install <sdk-path>/as_python_client-*.whl\n"
    "Ensure the native AS libraries are on LD_LIBRARY_PATH (Linux) or PATH (Windows). "
    "Connection URL format: tibcosub://hostname:port"
)


class ActiveSpacesAdapter(VectorStoreAdapter):
    """TIBCO ActiveSpaces vector store adapter."""

    def __init__(self, url: str, api_key: str = "") -> None:  # noqa: ARG002
        if not url:
            raise ValueError(
                "ActiveSpaces requires a connection URL in 'Vector DB URL'. "
                "Format: tibcosub://hostname:port"
            )
        try:
            import as_python_client as _as  # noqa: F401
        except ImportError as exc:
            raise ImportError(_INSTALL_MSG) from exc

        import as_python_client as _as
        self._url = url
        self._as = _as
        # Connection is opened per-operation (AS sessions are not long-lived TCP)
        log.info("ActiveSpaces: configured for %s", url)

    def _connect(self):
        # Connect to the AS grid; exact API depends on AS Python SDK version
        return self._as.connect(self._url)

    def ingest(self, chunks: list[dict], collection_name: str, reset: bool = True) -> int:
        conn = self._connect()
        try:
            space = conn.get_space(collection_name)
            if reset:
                space.clear()
                log.info("ActiveSpaces: cleared space '%s'.", collection_name)
            for c in chunks:
                space.put({
                    "id":          c.get("doc_id", ""),
                    "text":        c["text"],
                    "vector":      c["vector"],
                    "file_name":   c.get("file_name", ""),
                    "source_type": c.get("source_type", ""),
                    "product":     c.get("product", ""),
                    "section":     c.get("section", ""),
                })
            log.info("ActiveSpaces: stored %d chunks in '%s'.", len(chunks), collection_name)
            return len(chunks)
        finally:
            conn.close()

    def search(
        self,
        query: str,  # noqa: ARG002
        query_vector: list[float],
        collection_name: str,
        limit: int = 5,
        product_filter: str | None = None,
    ) -> list[dict]:
        conn = self._connect()
        try:
            space = conn.get_space(collection_name)
            # AS 5.x vector search API (adjust method name for your SDK version)
            results = space.search_by_vector(
                vector=query_vector,
                top_k=limit,
                filter={"product": product_filter} if product_filter else None,
            )
            if not results and product_filter:
                results = space.search_by_vector(vector=query_vector, top_k=limit)
            return [
                {
                    "text":      r.get("text", ""),
                    "file_name": r.get("file_name", ""),
                    "section":   r.get("section", ""),
                    "product":   r.get("product", ""),
                    "score":     r.get("score", 0.0),
                }
                for r in results
            ]
        finally:
            conn.close()

    def delete_collection(self, collection_name: str) -> None:
        conn = self._connect()
        try:
            space = conn.get_space(collection_name)
            space.clear()
            log.info("ActiveSpaces: cleared space '%s'.", collection_name)
        except Exception as exc:
            log.warning("ActiveSpaces delete_collection failed: %s", exc)
        finally:
            conn.close()

    def collection_exists(self, collection_name: str) -> bool:
        try:
            conn = self._connect()
            try:
                conn.get_space(collection_name)
                return True
            finally:
                conn.close()
        except Exception:
            return False
