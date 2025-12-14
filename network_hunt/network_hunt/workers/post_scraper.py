"""Post Scraper Worker for scraping makers from post pages."""

from ..db import supabase
from ..scrapers.ph_profile import PHProfileScraper
from .base import BaseWorker


class PostScraperWorker(BaseWorker):
    """Worker for scraping makers from Product Hunt post pages."""

    task_type = 'scrape_post'
    max_attempts = 3
    max_consecutive_failures = 5
    use_backoff = True
    backoff_base_seconds = 5.0  # Longer backoff for web scraping

    def __init__(self):
        super().__init__()
        self.scraper: PHProfileScraper | None = None

    def setup(self):
        """Start the browser."""
        self.scraper = PHProfileScraper(headless=False)
        self.scraper.start()

    def teardown(self):
        """Close the browser."""
        if self.scraper:
            self.scraper.close()
            self.scraper = None

    def process_task(self, task: dict) -> None:
        """Scrape makers from a post page."""
        slug = task['task_params']['slug']
        usernames = self.scraper.scrape_post_people(slug)

        for username in usernames:
            self.save_post_person(slug, username)
            self.create_task('scrape_profile', username, {'username': username})

        print(f"    Found {len(usernames)} makers")

    def save_post_person(self, post_slug: str, username: str):
        """Save post-person relationship to Supabase."""
        supabase.table("ph_post_people").upsert({
            "post_slug": post_slug,
            "username": username
        }, on_conflict="post_slug,username").execute()
