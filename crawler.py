#!/usr/bin/env python3
"""
LeetCode Discussion Crawler
---------------------------
This script crawls LeetCode discussion forums for interview questions,
particularly focusing on those with Google tags.
"""

import datetime
import logging
import os
import re
import time

import pandas as pd
import requests
import tenacity
from bs4 import BeautifulSoup

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("crawler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def _is_retryable(exc):
    """Return True if the exception should trigger a retry.
    JSONDecodeError is never retried — the response is broken, not transient.
    429 and 5xx HTTPErrors are retried. 4xx errors other than 429 are not."""
    if isinstance(exc, requests.exceptions.JSONDecodeError):
        return False
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        if response is not None:
            return response.status_code == 429 or response.status_code >= 500
        return False
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


class LeetCodeCrawler:
    def __init__(self):
        self.base_url = "https://leetcode.com"
        self.discussion_url = f"{self.base_url}/discuss/api/topics"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                          " (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com/discuss/interview-question/",
        }
        self.session = requests.Session()

    def _get_json(self, url, **kwargs):
        """GET a URL with retry/backoff. JSONDecodeError is re-raised immediately
        (no retry). 429 and 5xx are retried up to 3 times (4 total attempts)
        with 2s/4s/8s exponential backoff."""
        @tenacity.retry(
            retry=tenacity.retry_if_exception(_is_retryable),
            wait=tenacity.wait_exponential(multiplier=1, min=2, max=8),
            stop=tenacity.stop_after_attempt(4),
            before_sleep=tenacity.before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _do():
            response = self.session.get(
                url, headers=self.headers, timeout=10, **kwargs
            )
            response.raise_for_status()
            return response.json()

        return _do()

    def fetch_interview_questions(self, category="interview-question", company_tag="google", num_pages=10):
        """Fetch interview questions from LeetCode discussions."""
        all_posts = []

        for page in range(1, num_pages + 1):
            logger.info(f"Fetching page {page} of {company_tag} interview questions...")
            params = {
                "categories": category,
                "tags": company_tag,
                "orderBy": "hot",
                "skip": (page - 1) * 15,
                "limit": 15,
            }
            try:
                data = self._get_json(self.discussion_url, params=params)

                if "topics" not in data:
                    logger.warning(f"No topics found on page {page}. Response: {data}")
                    break

                posts = data.get("topics", [])
                if not posts:
                    logger.info(f"No more posts found on page {page}.")
                    break

                all_posts.extend(posts)
                logger.info(f"Found {len(posts)} posts on page {page}.")
                time.sleep(1)

            except requests.exceptions.JSONDecodeError as e:
                logger.error(f"JSON decode error on page {page}: {e}")
                continue
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching page {page}: {e}")
                continue

        return all_posts

    def extract_post_details(self, post_id):
        """Extract detailed information from a specific post."""
        try:
            post_url = f"{self.base_url}/discuss/api/topic/{post_id}/"
            post_data = self._get_json(post_url)

            post = ((post_data.get("data") or {}).get("post") or {})
            content = post.get("content") or ""
            soup = BeautifulSoup(content, "html.parser")

            # Cache anchor list — avoid two full tree traversals
            all_anchors = soup.find_all("a")

            # Extract LeetCode problem link — require leetcode.com hostname to
            # avoid external URLs like "evil.com/problems/two-sum" polluting dedup.
            problem_links = [
                a["href"] for a in all_anchors
                if "leetcode.com/problems/" in a.get("href", "")
                or a.get("href", "").startswith("/problems/")
            ]
            problem_link = problem_links[0] if problem_links else None

            # Classify question type:
            #   leetcode     — direct /problems/ link found
            #   discuss_link — links to another discuss post (no problem link)
            #   discussion   — pure text, no links
            if problem_link:
                question_type = "leetcode"
            elif any("/discuss/" in a.get("href", "") for a in all_anchors):
                question_type = "discuss_link"
            else:
                question_type = "discussion"

            # Plain-text description. Full text stored here;
            # truncation to 2000 chars happens at CSV export time.
            question_description = soup.get_text(separator=" ", strip=True)

            return {
                "title": post.get("title", ""),
                "question_description": question_description,
                "question_type": question_type,
                "created_at": post.get("creationDate", ""),
                "author": (post.get("author") or {}).get("username", ""),
                "post_id": post_id,
                "url": f"{self.base_url}/discuss/{post_id}/",
                "problem_link": problem_link,
            }

        except requests.exceptions.JSONDecodeError as e:
            logger.error(f"JSON decode error for post {post_id}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching post {post_id}: {e}")
            return None
        except (AttributeError, TypeError, KeyError) as e:
            # Guard against unexpected API response shapes (e.g. list instead of dict)
            logger.error(f"Unexpected API response shape for post {post_id}: {e}")
            return None

    def deduplicate(self, posts):
        """Deduplicate posts by LeetCode problem slug (extracted from problem_link).
        Keeps the most recent post per slug as canonical; adds integer field `frequency`.
        Posts with no extractable slug get frequency=1 and are kept without merging."""
        slug_groups = {}
        no_slug = []

        for post in posts:
            problem_link = post.get("problem_link") or ""
            slug = None
            if problem_link:
                m = re.search(r"/problems/([^/?#]+)", problem_link)
                if m:
                    slug = m.group(1)

            if slug:
                slug_groups.setdefault(slug, []).append(post)
            else:
                no_slug.append(post)

        result = []

        for slug, group in slug_groups.items():
            # Pick the most-recent post as canonical in O(k) instead of O(k log k)
            canonical = dict(max(
                group,
                key=lambda p: (p.get("created_at") or "", p.get("url") or ""),
            ))
            canonical["frequency"] = len(group)
            result.append(canonical)

        for post in no_slug:
            p = dict(post)
            p["frequency"] = 1
            result.append(p)

        return result

    def filter_by_since(self, posts, since_str):
        """Return posts created within the given window.
        since_str format: Nd (days) or Nw (weeks), e.g. '7d' or '2w'.
        Posts with missing created_at are included (conservative).
        Naive datetimes are treated as UTC."""
        m = re.fullmatch(r"(\d+)([dw])", since_str)
        if not m:
            raise ValueError(
                "Invalid --since format. Use Nd (days) or Nw (weeks), e.g. --since 7d"
            )
        n = int(m.group(1))
        unit = m.group(2)
        delta = datetime.timedelta(days=n) if unit == "d" else datetime.timedelta(weeks=n)
        cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - delta

        result = []
        for post in posts:
            created_at = post.get("created_at")
            if not created_at:
                result.append(post)
                continue
            try:
                dt = datetime.datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
                if dt >= cutoff:
                    result.append(post)
            except (ValueError, TypeError):
                result.append(post)
        return result

    def group_by_month(self, posts):
        """Group posts by month. Posts missing created_at are skipped."""
        posts_by_month = {}
        for post in posts:
            if "created_at" in post and post["created_at"]:
                try:
                    date_obj = datetime.datetime.fromisoformat(
                        str(post["created_at"]).replace("Z", "+00:00")
                    )
                    month_key = f"{date_obj.year}-{date_obj.month:02d}"
                    posts_by_month.setdefault(month_key, []).append(post)
                except (ValueError, AttributeError) as e:
                    logger.error(
                        f"Error parsing date for post {post.get('post_id', 'unknown')}: {e}"
                    )
        return posts_by_month

    def save_to_csv(self, posts, filename="leetcode_interview_questions.csv"):
        """Save posts to a CSV file. Truncates question_description to 2000 chars."""
        df = pd.DataFrame(posts)
        if "question_description" in df.columns:
            df["question_description"] = df["question_description"].str[:2000]
        df.to_csv(filename, index=False)
        logger.info(f"Saved {len(posts)} posts to {filename}")

    def save_by_month(self, posts_by_month, directory="output", company_tag="google"):
        """Save posts grouped by month to separate CSV files."""
        os.makedirs(directory, exist_ok=True)
        safe_tag = re.sub(r"[^\w\-]", "_", company_tag)
        for month, posts in posts_by_month.items():
            filename = os.path.join(
                directory, f"leetcode_{safe_tag}_interviews_{month}.csv"
            )
            df = pd.DataFrame(posts)
            if "question_description" in df.columns:
                df["question_description"] = df["question_description"].str[:2000]
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(posts)} posts for {month} to {filename}")

    def run(self, company_tag="google", num_pages=10, category="interview-question", since=None):
        """Fetch, process, deduplicate, and optionally filter posts.
        Returns the post list — callers are responsible for saving."""
        all_posts = self.fetch_interview_questions(
            category=category, company_tag=company_tag, num_pages=num_pages
        )
        logger.info(f"Found {len(all_posts)} total posts.")

        detailed_posts = []
        for post in all_posts:
            post_id = post.get("id")
            if post_id:
                logger.info(f"Fetching details for post {post_id}...")
                post_details = self.extract_post_details(post_id)
                if post_details:
                    detailed_posts.append(post_details)
                time.sleep(1)

        logger.info(f"Processed {len(detailed_posts)} posts with details.")

        detailed_posts = self.deduplicate(detailed_posts)
        logger.info(f"After deduplication: {len(detailed_posts)} posts.")

        if since:
            detailed_posts = self.filter_by_since(detailed_posts, since)
            logger.info(f"After --since filter: {len(detailed_posts)} posts.")

        return detailed_posts


if __name__ == "__main__":
    crawler = LeetCodeCrawler()
    posts = crawler.run(company_tag="google", num_pages=5)
    print(f"Crawled {len(posts)} interview questions")
    crawler.save_to_csv(posts)
    posts_by_month = crawler.group_by_month(posts)
    crawler.save_by_month(posts_by_month, company_tag="google")
