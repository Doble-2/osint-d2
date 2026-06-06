"""Tests for agent tool definitions and execution."""

from __future__ import annotations

from core.services.agent_tools import AGENT_TOOLS, _compact_profiles
from core.domain.models import SocialProfile


# ---------------------------------------------------------------------------
# Tool schema validation
# ---------------------------------------------------------------------------

class TestToolSchemas:
    def test_all_tools_have_required_fields(self):
        for tool in AGENT_TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"

    def test_tool_names_are_unique(self):
        names = [t["function"]["name"] for t in AGENT_TOOLS]
        assert len(names) == len(set(names))

    def test_expected_tools_exist(self):
        names = {t["function"]["name"] for t in AGENT_TOOLS}
        assert "scan_username" in names
        assert "scan_email" in names
        assert "breach_check" in names
        assert "generate_report" in names

    def test_all_tools_have_required_params(self):
        for tool in AGENT_TOOLS:
            params = tool["function"]["parameters"]
            assert "properties" in params
            assert "required" in params
            assert isinstance(params["required"], list)


# ---------------------------------------------------------------------------
# Profile compaction
# ---------------------------------------------------------------------------

class TestCompactProfiles:
    def test_compact_basic_profile(self):
        profile = SocialProfile(
            url="https://github.com/test",
            username="test",
            network_name="github",
            exists=True,
            bio="A developer",
            image_url="https://example.com/avatar.png",
        )
        result = _compact_profiles([profile])
        assert len(result) == 1
        assert result[0]["network"] == "github"
        assert result[0]["exists"] is True
        assert result[0]["bio"] == "A developer"
        assert result[0]["avatar"] == "https://example.com/avatar.png"

    def test_compact_truncates_long_bio(self):
        profile = SocialProfile(
            url="https://example.com",
            username="test",
            network_name="test",
            exists=True,
            bio="A" * 500,
        )
        result = _compact_profiles([profile])
        assert len(result[0]["bio"]) == 300

    def test_compact_extracts_metadata(self):
        profile = SocialProfile(
            url="https://github.com/linus",
            username="linus",
            network_name="github",
            exists=True,
            metadata={
                "name": "Linus Torvalds",
                "location": "Portland, OR",
                "company": "Linux Foundation",
                "followers": 300000,
            },
        )
        result = _compact_profiles([profile])
        assert result[0]["name"] == "Linus Torvalds"
        assert result[0]["location"] == "Portland, OR"
        assert result[0]["followers"] == 300000

    def test_compact_respects_max_profiles(self):
        profiles = [
            SocialProfile(
                url=f"https://example.com/{i}",
                username=f"user{i}",
                network_name=f"net{i}",
                exists=True,
            )
            for i in range(50)
        ]
        result = _compact_profiles(profiles, max_profiles=5)
        assert len(result) == 5

    def test_compact_empty_list(self):
        assert _compact_profiles([]) == []
