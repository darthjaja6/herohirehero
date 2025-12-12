"""Local SQLite database for work data (posts, knowledge, queue)."""

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from typing import Any

# Data directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "network_hunt.db"


def get_connection() -> sqlite3.Connection:
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Context manager for database connection."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_local_db():
    """Initialize local SQLite database with all tables."""
    with get_db() as conn:
        # 1. ph_posts - Product Hunt 产品
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ph_posts (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tagline TEXT,
                description TEXT,
                slug TEXT,
                url TEXT,
                website_url TEXT,
                votes_count INTEGER DEFAULT 0,
                comments_count INTEGER DEFAULT 0,
                reviews_rating REAL,
                reviews_count INTEGER DEFAULT 0,
                topics TEXT,
                product_links TEXT,
                media TEXT,
                featured_at TEXT,
                created_at TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_posts_featured ON ph_posts(featured_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_posts_votes ON ph_posts(votes_count DESC)")

        # 2. ph_comments - Product Hunt 评论
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ph_comments (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                body TEXT,
                user_id TEXT,
                user_name TEXT,
                user_username TEXT,
                created_at TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ph_comments_post ON ph_comments(post_id)")

        # 3. person_posts - 人员-产品关联
        conn.execute("""
            CREATE TABLE IF NOT EXISTS person_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                post_id TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, post_id, role)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_person_posts_person ON person_posts(person_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_person_posts_post ON person_posts(post_id)")

        # 3. person_knowledge - 搜索到的原始内容
        conn.execute("""
            CREATE TABLE IF NOT EXISTS person_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT,
                source_query TEXT,
                title TEXT,
                content TEXT,
                content_type TEXT,
                content_date TEXT,
                content_hash TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, content_hash)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_person_knowledge_person ON person_knowledge(person_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_person_knowledge_source ON person_knowledge(source_type)")

        # 4. enrichment_queue - 任务队列
        conn.execute("""
            CREATE TABLE IF NOT EXISTS enrichment_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                last_error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_enrichment_queue_status ON enrichment_queue(status, priority DESC)")

    print(f"Local database initialized: {DB_PATH}")


# ============================================
# ph_posts 操作
# ============================================

def upsert_post(
    id: str,
    name: str,
    tagline: str | None,
    description: str | None,
    slug: str,
    url: str | None,
    website_url: str | None,
    votes_count: int,
    comments_count: int,
    reviews_rating: float | None,
    reviews_count: int,
    topics: list[str],
    product_links: list[dict],
    media: list[dict],
    featured_at: str | None,
    created_at: str,
):
    """Insert or update a post."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO ph_posts (id, name, tagline, description, slug, url, website_url,
                                  votes_count, comments_count, reviews_rating, reviews_count,
                                  topics, product_links, media, featured_at, created_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                tagline = excluded.tagline,
                description = excluded.description,
                url = excluded.url,
                votes_count = excluded.votes_count,
                comments_count = excluded.comments_count,
                reviews_rating = excluded.reviews_rating,
                reviews_count = excluded.reviews_count,
                topics = excluded.topics,
                product_links = excluded.product_links,
                media = excluded.media,
                fetched_at = CURRENT_TIMESTAMP
        """, (id, name, tagline, description, slug, url, website_url,
              votes_count, comments_count, reviews_rating, reviews_count,
              json.dumps(topics), json.dumps(product_links), json.dumps(media),
              featured_at, created_at))


def get_post(post_id: str) -> dict | None:
    """Get a post by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM ph_posts WHERE id = ?", (post_id,)).fetchone()
        if row:
            result = dict(row)
            result["topics"] = json.loads(result["topics"]) if result["topics"] else []
            return result
        return None


def get_posts_count() -> int:
    """Get total posts count."""
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM ph_posts").fetchone()[0]


def get_top_posts(limit: int = 10) -> list[dict]:
    """Get top posts by votes."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM ph_posts ORDER BY votes_count DESC LIMIT ?",
            (limit,)
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["topics"] = json.loads(result["topics"]) if result["topics"] else []
            results.append(result)
        return results


# ============================================
# ph_comments 操作
# ============================================

def upsert_comment(
    id: str,
    post_id: str,
    body: str | None,
    user_id: str | None,
    user_name: str | None,
    user_username: str | None,
    created_at: str | None,
):
    """Insert or update a comment."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO ph_comments (id, post_id, body, user_id, user_name, user_username, created_at, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                body = excluded.body,
                user_name = excluded.user_name,
                user_username = excluded.user_username,
                fetched_at = CURRENT_TIMESTAMP
        """, (id, post_id, body, user_id, user_name, user_username, created_at))


def get_post_comments(post_id: str) -> list[dict]:
    """Get comments for a post."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM ph_comments WHERE post_id = ? ORDER BY created_at ASC",
            (post_id,)
        ).fetchall()
        return [dict(row) for row in rows]


# ============================================
# person_posts 操作
# ============================================

def upsert_person_post(person_id: str, post_id: str, role: str):
    """Link a person to a post."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO person_posts (person_id, post_id, role)
            VALUES (?, ?, ?)
            ON CONFLICT(person_id, post_id, role) DO NOTHING
        """, (person_id, post_id, role))


def get_person_posts(person_id: str) -> list[dict]:
    """Get all posts for a person."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT pp.*, p.name as post_name, p.votes_count
            FROM person_posts pp
            LEFT JOIN ph_posts p ON pp.post_id = p.id
            WHERE pp.person_id = ?
        """, (person_id,)).fetchall()
        return [dict(row) for row in rows]


def get_person_posts_count(person_id: str) -> int:
    """Get posts count for a person."""
    with get_db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM person_posts WHERE person_id = ? AND role = 'maker'",
            (person_id,)
        ).fetchone()[0]


def get_person_total_votes(person_id: str) -> int:
    """Get total votes for a person's posts."""
    with get_db() as conn:
        result = conn.execute("""
            SELECT COALESCE(SUM(p.votes_count), 0)
            FROM person_posts pp
            JOIN ph_posts p ON pp.post_id = p.id
            WHERE pp.person_id = ? AND pp.role = 'maker'
        """, (person_id,)).fetchone()
        return result[0] if result else 0


# ============================================
# person_knowledge 操作
# ============================================

def insert_knowledge(
    person_id: str,
    source_type: str,
    content: str,
    content_hash: str,
    source_url: str | None = None,
    source_query: str | None = None,
    title: str | None = None,
    content_type: str | None = None,
    content_date: str | None = None,
) -> bool:
    """Insert knowledge item, returns True if inserted (not duplicate)."""
    with get_db() as conn:
        try:
            conn.execute("""
                INSERT INTO person_knowledge
                (person_id, source_type, source_url, source_query, title, content, content_type, content_date, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (person_id, source_type, source_url, source_query, title, content, content_type, content_date, content_hash))
            return True
        except sqlite3.IntegrityError:
            return False  # Duplicate


def get_person_knowledge(person_id: str, source_type: str | None = None) -> list[dict]:
    """Get knowledge items for a person."""
    with get_db() as conn:
        if source_type:
            rows = conn.execute(
                "SELECT * FROM person_knowledge WHERE person_id = ? AND source_type = ? ORDER BY fetched_at DESC",
                (person_id, source_type)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM person_knowledge WHERE person_id = ? ORDER BY fetched_at DESC",
                (person_id,)
            ).fetchall()
        return [dict(row) for row in rows]


def get_knowledge_count(person_id: str | None = None) -> int:
    """Get knowledge count."""
    with get_db() as conn:
        if person_id:
            return conn.execute(
                "SELECT COUNT(*) FROM person_knowledge WHERE person_id = ?",
                (person_id,)
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM person_knowledge").fetchone()[0]


# ============================================
# enrichment_queue 操作
# ============================================

def queue_task(person_id: str, task_type: str, priority: int = 0):
    """Add a task to the queue."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO enrichment_queue (person_id, task_type, priority)
            VALUES (?, ?, ?)
        """, (person_id, task_type, priority))


def get_pending_tasks(limit: int = 10) -> list[dict]:
    """Get pending tasks ordered by priority."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM enrichment_queue
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(row) for row in rows]


def update_task_status(task_id: int, status: str, error: str | None = None):
    """Update task status."""
    with get_db() as conn:
        if status == 'processing':
            conn.execute("""
                UPDATE enrichment_queue
                SET status = ?, attempts = attempts + 1
                WHERE id = ?
            """, (status, task_id))
        elif status in ('completed', 'failed'):
            conn.execute("""
                UPDATE enrichment_queue
                SET status = ?, last_error = ?, processed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, error, task_id))
        else:
            conn.execute("""
                UPDATE enrichment_queue
                SET status = ?, last_error = ?
                WHERE id = ?
            """, (status, error, task_id))


def get_task(task_id: int) -> dict | None:
    """Get a task by ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM enrichment_queue WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def get_queue_stats() -> dict:
    """Get queue statistics."""
    with get_db() as conn:
        stats = {}
        for status in ['pending', 'processing', 'completed', 'failed']:
            count = conn.execute(
                "SELECT COUNT(*) FROM enrichment_queue WHERE status = ?",
                (status,)
            ).fetchone()[0]
            stats[status] = count
        return stats


# Initialize on import
init_local_db()
