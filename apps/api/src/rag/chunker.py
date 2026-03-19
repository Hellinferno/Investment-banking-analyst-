"""
Semantic-aware text chunker for the RAG pipeline.

Splits parsed document text into overlapping chunks of ~512 tokens with
paragraph-aware boundaries. Each chunk carries metadata for traceability.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Rough token estimate: 1 token ≈ 4 chars for English financial text
_CHARS_PER_TOKEN = 4.0


@dataclass
class Chunk:
    text: str
    chunk_index: int
    total_chunks: int
    doc_id: str
    source: str
    start_char: int
    end_char: int

    def __repr__(self) -> str:
        preview = self.text[:80].replace("\n", " ")
        return f"Chunk[{self.chunk_index}/{self.total_chunks}] {preview}..."


@dataclass
class ChunkConfig:
    max_tokens: int = 512
    overlap_tokens: int = 64
    min_chunk_chars: int = 100
    overlap_chars: int = field(default=None)

    def __post_init__(self) -> None:
        if self.overlap_chars is None:
            self.overlap_chars = int(self.overlap_tokens * _CHARS_PER_TOKEN)
        self.max_chars = int(self.max_tokens * _CHARS_PER_TOKEN)


_para_re = re.compile(r"\n\n+")
_spaces_re = re.compile(r"[ \t]+")


def _normalize_whitespace(text: str) -> str:
    return _spaces_re.sub(" ", _para_re.sub("\n\n", text)).strip()


def chunk_text(
    text: str,
    doc_id: str,
    source_filename: str,
    config: ChunkConfig | None = None,
) -> list[Chunk]:
    """
    Split *text* into semantically coherent chunks.

    Strategy
    --------
    1. Split on paragraph boundaries (double newlines) first.
    2. Accumulate paragraphs into chunks that respect max_chars.
    3. If a single paragraph exceeds max_chars, split on sentence boundaries.
    4. Overlap is applied character-by-character between consecutive chunks.

    Parameters
    ----------
    text: Raw parsed document text.
    doc_id: Document UUID (for provenance).
    source_filename: Original filename (for citation).
    config: Optional tuning parameters.

    Returns
    -------
    List of Chunk objects sorted by position in document.
    """
    if config is None:
        config = ChunkConfig()

    text = _normalize_whitespace(text)
    if not text:
        return []

    max_chars = config.max_chars
    overlap = config.overlap_chars
    min_chars = config.min_chunk_chars

    chunks: list[Chunk] = []
    paragraphs = _para_re.split(text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    current_body: list[str] = []
    current_len = 0
    start_char = 0

    def emit(body: list[str], start: int, end: int, total: int) -> Chunk:
        chunk_text = "\n\n".join(body)
        return Chunk(
            text=chunk_text,
            chunk_index=len(chunks),
            total_chunks=total,
            doc_id=doc_id,
            source=source_filename,
            start_char=start,
            end_char=end,
        )

    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        para_len = len(para)

        # Single paragraph exceeds limit — split on sentences
        if para_len > max_chars:
            # Flush current body first
            if current_body:
                body_text = "\n\n".join(current_body)
                body_end = start_char + len(body_text)
                chunks.append(emit(current_body, start_char, body_end, 0))  # placeholder total
                start_char = max(0, body_end - overlap)
                current_body = []
                current_len = 0

            # Split long paragraph on sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", para)
            sub_body: list[str] = []
            sub_len = 0
            for sent in sentences:
                if sub_len + len(sent) + 1 > max_chars and sub_body:
                    sub_text = " ".join(sub_body)
                    sub_start = para.find(sub_text)
                    sub_end = sub_start + len(sub_text)
                    chunks.append(emit(sub_body, start_char + sub_start, start_char + sub_end, 0))
                    sub_body = []
                    sub_len = 0
                sub_body.append(sent)
                sub_len += len(sent) + 1
            if sub_body:
                sub_text = " ".join(sub_body)
                sub_start = para.find(sub_text)
                sub_end = sub_start + len(sub_text)
                chunks.append(emit(sub_body, start_char + sub_start, start_char + sub_end, 0))
            i += 1
            start_char += para_len + 2
            continue

        # Adding this paragraph would exceed limit
        if current_len + para_len + 2 > max_chars and current_body:
            body_text = "\n\n".join(current_body)
            body_end = start_char + len(body_text)
            chunks.append(emit(current_body, start_char, body_end, 0))
            # Overlap: keep last paragraph for continuity
            overlap_text = current_body[-1] if current_body else ""
            start_char = max(0, body_end - overlap)
            current_body = []
            current_len = 0
            if overlap_text and overlap_text != para:
                current_body.append(overlap_text)
                current_len = len(overlap_text)
                start_char -= len(overlap_text) + 2

        current_body.append(para)
        current_len += para_len + 2
        i += 1

    # Flush remaining
    if current_body:
        body_text = "\n\n".join(current_body)
        body_end = start_char + len(body_text)
        chunks.append(emit(current_body, start_char, body_end, 0))

    if not chunks:
        return []

    # Fix total_chunks now that we know the count
    total = len(chunks)
    for c in chunks:
        c.total_chunks = total

    logger.debug("Chunked %s into %d pieces (max_tokens=%d)", doc_id, total, config.max_tokens)
    return chunks
