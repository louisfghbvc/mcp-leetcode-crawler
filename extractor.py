#!/usr/bin/env python3
"""
AI Extraction Layer
-------------------
Uses Claude Haiku to transform raw discussion posts into structured data:
  problem_name, leetcode_url, interview_stage, difficulty, reported_outcome

Usage (standalone):
    from extractor import enrich_posts
    enriched = enrich_posts(posts)

Cost: ~$0.001 per post with claude-haiku-4-5-20251001.
Enriched fields are added in-place — existing fields are preserved.
"""

import json
import logging
import os
import time

import anthropic

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are analyzing a LeetCode interview discussion post. Extract structured data from it.

Post title: {title}
Post content: {content}

Extract EXACTLY these 5 fields and respond with ONLY a valid JSON object, no explanation:

{{
  "problem_name": "<LeetCode problem name, e.g. 'LRU Cache' — or null if none mentioned>",
  "leetcode_url": "<full URL e.g. 'https://leetcode.com/problems/lru-cache/' — or null>",
  "interview_stage": "<one of: 'phone screen', 'online assessment', 'onsite', 'final round', or null>",
  "difficulty": "<one of: 'easy', 'medium', 'hard', or null if not mentioned>",
  "reported_outcome": "<one of: 'passed', 'failed', 'no mention'>"
}}

Rules:
- If a problem_link is available in the post, prefer it for leetcode_url over guessing.
- difficulty should reflect what the author says, not your own assessment.
- reported_outcome is 'no mention' when the author doesn't say whether they passed or failed.
- Return null (JSON null) for unknown fields — never make up values."""

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_RETRY_SLEEP = 5  # seconds between retries on rate limit


def _extract_one(client: anthropic.Anthropic, post: dict, model: str) -> dict:
    """Call Claude to extract structured fields from one post. Returns extracted dict."""
    title = post.get("title") or ""
    content = (post.get("question_description") or "")[:1500]  # keep tokens bounded
    # If we already have a problem_link, hint the model
    problem_link = post.get("problem_link")
    if problem_link:
        content = f"[Known problem link: {problem_link}]\n\n{content}"

    # Escape user-controlled curly braces so str.format() doesn't crash on {title}
    # or {content} values that themselves contain {placeholder}-like substrings.
    safe_title = title.replace("{", "{{").replace("}", "}}")
    safe_content = content.replace("{", "{{").replace("}", "}}")
    prompt = _EXTRACTION_PROMPT.format(title=safe_title, content=safe_content)

    for attempt in range(3):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            # Strip markdown code fences — handle any language tag (```json, ```javascript, etc.)
            if raw.startswith("```"):
                first_newline = raw.find("\n")
                raw = raw[first_newline + 1:] if first_newline != -1 else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3].rstrip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed for post {post.get('post_id')}: {e}")
            return {}
        except anthropic.RateLimitError:
            if attempt < 2:
                logger.warning(f"Rate limited — sleeping {_RETRY_SLEEP}s")
                time.sleep(_RETRY_SLEEP)
            else:
                logger.error(f"Rate limit exhausted for post {post.get('post_id')}")
                return {}
        except anthropic.APIError as e:
            logger.error(f"API error for post {post.get('post_id')}: {e}")
            return {}

    return {}


def enrich_posts(
    posts: list[dict],
    model: str = _DEFAULT_MODEL,
    api_key: str | None = None,
) -> list[dict]:
    """Enrich a list of posts with AI-extracted structured fields.

    Each post gets 5 new fields added:
      problem_name, leetcode_url, interview_stage, difficulty, reported_outcome

    Already-enriched posts (those with 'reported_outcome' set) are skipped.

    Args:
        posts: List of post dicts from crawler.run() or _load_cache().
        model: Claude model ID (default: claude-haiku-4-5-20251001).
        api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns:
        The same list with enrichment fields added in-place. Also returns it
        for convenience (modifies the original list).
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError(
            "Anthropic API key required. Set ANTHROPIC_API_KEY or pass api_key=..."
        )

    client = anthropic.Anthropic(api_key=key)
    enriched_count = 0
    skipped_count = 0

    for post in posts:
        # Skip already-enriched posts
        if post.get("reported_outcome") is not None:
            skipped_count += 1
            continue

        extracted = _extract_one(client, post, model)
        post["problem_name"] = extracted.get("problem_name")
        post["leetcode_url"] = extracted.get("leetcode_url") or post.get("problem_link")
        post["interview_stage"] = extracted.get("interview_stage")
        post["difficulty"] = extracted.get("difficulty")
        if extracted:
            post["reported_outcome"] = extracted.get("reported_outcome", "no mention")
            enriched_count += 1
        else:
            # Leave reported_outcome as None so the post can be retried on the next
            # enrich_posts call. Setting "no mention" here would make API failures
            # indistinguishable from successful extractions, permanently skip-listing
            # posts that never got a real API response.
            post["reported_outcome"] = None

    failed_count = len(posts) - enriched_count - skipped_count
    logger.info(
        f"Enriched {enriched_count} posts ({skipped_count} already done, "
        f"{failed_count} failed)."
    )
    return posts
