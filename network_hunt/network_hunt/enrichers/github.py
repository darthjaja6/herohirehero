import httpx
from datetime import datetime

from ..config import config
from .types import EnrichmentResult, KnowledgeItem, ContactItem, Person


def github_get(endpoint: str) -> dict | list:
    """Make a GitHub API request."""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {config.github.token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"{config.github.api_url}{endpoint}"
    print(f"    GitHub: {endpoint}")
    response = httpx.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def search_github(person: Person, incremental: bool = False, cutoff: str | None = None) -> EnrichmentResult:
    """Search GitHub for person's profile and activity."""
    knowledge: list[KnowledgeItem] = []
    contacts: list[ContactItem] = []

    try:
        username = person.github  # Changed from github_username

        # Search for user if no known username
        if not username:
            search_result = github_get(f"/search/users?q={person.name}&per_page=5")

            if search_result.get("items"):
                candidate = search_result["items"][0]

                # Verify name match
                user_details = github_get(f"/users/{candidate['login']}")
                user_name = user_details.get("name", "").lower()
                person_name = person.name.lower()

                if user_name and (person_name in user_name or user_name in person_name):
                    username = candidate["login"]
                    contacts.append(ContactItem(
                        contact_type="github",
                        contact_value=username,
                        confidence="medium",
                        source="github_search",
                    ))

        if not username:
            print(f"    GitHub: No user found for {person.name}")
            return EnrichmentResult(success=True, knowledge=knowledge, contacts=contacts)

        # Get user profile
        user = github_get(f"/users/{username}")

        # Add profile knowledge
        profile_content = " | ".join(filter(None, [
            user.get("bio"),
            f"Repos: {user.get('public_repos', 0)}",
            f"Followers: {user.get('followers', 0)}",
        ]))

        knowledge.append(KnowledgeItem(
            source_type="github",
            source_url=user.get("html_url"),
            title=f"GitHub: {user.get('name') or user.get('login')}",
            content=profile_content,
            content_type="profile",
        ))

        # Extract contacts
        if user.get("email"):
            contacts.append(ContactItem(
                contact_type="email",
                contact_value=user["email"],
                confidence="high",
                source="github_profile",
            ))

        if user.get("blog"):
            contacts.append(ContactItem(
                contact_type="website",
                contact_value=user["blog"],
                confidence="high",
                source="github_profile",
            ))

        if user.get("twitter_username"):
            contacts.append(ContactItem(
                contact_type="twitter",
                contact_value=user["twitter_username"],
                confidence="high",
                source="github_profile",
            ))

        # Get recent repos
        repos = github_get(f"/users/{username}/repos?sort=updated&per_page=10")

        cutoff_dt = None
        if incremental and cutoff:
            cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))

        for repo in repos:
            repo_date = datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00"))

            if cutoff_dt and repo_date < cutoff_dt:
                continue

            repo_content = " | ".join(filter(None, [
                repo.get("description"),
                f"Language: {repo.get('language')}" if repo.get("language") else None,
                f"Stars: {repo.get('stargazers_count', 0)}",
            ]))

            knowledge.append(KnowledgeItem(
                source_type="github",
                source_url=repo.get("html_url"),
                title=repo.get("name"),
                content=repo_content,
                content_type="repo",
                content_date=repo.get("updated_at"),
            ))

        # Get recent activity
        events = github_get(f"/users/{username}/events/public?per_page=30")

        # Filter by date if incremental
        if cutoff_dt:
            events = [
                e for e in events
                if datetime.fromisoformat(e["created_at"].replace("Z", "+00:00")) >= cutoff_dt
            ]

        # Summarize activity
        event_counts: dict[str, int] = {}
        for event in events:
            event_type = event.get("type", "Unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        if event_counts:
            activity_summary = ", ".join(f"{k}: {v}" for k, v in event_counts.items())
            knowledge.append(KnowledgeItem(
                source_type="github",
                source_url=f"https://github.com/{username}",
                title="Recent Activity",
                content=activity_summary,
                content_type="activity",
                content_date=events[0]["created_at"] if events else None,
            ))

        print(f"    GitHub: {len(knowledge)} items, {len(contacts)} contacts")
        return EnrichmentResult(success=True, knowledge=knowledge, contacts=contacts)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"    GitHub: User not found")
            return EnrichmentResult(success=True, knowledge=knowledge, contacts=contacts)
        print(f"    GitHub search failed: {e}")
        return EnrichmentResult(success=False, error=str(e))
    except Exception as e:
        print(f"    GitHub search failed: {e}")
        return EnrichmentResult(success=False, error=str(e))
