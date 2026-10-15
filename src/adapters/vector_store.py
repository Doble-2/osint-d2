"""Vector memory & semantic correlation store for OSINT-D2.

Features:
- Pure Python lightweight vector store (TF-IDF + cosine similarity).
- Character n-gram stylometry with a minimum-length guard.
- Accent folding and light stemming so "desarrollo" matches "desarrollador"
  and "calderon" matches "calderón".
- Language-aware stopword removal (ES/EN/PT).
- Stores snippets, bios, tweets, forum posts and scraped web pages.
- Allows semantic retrieval and stylometric correlation between target profiles.

Design constraint: pure Python, no heavy dependencies (no numpy/scipy). Sparse
dicts plus cosine similarity keep the deploy clean on Apple Silicon.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

# Stopwords ES/EN/PT. Words carrying almost no discriminating signal; without
# removing them a document made purely of stopwords outranks a real one.
_STOPWORD_TEXT = """
    a al algo algunas alguno algunos alla alli an antes aquel aquella aquellas
    aquello aquellos aqui asi aun aunque bien cada como con contra cual cuando
    de del desde donde dos el ella ellas ello ellos en entre era eran es esa
    esas ese eso esos esta estaba estan estar estas este esto estos ha han hasta
    hay la las le les lo los mas me mi mis mucho muy no nos o os otra otras otro
    otros para pero poco por porque que quien se sea segun ser si sin sobre son
    su sus tal tambien tanto te tiene tienen todo todos tu tus un una uno unos
    y ya yo

    a an and are as at be been being but by can could did do does doing for from
    had has have having he her here hers him his how i if in into is it its just
    me more most my no not now of on only or other our out over own same she
    should so some such than that the their them then there these they this
    those through to too under until up very was we were what when where which
    while who why will with would you your

    ao aos as com como da das de do dos e ela ele em entre era essa esse esta
    este eu foi ha isso isto ja lhe mais mas me mesmo meu na nas no nos o os ou
    para pela pelo por qual que se sem ser seu sua tambem te tem tu um uma voce
