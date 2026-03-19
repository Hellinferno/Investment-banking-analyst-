"""
ChromaDB-backed vector indexer for the RAG pipeline.

Provides per-deal ChromaDB collections with UUID-named collections.
Each document gets its own collection; deals can aggregate across their
documents at retrieval time.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from .chunker import Chunk, ChunkConfig, chunk_text
from .embedder import Embedder

logger = logging.getLogger(__name__)

_CHROMA_DIR = os.environ.get("AIBAA_CHROMA_DIR", "./chroma_data")
_COLLECTION_PREFIX = "deal_"
_BGE_DIM = 768

_client: Any = None
_collection_cache: dict[str, Any] = {}


def _get_client() -> Any:
    """Lazily initialise the ChromaDB client."""
    global _client
    if _client is not None:
        return _client

    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        _client = chromadb.PersistentClient(
            path=str(Path(_CHROMA_DIR).resolve()),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        logger.info("ChromaDB client initialised at %s", _CHROMA_DIR)
        return _client
    except ImportError:
        logger.error("chromadb not installed — RAG indexing will not work")
        return None


def _make_collection_name(deal_id: str) -> str:
    safe = deal_id.replace("-", "_")
    return f"{_COLLECTION_PREFIX}{safe}"


def index_document(
    doc_id: str,
    deal_id: str,
    text: str,
    source_filename: str,
    chunk_config: ChunkConfig | None = None,
    embedder: Embedder | None = None,
) -> list[str]:
    """
    Parse *text* into chunks, embed them, and store in ChromaDB.

    Parameters
    ----------
    doc_id: Document UUID (used as prefix for chunk IDs).
    deal_id: Deal UUID (used as collection name).
    text: Parsed document text.
    source_filename: Original filename for citation metadata.
    chunk_config: Optional chunking configuration.
    embedder: Optional embedder instance (created if not provided).

    Returns
    -------
    List of chunk IDs that were indexed.

    Raises
    ------
    RuntimeError if ChromaDB is not available.
    """
    client = _get_client()
    if client is None:
        raise RuntimeError("ChromaDB client not available — install chromadb and sentence-transformers")

    if embedder is None:
        embedder = Embedder(dim=_BGE_DIM)

    chunks = chunk_text(text, doc_id, source_filename, chunk_config)
    if not chunks:
        logger.info("No chunks generated for doc_id=%s", doc_id)
        return []

    # Embed all chunks in one batch
    chunk_texts = [c.text for c in chunks]
    embeddings = embedder.embed(chunk_texts)

    collection_name = _make_collection_name(deal_id)

    try:
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"deal_id": deal_id, "doc_id": doc_id},
        )
    except Exception as exc:
        logger.error("Failed to get/create collection %s: %s", collection_name, exc)
        raise RuntimeError(f"ChromaDB collection creation failed: {exc}") from exc

    # Build ids, documents, metadatas, embeddings
    ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "doc_id": c.doc_id,
            "source": c.source,
            "chunk_index": c.chunk_index,
            "total_chunks": c.total_chunks,
            "start_char": c.start_char,
            "end_char": c.end_char,
        }
        for c in chunks
    ]

    try:
        # Upsert: idempotent — re-indexing a doc replaces old chunks
        collection.upsert(ids=ids, documents=chunk_texts, metadatas=metadatas, embeddings=embeddings)
    except Exception as exc:
        logger.error("ChromaDB upsert failed for doc_id=%s: %s", doc_id, exc)
        raise RuntimeError(f"ChromaDB upsert failed: {exc}") from exc

    logger.info("Indexed %d chunks for doc_id=%s in collection=%s", len(chunks), doc_id, collection_name)
    return ids


def delete_document_chunks(doc_id: str, deal_id: str) -> int:
    """
    Remove all chunks belonging to *doc_id* from the deal's ChromaDB collection.

    Returns the number of chunks deleted.
    """
    client = _get_client()
    if client is None:
        return 0

    collection_name = _make_collection_name(deal_id)
    try:
        collection = client.get_collection(name=collection_name)
        # Find all chunk IDs for this doc
        result = collection.get(where={"doc_id": doc_id})
        chunk_ids: list[str] = result.get("ids", []) if result else []
        if chunk_ids:
            collection.delete(ids=chunk_ids)
            logger.info("Deleted %d chunks for doc_id=%s from collection=%s", len(chunk_ids), doc_id, collection_name)
        return len(chunk_ids)
    except Exception as exc:
        logger.warning("Failed to delete chunks for doc_id=%s: %s", doc_id, exc)
        return 0


def get_collection_stats(deal_id: str) -> dict[str, Any]:
    """Return count and_peek of the first 3 items in a deal's ChromaDB collection."""
    client = _get_client()
    if client is None:
        return {"count": 0, "error": "ChromaDB unavailable"}

    collection_name = _make_collection_name(deal_id)
    try:
        collection = client.get_collection(name=collection_name)
        count = collection.count()
        sample = collection.peek(limit=3)
        return {
            "count": count,
            "sample_ids": sample.get("ids", []) if sample else [],
            "collection": collection_name,
        }
    except Exception as exc:
        return {"count": 0, "error": str(exc)}


def reset_deal_index(deal_id: str) -> bool:
    """Delete the entire ChromaDB collection for a deal."""
    client = _get_client()
    if client is None:
        return False

    collection_name = _make_collection_name(deal_id)
    try:
        client.delete_collection(name=collection_name)
        logger.info("Reset index for deal_id=%s (deleted collection %s)", deal_id, collection_name)
        return True
    except Exception as exc:
        logger.warning("Failed to reset index for deal_id=%s: %s", deal_id, exc)
        return False


def reset_all_indexes() -> None:
    """Delete ALL ChromaDB collections. Use with caution."""
    client = _get_client()
    if client is None:
        return
    try:
        client.reset()
        logger.warning("All ChromaDB collections have been deleted")
    except Exception as exc:
        logger.error("Failed to reset ChromaDB: %s", exc)
