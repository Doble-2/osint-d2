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


# ---------------------------------------------------------------------------
# Regresiones: cada test cubre un defecto real medido en el motor.
# ---------------------------------------------------------------------------


def test_stopword_list_is_words_not_characters():
    """_STOPWORDS must be built with .split(); frozenset("text") yields chars."""
    from adapters.vector_store import _STOPWORDS

    assert "de" in _STOPWORDS
    assert "the" in _STOPWORDS
    assert len(_STOPWORDS) > 100


def test_stemming_collapses_derivational_families():
    """'desarrollo' must match 'desarrollador' (was a total miss before)."""
    from adapters.vector_store import stem

    assert stem("desarrollo") == stem("desarrollador") == stem("desarrollar")
    assert stem("automatizar") == stem("automatizacion")
    assert stem("programacion") == stem("programador")


def test_search_matches_derivational_variants():
    """Querying with a different derivation of an indexed word must hit."""
    store = VectorStore()
    store.add_document("d1", "github", "desarrollador de software especializado en automatizacion")

    for query in ["desarrollo", "desarrollador", "automatizar", "automatizacion"]:
        results = store.search_semantic(query, limit=1)
        assert results, f"'{query}' should match the indexed document"


def test_accents_are_folded_both_ways():
    """'calderon' must match 'calderón' - identifiers are typed without accents."""
    store = VectorStore()
    store.add_document("d1", "web", "Angel Calderón Rodríguez es desarrollador")

    for query in ["calderon", "calderón", "CALDERON", "rodriguez", "Rodríguez"]:
        assert store.search_semantic(query, limit=1), f"'{query}' should match"


def test_stopword_only_documents_are_not_indexed():
    """A document made purely of stopwords carries no signal."""
    store = VectorStore()
    store.add_document("basura", "twitter", "y de la que el para con un es una")
    store.add_document("real", "github", "ingenieria inversa de malware y analisis forense")

    results = store.search_semantic("que es el analisis de malware", limit=2)
    assert results
    assert results[0]["source"] == "github", "the real document must outrank noise"


def test_long_documents_are_not_crushed_by_length():
    """BM25 length normalisation: a long doc containing the query stays relevant."""
    store = VectorStore()
    short = "python automation osint"
    long_text = short + " " + " ".join(f"ruido{i}" for i in range(100))
    store.add_document("corto", "a", short)
    store.add_document("largo", "b", long_text)

    results = store.search_semantic("python automation osint", limit=2)
    assert len(results) == 2, "both documents contain the query"
    by_id = {r["doc_id"]: r["score"] for r in results}
    # The short doc still wins, but not by the 8x margin plain cosine produced.
    assert by_id["corto"] > by_id["largo"]
    assert by_id["largo"] / by_id["corto"] > 0.25


def test_stylometry_ignores_tiny_samples():
    """'ok' vs 'ok' scored a spurious 1.0 before the minimum-length guard."""
    store = VectorStore()
    store.add_document("a", "gh", "ok")
    store.add_document("b", "tw", "ok")
    store.add_document("c", "web", "un texto completamente distinto sobre cocina italiana y sus tradiciones")

    assert store.correlate_author_style("ok", limit=3) == []


def test_stylometry_still_discriminates_real_text():
    """The minimum-length guard must not break genuine correlation."""
    store = VectorStore()
    store.add_document("a1", "github", "I really love building automation tools with Python and testing them thoroughly")
    store.add_document("a2", "twitter", "I really love building automation tools with Python and testing them carefully")
    store.add_document("b1", "web", "Completely different text about cooking pasta in the Italian tradition today")

    matches = store.correlate_author_style(
        "I really love building automation tools with Python and testing everything", limit=3
    )
    assert matches[0]["doc_id"] in ("a1", "a2")
    assert matches[0]["stylometric_score"] > 0.5
    assert matches[-1]["doc_id"] == "b1"
