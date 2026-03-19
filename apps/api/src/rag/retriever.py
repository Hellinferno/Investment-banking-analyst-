"""
Top-K semantic retriever for the RAG pipeline.

Queries ChromaDB collections using cosine-similarity ranking against
a query embedding. Returns the top-K most relevant chunks with full
metadata for agent context injection.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Optional

from .embedder import Embedder

logger = logging.getLogger(__name__)

_BGE_DIM = 768

_client: Any = None


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        import os as _os

        _client = chromadb.PersistentClient(
            path=str(_os.environ.get("AIBAA_CHROMA_DIR", "./chroma_data")),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        return _client
    except ImportError:
        return None


@dataclass
class RetrievedChunk:
    text: str
    doc_id: str
    source: str
    chunk_index: int
    total_chunks: int
    start_char: int
    end_char: int
    score: float

    def citation(self) -> str:
        """Human-readable source citation."""
        return f"[{self.source} · chunk {self.chunk_index + 1}/{self.total_chunks}]"

    def truncate(self, max_chars: int = 2000) -> str:
        """Return text truncated to max_chars with ellipsis."""
        if len(self.text) <= max_chars:
            return self.text
        return self.text[: max_chars - 3].rstrip() + "..."


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_context(
    deal_id: str,
    query: str,
    top_k: int = 8,
    min_score: float = 0.0,
    embedder: Embedder | None = None,
    doc_ids: list[str] | None = None,
) -> list[RetrievedChunk]:
    """
    Retrieve the top-K most relevant chunks for a query from a deal's vector index.

    Parameters
    ----------
    deal_id: Deal UUID — maps to ChromaDB collection name.
    query: Natural-language query string.
    top_k: Maximum number of chunks to return (default 8; capped at 20).
    min_score: Minimum cosine-similarity score (0–1) to include a result.
        Results below this threshold are silently dropped.
    embedder: Optional Embedder instance (created if not provided).
    doc_ids: Optional list of specific document IDs to restrict search to.

    Returns
    -------
    List of RetrievedChunk objects sorted by relevance (highest score first).
    An empty list is returned if ChromaDB is unavailable or no results pass min_score.

    Notes
    -----
    - Uses BAAI/bge-base-en-v1.5 embeddings with query embedding combined with
      a generic financial query augmentation prompt ("Represent this financial
      query for semantic search: {query}").
    - ChromaDB's internal cosine similarity is used for ranking when
      sentence-transformers is available; otherwise a simple dot-product fallback.
    """
    client = _get_client()
    if client is None:
        logger.warning("ChromaDB unavailable — cannot retrieve context for deal_id=%s", deal_id)
        return []

    if embedder is None:
        embedder = Embedder(dim=_BGE_DIM)

    top_k = max(1, min(top_k, 20))

    safe_deal_id = deal_id.replace("-", "_")
    collection_name = f"deal_{safe_deal_id}"

    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        logger.info("No ChromaDB collection found for deal_id=%s", deal_id)
        return []

    # Query embedding with financial-domain augmentation
    augmented_query = f"Represent this financial query for semantic search: {query}"
    query_emb = embedder.embed([augmented_query])[0]

    # Build where filter for specific doc_ids if provided
    where_filter: dict[str, Any] | None = None
    if doc_ids and len(doc_ids) == 1:
        where_filter = {"doc_id": doc_ids[0]}
    elif doc_ids and len(doc_ids) > 1:
        # ChromaDB doesn't support IN with list; fetch all and filter
        pass

    try:
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.error("ChromaDB query failed for deal_id=%s: %s", deal_id, exc)
        return []

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    ids: list[str] = results["ids"][0]
    docs: list[str] = results["documents"][0] if results.get("documents") else []
    metas: list[dict] = results["metadatas"][0] if results.get("metadatas") else []
    distances: list[float] = results["distances"][0] if results.get("distances") else []

    # Convert ChromaDB L2 distance to cosine similarity (approximate for normalised vectors)
    def dist_to_score(d: float) -> float:
        # For normalised bge embeddings: score ≈ 1 - d/√2 (maps L2→cosine-like 0-1)
        if d < 0:
            d = 0.0
        return max(0.0, 1.0 - d / math.sqrt(2))

    chunks: list[RetrievedChunk] = []
    for chunk_id, doc_text, meta, dist in zip(ids, docs, metas, distances):
        score = dist_to_score(dist)
        if score < min_score:
            continue

        # Filter by doc_ids if provided (since ChromaDB IN not easy)
        if doc_ids and meta.get("doc_id") not in doc_ids:
            continue

        chunks.append(
            RetrievedChunk(
                text=doc_text,
                doc_id=meta.get("doc_id", ""),
                source=meta.get("source", "unknown"),
                chunk_index=meta.get("chunk_index", 0),
                total_chunks=meta.get("total_chunks", 1),
                start_char=meta.get("start_char", 0),
                end_char=meta.get("end_char", 0),
                score=round(score, 4),
            )
        )

    # Sort by score descending
    chunks.sort(key=lambda c: c.score, reverse=True)

    logger.debug(
        "Retrieved %d chunks for query (deal_id=%s, top_k=%d)",
        len(chunks),
        deal_id,
        top_k,
    )
    return chunks


def build_context_string(
    chunks: list[RetrievedChunk],
    max_chars: int = 8000,
    include_citations: bool = True,
) -> str:
    """
    Concatenate retrieved chunks into a single context string for LLM injection.

    Parameters
    ----------
    chunks: List of RetrievedChunk objects from retrieve_context().
    max_chars: Maximum total characters (hard cap for LLM context windows).
    include_citations: Prepend each chunk with its source citation.

    Returns
    -------
    Single string with all chunk texts joined by double newlines.
    """
    parts: list[str] = []
    total = 0

    for chunk in chunks:
        if include_citations:
            header = f"[Source: {chunk.citation()}, relevance: {chunk.score:.2f}]\n"
        else:
            header = ""

        entry = header + chunk.truncate(max_chars=max(500, max_chars // max(4, len(chunks))) - len(header))
        entry_len = len(entry) + 2  # +2 for \n\n joiner

        if total + entry_len > max_chars:
            remaining = max_chars - total - 5
            if remaining > 50:
                parts.append(entry[:remaining].rstrip() + "…")
            break

        parts.append(entry)
        total += entry_len

    if not parts:
        return "[No relevant context retrieved]"

    return "\n\n---\n\n".join(parts)
