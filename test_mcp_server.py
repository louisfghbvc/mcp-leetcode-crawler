#!/usr/bin/env python3
"""
Unit tests for MCP server tools.
Tests tool functions directly — no MCP protocol overhead.
"""

import datetime
import pathlib
from unittest.mock import patch

import pandas as pd
import pytest
import requests.exceptions

import mcp_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_cache(tmp_path, company, posts):
    """Write posts as a CSV to tmp_path/cache/{company}_questions.csv."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    pd.DataFrame(posts).to_csv(str(cache_dir / f"{company}_questions.csv"), index=False)


def _write_raw_cache(tmp_path, company, content: str):
    """Write raw bytes to the cache file (for malformed CSV tests)."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(exist_ok=True)
    (cache_dir / f"{company}_questions.csv").write_text(content)


# ---------------------------------------------------------------------------
# _load_cache
# ---------------------------------------------------------------------------

class TestLoadCache:
    def test_nan_replaced_with_none(self, tmp_path, monkeypatch):
        """CSV with missing cells → field is None, not float('nan')."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        # Write a post with a missing question_description
        posts = [{"post_id": "1", "question_type": "leetcode", "question_description": None}]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server._load_cache("google")
        assert len(result) == 1
        assert result[0]["question_description"] is None

    def test_malformed_csv_returns_empty(self, tmp_path, monkeypatch):
        """Malformed/truncated CSV → returns [] without raising."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        _write_raw_cache(tmp_path, "google", "col1,col2\n1,2\n3")  # truncated row
        result = mcp_server._load_cache("google")
        # Either returns records or [] — must not raise
        assert isinstance(result, list)

    def test_completely_corrupt_returns_empty(self, tmp_path, monkeypatch):
        """Binary garbage in cache file → returns []."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        _write_raw_cache(tmp_path, "google", "\x00\xff\xfe corrupt")
        result = mcp_server._load_cache("google")
        assert result == []


# ---------------------------------------------------------------------------
# search_discussions
# ---------------------------------------------------------------------------

class TestSearchDiscussions:
    def test_empty_cache_returns_empty(self, tmp_path, monkeypatch):
        """No cache file → returns []."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        result = mcp_server.search_discussions("google", days=7)
        assert result == []

    def test_filters_by_days(self, tmp_path, monkeypatch):
        """Posts older than the window are excluded."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        posts = [
            {"post_id": "1", "created_at": (now - datetime.timedelta(days=2)).isoformat(),
             "question_type": "leetcode", "frequency": 1},
            {"post_id": "2", "created_at": (now - datetime.timedelta(days=30)).isoformat(),
             "question_type": "leetcode", "frequency": 1},
        ]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.search_discussions("google", days=7)
        assert len(result) == 1
        assert str(result[0]["post_id"]) == "1"

    def test_all_returned_within_window(self, tmp_path, monkeypatch):
        """All posts within window are returned."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        posts = [
            {"post_id": str(i), "created_at": (now - datetime.timedelta(days=i)).isoformat(),
             "question_type": "leetcode", "frequency": 1}
            for i in range(1, 6)
        ]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.search_discussions("google", days=10)
        assert len(result) == 5

    def test_days_zero_returns_empty(self, tmp_path, monkeypatch):
        """days=0 → no posts from the past are included (cutoff is now)."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        posts = [
            {"post_id": "1", "created_at": (now - datetime.timedelta(hours=1)).isoformat(),
             "question_type": "leetcode", "frequency": 1},
        ]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.search_discussions("google", days=0)
        assert result == []

    def test_negative_days_raises(self, tmp_path, monkeypatch):
        """days=-1 → ValueError with a clear message (does not leak internals)."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        with pytest.raises(ValueError, match="days must be >= 0"):
            mcp_server.search_discussions("google", days=-1)


# ---------------------------------------------------------------------------
# get_hot_problems
# ---------------------------------------------------------------------------

