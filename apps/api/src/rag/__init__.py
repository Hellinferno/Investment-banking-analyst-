"""
RAG (Retrieval-Augmented Generation) pipeline.

Modules:
  chunker  — Semantic-aware text splitting (~512 tokens, paragraph-aware)
  embedder — BAAI/bge-base-en-v1.5 embeddings (sentence-transformers, TF-IDF fallback)
  indexer  — ChromaDB persistent vector store, per-deal collections
  retriever — Top-K cosine-similarity retrieval with citation metadata

Usage:
  from rag import index_document, retrieve_context, build_context_string

  # Index a parsed document
  index_document(doc_id, deal_id, text, filename)

  # Retrieve relevant context for an agent query
  chunks = retrieve_context(deal_id, "What is the revenue growth rate?")
  context = build_context_string(chunks)
"""
from .chunker import Chunk, ChunkConfig, chunk_text
from .embedder import Embedder
from .indexer import delete_document_chunks, get_collection_stats, index_document, reset_all_indexes, reset_deal_index
from .retriever import RetrievedChunk, build_context_string, retrieve_context

__all__ = [
    "Chunk",
    "ChunkConfig",
    "chunk_text",
    "Embedder",
    "index_document",
    "delete_document_chunks",
    "get_collection_stats",
    "reset_all_indexes",
    "reset_deal_index",
    "RetrievedChunk",
    "retrieve_context",
    "build_context_string",
]
