"""Base worker class with common task queue logic."""

import time
from abc import ABC, abstractmethod
from datetime import datetime

from ..db import supabase


class BaseWorker(ABC):
    """Base class for all workers."""

    # Subclass must define
    task_type: str

    # Configurable
    max_attempts: int = 3
    max_consecutive_failures: int = 5
    processing_timeout_minutes: int = 10

    # Exponential back-off
    use_backoff: bool = True
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 60.0

    def __init__(self):
        self.consecutive_failures = 0

    # ========== Subclass must implement ==========

    @abstractmethod
    def process_task(self, task: dict) -> None:
        """Process a single task. Subclass implements specific logic."""
        raise NotImplementedError

    # ========== Subclass can override ==========

    def setup(self):
        """Called before processing tasks. E.g., start browser."""
        pass

    def teardown(self):
        """Called after processing tasks. E.g., close browser."""
        pass

    # ========== Common logic ==========

    def run(self, limit: int = 100):
        """Main entry point."""
        self.cleanup_stale_tasks()
        tasks = self.get_pending_tasks(limit)

        if not tasks:
            print(f"No pending {self.task_type} tasks")
            return

        print(f"Processing {len(tasks)} {self.task_type} tasks...")

        self.setup()
        completed = 0
        failed = 0

        try:
            for i, task in enumerate(tasks):
                if self.consecutive_failures >= self.max_consecutive_failures:
                    print(f"Too many consecutive failures ({self.consecutive_failures}), stopping")
                    break

                self.mark_processing(task['id'])

                try:
                    self.process_task(task)
                    self.mark_completed(task['id'])
                    self.consecutive_failures = 0
                    completed += 1
                    print(f"  [{i+1}/{len(tasks)}] {task['task_key']}: done")

                except Exception as e:
                    self.handle_failure(task, e)
                    failed += 1
                    print(f"  [{i+1}/{len(tasks)}] {task['task_key']}: error - {e}")

                    # Exponential back-off after failure
                    if self.use_backoff and self.consecutive_failures < self.max_consecutive_failures:
                        delay = self.calculate_backoff_delay(self.consecutive_failures)
                        print(f"    Backing off for {delay:.1f}s...")
                        time.sleep(delay)
        finally:
            self.teardown()

        print(f"\nCompleted: {completed}, Failed: {failed}")

    def calculate_backoff_delay(self, failure_count: int) -> float:
        """Calculate exponential back-off delay."""
        delay = self.backoff_base_seconds * (2 ** (failure_count - 1))
        return min(delay, self.backoff_max_seconds)

    def get_pending_tasks(self, limit: int) -> list[dict]:
        """Get pending tasks for this worker type."""
        result = supabase.table("ph_tasks").select("*").eq(
            "task_type", self.task_type
        ).eq("status", "pending").order("created_at").limit(limit).execute()
        return result.data or []

    def mark_processing(self, task_id: int):
        """Mark task as processing."""
        supabase.table("ph_tasks").update({
            "status": "processing",
            "started_at": datetime.now().isoformat()
        }).eq("id", task_id).execute()

    def mark_completed(self, task_id: int):
        """Mark task as completed."""
        supabase.table("ph_tasks").update({
            "status": "completed",
            "completed_at": datetime.now().isoformat()
        }).eq("id", task_id).execute()

    def handle_failure(self, task: dict, error: Exception):
        """Handle task failure with retry logic."""
        attempts = task['attempts'] + 1

        if attempts >= self.max_attempts:
            status = 'failed'
        else:
            status = 'pending'  # Re-queue for retry

        supabase.table("ph_tasks").update({
            "status": status,
            "attempts": attempts,
            "error": str(error)[:500],  # Truncate long errors
            "started_at": None
        }).eq("id", task['id']).execute()

        self.consecutive_failures += 1

    def create_task(self, task_type: str, task_key: str, task_params: dict):
        """Create a downstream task only if it doesn't exist."""
        supabase.table("ph_tasks").upsert({
            "task_type": task_type,
            "task_key": task_key,
            "task_params": task_params,
            "status": "pending"
        }, on_conflict="task_type,task_key", ignore_duplicates=True).execute()

    def cleanup_stale_tasks(self):
        """Reset stale processing tasks back to pending."""
        try:
            result = supabase.rpc("cleanup_stale_tasks", {
                "p_task_type": self.task_type,
                "p_timeout_minutes": self.processing_timeout_minutes
            }).execute()
            if result.data and result.data > 0:
                print(f"Reset {result.data} stale {self.task_type} tasks")
        except Exception as e:
            print(f"Warning: cleanup_stale_tasks failed: {e}")

    @classmethod
    def get_stats(cls) -> dict:
        """Get task statistics for this worker type."""
        result = supabase.table("ph_tasks").select(
            "status", count="exact"
        ).eq("task_type", cls.task_type).execute()

        # This doesn't work well with supabase-py, let's do it differently
        pending = supabase.table("ph_tasks").select("id", count="exact").eq(
            "task_type", cls.task_type
        ).eq("status", "pending").execute()

        processing = supabase.table("ph_tasks").select("id", count="exact").eq(
            "task_type", cls.task_type
        ).eq("status", "processing").execute()

        completed = supabase.table("ph_tasks").select("id", count="exact").eq(
            "task_type", cls.task_type
        ).eq("status", "completed").execute()

        failed = supabase.table("ph_tasks").select("id", count="exact").eq(
            "task_type", cls.task_type
        ).eq("status", "failed").execute()

        return {
            "pending": pending.count or 0,
            "processing": processing.count or 0,
            "completed": completed.count or 0,
            "failed": failed.count or 0,
        }
