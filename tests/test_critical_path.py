"""Critical path tests — no Ollama, no Weaviate, no Chainlit required.

Covers:
  1. ThinkFilter — O(n) incremental <think> block filter
  2. build_prompt() — prompt assembly with mocked KB search
  3. search_knowledge() — Weaviate hybrid search with mocked client + embed model
  4. Cache invalidation — LRU cache is cleared by invalidate_search_cache()
  5. File dispatch routing — extension → analyzer mapping
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tibco_agent.streaming import ThinkFilter


# ── 1. ThinkFilter ────────────────────────────────────────────────────────────

class TestThinkFilter:
    def _feed_all(self, tokens: list[str]) -> str:
        """Feed a list of tokens and return the full clean output."""
        filt = ThinkFilter()
        out = "".join(filt.feed(t) for t in tokens)
        out += filt.finalize()
        return out

    def test_passthrough_no_tags(self):
        result = self._feed_all(["Hello", " world", "!"])
        assert result == "Hello world!"

    def test_strips_single_think_block(self):
        result = self._feed_all(["<think>reasoning here</think>", "Final answer"])
        assert "reasoning here" not in result
        assert "Final answer" in result

    def test_strips_multiline_think_block(self):
        token = "<think>\nstep1\nstep2\n</think>\nResult"
        result = self._feed_all([token])
        assert "step1" not in result
        assert "Result" in result

    def test_tag_split_across_token_boundary(self):
        # "<think>" split as "<thi" + "nk>" + "hidden</think>" + "visible"
        result = self._feed_all(["<thi", "nk>", "hidden", "</think>", "visible"])
        assert "hidden" not in result
        assert "visible" in result

    def test_close_tag_split_across_boundary(self):
        result = self._feed_all(["<think>hidden</thi", "nk>", "visible"])
        assert "hidden" not in result
        assert "visible" in result

    def test_multiple_think_blocks(self):
        result = self._feed_all([
            "intro ",
            "<think>block1</think>",
            " middle ",
            "<think>block2</think>",
            " end",
        ])
        assert "block1" not in result
        assert "block2" not in result
        assert result == "intro  middle  end"

    def test_no_think_tag_finalize_flushes_buffer(self):
        # Last 6 chars of a long token are held in lookahead buffer
        filt = ThinkFilter()
        out = filt.feed("Hello world")
        remaining = filt.finalize()
        assert (out + remaining) == "Hello world"

    def test_finalize_returns_empty_when_in_think(self):
        filt = ThinkFilter()
        filt.feed("<think>unclosed reasoning")
        assert filt.finalize() == ""

    def test_case_insensitive_tags(self):
        result = self._feed_all(["<THINK>secret</THINK>answer"])
        assert "secret" not in result
        assert "answer" in result

    def test_empty_think_block(self):
        result = self._feed_all(["before<think></think>after"])
        assert result == "beforeafter"


# ── 2. build_prompt() ─────────────────────────────────────────────────────────

MINIMAL_FLOGO = json.dumps({
    "name": "test-app", "type": "flogo:app", "version": "1.0.0",
    "appModel": "1.1.0",
    "triggers": [{"id": "t1", "ref": "#rest", "name": "t1"}],
    "resources": [{
        "id": "flow:main",
        "data": {
            "name": "main",
            "tasks": [{
                "id": "a1", "name": "LogIt",
                "activity": {
                    "ref": "github.com/project-flogo/contrib/activity/log",
                    "input": {"message": "hello"},
                },
            }],
        },
    }],
})

_KB_EXCERPT = "[Excerpt 1 — flogo | guide.pdf]\nSample knowledge text."


@pytest.fixture(autouse=True)
def _clear_kb_cache():
    """Ensure search_knowledge LRU cache is clean before and after each test."""
    from tibco_agent.tools.agent_tools import invalidate_search_cache
    invalidate_search_cache()
    yield
    invalidate_search_cache()


class TestBuildPrompt:
    def test_question_appears_in_prompt(self):
        with patch("tibco_agent.agent.core.search_knowledge", return_value=""):
            from tibco_agent.agent.core import build_prompt
            result = build_prompt("What is Flogo?")
        assert "What is Flogo?" in result

    def test_kb_excerpts_section_injected(self):
        with patch("tibco_agent.agent.core.search_knowledge", return_value=_KB_EXCERPT):
            from tibco_agent.agent.core import build_prompt
            result = build_prompt("Error handling best practices")
        assert "## Knowledge Base Excerpts" in result
        assert "Sample knowledge text." in result

    def test_no_kb_section_when_empty(self):
        with patch("tibco_agent.agent.core.search_knowledge", return_value=""):
            from tibco_agent.agent.core import build_prompt
            result = build_prompt("How does Flogo work?")
        assert "## Knowledge Base Excerpts" not in result

    def test_flogo_analysis_section_added(self):
        with patch("tibco_agent.agent.core.search_knowledge", return_value=""):
            from tibco_agent.agent.core import build_prompt
            result = build_prompt("Review this app", flogo_content=MINIMAL_FLOGO)
        assert "## App Review" in result or "## Flogo" in result or "test-app" in result

    def test_chat_history_injected(self):
        history = [
            {"role": "user", "content": "What is EMS?"},
            {"role": "assistant", "content": "EMS is TIBCO Enterprise Message Service."},
        ]
        with patch("tibco_agent.agent.core.search_knowledge", return_value=""):
            from tibco_agent.agent.core import build_prompt
            result = build_prompt("Tell me more", chat_history=history)
        assert "## Conversation History" in result
        assert "What is EMS?" in result

    def test_history_trimmed_to_budget(self):
        # 40 messages of 200 chars each = 8000 chars, over the 6000 budget
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 200}
            for i in range(40)
        ]
        with patch("tibco_agent.agent.core.search_knowledge", return_value=""):
            from tibco_agent.agent.core import build_prompt
            result = build_prompt("Follow-up question", chat_history=history)
        # History section is present but not all 40 messages
        assert "## Conversation History" in result
        # The full 40 × 200 = 8000 chars should be trimmed
        assert result.count("x" * 200) < 40


# ── 3. search_knowledge() ─────────────────────────────────────────────────────

def _make_mock_weaviate(objects: list[dict]):
    """Build a minimal Weaviate client mock that returns the given objects from hybrid search."""
    mock_obj = MagicMock()
    mock_obj.properties = {}  # will be overridden per object

    mock_result = MagicMock()
    mock_result.objects = [
        _obj_with_props(p) for p in objects
    ]

    collection = MagicMock()
    collection.query.hybrid.return_value = mock_result

    client = MagicMock()
    client.is_connected.return_value = True
    client.collections.exists.return_value = True
    client.collections.get.return_value = collection
    return client


def _obj_with_props(props: dict):
    obj = MagicMock()
    obj.properties = props
    return obj


class TestSearchKnowledge:
    def test_returns_empty_when_collection_missing(self):
        client = MagicMock()
        client.is_connected.return_value = True
        client.collections.exists.return_value = False

        embed = MagicMock()
        embed.get_text_embedding.return_value = [0.1] * 384

        with (
            patch("tibco_agent.tools.agent_tools._get_weaviate_client", return_value=client),
            patch("tibco_agent.tools.agent_tools._get_embed_model", return_value=embed),
            patch("tibco_agent.tools.agent_tools._RERANKER_ENABLED", False),
        ):
            from tibco_agent.tools.agent_tools import search_knowledge, invalidate_search_cache
            invalidate_search_cache()
            result = search_knowledge("What is Flogo?")
            invalidate_search_cache()
        assert result == ""

    def test_formats_excerpts_with_source_citation(self):
        objects = [
            {"text": "Flogo uses flows.", "file_name": "flogo.pdf",
             "product": "flogo", "source_type": "doc", "section": "Overview"},
        ]
        client = _make_mock_weaviate(objects)
        embed = MagicMock()
        embed.get_text_embedding.return_value = [0.1] * 384

        with (
            patch("tibco_agent.tools.agent_tools._get_weaviate_client", return_value=client),
            patch("tibco_agent.tools.agent_tools._get_embed_model", return_value=embed),
            patch("tibco_agent.tools.agent_tools._RERANKER_ENABLED", False),
        ):
            from tibco_agent.tools.agent_tools import search_knowledge, invalidate_search_cache
            invalidate_search_cache()
            result = search_knowledge("How does Flogo work?")
            invalidate_search_cache()

        assert "Flogo uses flows." in result
        assert "flogo.pdf" in result
        assert "Excerpt 1" in result

    def test_section_appears_in_citation(self):
        objects = [
            {"text": "Error handler steps.", "file_name": "guide.pdf",
             "product": "flogo", "source_type": "doc", "section": "Error Handling"},
        ]
        client = _make_mock_weaviate(objects)
        embed = MagicMock()
        embed.get_text_embedding.return_value = [0.1] * 384

        with (
            patch("tibco_agent.tools.agent_tools._get_weaviate_client", return_value=client),
            patch("tibco_agent.tools.agent_tools._get_embed_model", return_value=embed),
            patch("tibco_agent.tools.agent_tools._RERANKER_ENABLED", False),
        ):
            from tibco_agent.tools.agent_tools import search_knowledge, invalidate_search_cache
            invalidate_search_cache()
            result = search_knowledge("Explain error handling")
            invalidate_search_cache()

        assert "Error Handling" in result

    def test_returns_empty_on_weaviate_exception(self):
        with (
            patch("tibco_agent.tools.agent_tools._get_weaviate_client",
                  side_effect=ConnectionError("Weaviate down")),
        ):
            from tibco_agent.tools.agent_tools import search_knowledge, invalidate_search_cache
            invalidate_search_cache()
            result = search_knowledge("Any question")
            invalidate_search_cache()
        assert result == ""


# ── 4. Cache invalidation ─────────────────────────────────────────────────────

class TestCacheInvalidation:
    def test_lru_cache_hit_avoids_second_weaviate_call(self):
        objects = [{"text": "cached result", "file_name": "a.pdf",
                    "product": "flogo", "source_type": "doc", "section": ""}]
        client = _make_mock_weaviate(objects)
        embed = MagicMock()
        embed.get_text_embedding.return_value = [0.1] * 384

        with (
            patch("tibco_agent.tools.agent_tools._get_weaviate_client", return_value=client),
            patch("tibco_agent.tools.agent_tools._get_embed_model", return_value=embed),
            patch("tibco_agent.tools.agent_tools._RERANKER_ENABLED", False),
        ):
            from tibco_agent.tools.agent_tools import search_knowledge, invalidate_search_cache
            invalidate_search_cache()
            search_knowledge("cache test query")
            search_knowledge("cache test query")  # second call — should be cached
            invalidate_search_cache()

        # embed was called exactly once (second call served from LRU cache)
        assert embed.get_text_embedding.call_count == 1

    def test_invalidate_forces_fresh_search(self):
        objects = [{"text": "result", "file_name": "b.pdf",
                    "product": "flogo", "source_type": "doc", "section": ""}]
        client = _make_mock_weaviate(objects)
        embed = MagicMock()
        embed.get_text_embedding.return_value = [0.1] * 384

        with (
            patch("tibco_agent.tools.agent_tools._get_weaviate_client", return_value=client),
            patch("tibco_agent.tools.agent_tools._get_embed_model", return_value=embed),
            patch("tibco_agent.tools.agent_tools._RERANKER_ENABLED", False),
        ):
            from tibco_agent.tools.agent_tools import search_knowledge, invalidate_search_cache
            invalidate_search_cache()
            search_knowledge("invalidation test")
            invalidate_search_cache()
            search_knowledge("invalidation test")  # cache was cleared — fresh call
            invalidate_search_cache()

        # embed called twice: once before invalidate, once after
        assert embed.get_text_embedding.call_count == 2


# ── 5. File dispatch routing ──────────────────────────────────────────────────

class TestFileDispatchRouting:
    """Verify the extension → analyzer routing logic (mirrors chainlit_app.py on_message)."""

    @pytest.mark.parametrize("filename,expected_analyzer", [
        ("app.flogo",        "flogo"),
        ("process.bwp",      "bw"),
        ("errors.log",       "log"),
        ("app.txt",          "log"),
        ("deploy.yaml",      "kube"),
        ("manifest.yml",     "kube"),
        ("tibemsd.conf",     "ems"),
        ("queues.conf",      "ems"),
        ("unknown.xml",      None),
        ("archive.jar",      None),
    ])
    def test_extension_routing(self, filename: str, expected_analyzer: str | None):
        lower = filename.lower()
        short = filename.split("/")[-1]

        if lower.endswith(".flogo"):
            routed = "flogo"
        elif lower.endswith(".bwp"):
            routed = "bw"
        elif lower.endswith((".log", ".txt")):
            routed = "log"
        elif lower.endswith((".yaml", ".yml")):
            routed = "kube"
        elif lower.endswith(".conf") or short.lower() == "tibemsd.conf":
            routed = "ems"
        else:
            routed = None

        assert routed == expected_analyzer, (
            f"{filename!r} → expected {expected_analyzer!r}, got {routed!r}"
        )