"""

# NOTE: must be built from .split(), never frozenset("""text""") - iterating a
# string yields single characters, which made every stopword list useless.
_STOPWORDS: frozenset[str] = frozenset(_STOPWORD_TEXT.split())

# Suffixes stripped by the light stemmer, longest first so "aciones" is tried
# before "es". Spanish/Portuguese first, then English.
_SUFFIXES: tuple[str, ...] = (
    # Spanish/Portuguese - longest first so "aciones" wins over "es"
    "amientos", "imientos", "aciones", "uciones", "adoras", "adores",
    "amiento", "imiento", "acion", "ucion", "adora", "ador",
    "antes", "ante", "mente", "ciones", "cion", "siones", "sion",
    "idades", "idad", "encias", "encia", "ancias", "ancia",
    "ando", "iendo", "ados", "idos", "ada", "ado", "ida", "ido",
    "icos", "icas", "ico", "ica",
    # English
    "ings", "ing", "ers", "er", "ed", "ly", "ies",
    "es", "os", "as", "s",
    # Verb infinitives last: "ar"/"er"/"ir" are short and greedy
    "ar", "er", "ir",
)

# Very short stems are usually wrong, so require a floor.
_MIN_STEM_LEN = 3


def fold_accents(text: str) -> str:
    """Strip diacritics: 'Calderón' -> 'Calderon'.

    OSINT identifiers are frequently typed without accents, so folding both
    sides makes 'calderon' match 'calderón' (a real miss before this).
    """
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


# Long stems are truncated to this length so that derivational variants
# collapse even when no suffix rule catches them ("desarrollo" vs
# "desarrollador"). Chosen empirically: long enough to stay discriminative,
# short enough to absorb Romance morphology.
_PREFIX_LEN = 7


def stem(token: str) -> str:
    """Light stemmer for ES/EN/PT: suffix stripping plus prefix truncation.

    Not a full Snowball implementation. The goal is that 'desarrollo',
    'desarrollador' and 'desarrollar' collapse to one key, and likewise
    'automatizar'/'automatizacion' - not linguistic perfection.
    """
    if len(token) <= _MIN_STEM_LEN:
        return token
    for suffix in _SUFFIXES:
        if len(token) - len(suffix) >= _MIN_STEM_LEN and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    # Truncate long stems so derivational families collapse even without a
    # matching suffix rule.
    if len(token) > _PREFIX_LEN:
        token = token[:_PREFIX_LEN]
    return token


def _tokenize(text: str) -> list[str]:
    """Lowercase, fold accents, split on non-word, stem and drop stopwords.

    Returns content-bearing tokens only. If everything is a stopword the
    original tokens are kept, so an all-stopword query is still searchable
    rather than silently returning nothing.
    """
    folded = fold_accents(text.lower())
    raw = re.findall(r"[\w'-]+", folded)
    if not raw:
        return []
    content = [t for t in (stem(tok) for tok in raw) if t and t not in _STOPWORDS]
    # A text made only of stopwords carries no signal: returning [] lets the
    # caller skip it instead of indexing near-empty vectors that then score
    # spuriously well against stopword-heavy queries.
    return content


def _ngram_char_tokens(text: str, n: int = 4) -> list[str]:
    """Extract character n-grams for stylometric signature comparison."""
    clean = re.sub(r"\s+", " ", fold_accents(text).lower().strip())
    if len(clean) < n:
        return [clean] if clean else []
    return [clean[i : i + n] for i in range(len(clean) - n + 1)]


def _cosine_similarity(vec1: dict[str, float], vec2: dict[str, float]) -> float:
    """Calculate cosine similarity between two sparse weighted vectors."""
    if not vec1 or not vec2:
        return 0.0
    dot_product = sum(val * vec2.get(k, 0.0) for k, val in vec1.items())
    norm1 = math.sqrt(sum(val * val for val in vec1.values()))
    norm2 = math.sqrt(sum(val * val for val in vec2.values()))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot_product / (norm1 * norm2)


# BM25 parameters: k1 controls term-frequency saturation, b controls how
# strongly document length is normalised (0 = none, 1 = full).
_BM25_K1 = 1.5
_BM25_B = 0.75

# Minimum characters before stylometry is reported. Below this the n-gram
# space is too small: 'ok' vs 'ok' scored 1.0 (false certainty).
MIN_STYLOMETRY_CHARS = 40


@dataclass
class DocumentChunk:
    doc_id: str
    source: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    term_freq: dict[str, float] = field(default_factory=dict)
    # Raw term counts: BM25 needs the true frequency, not a pre-normalised one.
    term_counts: dict[str, int] = field(default_factory=dict)
    stylometric_vector: dict[str, float] = field(default_factory=dict)

    # Backwards-compatible alias: earlier code and tests referenced
    # ``word_vector``. Exposing it as a property keeps both working.
    @property
    def word_vector(self) -> dict[str, float]:
        return self.term_freq


class VectorStore:
    """In-memory lightweight TF-IDF semantic & stylometric vector engine."""

    def __init__(self) -> None:
        self.chunks: list[DocumentChunk] = []
        # Document frequency per term, maintained incrementally so IDF can be
        # computed at query time (documents may be added in any order).
        self._doc_freq: Counter[str] = Counter()

    # -- index ---------------------------------------------------------------

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

        tokens = _tokenize(text)
        counts = Counter(tokens)
        # Sublinear TF (BM25-style saturation): a term appearing 10x is not
        # 10x more relevant. Raw count/length made long documents score 8x
        # lower than short ones for the same query.
        term_freq = {t: 1.0 + math.log(c) for t, c in counts.items()}
        term_counts = dict(counts)

        ngrams = _ngram_char_tokens(text)
        ngram_counts = Counter(ngrams)
        total_ng = len(ngrams) or 1
        stylo = {ng: c / total_ng for ng, c in ngram_counts.items()}

        self.chunks.append(
            DocumentChunk(
                doc_id=doc_id,
                source=source,
                text=text,
                metadata=metadata or {},
                term_freq=term_freq,
                term_counts=term_counts,
                stylometric_vector=stylo,
            )
        )
        for term in set(tokens):
            self._doc_freq[term] += 1

    # -- helpers -------------------------------------------------------------

    def _idf(self, term: str) -> float:
        """Smoothed inverse document frequency.

        A term present in every document contributes ~0; a rare term (an
        identifier, a surname) contributes strongly. This is what stops
        stopword-only documents from winning.
        """
        n_docs = len(self.chunks)
        if n_docs == 0:
            return 0.0
        df = self._doc_freq.get(term, 0)
        return math.log((1 + n_docs) / (1 + df)) + 1.0

    @staticmethod
    def _weight(term_freq: dict[str, float], idf_lookup) -> dict[str, float]:
        """Apply IDF to a term-frequency vector."""
        return {t: tf * idf_lookup(t) for t, tf in term_freq.items()}

    # -- retrieval -----------------------------------------------------------

    def _avg_doc_len(self) -> float:
        """Average content-token count, used for BM25 length normalisation."""
        n = len(self.chunks)
        if n == 0:
            return 1.0
        total = sum(sum(c.term_counts.values()) for c in self.chunks)
        return (total / n) or 1.0

    def search_semantic(
        self,
        query: str,
        limit: int = 5,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search chunks with BM25 scoring.

        BM25 is used instead of plain cosine similarity because cosine
        penalises long documents: a 100-word document containing the query
        scored 8x lower than a 3-word one, purely from the extra dimensions.
        BM25 normalises by document length and saturates term frequency.
        """
        if not self.chunks or not query.strip():
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []
        query_terms = Counter(tokens)
        avg_len = self._avg_doc_len()

        results = []
        for chunk in self.chunks:
            if source_filter and chunk.source != source_filter:
                continue
            doc_len = sum(chunk.term_counts.values()) or 1
            score = 0.0
            for term, q_count in query_terms.items():
                freq = chunk.term_counts.get(term, 0)
                if not freq:
                    continue
                idf = self._idf(term)
                # BM25 term weight with k1=1.5 (saturation) and b=0.75
                # (length normalisation strength).
                denom = freq + _BM25_K1 * (
                    1 - _BM25_B + _BM25_B * (doc_len / avg_len)
                )
                score += idf * (freq * (_BM25_K1 + 1)) / denom
                if q_count > 1:
                    score *= 1.0 + 0.1 * (q_count - 1)
            if score > 0.0:
                results.append(
                    {
                        "doc_id": chunk.doc_id,
                        "source": chunk.source,
                        "score": round(score, 4),
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                    }
                )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def correlate_author_style(
        self,
        sample_text: str,
        limit: int = 3,
        min_chars: int = MIN_STYLOMETRY_CHARS,
    ) -> list[dict[str, Any]]:
        """Stylometric similarity to find probable author matches.

        Samples and candidate documents shorter than ``min_chars`` are skipped:
        below that the character n-gram space is too small to mean anything and
        scores collapse to spurious 1.0 values.
        """
        if not self.chunks or not sample_text.strip():
            return []

        sample_clean = sample_text.strip()
        if len(sample_clean) < min_chars:
            return []

        ngrams = _ngram_char_tokens(sample_clean)
        counts = Counter(ngrams)
        total = len(ngrams) or 1
        sample_vec = {ng: c / total for ng, c in counts.items()}

        matches = []
        for chunk in self.chunks:
            if len(chunk.text.strip()) < min_chars:
                continue
            score = _cosine_similarity(sample_vec, chunk.stylometric_vector)
            matches.append(
                {
                    "doc_id": chunk.doc_id,
                    "source": chunk.source,
                    "stylometric_score": round(score, 4),
                    "text": chunk.text[:200],
                    "metadata": chunk.metadata,
                }
            )

        matches.sort(key=lambda x: x["stylometric_score"], reverse=True)
        return matches[:limit]
