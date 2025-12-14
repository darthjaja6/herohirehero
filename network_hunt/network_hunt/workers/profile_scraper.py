"""Profile Scraper Worker for scraping user profiles."""

from ..db import supabase
from ..scrapers.ph_profile import PHProfileScraper, PHProfile
from .base import BaseWorker


class ProfileScraperWorker(BaseWorker):
    """Worker for scraping Product Hunt user profiles."""

    task_type = 'scrape_profile'
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
        """Scrape a user profile."""
        username = task['task_params']['username']
        profile = self.scraper.scrape_full_profile(username)
        self.save_profile(profile)

    def save_profile(self, profile: PHProfile):
        """Save profile to Supabase."""
        data = {
            "username": profile.username,
            "name": profile.name,
            "headline": profile.headline,
            "bio": profile.bio,
            "avatar_url": profile.avatar_url,
            "links": profile.links if profile.links else None,
            "followers_count": profile.followers_count,
            "following_count": profile.following_count,
            "hunted_count": profile.hunted_count,
            "collections_count": profile.collections_count,
            "reviews_count": profile.reviews_count,
            "badges": profile.badges if profile.badges else None,
            "following": profile.following if profile.following else None,
            "hunted_posts": profile.hunted_posts if profile.hunted_posts else None,
            "collections": [
                c.name if hasattr(c, "name") else c for c in profile.collections
            ] if profile.collections else None,
            "reviews": [
                {"tool": r.tool_name, "product": r.product_name, "text": r.text}
                if hasattr(r, "tool_name") else r
                for r in profile.reviews
            ] if profile.reviews else None,
        }
        supabase.table("ph_profiles").upsert(data, on_conflict="username").execute()
