#!/usr/bin/env python3
"""
Unit tests for the CLI --enrich integration path.
No actual API calls or crawling — all external calls are mocked.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

import cli


def _mock_crawler(posts):
    """Return a mock LeetCodeCrawler that returns `posts` from run()."""
    crawler = MagicMock()
    crawler.run.return_value = posts
    crawler.filter_by_since.return_value = posts
    crawler.group_by_month.return_value = {}
    return crawler


class TestCliEnrich:
    def test_enrich_flag_calls_enrich_posts(self, capsys):
        """--enrich passes posts through enrich_posts before saving."""
        fake_posts = [{"post_id": "1", "title": "Two Sum"}]

        def fake_enrich(posts, **kwargs):
            for p in posts:
                p["reported_outcome"] = "passed"
            return posts

        with patch("cli.LeetCodeCrawler", return_value=_mock_crawler(fake_posts)), \
             patch("cli.enrich_posts", side_effect=fake_enrich) as mock_enrich:
            with pytest.raises(SystemExit, match="0") if False else __import__("contextlib").nullcontext():
                cli_args = ["--enrich", "--company", "google", "--pages", "1",
                            "--output", "/dev/null", "--output-dir", "/tmp"]
                with patch("sys.argv", ["cli.py"] + cli_args):
                    cli.main()

        mock_enrich.assert_called_once_with(fake_posts)

    def test_no_enrich_flag_skips_enrich_posts(self):
        """Without --enrich, enrich_posts is never called."""
        fake_posts = [{"post_id": "1", "title": "Two Sum"}]

        with patch("cli.LeetCodeCrawler", return_value=_mock_crawler(fake_posts)), \
             patch("cli.enrich_posts") as mock_enrich:
            with patch("sys.argv", ["cli.py", "--company", "google", "--pages", "1",
                                    "--output", "/dev/null", "--output-dir", "/tmp"]):
                cli.main()

        mock_enrich.assert_not_called()
