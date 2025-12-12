#!/usr/bin/env python3
"""Network Hunt CLI - Discover talented makers from Product Hunt."""

import click

from .db import supabase
from .db.local import (
    get_posts_count, get_top_posts, get_post,
    get_person_posts_count, get_person_total_votes,
    get_knowledge_count, get_queue_stats,
)
from .crawlers import crawl_producthunt
from .enrichers import enrich_person, process_queue, queue_top_persons


@click.group()
def cli():
    """Network Hunt - Discover and track talented makers from Product Hunt."""
    pass


@cli.command()
@click.option("-m", "--mode", type=click.Choice(["backfill", "incremental"]), default="incremental")
@click.option("-d", "--days", type=int, default=7, help="Days to crawl back (backfill mode)")
@click.option("--max-posts", type=int, default=None, help="Maximum posts to crawl")
def crawl(mode: str, days: int, max_posts: int | None):
    """Crawl Product Hunt for posts and makers."""
    click.echo(f"Starting {mode} crawl...")
    crawl_producthunt(mode, days=days, max_posts=max_posts)  # type: ignore
    click.echo("Crawl completed!")


@cli.command()
@click.option("-p", "--person-id", default=None, help="Specific person ID to enrich")
@click.option("-t", "--task", type=click.Choice(["twitter", "linkedin", "github", "arxiv", "general", "full"]), default="full")
@click.option("-i", "--incremental", is_flag=True, help="Only fetch new data since last enrichment")
@click.option("--min-score", type=int, default=0, help="Minimum importance score for batch enrichment")
@click.option("-l", "--limit", type=int, default=10, help="Maximum persons to enrich")
def enrich(person_id: str | None, task: str, incremental: bool, min_score: int, limit: int):
    """Enrich person data from various sources."""
    if person_id:
        click.echo(f"Enriching person {person_id}...")
        result = enrich_person(person_id, [task], incremental)  # type: ignore
        click.echo(f"Result: {result}")
    else:
        click.echo(f"Queuing top persons (min score: {min_score}, limit: {limit})...")
        queued = queue_top_persons(min_score, limit)
        click.echo(f"Queued {queued} persons")
        click.echo("Processing queue...")
        process_queue(limit)


@cli.command()
@click.option("--process", is_flag=True, help="Process pending tasks")
@click.option("-l", "--limit", type=int, default=10, help="Maximum tasks to process")
@click.option("--status", "show_status", is_flag=True, help="Show queue status")
def queue(process: bool, limit: int, show_status: bool):
    """Manage the enrichment queue."""
    if show_status:
        # Use local SQLite queue stats
        stats = get_queue_stats()
        click.echo("Queue Status (local SQLite):")
        click.echo(f"  Pending:    {stats.get('pending', 0)}")
        click.echo(f"  Processing: {stats.get('processing', 0)}")
        click.echo(f"  Completed:  {stats.get('completed', 0)}")
        click.echo(f"  Failed:     {stats.get('failed', 0)}")

    if process:
        click.echo(f"Processing up to {limit} tasks...")
        process_queue(limit)


@cli.command()
def stats():
    """Show database statistics."""
    # Local SQLite
    posts_count = get_posts_count()
    knowledge_count = get_knowledge_count()

    # Supabase
    persons = supabase.table("persons").select("id", count="exact").execute()

    click.echo("\nDatabase Statistics\n")
    click.echo("Supabase:")
    click.echo(f"  Persons:        {persons.count or 0}")
    click.echo("\nLocal SQLite:")
    click.echo(f"  Posts:          {posts_count}")
    click.echo(f"  Knowledge:      {knowledge_count}")

    # Queue stats
    queue_stats = get_queue_stats()
    click.echo(f"\nQueue: {queue_stats.get('pending', 0)} pending, {queue_stats.get('completed', 0)} completed")

    # Top posts from local DB
    top_posts = get_top_posts(5)
    if top_posts:
        click.echo("\nTop Posts by Votes (local):\n")
        for p in top_posts:
            click.echo(f"  {p['votes_count']:4d} - {p['name']}")

    # Top persons from Supabase
    top = supabase.table("persons").select(
        "name, importance_score, twitter, github"
    ).order("importance_score", desc=True).limit(10).execute()

    if top.data:
        click.echo("\nTop Persons by Importance Score:\n")
        for p in top.data:
            socials = []
            if p.get("twitter"):
                socials.append(f"@{p['twitter']}")
            if p.get("github"):
                socials.append(f"gh:{p['github']}")
            social_str = f" ({', '.join(socials)})" if socials else ""
            click.echo(f"  {p['importance_score']:4d} - {p['name']}{social_str}")


@cli.command()
@click.option("-l", "--limit", type=int, default=20, help="Number of persons to show")
@click.option("--with-email", is_flag=True, help="Only show persons with email")
@click.option("--with-twitter", is_flag=True, help="Only show persons with Twitter")
@click.option("--min-score", type=int, default=0, help="Minimum importance score")
def persons(limit: int, with_email: bool, with_twitter: bool, min_score: int):
    """List persons in database."""
    query = supabase.table("persons").select(
        "id, name, headline, twitter, github, email, importance_score"
    ).order("importance_score", desc=True).limit(limit)

    if with_email:
        query = query.not_.is_("email", "null")
    if with_twitter:
        query = query.not_.is_("twitter", "null")
    if min_score > 0:
        query = query.gte("importance_score", min_score)

    result = query.execute()

    click.echo("\nPersons\n")
    for p in result.data or []:
        click.echo(f"[{p['importance_score']}] {p['name']}")
        if p.get("headline"):
            click.echo(f"    {p['headline']}")

        contacts = []
        if p.get("twitter"):
            contacts.append(f"Twitter: @{p['twitter']}")
        if p.get("github"):
            contacts.append(f"GitHub: {p['github']}")
        if p.get("email"):
            contacts.append(f"Email: {p['email']}")

        if contacts:
            click.echo(f"    {' | '.join(contacts)}")
        click.echo(f"    ID: {p['id']}")
        click.echo("")


@cli.command("update-scores")
def update_scores():
    """Recalculate importance scores for all persons."""
    click.echo("Updating importance scores...")

    persons_result = supabase.table("persons").select("id, twitter, github").execute()

    updated = 0
    for person in persons_result.data or []:
        person_id = person["id"]

        # Get maker posts count and total votes from local SQLite
        post_count = get_person_posts_count(person_id)
        total_votes = get_person_total_votes(person_id)

        score = (
            post_count * 10 +
            total_votes // 10 +
            (5 if person.get("twitter") else 0) +
            (5 if person.get("github") else 0)
        )

        supabase.table("persons").update({"importance_score": score}).eq("id", person_id).execute()
        updated += 1

    click.echo(f"Updated scores for {updated} persons")


if __name__ == "__main__":
    cli()
