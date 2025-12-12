from dataclasses import dataclass, field
from typing import Literal


SourceType = Literal["twitter", "linkedin", "github", "arxiv", "serp", "product_hunt", "website"]
ContactType = Literal["email", "twitter", "linkedin", "github", "website", "phone", "other"]
Confidence = Literal["high", "medium", "low"]
TaskType = Literal["twitter", "linkedin", "github", "arxiv", "general", "full"]


@dataclass
class KnowledgeItem:
    source_type: SourceType
    content: str
    source_url: str | None = None
    source_query: str | None = None
    title: str | None = None
    content_type: str | None = None
    content_date: str | None = None


@dataclass
class ContactItem:
    contact_type: ContactType
    contact_value: str
    confidence: Confidence
    source: str


@dataclass
class EnrichmentResult:
    success: bool
    knowledge: list[KnowledgeItem] = field(default_factory=list)
    contacts: list[ContactItem] = field(default_factory=list)
    error: str | None = None


@dataclass
class Person:
    """Person data from Supabase persons table."""
    id: str
    name: str
    headline: str | None = None
    # Platform IDs
    ph_id: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    github: str | None = None
    # Contact info
    website: str | None = None
    email: str | None = None
    # Per-channel cutoffs for incremental enrichment
    twitter_cutoff: str | None = None
    linkedin_cutoff: str | None = None
    github_cutoff: str | None = None
    arxiv_cutoff: str | None = None
    serp_cutoff: str | None = None
