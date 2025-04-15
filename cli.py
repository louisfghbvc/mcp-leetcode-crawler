#!/usr/bin/env python3
"""
Command-Line Interface for LeetCode Crawler
-------------------------------------------
Provides a user-friendly interface to run the LeetCode crawler with various options.
"""

import argparse
import logging
import sys
from crawler import LeetCodeCrawler

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
    
    args = parser.parse_args()
    
    # Set up logging based on verbosity
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("crawler.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting crawler with company tag: {args.company}, pages: {args.pages}")
    
    # Initialize and run the crawler
    crawler = LeetCodeCrawler()
    posts = crawler.run(company_tag=args.company, num_pages=args.pages)
    
    # Save results
    crawler.save_to_csv(posts, filename=args.output)
    
    # Group by month and save
    posts_by_month = crawler.group_by_month(posts)
    crawler.save_by_month(posts_by_month, directory=args.output_dir)
    
    logger.info(f"Crawler completed. Found {len(posts)} posts.")
    print(f"Crawler completed. Found {len(posts)} posts.")
    print(f"Results saved to {args.output} and grouped by month in {args.output_dir}/")

if __name__ == "__main__":
    main()
