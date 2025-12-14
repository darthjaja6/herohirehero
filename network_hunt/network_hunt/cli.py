#!/usr/bin/env python3
"""Network Hunt CLI - Discover talented makers from Product Hunt."""

import click

from .db import supabase
from .workers import APIWorker, PostScraperWorker, ProfileScraperWorker


@click.group()
def cli():
    """Network Hunt - Discover and track talented makers from Product Hunt."""
    pass


# ========== Crawl Commands ==========

@cli.group()
def crawl():
    """Crawl Product Hunt data."""
    pass


@crawl.command("api")
@click.option("-m", "--mode", type=click.Choice(["backfill", "incremental"]), default="incremental")
@click.option("-d", "--days", type=int, default=7, help="Days to crawl back (backfill mode)")
@click.option("--schedule-only", is_flag=True, help="Only schedule tasks, don't run")
@click.option("-l", "--limit", type=int, default=100, help="Maximum tasks to process")
def crawl_api(mode: str, days: int, schedule_only: bool, limit: int):
    """Crawl Product Hunt API for posts."""
    if mode == "backfill":
        APIWorker.schedule_backfill(days)
    else:
        APIWorker.schedule_incremental()

    if not schedule_only:
        APIWorker().run(limit)


@crawl.command("posts")
@click.option("-l", "--limit", type=int, default=100, help="Maximum tasks to process")
def crawl_posts(limit: int):
    """Scrape post pages for makers."""
    PostScraperWorker().run(limit)


@crawl.command("profiles")
@click.option("-l", "--limit", type=int, default=100, help="Maximum tasks to process")
def crawl_profiles(limit: int):
    """Scrape user profiles."""
    ProfileScraperWorker().run(limit)


@crawl.command("all")
@click.option("-m", "--mode", type=click.Choice(["backfill", "incremental"]), default="incremental")
@click.option("-d", "--days", type=int, default=7, help="Days to crawl back (backfill mode)")
@click.option("-l", "--limit", type=int, default=100, help="Maximum tasks per stage")
def crawl_all(mode: str, days: int, limit: int):
    """Run all crawl stages in sequence."""
    click.echo("=== Stage 1: API ===")
    if mode == "backfill":
        APIWorker.schedule_backfill(days)
    else:
        APIWorker.schedule_incremental()
    APIWorker().run(limit)

    click.echo("\n=== Stage 2: Post Scraping ===")
    PostScraperWorker().run(limit)

    click.echo("\n=== Stage 3: Profile Scraping ===")
    ProfileScraperWorker().run(limit)

    click.echo("\nAll stages completed!")


# ========== Task Commands ==========

@cli.command("tasks")
@click.option("--retry-failed", is_flag=True, help="Reset failed tasks to pending")
@click.option("--cleanup", is_flag=True, help="Reset stale processing tasks")
def tasks(retry_failed: bool, cleanup: bool):
    """Show task queue status."""
    if retry_failed:
        result = supabase.table("ph_tasks").update({
            "status": "pending",
            "error": None
        }).eq("status", "failed").execute()
        click.echo(f"Reset {len(result.data or [])} failed tasks to pending")
        return

    if cleanup:
        for worker_cls in [APIWorker, PostScraperWorker, ProfileScraperWorker]:
            worker_cls().cleanup_stale_tasks()
        return

    click.echo("\nTask Queue Status\n")

    for worker_cls in [APIWorker, PostScraperWorker, ProfileScraperWorker]:
        stats = worker_cls.get_stats()
        total = sum(stats.values())
        click.echo(f"  {worker_cls.task_type}:")
        click.echo(f"    {stats['pending']:4d} pending, {stats['completed']:4d} completed, {stats['failed']:4d} failed")


# ========== Stats Command ==========

@cli.command()
def stats():
    """Show database statistics."""
    # Supabase counts
    posts = supabase.table("ph_posts").select("id", count="exact").execute()
    post_people = supabase.table("ph_post_people").select("id", count="exact").execute()
    profiles = supabase.table("ph_profiles").select("username", count="exact").execute()

    click.echo("\nDatabase Statistics (Supabase)\n")
    click.echo(f"  Posts:          {posts.count or 0}")
    click.echo(f"  Post People:    {post_people.count or 0}")
    click.echo(f"  Profiles:       {profiles.count or 0}")

    # Task stats
    click.echo("\nTask Queue:\n")
    for worker_cls in [APIWorker, PostScraperWorker, ProfileScraperWorker]:
        stats = worker_cls.get_stats()
        click.echo(f"  {worker_cls.task_type}:")
        click.echo(f"    {stats['pending']:4d} pending, {stats['completed']:4d} completed, {stats['failed']:4d} failed")

    # Top posts
    top_posts = supabase.table("ph_posts").select(
        "name, votes_count"
    ).order("votes_count", desc=True).limit(5).execute()

    if top_posts.data:
        click.echo("\nTop Posts by Votes:\n")
        for p in top_posts.data:
            click.echo(f"  {p['votes_count']:4d} - {p['name']}")

    # Top profiles
    top_profiles = supabase.table("ph_profiles").select(
        "username, name, followers_count, links"
    ).order("followers_count", desc=True).limit(5).execute()

    if top_profiles.data:
        click.echo("\nTop Profiles by Followers:\n")
        for p in top_profiles.data:
            links = p.get("links") or []
            link_count = len(links)
            link_str = f" [{link_count} links]" if link_count else ""
            click.echo(f"  {p['followers_count']:5d} - @{p['username']} ({p['name']}){link_str}")


# ========== Reset Command ==========

@cli.command("reset")
@click.option("--confirm", is_flag=True, help="Confirm reset")
@click.option("--tasks-only", is_flag=True, help="Only reset tasks, keep data")
def reset(confirm: bool, tasks_only: bool):
    """Reset all crawl progress and data."""
    if not confirm:
        if tasks_only:
            click.echo("This will delete all tasks from ph_tasks.")
        else:
            click.echo("This will delete all ph_posts, ph_post_people, ph_profiles, and ph_tasks.")
        click.echo("Run with --confirm to proceed.")
        return

    click.echo("Resetting...")

    # Always clear tasks
    supabase.table("ph_tasks").delete().neq("task_type", "").execute()
    click.echo("  Cleared ph_tasks")

    if not tasks_only:
        supabase.table("ph_profiles").delete().neq("username", "").execute()
        click.echo("  Cleared ph_profiles")

        supabase.table("ph_post_people").delete().neq("username", "").execute()
        click.echo("  Cleared ph_post_people")

        supabase.table("ph_posts").delete().neq("id", "").execute()
        click.echo("  Cleared ph_posts")

    click.echo("\nReset complete!")


if __name__ == "__main__":
    cli()
