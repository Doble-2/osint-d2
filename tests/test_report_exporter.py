"""Tests for HTML report rendering."""

from __future__ import annotations

import re
import pytest

from adapters.report_exporter import render_person_html
from core.domain.language import Language
from core.domain.models import PersonEntity, SocialProfile


def _sample_person() -> PersonEntity:
    return PersonEntity(
        target="testuser",
        profiles=[
            SocialProfile(
                url="https://github.com/testuser",
                username="testuser",
                network_name="github",
                exists=True,
                bio="A developer",
                image_url="https://avatar.example.com/u.png",
            ),
            SocialProfile(
                url="https://x.com/testuser",
                username="testuser",
                network_name="x",
                exists=False,
            ),
        ],
    )


class TestRenderPersonHtml:
    @pytest.mark.parametrize("language", [Language.ENGLISH, Language.SPANISH, Language.PORTUGUESE])
    def test_renders_html_for_language(self, language: Language):
        html = render_person_html(person=_sample_person(), language=language)
        assert "<html" in html
        assert "testuser" in html
        assert len(html) > 1000

    def test_english_contains_expected_labels(self):
        html = render_person_html(person=_sample_person(), language=Language.ENGLISH)
        assert "CONFIDENTIAL" in html

    def test_spanish_contains_expected_labels(self):
        html = render_person_html(person=_sample_person(), language=Language.SPANISH)
        assert "CONFIDENCIAL" in html

    def test_empty_profiles(self):
        person = PersonEntity(target="nobody", profiles=[])
        html = render_person_html(person=person, language=Language.ENGLISH)
        assert "<html" in html
        assert "nobody" in html


def test_toc_uses_the_first_page_of_each_section():
    from types import SimpleNamespace

    from adapters.report_exporter import _toc_pages_css

    document = SimpleNamespace(pages=[
        SimpleNamespace(anchors={}),
        SimpleNamespace(anchors={"sec-01": (0, 0)}),
        SimpleNamespace(anchors={"sec-01": (0, 0), "other": (0, 0)}),
        SimpleNamespace(anchors={"sec-02": (0, 0)}),
    ])

    css = _toc_pages_css(document)

    assert 'href="#sec-01"]::after { content: "2"; }' in css
    assert 'href="#sec-02"]::after { content: "4"; }' in css
    assert "other" not in css


def _box_text(box) -> str:
    children = getattr(box, "children", None)
    return getattr(box, "text", "") + "".join(_box_text(child) for child in children or [])


def test_table_of_contents_prints_page_numbers(tmp_path):
    """Guards a WeasyPrint upgrade that silently printed page 0 for every section."""
    weasyprint = pytest.importorskip("weasyprint")
    from adapters.report_exporter import _with_toc_pages, render_person_html

    html = render_person_html(person=PersonEntity(target="demo", profiles=[]), language=Language.ENGLISH)
    base_url = str(tmp_path)

    document = weasyprint.HTML(string=_with_toc_pages(weasyprint.HTML, html, base_url), base_url=base_url).render()

    toc_text = _box_text(document.pages[1]._page_box)
    numbers = [int(n) for n in re.findall(r"Summary\s*(\d+)|Matrix\s*(\d+)", toc_text) for n in n if n]
    assert len(numbers) == 2, toc_text
    assert 2 < numbers[0] <= numbers[1]
