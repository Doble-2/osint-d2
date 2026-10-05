import pytest
from adapters.vector_store import VectorStore


def test_vector_store_add_and_search():
    store = VectorStore()
    store.add_document(
        doc_id="gh_profile",
        source="github",
        text="Software engineer working with Python, Flutter, FastAPI and AI Agents.",
        metadata={"platform": "github"},
    )
    store.add_document(
        doc_id="art_profile",
        source="instagram",
        text="Oil painting artist, landscapes and classical photography in Paris.",
        metadata={"platform": "instagram"},
    )

    results = store.search_semantic("FastAPI and Python agents", limit=1)
    assert len(results) == 1
    assert results[0]["doc_id"] == "gh_profile"
    assert results[0]["score"] > 0.3


def test_vector_store_stylometric_correlation():
    store = VectorStore()
    text_author_a = "Building high-performance systems with Flutter & Python. Obsessed with quality. 🐧"
    text_author_b = "Just baked some fresh chocolate cookies with family today! 🍪"

    store.add_document("profile_a", "github", text_author_a)
    store.add_document("profile_b", "blog", text_author_b)

    sample = "Obsessed with high-performance code and quality systems. 🐧"
    matches = store.correlate_author_style(sample, limit=1)

    assert len(matches) == 1
    assert matches[0]["doc_id"] == "profile_a"
    assert matches[0]["stylometric_score"] > 0.4