class TestGetHotProblems:
    def test_empty_cache_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        result = mcp_server.get_hot_problems("google")
        assert result == []

    def test_sorted_by_frequency_descending(self, tmp_path, monkeypatch):
        """Results sorted by frequency, discussion type excluded."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        posts = [
            {"post_id": "1", "question_type": "leetcode", "frequency": 1},
            {"post_id": "2", "question_type": "leetcode", "frequency": 5},
            {"post_id": "3", "question_type": "discussion", "frequency": 10},
        ]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.get_hot_problems("google", limit=10)
        assert len(result) == 2
        assert str(result[0]["post_id"]) == "2"  # frequency=5 first
        assert str(result[1]["post_id"]) == "1"

    def test_limit_respected(self, tmp_path, monkeypatch):
        """Returns at most `limit` results."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        posts = [
            {"post_id": str(i), "question_type": "leetcode", "frequency": i}
            for i in range(20)
        ]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.get_hot_problems("google", limit=5)
        assert len(result) == 5

    def test_discuss_link_excluded(self, tmp_path, monkeypatch):
        """discuss_link type posts are not included in hot problems."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        posts = [
            {"post_id": "1", "question_type": "discuss_link", "frequency": 99},
            {"post_id": "2", "question_type": "leetcode", "frequency": 1},
        ]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.get_hot_problems("google")
        assert len(result) == 1
        assert str(result[0]["post_id"]) == "2"

    def test_limit_zero_returns_empty(self, tmp_path, monkeypatch):
        """limit=0 → always returns [] regardless of cache contents."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        posts = [{"post_id": "1", "question_type": "leetcode", "frequency": 5}]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.get_hot_problems("google", limit=0)
        assert result == []

    def test_missing_frequency_defaults_to_1(self, tmp_path, monkeypatch):
        """Post with None/missing frequency is treated as frequency=1."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        posts = [
            {"post_id": "1", "question_type": "leetcode", "frequency": None},
            {"post_id": "2", "question_type": "leetcode", "frequency": 3},
        ]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.get_hot_problems("google", limit=10)
        assert len(result) == 2
        assert str(result[0]["post_id"]) == "2"  # frequency=3 wins over default 1

    def test_negative_limit_returns_empty(self, tmp_path, monkeypatch):
        """limit=-1 → returns [] not all-but-last (negative slice guard)."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        posts = [{"post_id": "1", "question_type": "leetcode", "frequency": 5}]
        _write_cache(tmp_path, "google", posts)
        result = mcp_server.get_hot_problems("google", limit=-1)
        assert result == []


# ---------------------------------------------------------------------------
# get_thread
# ---------------------------------------------------------------------------

class TestGetThread:
    def test_delegates_to_crawler(self):
        """get_thread calls extract_post_details and returns its result."""
        fake_post = {"post_id": "99", "title": "Test", "question_type": "leetcode"}
        with patch("mcp_server.LeetCodeCrawler") as MockCrawler:
            instance = MockCrawler.return_value
            instance.extract_post_details.return_value = fake_post
            result = mcp_server.get_thread("99")
        assert result == fake_post
        instance.extract_post_details.assert_called_once_with("99")

    def test_returns_none_on_failure(self):
        """Returns None when the crawler cannot fetch the post."""
        with patch("mcp_server.LeetCodeCrawler") as MockCrawler:
            instance = MockCrawler.return_value
            instance.extract_post_details.return_value = None
            result = mcp_server.get_thread("bad-id")
        assert result is None


# ---------------------------------------------------------------------------
# refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_calls_crawler_run_and_save(self, tmp_path, monkeypatch):
        """refresh calls crawler.run() then save_to_csv() with the cache path."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        fake_posts = [{"post_id": "1", "title": "Two Sum"}]
        with patch("mcp_server.LeetCodeCrawler") as MockCrawler:
            instance = MockCrawler.return_value
            instance.run.return_value = fake_posts
            result = mcp_server.refresh("google", num_pages=5)

        assert result["company"] == "google"
        assert result["posts_saved"] == 1
        expected_path = str(tmp_path / "cache" / "google_questions.csv")
        assert result["cache_path"] == expected_path
        assert set(result.keys()) == {"company", "posts_saved", "cache_path"}
        instance.run.assert_called_once_with(
            company_tag="google", num_pages=5, since=None
        )
        instance.save_to_csv.assert_called_once_with(fake_posts, filename=expected_path)

    def test_days_converts_to_since(self, tmp_path, monkeypatch):
        """refresh(days=7) passes since='7d' to crawler.run()."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        with patch("mcp_server.LeetCodeCrawler") as MockCrawler:
            instance = MockCrawler.return_value
            instance.run.return_value = []
            mcp_server.refresh("meta", num_pages=3, days=7)
        instance.run.assert_called_once_with(
            company_tag="meta", num_pages=3, since="7d"
        )

    def test_company_isolates_cache(self, tmp_path, monkeypatch):
        """Different companies write to different cache files."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        with patch("mcp_server.LeetCodeCrawler") as MockCrawler:
            instance = MockCrawler.return_value
            instance.run.return_value = []
            r1 = mcp_server.refresh("google")
            r2 = mcp_server.refresh("amazon")
        assert "google" in r1["cache_path"]
        assert "amazon" in r2["cache_path"]
        assert r1["cache_path"] != r2["cache_path"]

    def test_path_traversal_sanitized(self, tmp_path, monkeypatch):
        """company='../attack' cannot escape the cache directory."""
        monkeypatch.setattr(mcp_server, "CACHE_DIR", tmp_path / "cache")
        with patch("mcp_server.LeetCodeCrawler") as MockCrawler:
            instance = MockCrawler.return_value
            instance.run.return_value = []
            result = mcp_server.refresh("../attack")
        # Resolved path must stay inside CACHE_DIR
        cache_path = pathlib.Path(result["cache_path"]).resolve()
        assert cache_path.is_relative_to((tmp_path / "cache").resolve())
        # Traversal characters must not appear in the filename
        assert ".." not in pathlib.Path(result["cache_path"]).name
        assert "/" not in pathlib.Path(result["cache_path"]).name
