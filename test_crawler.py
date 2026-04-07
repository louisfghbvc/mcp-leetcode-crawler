#!/usr/bin/env python3
"""
Unit tests for LeetCodeCrawler.
Uses `responses` to mock HTTP calls — no real network access.
"""

import datetime

import pytest
import responses as responses_lib

from crawler import LeetCodeCrawler


DISCUSS_API = "https://leetcode.com/discuss/api/topics"
TOPIC_API = "https://leetcode.com/discuss/api/topic"


def _make_topic_list(n=15, prefix="post"):
    return [{"id": f"{prefix}-{i}"} for i in range(n)]


def _make_post_response(post_id, content="", title="Test", created_at="2026-01-01T00:00:00Z", author="user"):
    return {
        "data": {
            "post": {
                "title": title,
                "content": content,
                "creationDate": created_at,
                "author": {"username": author},
            }
        }
    }


# ---------------------------------------------------------------------------
# HTTP Resilience
# ---------------------------------------------------------------------------

class TestHTTPResilience:
    @responses_lib.activate
    def test_429_retry_then_success(self):
        """429 on first call, success on second → 15 posts returned, 2 HTTP calls."""
        crawler = LeetCodeCrawler()

        responses_lib.add(
            responses_lib.GET, DISCUSS_API,
            json={"error": "rate limited"}, status=429,
        )
        responses_lib.add(
            responses_lib.GET, DISCUSS_API,
            json={"topics": _make_topic_list(15)}, status=200,
        )
        # Page 2 — empty to stop pagination
        responses_lib.add(
            responses_lib.GET, DISCUSS_API,
            json={"topics": []}, status=200,
        )

        posts = crawler.fetch_interview_questions(num_pages=5)
        assert len(posts) == 15
        # First URL hit twice (retry) + once for page 2 = 3 calls total
        assert len(responses_lib.calls) >= 2

    @responses_lib.activate
    def test_3x_500_exhaust_returns_partial(self):
        """3 consecutive 500s on page 1 → empty list, no exception."""
        crawler = LeetCodeCrawler()

        for _ in range(3):
            responses_lib.add(
                responses_lib.GET, DISCUSS_API,
                json={"error": "server error"}, status=500,
            )

        posts = crawler.fetch_interview_questions(num_pages=5)
        assert posts == []

    @responses_lib.activate
    def test_two_page_pagination(self):
        """Page 1 → 15, page 2 → 15, page 3 → empty → 30 posts returned."""
        crawler = LeetCodeCrawler()

        responses_lib.add(responses_lib.GET, DISCUSS_API,
                          json={"topics": _make_topic_list(15, "a")}, status=200)
        responses_lib.add(responses_lib.GET, DISCUSS_API,
                          json={"topics": _make_topic_list(15, "b")}, status=200)
        responses_lib.add(responses_lib.GET, DISCUSS_API,
                          json={"topics": []}, status=200)

        posts = crawler.fetch_interview_questions(num_pages=5)
        assert len(posts) == 30

    @responses_lib.activate
    def test_malformed_json_returns_none(self):
        """Malformed JSON body → extract_post_details returns None."""
        crawler = LeetCodeCrawler()

        responses_lib.add(
            responses_lib.GET, f"{TOPIC_API}/42/",
            body=b"not-json", status=200,
            content_type="application/json",
        )

        result = crawler.extract_post_details("42")
        assert result is None


# ---------------------------------------------------------------------------
# Data Grouping
# ---------------------------------------------------------------------------

class TestGroupByMonth:
    def test_missing_created_at_skipped(self):
        """Post with no created_at is skipped; others grouped correctly."""
        crawler = LeetCodeCrawler()
        posts = [
            {"post_id": "1", "created_at": "2026-03-15T00:00:00Z"},
            {"post_id": "2", "created_at": "2026-03-20T00:00:00Z"},
            {"post_id": "3"},  # no created_at
        ]
        result = crawler.group_by_month(posts)
        assert "2026-03" in result
        assert len(result["2026-03"]) == 2
        # No KeyError, no crash
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_same_slug_frequency_3(self):
        """3 posts with same problem_link → 1 result with frequency=3."""
        crawler = LeetCodeCrawler()
        posts = [
            {"post_id": str(i), "problem_link": "https://leetcode.com/problems/two-sum/",
             "created_at": f"2026-01-0{i+1}T00:00:00Z", "url": f"https://leetcode.com/discuss/{i}/"}
            for i in range(3)
        ]
        result = crawler.deduplicate(posts)
        assert len(result) == 1
        assert result[0]["frequency"] == 3

    def test_no_url_all_kept_frequency_1(self):
        """3 posts with no problem_link → all 3 returned, each frequency=1."""
        crawler = LeetCodeCrawler()
        posts = [
            {"post_id": str(i), "problem_link": None}
            for i in range(3)
        ]
        result = crawler.deduplicate(posts)
        assert len(result) == 3
        assert all(p["frequency"] == 1 for p in result)


# ---------------------------------------------------------------------------
# Time Filter
# ---------------------------------------------------------------------------

