#!/usr/bin/env python3
"""
LeetCode Discussion Crawler
---------------------------
This script crawls LeetCode discussion forums for interview questions,
particularly focusing on those with Google tags.
"""

import requests
from bs4 import BeautifulSoup
import json
import datetime
import os
import pandas as pd
import time
import logging

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

class LeetCodeCrawler:
    def __init__(self):
        self.base_url = "https://leetcode.com"
        self.discussion_url = f"{self.base_url}/discuss/api/topics"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com/discuss/interview-question/",
        }
        self.session = requests.Session()
        
    def fetch_interview_questions(self, category="interview-question", company_tag="google", num_pages=10):
        """Fetch interview questions from LeetCode discussions."""
        all_posts = []
        
        for page in range(1, num_pages + 1):
            logger.info(f"Fetching page {page} of {company_tag} interview questions...")
            
            params = {
                "categories": category,
                "tags": company_tag,
                "orderBy": "hot",
                "skip": (page - 1) * 15,  # LeetCode shows 15 discussions per page
                "limit": 15,
            }
            
            try:
                response = self.session.get(self.discussion_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                if "topics" not in data:
                    logger.warning(f"No topics found on page {page}. Response: {data}")
                    break
                
                posts = data.get("topics", [])
                if not posts:
                    logger.info(f"No more posts found on page {page}.")
                    break
                
                all_posts.extend(posts)
                logger.info(f"Found {len(posts)} posts on page {page}.")
                
                # Don't hammer the server
                time.sleep(1)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching page {page}: {e}")
                break
                
        return all_posts
    
    def extract_post_details(self, post_id):
        """Extract detailed information from a specific post."""
        try:
            post_url = f"{self.base_url}/discuss/api/topic/{post_id}/"
            response = self.session.get(post_url)
            response.raise_for_status()
            post_data = response.json()
            
            # Extract problem link if available
            content = post_data.get("data", {}).get("post", {}).get("content", "")
            soup = BeautifulSoup(content, "html.parser")
            problem_links = [a["href"] for a in soup.find_all("a") if "problems" in a.get("href", "")]
            problem_link = problem_links[0] if problem_links else None
            
            return {
                "title": post_data.get("data", {}).get("post", {}).get("title", ""),
                "content": post_data.get("data", {}).get("post", {}).get("content", ""),
                "created_at": post_data.get("data", {}).get("post", {}).get("creationDate", ""),
                "author": post_data.get("data", {}).get("post", {}).get("author", {}).get("username", ""),
                "post_id": post_id,
                "url": f"{self.base_url}/discuss/{post_id}/",
                "problem_link": problem_link
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching post {post_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing post {post_id}: {e}")
            return None
    
    def group_by_month(self, posts):
        """Group posts by month."""
        posts_by_month = {}
        
        for post in posts:
            if "created_at" in post and post["created_at"]:
                try:
                    # Parse the creation date
                    date_obj = datetime.datetime.fromisoformat(post["created_at"].replace("Z", "+00:00"))
                    month_key = f"{date_obj.year}-{date_obj.month:02d}"
                    
                    if month_key not in posts_by_month:
                        posts_by_month[month_key] = []
                    
                    posts_by_month[month_key].append(post)
                except Exception as e:
                    logger.error(f"Error parsing date for post {post.get('post_id', 'unknown')}: {e}")
        
        return posts_by_month
    
    def save_to_csv(self, posts, filename="leetcode_interview_questions.csv"):
        """Save posts to a CSV file."""
        df = pd.DataFrame(posts)
        df.to_csv(filename, index=False)
        logger.info(f"Saved {len(posts)} posts to {filename}")
    
    def save_by_month(self, posts_by_month, directory="output"):
        """Save posts grouped by month to separate CSV files."""
        if not os.path.exists(directory):
            os.makedirs(directory)
        
        for month, posts in posts_by_month.items():
            filename = os.path.join(directory, f"leetcode_google_interviews_{month}.csv")
            df = pd.DataFrame(posts)
            df.to_csv(filename, index=False)
            logger.info(f"Saved {len(posts)} posts for {month} to {filename}")
    
    def run(self, company_tag="google", num_pages=10):
        """Run the crawler to fetch and process interview questions."""
        # Fetch all posts from discussion pages
        all_posts = self.fetch_interview_questions(company_tag=company_tag, num_pages=num_pages)
        logger.info(f"Found {len(all_posts)} total posts.")
        
        # Extract detailed information for each post
        detailed_posts = []
        for post in all_posts:
            post_id = post.get("id")
            if post_id:
                logger.info(f"Fetching details for post {post_id}...")
                post_details = self.extract_post_details(post_id)
                if post_details:
                    detailed_posts.append(post_details)
                # Don't hammer the server
                time.sleep(1)
        
        logger.info(f"Processed {len(detailed_posts)} posts with details.")
        
        # Save all posts to a single CSV
        self.save_to_csv(detailed_posts)
        
        # Group by month and save to separate files
        posts_by_month = self.group_by_month(detailed_posts)
        self.save_by_month(posts_by_month)
        
        return detailed_posts

if __name__ == "__main__":
    crawler = LeetCodeCrawler()
    posts = crawler.run(company_tag="google", num_pages=5)  # Start with a small number for testing
    print(f"Crawled {len(posts)} interview questions")
