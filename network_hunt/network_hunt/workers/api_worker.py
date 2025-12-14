"""API Worker for crawling Product Hunt API."""

import time
from datetime import datetime, timedelta
from dataclasses import dataclass

from gql import gql, Client
from gql.transport.httpx import HTTPXTransport

from ..config import config
from ..db import supabase
from .base import BaseWorker


@dataclass
class PHProductLink:
    type: str
    url: str


@dataclass
class PHMedia:
    type: str
    url: str


@dataclass
class PHPost:
    id: str
    name: str
    tagline: str | None
    description: str | None
    slug: str
    url: str | None
    website: str | None
    votes_count: int
    comments_count: int
    reviews_rating: float | None
    reviews_count: int
    featured_at: str | None
    created_at: str
    topics: list[str]
    product_links: list[PHProductLink]
    media: list[PHMedia]


GET_POSTS_QUERY = gql("""
    query GetPosts($postedAfter: DateTime, $postedBefore: DateTime, $after: String, $first: Int) {
        posts(
            postedAfter: $postedAfter
            postedBefore: $postedBefore
            featured: true
            order: VOTES
            first: $first
            after: $after
        ) {
            edges {
                node {
                    id
                    name
                    tagline
                    description
                    slug
                    url
                    website
                    votesCount
                    commentsCount
                    reviewsRating
                    reviewsCount
                    featuredAt
                    createdAt
                    topics(first: 10) {
                        edges {
                            node {
                                name
                            }
                        }
                    }
                    productLinks {
                        type
                        url
                    }
                    media {
                        type
                        url
                    }
                }
                cursor
            }
            pageInfo {
                hasNextPage
                endCursor
            }
        }
    }
""")


class APIWorker(BaseWorker):
    """Worker for crawling Product Hunt API by day."""

    task_type = 'crawl_api_day'
    max_attempts = 3
    use_backoff = True

    def __init__(self):
        super().__init__()
        transport = HTTPXTransport(
            url=config.product_hunt.api_url,
            headers={"Authorization": f"Bearer {config.product_hunt.token}"},
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=False)
        self.request_delay = 1.0 / config.product_hunt.requests_per_second

    def process_task(self, task: dict) -> None:
        """Crawl all posts for a specific day."""
        date_str = task['task_params']['date']
        date = datetime.fromisoformat(date_str)

        # Crawl from start of day to end of day
        posted_after = date.replace(hour=0, minute=0, second=0).isoformat()
        posted_before = (date + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat()

        cursor = None
        total_posts = 0

        while True:
            result = self.fetch_posts(posted_after, posted_before, cursor)
            edges = result["posts"]["edges"]
            page_info = result["posts"]["pageInfo"]

            for edge in edges:
                post = self.parse_post(edge["node"])
                self.save_post(post)
                self.create_task('scrape_post', post.slug, {'slug': post.slug})
                total_posts += 1

            if page_info["hasNextPage"] and page_info["endCursor"]:
                cursor = page_info["endCursor"]
                time.sleep(self.request_delay)
            else:
                break

        print(f"    Fetched {total_posts} posts for {date_str}")

    def fetch_posts(
        self,
        posted_after: str,
        posted_before: str,
        cursor: str | None = None,
    ) -> dict:
        """Fetch posts from API."""
        variables = {
            "postedAfter": posted_after,
            "postedBefore": posted_before,
            "after": cursor,
            "first": 20,
        }
        return self.client.execute(GET_POSTS_QUERY, variable_values=variables)

    def parse_post(self, node: dict) -> PHPost:
        """Parse API response into PHPost."""
        topics = [edge["node"]["name"] for edge in node.get("topics", {}).get("edges", [])]

        product_links = [
            PHProductLink(type=pl["type"], url=pl["url"])
            for pl in node.get("productLinks", []) or []
        ]

        media = [
            PHMedia(type=m["type"], url=m["url"])
            for m in node.get("media", []) or []
        ]

        return PHPost(
            id=node["id"],
            name=node["name"],
            tagline=node.get("tagline"),
            description=node.get("description"),
            slug=node["slug"],
            url=node.get("url"),
            website=node.get("website"),
            votes_count=node.get("votesCount", 0),
            comments_count=node.get("commentsCount", 0),
            reviews_rating=node.get("reviewsRating"),
            reviews_count=node.get("reviewsCount", 0),
            featured_at=node.get("featuredAt"),
            created_at=node["createdAt"],
            topics=topics,
            product_links=product_links,
            media=media,
        )

    def save_post(self, post: PHPost):
        """Save post to Supabase."""
        data = {
            "id": post.id,
            "name": post.name,
            "tagline": post.tagline,
            "description": post.description,
            "slug": post.slug,
            "url": post.url,
            "website_url": post.website,
            "votes_count": post.votes_count,
            "comments_count": post.comments_count,
            "reviews_rating": post.reviews_rating,
            "reviews_count": post.reviews_count,
            "topics": post.topics,
            "product_links": [{"type": pl.type, "url": pl.url} for pl in post.product_links],
            "media": [{"type": m.type, "url": m.url} for m in post.media],
            "featured_at": post.featured_at,
            "created_at": post.created_at,
        }
        supabase.table("ph_posts").upsert(data, on_conflict="id").execute()

    @classmethod
    def schedule_backfill(cls, days: int) -> int:
        """Schedule crawl_api_day tasks for the past N days."""
        today = datetime.now().date()
        scheduled = 0

        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.isoformat()

            # Create task only if it doesn't exist
            supabase.table("ph_tasks").upsert({
                "task_type": cls.task_type,
                "task_key": date_str,
                "task_params": {"date": date_str},
                "status": "pending"
            }, on_conflict="task_type,task_key", ignore_duplicates=True).execute()
            scheduled += 1

        print(f"Scheduled {scheduled} crawl_api_day tasks")
        return scheduled

    @classmethod
    def schedule_incremental(cls) -> int:
        """Schedule crawl_api_day task for today."""
        today = datetime.now().date().isoformat()

        supabase.table("ph_tasks").upsert({
            "task_type": cls.task_type,
            "task_key": today,
            "task_params": {"date": today},
            "status": "pending"
        }, on_conflict="task_type,task_key", ignore_duplicates=True).execute()

        print(f"Scheduled crawl_api_day task for {today}")
        return 1
