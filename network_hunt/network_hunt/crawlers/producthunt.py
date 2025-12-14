import time
from datetime import datetime, timedelta
from typing import Literal
from dataclasses import dataclass, asdict
from gql import gql, Client
from gql.transport.httpx import HTTPXTransport

from ..config import config
from ..db import supabase
from ..scrapers.ph_profile import PHProfileScraper, PHProfile


@dataclass
class PHComment:
    id: str
    body: str | None
    created_at: str | None
    user_id: str | None
    user_name: str | None
    user_username: str | None


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
    comments: list[PHComment]


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


class ProductHuntCrawler:
    def __init__(self):
        transport = HTTPXTransport(
            url=config.product_hunt.api_url,
            headers={"Authorization": f"Bearer {config.product_hunt.token}"},
        )
        self.client = Client(transport=transport, fetch_schema_from_transport=False)
        self.request_delay = 1.0 / config.product_hunt.requests_per_second

    def get_source_state(self) -> dict | None:
        """Get crawl state from Supabase."""
        result = supabase.table("data_source_state").select("*").eq("source", "product_hunt").single().execute()
        return result.data

    def update_source_state(self, **updates):
        """Update crawl state in Supabase."""
        supabase.table("data_source_state").update(updates).eq("source", "product_hunt").execute()

    def fetch_posts(
        self,
        posted_after: str | None = None,
        posted_before: str | None = None,
        after: str | None = None,
        first: int = 20,
    ) -> dict:
        variables = {
            "postedAfter": posted_after,
            "postedBefore": posted_before,
            "after": after,
            "first": first,
        }
        print(f"  Fetching posts: after={posted_after}, before={posted_before}")
        result = self.client.execute(GET_POSTS_QUERY, variable_values=variables)
        return result

    def parse_post(self, node: dict) -> PHPost:
        topics = [edge["node"]["name"] for edge in node.get("topics", {}).get("edges", [])]

        product_links = [
            PHProductLink(type=pl["type"], url=pl["url"])
            for pl in node.get("productLinks", []) or []
        ]

        media = [
            PHMedia(type=m["type"], url=m["url"])
            for m in node.get("media", []) or []
        ]

        # Comments 需要单独查询，这里先返回空（API 复杂度限制）
        comments: list[PHComment] = []

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
            comments=comments,
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

    def crawl_backfill(self, days: int = 30, max_posts: int | None = None):
        """Crawl historical data, going backwards from oldest_date."""
        state = self.get_source_state()
        if not state or state["status"] != "active":
            print("Backfill crawl is not active")
            return

        start_date = datetime.fromisoformat(state["oldest_date"]) if state["oldest_date"] else datetime.now()
        end_date = start_date - timedelta(days=days)

        print(f"Backfill: {start_date.date()} -> {end_date.date()}")

        cursor = state.get("last_cursor")
        current_date = start_date
        total_posts = 0

        while current_date > end_date:
            if max_posts and total_posts >= max_posts:
                break

            day_before = current_date - timedelta(days=1)

            try:
                result = self.fetch_posts(
                    posted_after=day_before.isoformat(),
                    posted_before=current_date.isoformat(),
                    after=cursor,
                )

                edges = result["posts"]["edges"]
                page_info = result["posts"]["pageInfo"]

                for edge in edges:
                    if max_posts and total_posts >= max_posts:
                        break

                    post = self.parse_post(edge["node"])
                    self.save_post(post)

                    total_posts += 1
                    print(f"[{total_posts}] {post.name} ({post.votes_count} votes)")

                if page_info["hasNextPage"] and page_info["endCursor"]:
                    cursor = page_info["endCursor"]
                    self.update_source_state(last_cursor=cursor)
                else:
                    cursor = None
                    current_date = day_before
                    self.update_source_state(
                        oldest_date=current_date.date().isoformat(),
                        last_cursor=None,
                    )
                    print(f"  Completed day, moving to {current_date.date()}")

                time.sleep(self.request_delay)

            except Exception as e:
                print(f"Error: {e}")
                raise

        print(f"\nBackfill complete. Total posts: {total_posts}")

    def crawl_incremental(self):
        """Crawl new data from newest_date to today."""
        state = self.get_source_state()
        if not state or state["status"] != "active":
            print("Incremental crawl is not active")
            return

        last_date = datetime.fromisoformat(state["newest_date"]) if state["newest_date"] else datetime.now()
        today = datetime.now()

        if last_date.date() >= today.date():
            print("Already up to date")
            return

        print(f"Incremental: {last_date.date()} -> {today.date()}")

        cursor = None
        total_posts = 0
        has_more = True

        while has_more:
            try:
                result = self.fetch_posts(
                    posted_after=last_date.isoformat(),
                    posted_before=today.isoformat(),
                    after=cursor,
                )

                edges = result["posts"]["edges"]
                page_info = result["posts"]["pageInfo"]

                for edge in edges:
                    post = self.parse_post(edge["node"])
                    self.save_post(post)

                    total_posts += 1
                    print(f"[{total_posts}] {post.name} ({post.votes_count} votes)")

                if page_info["hasNextPage"] and page_info["endCursor"]:
                    cursor = page_info["endCursor"]
                else:
                    has_more = False

                time.sleep(self.request_delay)

            except Exception as e:
                print(f"Error: {e}")
                raise

        self.update_source_state(
            newest_date=today.date().isoformat(),
            last_cursor=None,
        )
        print(f"\nIncremental complete. Total new posts: {total_posts}")

    def crawl(self, mode: Literal["backfill", "incremental"], days: int = 7, max_posts: int | None = None):
        if mode == "backfill":
            self.crawl_backfill(days=days, max_posts=max_posts)
        else:
            self.crawl_incremental()

    def scrape_posts(self, slugs: list[str]):
        """Scrape usernames from post pages and save to Supabase."""
        print(f"\nScraping {len(slugs)} posts for usernames...")
        with PHProfileScraper() as scraper:
            for i, slug in enumerate(slugs):
                try:
                    usernames = scraper.scrape_post_people(slug)
                    for username in usernames:
                        supabase.table("ph_post_people").upsert(
                            {"post_slug": slug, "username": username},
                            on_conflict="post_slug,username"
                        ).execute()
                    print(f"  [{i+1}/{len(slugs)}] {slug}: {len(usernames)} makers")
                except Exception as e:
                    print(f"  [{i+1}/{len(slugs)}] {slug}: error - {e}")

    def get_unscraped_usernames(self) -> list[str]:
        """Get usernames from ph_post_people that don't have profiles yet."""
        # Get all usernames from ph_post_people
        post_people = supabase.table("ph_post_people").select("username").execute()
        all_usernames = set(row["username"] for row in post_people.data)

        # Get usernames that already have profiles
        profiles = supabase.table("ph_profiles").select("username").execute()
        scraped_usernames = set(row["username"] for row in profiles.data)

        # Return unscraped
        return list(all_usernames - scraped_usernames)

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
            "collections": [c.name if hasattr(c, "name") else c for c in profile.collections] if profile.collections else None,
            "reviews": [
                {"tool": r.tool_name, "product": r.product_name, "text": r.text} if hasattr(r, "tool_name") else r
                for r in profile.reviews
            ] if profile.reviews else None,
        }
        supabase.table("ph_profiles").upsert(data, on_conflict="username").execute()

    def scrape_profiles(self):
        """Scrape profiles for all usernames that don't have profiles yet."""
        usernames = self.get_unscraped_usernames()
        if not usernames:
            print("No unscraped usernames found")
            return

        print(f"\nScraping {len(usernames)} profiles...")
        with PHProfileScraper() as scraper:
            for i, username in enumerate(usernames):
                try:
                    profile = scraper.scrape_full_profile(username)
                    self.save_profile(profile)
                    print(f"  [{i+1}/{len(usernames)}] @{username}: {profile.name}")
                except Exception as e:
                    print(f"  [{i+1}/{len(usernames)}] @{username}: error - {e}")


def crawl_producthunt(
    mode: Literal["backfill", "incremental"],
    days: int = 7,
    max_posts: int | None = None,
    scrape: bool = False,
):
    crawler = ProductHuntCrawler()
    crawler.crawl(mode, days=days, max_posts=max_posts)

    if scrape:
        # Get recent posts from Supabase
        result = supabase.table("ph_posts").select("slug").order(
            "fetched_at", desc=True
        ).limit(max_posts or 100).execute()
        slugs = [row["slug"] for row in result.data]

        if slugs:
            crawler.scrape_posts(slugs)
            crawler.scrape_profiles()
