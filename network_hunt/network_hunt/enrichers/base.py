import hashlib
import time
from datetime import datetime

from ..db import supabase
from ..db.local import insert_knowledge, get_pending_tasks, update_task_status, queue_task
from .types import EnrichmentResult, KnowledgeItem, ContactItem, Person, TaskType
from .serp import search_twitter, search_linkedin, search_general
from .github import search_github
from .arxiv import search_arxiv


TASK_HANDLERS = {
    "twitter": search_twitter,
    "linkedin": search_linkedin,
    "github": search_github,
    "arxiv": search_arxiv,
    "general": search_general,
}

# Map task type to cutoff column name
CUTOFF_COLUMNS = {
    "twitter": "twitter_cutoff",
    "linkedin": "linkedin_cutoff",
    "github": "github_cutoff",
    "arxiv": "arxiv_cutoff",
    "general": "serp_cutoff",
}


def hash_content(content: str) -> str:
    """Generate SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


def get_person(person_id: str) -> Person | None:
    """Get person by ID from Supabase."""
    result = supabase.table("persons").select("*").eq("id", person_id).single().execute()

    if not result.data:
        return None

    data = result.data
    return Person(
        id=data["id"],
        name=data["name"],
        headline=data.get("headline"),
        ph_id=data.get("ph_id"),
        twitter=data.get("twitter"),
        linkedin=data.get("linkedin"),
        github=data.get("github"),
        website=data.get("website"),
        email=data.get("email"),
        twitter_cutoff=data.get("twitter_cutoff"),
        linkedin_cutoff=data.get("linkedin_cutoff"),
        github_cutoff=data.get("github_cutoff"),
        arxiv_cutoff=data.get("arxiv_cutoff"),
        serp_cutoff=data.get("serp_cutoff"),
    )


def save_knowledge(person_id: str, items: list[KnowledgeItem]) -> int:
    """Save knowledge items to local SQLite."""
    saved = 0

    for item in items:
        content_hash = hash_content(f"{item.source_type}:{item.source_url}:{item.content}")

        if insert_knowledge(
            person_id=person_id,
            source_type=item.source_type,
            content=item.content,
            content_hash=content_hash,
            source_url=item.source_url,
            source_query=item.source_query,
            title=item.title,
            content_type=item.content_type,
            content_date=item.content_date,
        ):
            saved += 1

    return saved


def update_person_from_contacts(person_id: str, contacts: list[ContactItem]):
    """Update person record in Supabase with high-confidence contacts."""
    updates = {}

    for contact in contacts:
        if contact.confidence != "high":
            continue

        if contact.contact_type == "twitter":
            updates["twitter"] = contact.contact_value
        elif contact.contact_type == "github":
            updates["github"] = contact.contact_value
        elif contact.contact_type == "linkedin":
            updates["linkedin"] = contact.contact_value
        elif contact.contact_type == "email":
            updates["email"] = contact.contact_value
        elif contact.contact_type == "website":
            updates["website"] = contact.contact_value

    if updates:
        supabase.table("persons").update(updates).eq("id", person_id).execute()


def get_cutoff_for_task(person: Person, task_type: str) -> str | None:
    """Get the appropriate cutoff date for a task type."""
    if task_type == "twitter":
        return person.twitter_cutoff
    elif task_type == "linkedin":
        return person.linkedin_cutoff
    elif task_type == "github":
        return person.github_cutoff
    elif task_type == "arxiv":
        return person.arxiv_cutoff
    elif task_type == "general":
        return person.serp_cutoff
    return None


def enrich_person(
    person_id: str,
    task_types: list[TaskType] | None = None,
    incremental: bool = False,
) -> dict:
    """Enrich a person with data from various sources."""
    if task_types is None:
        task_types = ["full"]

    person = get_person(person_id)
    if not person:
        return {"success": False, "knowledge": 0, "contacts": 0}

    print(f"\nEnriching: {person.name}")
    print(f"  Tasks: {task_types}, Incremental: {incremental}")

    all_knowledge: list[KnowledgeItem] = []
    all_contacts: list[ContactItem] = []

    # Determine which tasks to run
    tasks_to_run = list(TASK_HANDLERS.keys()) if "full" in task_types else [t for t in task_types if t != "full"]

    cutoff_updates = {}
    now = datetime.now().isoformat()

    for task_type in tasks_to_run:
        handler = TASK_HANDLERS.get(task_type)
        if not handler:
            continue

        try:
            # Use per-channel cutoff for incremental mode
            task_cutoff = get_cutoff_for_task(person, task_type) if incremental else None
            result = handler(person, incremental, task_cutoff)

            if result.success:
                all_knowledge.extend(result.knowledge)
                all_contacts.extend(result.contacts)
                # Update cutoff for this channel
                cutoff_col = CUTOFF_COLUMNS.get(task_type)
                if cutoff_col:
                    cutoff_updates[cutoff_col] = now

        except Exception as e:
            print(f"    {task_type} error: {e}")

        time.sleep(1)  # Rate limiting between sources

    # Save results to local SQLite
    knowledge_count = save_knowledge(person_id, all_knowledge)

    # Update person with high-confidence contacts in Supabase
    update_person_from_contacts(person_id, all_contacts)

    # Update per-channel cutoffs in Supabase
    if cutoff_updates:
        supabase.table("persons").update(cutoff_updates).eq("id", person_id).execute()

    print(f"  Done: {knowledge_count} knowledge, {len(all_contacts)} contacts")

    return {"success": True, "knowledge": knowledge_count, "contacts": len(all_contacts)}


def queue_enrichment(
    person_id: str,
    task_type: TaskType = "full",
    priority: int = 0,
):
    """Add person to enrichment queue in local SQLite."""
    queue_task(person_id, task_type, priority)


def queue_top_persons(min_score: int = 50, limit: int = 100) -> int:
    """Queue top persons by importance score for enrichment."""
    result = supabase.table("persons").select("id, importance_score").gte(
        "importance_score", min_score
    ).order("importance_score", desc=True).limit(limit).execute()

    queued = 0
    for person in result.data or []:
        queue_task(person["id"], "full", priority=person["importance_score"])
        queued += 1

    print(f"Queued {queued} persons for enrichment")
    return queued


def process_queue(limit: int = 10):
    """Process pending enrichment tasks from local SQLite."""
    tasks = get_pending_tasks(limit)
    print(f"Processing {len(tasks)} enrichment tasks")

    for task in tasks:
        # Mark as processing
        update_task_status(task["id"], "processing")

        try:
            result = enrich_person(task["person_id"], [task["task_type"]], incremental=False)

            if result["success"]:
                update_task_status(task["id"], "completed")
            else:
                raise Exception("Enrichment failed")

        except Exception as e:
            error_msg = str(e)

            if task["attempts"] + 1 >= task["max_attempts"]:
                update_task_status(task["id"], "failed", error_msg)
            else:
                update_task_status(task["id"], "pending", error_msg)

        time.sleep(2)  # Rate limiting between tasks
