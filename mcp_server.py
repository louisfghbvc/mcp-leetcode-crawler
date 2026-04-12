#!/usr/bin/env python3
"""
MCP Server for LeetCode Discussion Crawler
------------------------------------------
Exposes 4 tools via the Model Context Protocol (stdio transport):
  search_discussions - filter cached posts by company + time window
  get_hot_problems   - top LeetCode problems ranked by frequency
  get_thread         - real-time single-thread fetch
  refresh            - crawl and rebuild the on-disk cache

Usage:
  python mcp_server.py            # run as stdio MCP server
  mcp install mcp_server.py       # register with Claude Desktop

Cache lives in ./cache/{company}_questions.csv.
Run `refresh` once to populate it before using other tools.
"""

import pathlib
import re

import pandas as pd
from mcp.server.fastmcp import FastMCP

from crawler import LeetCodeCrawler

CACHE_DIR = pathlib.Path(__file__).parent / "cache"

mcp = FastMCP("leetcode-discussions")


def _cache_path(company: str) -> pathlib.Path:
    safe = re.sub(r"[^\w\-]", "_", company)
    CACHE_DIR.mkdir(exist_ok=True)
    return CACHE_DIR / f"{safe}_questions.csv"


def _load_cache(company: str) -> list[dict]:
    path = _cache_path(company)
    if not path.exists():
        return []
    try:
        df = pd.read_csv(str(path))
    except Exception:
        return []
    records = df.to_dict(orient="records")
    # Replace float NaN with None — works for all dtypes (v != v is True only for NaN)
    return [
        {k: None if (isinstance(v, float) and v != v) else v for k, v in r.items()}
        for r in records
    ]


@mcp.tool()
def search_discussions(company: str = "google", days: int = 30) -> list[dict]:
    """Search recent LeetCode discussion posts for a company.

    Args:
        company: Company tag, e.g. 'google', 'meta', 'amazon'. (default: google)
        days: How many days back to include. (default: 30)

    Returns cached posts filtered to the given time window.
    Run `refresh` first to populate the cache.
    """
    if days < 0:
        raise ValueError(f"days must be >= 0, got {days}")
    posts = _load_cache(company)
    if not posts:
        return []
    crawler = LeetCodeCrawler()
    return crawler.filter_by_since(posts, f"{days}d")


@mcp.tool()
def get_hot_problems(company: str = "google", limit: int = 10) -> list[dict]:
    """Get top LeetCode problems by discussion frequency for a company.

    Args:
        company: Company tag, e.g. 'google', 'meta', 'amazon'. (default: google)
        limit: Max problems to return, sorted by frequency. (default: 10)

    Returns only posts with question_type='leetcode', sorted by frequency descending.
    Run `refresh` first to populate the cache.
    """
    posts = _load_cache(company)
    if not posts:
        return []
    limit = max(0, limit)
    leetcode_posts = [p for p in posts if p.get("question_type") == "leetcode"]
    # int(float(...)) handles both NaN-replaced-None and pandas float-string "5.0" forms
    leetcode_posts.sort(key=lambda p: int(float(p.get("frequency") or 1)), reverse=True)
    return leetcode_posts[:limit]


@mcp.tool()
def get_thread(post_id: str) -> dict | None:
    """Fetch a single LeetCode discussion thread in real-time.

    Args:
        post_id: The LeetCode discussion post ID (numeric string).

    Makes a live HTTP request. Returns None if the post cannot be fetched.
    Does not use or update the cache.
    """
    crawler = LeetCodeCrawler()
    return crawler.extract_post_details(post_id)


@mcp.tool()
def refresh(
    company: str = "google",
    num_pages: int = 10,
    days: int | None = None,
) -> dict:
    """Crawl LeetCode and rebuild the on-disk cache for a company.

    Args:
        company: Company tag, e.g. 'google', 'meta', 'amazon'. (default: google)
        num_pages: Pages of discussions to crawl (15 posts/page). (default: 10)
        days: If set, only cache posts from the last N days.

    Returns a summary dict with 'company', 'posts_saved', and 'cache_path'.
    """
    crawler = LeetCodeCrawler()
    since = f"{days}d" if days is not None else None
    posts = crawler.run(company_tag=company, num_pages=num_pages, since=since)
    path = _cache_path(company)
    crawler.save_to_csv(posts, filename=str(path))
    return {"company": company, "posts_saved": len(posts), "cache_path": str(path)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
