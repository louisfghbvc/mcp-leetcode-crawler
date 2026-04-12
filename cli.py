#!/usr/bin/env python3
"""
Command-Line Interface for LeetCode Crawler
-------------------------------------------
Provides a user-friendly interface to run the LeetCode crawler with various options.
"""

import argparse
import logging
import re
import sys
from crawler import LeetCodeCrawler
from extractor import enrich_posts


def _parse_since(value):
    """Validate --since argument format: Nd (days) or Nw (weeks)."""
    if not re.fullmatch(r"\d+[dw]", value):
        raise argparse.ArgumentTypeError(
            "Invalid --since format. Use Nd (days) or Nw (weeks), e.g. --since 7d"
        )
    return value


def main():
    parser = argparse.ArgumentParser(description="Crawl LeetCode discussion forums for interview questions")

    # Company tag options
    parser.add_argument("--company", type=str, default="google",
                        help="Company tag to filter questions (default: google)")

    # Pagination options
    parser.add_argument("--pages", type=int, default=10,
                        help="Number of pages to crawl (default: 10)")

    # Output options
    parser.add_argument("--output", type=str, default="leetcode_interview_questions.csv",
                        help="Output CSV file path (default: leetcode_interview_questions.csv)")

    # Directory for monthly output
    parser.add_argument("--output-dir", type=str, default="output",
                        help="Directory for monthly output files (default: output)")

    # Verbosity
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose logging")

    # Category
    parser.add_argument("--category", type=str, default="interview-question",
                        help="Category to crawl (default: interview-question)")

    # Time window filter
    parser.add_argument("--since", type=_parse_since, default=None,
                        help="Only include posts from the last N days/weeks (e.g. 7d, 2w)")

    # AI enrichment
    parser.add_argument("--enrich", action="store_true",
                        help="Use Claude Haiku to extract problem_name, difficulty, "
                             "interview_stage, reported_outcome from each post "
                             "(requires ANTHROPIC_API_KEY)")

    args = parser.parse_args()

    # Adjust log level without calling basicConfig again (crawler.py already called it)
    logging.getLogger().setLevel(logging.DEBUG if args.verbose else logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info(f"Starting crawler with company tag: {args.company}, pages: {args.pages}")

    # Initialize and run the crawler
    crawler = LeetCodeCrawler()
    posts = crawler.run(
        company_tag=args.company,
        num_pages=args.pages,
        category=args.category,
        since=args.since,
    )

    # AI enrichment (optional)
    if args.enrich:
        logger.info("Enriching posts with AI extraction...")
        posts = enrich_posts(posts)
        logger.info(f"Enrichment complete.")

    # Save results
    crawler.save_to_csv(posts, filename=args.output)

    # Group by month and save
    posts_by_month = crawler.group_by_month(posts)
    crawler.save_by_month(posts_by_month, directory=args.output_dir, company_tag=args.company)

    logger.info(f"Crawler completed. Found {len(posts)} posts.")
    print(f"Crawler completed. Found {len(posts)} posts.")
    print(f"Results saved to {args.output} and grouped by month in {args.output_dir}/")


if __name__ == "__main__":
    main()
