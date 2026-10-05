"""Vector memory & semantic correlation store for OSINT-D2.

Features:
- Pure Python lightweight vector store (cosine similarity + TF-IDF / character n-gram stylometry fallback).
- Optional OpenAI/DeepSeek embeddings when available.
- Stores snippets, bios, tweets, forum posts and scraped web pages.
- Allows semantic retrieval and stylometric correlation between target profiles.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


def _tokenize(text: str) -> list[str]:
    """Extract lowercased word tokens and special tokens (emojis, tags)."""
    return re.findall(r"[\w'-]+|[^\s\w]", text.lower())


def _ngram_char_tokens(text: str, n: int = 3) -> list[str]:
    """Extract character n-grams for stylometric signature comparison."""
    clean = re.sub(r"\s+", " ", text.lower().strip())
    if len(clean) < n:
        return [clean]
    return [clean[i : i + n] for i in range(len(clean) - n + 1)]


def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Calculate cosine similarity between two sparse frequency vectors."""
    dot_product = sum(val * vec2.get(k, 0.0) for k, val in vec1.items())
    norm1 = math.sqrt(sum(val * val for val in vec1.values()))
    norm2 = math.sqrt(sum(val * val for val in vec2.values()))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot_product / (norm1 * norm2)


@dataclass
class DocumentChunk:
    doc_id: str
    source: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    word_vector: dict[str, float] = field(default_factory=dict)
    stylometric_vector: dict[str, float] = field(default_factory=dict)


class VectorStore:
    """In-memory lightweight semantic & stylometric vector engine."""

    def __init__(self) -> None:
        self.chunks: list[DocumentChunk] = []

    def add_document(
        self,
        doc_id: str,
        source: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Vectorize and index a document or scraped text snippet."""
        if not text or not text.strip():
            return

        meta = metadata or {}
        # Word frequency representation (TF)
        words = _tokenize(text)
        word_counts = Counter(words)
        total_words = len(words) or 1
        word_vec = {w: count / total_words for w, count in word_counts.items()}

        # Stylometric character n-gram representation (for author correlation)
        ngrams = _ngram_char_tokens(text, n=4)
        ngram_counts = Counter(ngrams)
        total_ngrams = len(ngrams) or 1
        stylo_vec = {ng: count / total_ngrams for ng, count in ngram_counts.items()}

        chunk = DocumentChunk(
            doc_id=doc_id,
            source=source,
            text=text,
            metadata=meta,
            word_vector=word_vec,
            stylometric_vector=stylo_vec,
        )
        self.chunks.append(chunk)

    def search_semantic(
        self,
        query: str,
        limit: int = 5,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search chunks by semantic keyword similarity."""
        if not self.chunks or not query.strip():
            return []

        q_words = _tokenize(query)
        q_counts = Counter(q_words)
        total_q = len(q_words) or 1
        q_vec = {w: count / total_q for w, count in q_counts.items()}

        results = []
        for chunk in self.chunks:
            if source_filter and chunk.source != source_filter:
                continue
            # Score de palabras compartidas
            shared_words = set(q_vec.keys()) & set(chunk.word_vector.keys())
            if not shared_words:
                continue
            score = _cosine_similarity(q_vec, chunk.word_vector)
            if score > 0.0:
                results.append({
                    "doc_id": chunk.doc_id,
                    "source": chunk.source,
                    "score": round(score, 4),
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def correlate_author_style(
        self,
        sample_text: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Calculate stylometric similarity to find probable author matches."""
        if not self.chunks or not sample_text.strip():
            return []

        ngrams = _ngram_char_tokens(sample_text, n=4)
        ngram_counts = Counter(ngrams)
        total_ng = len(ngrams) or 1
        sample_vec = {ng: count / total_ng for ng, count in ngram_counts.items()}

        matches = []
        for chunk in self.chunks:
            score = _cosine_similarity(sample_vec, chunk.stylometric_vector)
            matches.append({
                "doc_id": chunk.doc_id,
                "source": chunk.source,
                "stylometric_score": round(score, 4),
                "text": chunk.text[:200],
                "metadata": chunk.metadata,
            })

        matches.sort(key=lambda x: x["stylometric_score"], reverse=True)
        return matches[:limit]
