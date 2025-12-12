import time
import xml.etree.ElementTree as ET
import httpx
from datetime import datetime

from ..config import config
from .types import EnrichmentResult, KnowledgeItem, Person


ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def normalize_author_name(name: str) -> str:
    """Convert 'John Doe' to 'john_doe' for arXiv search."""
    return name.lower().replace(" ", "_")


def search_arxiv(person: Person, incremental: bool = False, cutoff: str | None = None) -> EnrichmentResult:
    """Search arXiv for papers by person."""
    knowledge: list[KnowledgeItem] = []

    try:
        author_name = normalize_author_name(person.name)
        search_query = f"au:{author_name}"

        params = {
            "search_query": search_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": "20",
        }

        print(f"    arXiv: {search_query}")
        response = httpx.get(config.arxiv.api_url, params=params, timeout=30)
        response.raise_for_status()

        # Parse XML
        root = ET.fromstring(response.text)

        cutoff_dt = None
        if incremental and cutoff:
            cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))

        for entry in root.findall("atom:entry", ARXIV_NS):
            # Parse entry
            paper_id = entry.find("atom:id", ARXIV_NS)
            title = entry.find("atom:title", ARXIV_NS)
            summary = entry.find("atom:summary", ARXIV_NS)
            published = entry.find("atom:published", ARXIV_NS)

            if paper_id is None or title is None:
                continue

            # Get authors
            authors = [
                author.find("atom:name", ARXIV_NS).text
                for author in entry.findall("atom:author", ARXIV_NS)
                if author.find("atom:name", ARXIV_NS) is not None
            ]

            # Get categories
            categories = [
                cat.get("term", "")
                for cat in entry.findall("atom:category", ARXIV_NS)
            ]

            # Get link
            link_elem = entry.find("atom:link[@type='text/html']", ARXIV_NS)
            if link_elem is None:
                link_elem = entry.find("atom:link", ARXIV_NS)
            link = link_elem.get("href") if link_elem is not None else paper_id.text

            published_date = published.text if published is not None else None

            # Skip if before cutoff
            if cutoff_dt and published_date:
                paper_date = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
                if paper_date < cutoff_dt:
                    continue

            # Verify author name matches
            author_match = any(
                person.name.lower() in author.lower() or author.lower() in person.name.lower()
                for author in authors
            )
            if not author_match:
                continue

            # Build content
            summary_text = summary.text.strip()[:500] if summary is not None else ""
            content = f"{summary_text}... | Authors: {', '.join(authors)} | Categories: {', '.join(categories)}"

            knowledge.append(KnowledgeItem(
                source_type="arxiv",
                source_url=link,
                source_query=search_query,
                title=title.text.strip().replace("\n", " ") if title.text else None,
                content=content,
                content_type="paper",
                content_date=published_date,
            ))

        # Respect rate limit
        time.sleep(config.arxiv.delay_seconds)

        print(f"    arXiv: {len(knowledge)} papers")
        return EnrichmentResult(success=True, knowledge=knowledge, contacts=[])

    except Exception as e:
        print(f"    arXiv search failed: {e}")
        return EnrichmentResult(success=False, error=str(e))