class TestFilterBySince:
    def test_7d_filters_old_posts(self):
        """2 posts within 7 days, 1 post 30 days old → 2 returned."""
        crawler = LeetCodeCrawler()
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        posts = [
            {"post_id": "1", "created_at": (now - datetime.timedelta(days=2)).isoformat()},
            {"post_id": "2", "created_at": (now - datetime.timedelta(days=5)).isoformat()},
            {"post_id": "3", "created_at": (now - datetime.timedelta(days=30)).isoformat()},
        ]
        result = crawler.filter_by_since(posts, "7d")
        assert len(result) == 2
        assert all(p["post_id"] in ("1", "2") for p in result)

    def test_invalid_format_raises_value_error(self):
        """'2x' is invalid → ValueError with clear message."""
        crawler = LeetCodeCrawler()
        with pytest.raises(ValueError, match="Invalid --since format"):
            crawler.filter_by_since([], "2x")

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime string (no timezone) succeeds without TypeError."""
        crawler = LeetCodeCrawler()
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        # Strip timezone info to make naive
        naive_ts = (now - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        posts = [{"post_id": "1", "created_at": naive_ts}]
        result = crawler.filter_by_since(posts, "7d")
        assert len(result) == 1

    def test_missing_created_at_included(self):
        """Post with no created_at → included (conservative)."""
        crawler = LeetCodeCrawler()
        posts = [{"post_id": "1"}]
        result = crawler.filter_by_since(posts, "7d")
        assert len(result) == 1

    def test_invalid_format_via_argparse(self):
        """CLI --since 2x → argparse SystemExit with error message."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "cli.py", "--since", "2x", "--pages", "0"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0
        assert "Invalid --since format" in result.stderr


# ---------------------------------------------------------------------------
# Category Wiring
# ---------------------------------------------------------------------------

class TestCategoryWiring:
    @responses_lib.activate
    def test_category_passed_to_api(self):
        """fetch_interview_questions(category='general') → HTTP params contain categories=general."""
        crawler = LeetCodeCrawler()

        responses_lib.add(responses_lib.GET, DISCUSS_API,
                          json={"topics": []}, status=200)

        crawler.fetch_interview_questions(category="general", num_pages=1)

        assert len(responses_lib.calls) == 1
        request = responses_lib.calls[0].request
        assert "categories=general" in request.url


# ---------------------------------------------------------------------------
# Question Type Classification
# ---------------------------------------------------------------------------

class TestQuestionTypeClassification:
    @responses_lib.activate
    def test_leetcode_type(self):
        """Post with /problems/ link → question_type='leetcode'."""
        crawler = LeetCodeCrawler()
        content = '<a href="https://leetcode.com/problems/two-sum/">Two Sum</a>'
        responses_lib.add(
            responses_lib.GET, f"{TOPIC_API}/1/",
            json=_make_post_response("1", content=content), status=200,
        )
        result = crawler.extract_post_details("1")
        assert result["question_type"] == "leetcode"
        assert result["problem_link"] == "https://leetcode.com/problems/two-sum/"

    @responses_lib.activate
    def test_discuss_link_type(self):
        """Post with /discuss/ link but no /problems/ → question_type='discuss_link'."""
        crawler = LeetCodeCrawler()
        content = '<a href="https://leetcode.com/discuss/12345/">See this thread</a>'
        responses_lib.add(
            responses_lib.GET, f"{TOPIC_API}/2/",
            json=_make_post_response("2", content=content), status=200,
        )
        result = crawler.extract_post_details("2")
        assert result["question_type"] == "discuss_link"
        assert result["problem_link"] is None

    @responses_lib.activate
    def test_discussion_type(self):
        """Post with no links → question_type='discussion'."""
        crawler = LeetCodeCrawler()
        content = "<p>Describe an algorithm to balance a BST.</p>"
        responses_lib.add(
            responses_lib.GET, f"{TOPIC_API}/3/",
            json=_make_post_response("3", content=content), status=200,
        )
        result = crawler.extract_post_details("3")
        assert result["question_type"] == "discussion"
        assert result["problem_link"] is None

    @responses_lib.activate
    def test_html_stripped_from_description(self):
        """question_description is plain text, no HTML tags."""
        crawler = LeetCodeCrawler()
        content = "<p>Find the <strong>longest</strong> substring.</p>"
        responses_lib.add(
            responses_lib.GET, f"{TOPIC_API}/4/",
            json=_make_post_response("4", content=content), status=200,
        )
        result = crawler.extract_post_details("4")
        assert "<" not in result["question_description"]
        assert "longest" in result["question_description"]

    @responses_lib.activate
    def test_null_content_returns_empty_description(self):
        """Post with null content → question_description='' and type='discussion'."""
        crawler = LeetCodeCrawler()
        responses_lib.add(
            responses_lib.GET, f"{TOPIC_API}/5/",
            json={"data": {"post": {
                "title": "Empty",
                "content": None,
                "creationDate": "2026-01-01T00:00:00Z",
                "author": {"username": "user"},
            }}},
            status=200,
        )
        result = crawler.extract_post_details("5")
        assert result is not None
        assert result["question_description"] == ""
        assert result["question_type"] == "discussion"


# ---------------------------------------------------------------------------
# CSV Truncation
# ---------------------------------------------------------------------------

class TestCSVTruncation:
    def test_question_description_truncated_at_2000(self, tmp_path):
        """save_to_csv truncates question_description to 2000 chars."""
        crawler = LeetCodeCrawler()
        posts = [{"post_id": "1", "question_description": "x" * 3000}]
        output = tmp_path / "out.csv"
        crawler.save_to_csv(posts, filename=str(output))

        import pandas as pd
        df = pd.read_csv(str(output))
        assert len(df["question_description"][0]) == 2000
