#!/usr/bin/env python3
"""
Unit tests for the AI extraction layer.
All Anthropic API calls are mocked — no real API key needed.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from extractor import enrich_posts, _extract_one


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_client(response_text: str):
    """Build a mock anthropic.Anthropic client that returns response_text."""
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=response_text)]
    client.messages.create.return_value = msg
    return client


def _make_post(post_id="1", title="Test", description="I was asked about LRU Cache.", problem_link=None):
    return {
        "post_id": post_id,
        "title": title,
        "question_description": description,
        "problem_link": problem_link,
    }


# ---------------------------------------------------------------------------
# _extract_one
# ---------------------------------------------------------------------------

class TestExtractOne:
    def test_structured_response_parsed(self):
        """Valid JSON from API → all 5 fields returned."""
        payload = {
            "problem_name": "LRU Cache",
            "leetcode_url": "https://leetcode.com/problems/lru-cache/",
            "interview_stage": "phone screen",
            "difficulty": "medium",
            "reported_outcome": "passed",
        }
        client = _fake_client(json.dumps(payload))
        result = _extract_one(client, _make_post(), model="claude-haiku-4-5-20251001")
        assert result["problem_name"] == "LRU Cache"
        assert result["interview_stage"] == "phone screen"
        assert result["difficulty"] == "medium"
        assert result["reported_outcome"] == "passed"

    def test_markdown_fences_stripped(self):
        """```json ... ``` wrapper is stripped before parsing."""
        payload = {"problem_name": "Two Sum", "leetcode_url": None,
                   "interview_stage": None, "difficulty": "easy", "reported_outcome": "no mention"}
        response = f"```json\n{json.dumps(payload)}\n```"
        client = _fake_client(response)
        result = _extract_one(client, _make_post(), model="claude-haiku-4-5-20251001")
        assert result["problem_name"] == "Two Sum"
        assert result["difficulty"] == "easy"

    def test_json_parse_failure_returns_empty(self):
        """Malformed JSON from API → returns {} without raising."""
        client = _fake_client("not json at all")
        result = _extract_one(client, _make_post(), model="claude-haiku-4-5-20251001")
        assert result == {}

    def test_problem_link_hinted_in_prompt(self):
        """When post has problem_link, it appears in the prompt content."""
        client = _fake_client("{}")
        post = _make_post(problem_link="https://leetcode.com/problems/two-sum/")
        _extract_one(client, post, model="claude-haiku-4-5-20251001")
        call_args = client.messages.create.call_args
        prompt_content = call_args[1]["messages"][0]["content"]
        assert "two-sum" in prompt_content

    def test_rate_limit_retries_then_returns_empty(self):
        """RateLimitError → retries up to 3 times, returns {} after exhausting."""
        import anthropic
        client = MagicMock()
        client.messages.create.side_effect = anthropic.RateLimitError(
            message="rate limited", response=MagicMock(status_code=429), body={}
        )
        with patch("extractor.time.sleep"):  # don't actually sleep in tests
            result = _extract_one(client, _make_post(), model="claude-haiku-4-5-20251001")
        assert result == {}
        assert client.messages.create.call_count == 3

    def test_api_error_returns_empty(self):
        """Generic APIError → returns {} without raising."""
        import anthropic
        client = MagicMock()
        client.messages.create.side_effect = anthropic.APIStatusError(
            message="server error", response=MagicMock(status_code=500), body={}
        )
        result = _extract_one(client, _make_post(), model="claude-haiku-4-5-20251001")
        assert result == {}


# ---------------------------------------------------------------------------
# enrich_posts
# ---------------------------------------------------------------------------

class TestEnrichPosts:
    def test_fields_added_to_posts(self):
        """enrich_posts adds 5 new fields to each post."""
        payload = {
            "problem_name": "LRU Cache",
            "leetcode_url": "https://leetcode.com/problems/lru-cache/",
            "interview_stage": "onsite",
            "difficulty": "hard",
            "reported_outcome": "failed",
        }
        posts = [_make_post()]
        with patch("extractor.anthropic.Anthropic", return_value=_fake_client(json.dumps(payload))):
            result = enrich_posts(posts, api_key="fake-key")
        assert result[0]["problem_name"] == "LRU Cache"
        assert result[0]["interview_stage"] == "onsite"
        assert result[0]["difficulty"] == "hard"
        assert result[0]["reported_outcome"] == "failed"

    def test_already_enriched_posts_skipped(self):
        """Posts with reported_outcome already set are not re-enriched."""
        posts = [
            {**_make_post("1"), "reported_outcome": "passed"},
            _make_post("2"),
        ]
        payload = {"problem_name": "X", "leetcode_url": None,
                   "interview_stage": None, "difficulty": None, "reported_outcome": "no mention"}
        with patch("extractor.anthropic.Anthropic", return_value=_fake_client(json.dumps(payload))) as MockAnth:
            enrich_posts(posts, api_key="fake-key")
            # Only 1 API call — post "1" was skipped
            assert MockAnth.return_value.messages.create.call_count == 1

    def test_missing_api_key_raises(self):
        """No API key → ValueError with a clear message."""
        import os
        env_backup = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="API key"):
                enrich_posts([_make_post()])
        finally:
            if env_backup:
                os.environ["ANTHROPIC_API_KEY"] = env_backup

    def test_failed_extraction_sets_none(self):
        """If API returns {}, reported_outcome is None so the post can be retried."""
        posts = [_make_post()]
        with patch("extractor.anthropic.Anthropic", return_value=_fake_client("not json")):
            enrich_posts(posts, api_key="fake-key")
        assert posts[0]["reported_outcome"] is None
        assert posts[0]["problem_name"] is None

    def test_problem_link_used_as_fallback_url(self):
        """When API returns null leetcode_url, problem_link is used instead."""
        posts = [_make_post(problem_link="https://leetcode.com/problems/two-sum/")]
        payload = {"problem_name": "Two Sum", "leetcode_url": None,
                   "interview_stage": None, "difficulty": "easy", "reported_outcome": "passed"}
        with patch("extractor.anthropic.Anthropic", return_value=_fake_client(json.dumps(payload))):
            enrich_posts(posts, api_key="fake-key")
        assert posts[0]["leetcode_url"] == "https://leetcode.com/problems/two-sum/"

    def test_modifies_list_in_place_and_returns_it(self):
        """enrich_posts returns the same list object it was given."""
        posts = [_make_post()]
        payload = {"problem_name": None, "leetcode_url": None,
                   "interview_stage": None, "difficulty": None, "reported_outcome": "no mention"}
        with patch("extractor.anthropic.Anthropic", return_value=_fake_client(json.dumps(payload))):
            result = enrich_posts(posts, api_key="fake-key")
        assert result is posts
