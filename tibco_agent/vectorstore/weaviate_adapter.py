"""Weaviate v4 adapter — hybrid BM25 + vector search, batch ingest."""
from __future__ import annotations

import logging
import threading

from .base import VectorStoreAdapter

log = logging.getLogger(__name__)

_HYBRID_ALPHA = 0.75   # 0 = pure BM25, 1 = pure vector
_SEARCH_LIMIT = 20     # candidates fetched before reranking

# Singleton clients keyed by URL string
_clients: dict[str, object] = {}
_lock = threading.Lock()


def _open_client(url: str):
    import weaviate
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


def _get_client(url: str):
    with _lock:
        client = _clients.get(url)
        if client is not None and not client.is_connected():
            try:
                client.close()
            except Exception:
                pass
            client = None
        if client is None:
            client = _open_client(url)
            _clients[url] = client
        return client


class WeaviateAdapter(VectorStoreAdapter):
    def __init__(self, url: str) -> None:
        self._url = url

    def ingest(self, chunks: list[dict], collection_name: str, reset: bool = True) -> int:
        from weaviate.classes.config import DataType, Property

        _PROPS = [
            Property(name="text",        data_type=DataType.TEXT),
            Property(name="file_name",   data_type=DataType.TEXT),
            Property(name="source_type", data_type=DataType.TEXT),
            Property(name="product",     data_type=DataType.TEXT),
            Property(name="doc_id",      data_type=DataType.TEXT),
            Property(name="section",     data_type=DataType.TEXT),
        ]

        client = _open_client(self._url)
        stored = 0
        with client:
            if client.collections.exists(collection_name):
                if reset:
                    client.collections.delete(collection_name)
                    log.info("Dropped Weaviate collection '%s'.", collection_name)
            if not client.collections.exists(collection_name):
                client.collections.create(name=collection_name, properties=_PROPS)
                log.info("Created Weaviate collection '%s'.", collection_name)

            collection = client.collections.get(collection_name)
            with collection.batch.dynamic() as batch:
                for c in chunks:
                    batch.add_object(
                        properties={
                            "text":        c["text"],
                            "file_name":   c.get("file_name", ""),
                            "source_type": c.get("source_type", ""),
                            "product":     c.get("product", ""),
                            "doc_id":      c.get("doc_id", ""),
                            "section":     c.get("section", ""),
                        },
                        vector=c["vector"],
                    )
                    stored += 1
        log.info("Weaviate: stored %d chunks in '%s'.", stored, collection_name)
        return stored

    def search(
        self,
        query: str,
        query_vector: list[float],
        collection_name: str,
        limit: int = 5,
        product_filter: str | None = None,
    ) -> list[dict]:
        from weaviate.classes.query import Filter

        client = _get_client(self._url)
        if not client.collections.exists(collection_name):
            return []

        return_props = ["text", "file_name", "product", "source_type", "section"]
        collection = client.collections.get(collection_name)
        filt = Filter.by_property("product").equal(product_filter) if product_filter else None

        result = collection.query.hybrid(
            query=query,
            vector=query_vector,
            alpha=_HYBRID_ALPHA,
            limit=_SEARCH_LIMIT,
            filters=filt,
            return_properties=return_props,
        )
        objects = [o.properties for o in result.objects]

        if not objects and product_filter:
            result = collection.query.hybrid(
                query=query,
                vector=query_vector,
                alpha=_HYBRID_ALPHA,
                limit=_SEARCH_LIMIT,
                return_properties=return_props,
            )
            objects = [o.properties for o in result.objects]

        return objects[:limit]

    def delete_collection(self, collection_name: str) -> None:
        try:
            client = _get_client(self._url)
            if client.collections.exists(collection_name):
                client.collections.delete(collection_name)
                log.info("Weaviate: dropped collection '%s'.", collection_name)
        except Exception as exc:
            log.warning("Weaviate delete_collection failed: %s", exc)

    def collection_exists(self, collection_name: str) -> bool:
        try:
            return _get_client(self._url).collections.exists(collection_name)
        except Exception:
            return False
