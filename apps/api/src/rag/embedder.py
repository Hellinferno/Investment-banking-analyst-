"""
Embedding generator for the RAG pipeline.

Uses sentence-transformers (BAAI/bge-base-en-v1.5) to generate dense
vector embeddings for document chunks. Falls back to a simple TF-IDF
embedder when the sentence-transformers model cannot be loaded.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = os.environ.get("AIBAA_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
_EMBEDDING_DIM = 768  # bge-base-en-v1.5 output dimension
_DEVICE = os.environ.get("AIBAA_EMBEDDING_DEVICE", "cpu")

_model: Any = None
_use_transformers = False


def _load_transformers_embedder() -> Any:
    """Lazily load the sentence-transformers embedder."""
    global _model, _use_transformers
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_EMBEDDING_MODEL, device=_DEVICE)
        _use_transformers = True
        logger.info("Loaded sentence-transformers embedder: %s (dim=%d)", _EMBEDDING_MODEL, _EMBEDDING_DIM)
        return _model
    except ImportError:
        logger.warning("sentence-transformers not installed — using TF-IDF fallback embedder")
        return None


class Embedder:
    """
    Generate dense vector embeddings for text chunks.

    Uses BAAI/bge-base-en-v1.5 when sentence-transformers is available,
    otherwise falls back to a lightweight TF-IDF embedder so the pipeline
    works without GPU/CUDA dependencies.
    """

    def __init__(self, model_name: str = _EMBEDDING_MODEL, dim: int = _EMBEDDING_DIM) -> None:
        self.model_name = model_name
        self.dim = dim
        self._hf_model = _load_transformers_embedder()
        self._tfidf: Any = None
        self._tfidf_corpus: list[str] = []
        self._tfidf_ready = False

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a batch of texts. Returns a list of embedding vectors (dim=_EMBEDDING_DIM).

        Parameters
        ----------
        texts: List of text strings to embed.

        Returns
        -------
        List of float embedding vectors, one per input text.
        """
        if not texts:
            return []

        if self._hf_model is not None:
            embeddings = self._hf_model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return [emb.tolist() for emb in embeddings]

        # TF-IDF fallback
        return self._tfidf_embed(texts)

    def _tfidf_embed(self, texts: list[str]) -> list[list[float]]:
        """Lightweight TF-IDF fallback embedder."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            logger.error("sklearn not available for TF-IDF fallback — returning zero vectors")
            return [[0.0] * self.dim for _ in texts]

        corpus = [t[:10000] for t in texts]  # cap at 10k chars per doc

        if not self._tfidf_ready or corpus != self._tfidf_corpus:
            max_features = min(2048, self.dim)
            self._vectorizer = TfidfVectorizer(
                max_features=max_features,
                stop_words="english",
                ngram_range=(1, 2),
            )
            try:
                tfidf_matrix = self._vectorizer.fit_transform(corpus)
                # Project to self.dim by padding or truncating
                vectors: list[list[float]] = []
                for row in tfidf_matrix.toarray():
                    vec = list(row)
                    if len(vec) < self.dim:
                        vec.extend([0.0] * (self.dim - len(vec)))
                    else:
                        vec = vec[: self.dim]
                    vectors.append(vec)
                self._tfidf_ready = True
                self._tfidf_corpus = corpus
                return vectors
            except Exception as exc:
                logger.error("TF-IDF embedding failed: %s", exc)
                return [[0.0] * self.dim for _ in texts]

        return [[0.0] * self.dim for _ in texts]

    @property
    def embedding_dim(self) -> int:
        return self.dim
