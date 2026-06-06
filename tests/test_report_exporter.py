"""Tests for HTML report rendering."""

from __future__ import annotations

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
