import re
import httpx
from datetime import datetime

from ..config import config
from .types import EnrichmentResult, KnowledgeItem, ContactItem, Person


def format_date_filter(after: datetime) -> str:
    """Format date for Google search time filter."""
    return f"cdr:1,cd_min:{after.month}/{after.day}/{after.year}"


def serp_search(query: str, num: int = 20, tbs: str | None = None) -> dict:
    """Execute a SerpAPI search."""
    params = {
        "api_key": config.serp.api_key,
        "engine": "google",
        "q": query,
        "num": str(num),
    }
    if tbs:
        params["tbs"] = tbs

    print(f"    SERP: {query[:60]}...")
    response = httpx.get(config.serp.base_url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def search_twitter(person: Person, incremental: bool = False, cutoff: str | None = None) -> EnrichmentResult:
    """Search for person's Twitter/X activity."""
    knowledge: list[KnowledgeItem] = []
    contacts: list[ContactItem] = []

    try:
        # Build query - use person.twitter (not twitter_username)
        if person.twitter:
            query = f'site:twitter.com/{person.twitter} OR site:x.com/{person.twitter}'
        else:
            query = f'site:twitter.com OR site:x.com "{person.name}"'

        tbs = None
        if incremental and cutoff:
            tbs = format_date_filter(datetime.fromisoformat(cutoff))

        result = serp_search(query, num=20, tbs=tbs)

        for item in result.get("organic_results", []):
            link = item.get("link", "")

            # Extract Twitter username
            match = re.search(r"(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)", link)
            if match and not person.twitter:
                contacts.append(ContactItem(
                    contact_type="twitter",
                    contact_value=match.group(1),
                    confidence="medium",
                    source="serp_twitter_search",
                ))

            knowledge.append(KnowledgeItem(
                source_type="twitter",
                source_url=link,
                source_query=query,
                title=item.get("title"),
                content=item.get("snippet", item.get("title", "")),
                content_type="tweet",
                content_date=item.get("date"),
            ))

        print(f"    Twitter: {len(knowledge)} results")
        return EnrichmentResult(success=True, knowledge=knowledge, contacts=contacts)

    except Exception as e:
        print(f"    Twitter search failed: {e}")
        return EnrichmentResult(success=False, error=str(e))


def search_linkedin(person: Person, incremental: bool = False, cutoff: str | None = None) -> EnrichmentResult:
    """Search for person's LinkedIn profile and posts."""
    knowledge: list[KnowledgeItem] = []
    contacts: list[ContactItem] = []

    try:
        # Search profile - use person.linkedin
        if person.linkedin:
            profile_query = f'site:linkedin.com "{person.linkedin}"'
        else:
            profile_query = f'site:linkedin.com/in "{person.name}" {person.headline or ""}'.strip()

        tbs = None
        if incremental and cutoff:
            tbs = format_date_filter(datetime.fromisoformat(cutoff))

        result = serp_search(profile_query, num=10, tbs=tbs)

        for item in result.get("organic_results", []):
            link = item.get("link", "")

            # Extract LinkedIn URL
            if "linkedin.com/in/" in link and not person.linkedin:
                contacts.append(ContactItem(
                    contact_type="linkedin",
                    contact_value=link,
                    confidence="medium",
                    source="serp_linkedin_search",
                ))

            knowledge.append(KnowledgeItem(
                source_type="linkedin",
                source_url=link,
                source_query=profile_query,
                title=item.get("title"),
                content=item.get("snippet", item.get("title", "")),
                content_type="profile",
            ))

        # Search posts
        posts_query = f'site:linkedin.com/posts "{person.name}"'
        posts_result = serp_search(posts_query, num=10, tbs=tbs)

        for item in posts_result.get("organic_results", []):
            knowledge.append(KnowledgeItem(
                source_type="linkedin",
                source_url=item.get("link"),
                source_query=posts_query,
                title=item.get("title"),
                content=item.get("snippet", item.get("title", "")),
                content_type="post",
                content_date=item.get("date"),
            ))

        print(f"    LinkedIn: {len(knowledge)} results")
        return EnrichmentResult(success=True, knowledge=knowledge, contacts=contacts)

    except Exception as e:
        print(f"    LinkedIn search failed: {e}")
        return EnrichmentResult(success=False, error=str(e))


def search_general(person: Person, incremental: bool = False, cutoff: str | None = None) -> EnrichmentResult:
    """General web search for person."""
    knowledge: list[KnowledgeItem] = []
    contacts: list[ContactItem] = []

    try:
        query = f'"{person.name}" (founder OR CEO OR maker OR startup OR entrepreneur)'

        tbs = None
        if incremental and cutoff:
            tbs = format_date_filter(datetime.fromisoformat(cutoff))

        result = serp_search(query, num=20, tbs=tbs)

        for item in result.get("organic_results", []):
            snippet = item.get("snippet", "")

            knowledge.append(KnowledgeItem(
                source_type="serp",
                source_url=item.get("link"),
                source_query=query,
                title=item.get("title"),
                content=snippet,
                content_type="article",
                content_date=item.get("date"),
            ))

            # Try to extract email
            email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", snippet)
            if email_match:
                contacts.append(ContactItem(
                    contact_type="email",
                    contact_value=email_match.group(0),
                    confidence="low",
                    source="serp_general_search",
                ))

        print(f"    General: {len(knowledge)} results")
        return EnrichmentResult(success=True, knowledge=knowledge, contacts=contacts)

    except Exception as e:
        print(f"    General search failed: {e}")
        return EnrichmentResult(success=False, error=str(e))
