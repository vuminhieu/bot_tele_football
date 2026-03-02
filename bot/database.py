"""SQLite database layer for vote tracking.

All functions are async using aiosqlite. Database auto-creates on first init.
"""

import logging

import aiosqlite

from bot.config import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS members (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT NOT NULL,
    registered_at TEXT DEFAULT (datetime('now','localtime')),
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id TEXT UNIQUE NOT NULL,
    message_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    week_label TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    closed_at TEXT,
    is_closed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    option_id INTEGER NOT NULL,
    voted_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (poll_id) REFERENCES polls(poll_id),
    FOREIGN KEY (user_id) REFERENCES members(user_id),
    UNIQUE(poll_id, user_id)
);
"""


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create database tables if they don't exist. Enable WAL mode."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(_SCHEMA_SQL)
        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


async def register_member(
    user_id: int, username: str | None, full_name: str
) -> None:
    """Register or update a member. Idempotent — upserts on conflict."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO members (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                is_active = 1
            """,
            (user_id, username, full_name),
        )
        await db.commit()


async def get_active_members() -> list[dict]:
    """Return all active members."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT user_id, username, full_name FROM members WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def deactivate_member(user_id: int) -> None:
    """Mark a member as inactive (left or kicked from group)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE members SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()

# ---------------------------------------------------------------------------
# Polls
# ---------------------------------------------------------------------------


async def save_poll(
    poll_id: str, message_id: int, chat_id: int, week_label: str
) -> None:
    """Save a new poll record."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO polls (poll_id, message_id, chat_id, week_label)
            VALUES (?, ?, ?, ?)
            """,
            (poll_id, message_id, chat_id, week_label),
        )
        await db.commit()


async def get_current_poll() -> dict | None:
    """Get the latest open (not closed) poll, or None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT poll_id, message_id, chat_id, week_label
            FROM polls
            WHERE is_closed = 0
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def close_poll(poll_id: str) -> None:
    """Mark a poll as closed with timestamp."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE polls SET is_closed = 1, closed_at = datetime('now','localtime')
            WHERE poll_id = ?
            """,
            (poll_id,),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Votes
# ---------------------------------------------------------------------------


async def save_vote(poll_id: str, user_id: int, option_id: int) -> None:
    """Save or update a vote. Uses UPSERT for idempotency."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO votes (poll_id, user_id, option_id)
            VALUES (?, ?, ?)
            ON CONFLICT(poll_id, user_id) DO UPDATE SET
                option_id = excluded.option_id,
                voted_at = datetime('now','localtime')
            """,
            (poll_id, user_id, option_id),
        )
        await db.commit()


async def delete_vote(poll_id: str, user_id: int) -> None:
    """Remove a vote (when user retracts their answer)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM votes WHERE poll_id = ? AND user_id = ?",
            (poll_id, user_id),
        )
        await db.commit()




async def get_voters_by_option(poll_id: str, option_id: int) -> list[dict]:
    """Get voters who chose a specific option."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT v.user_id, m.full_name
            FROM votes v
            JOIN members m ON v.user_id = m.user_id
            WHERE v.poll_id = ? AND v.option_id = ?
            """,
            (poll_id, option_id),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_non_voters(poll_id: str) -> list[dict]:
    """Get active members who haven't voted in a specific poll."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT m.user_id, m.full_name
            FROM members m
            WHERE m.is_active = 1
              AND m.user_id NOT IN (
                  SELECT v.user_id FROM votes v WHERE v.poll_id = ?
              )
            """,
            (poll_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Consecutive inactive tracking
# ---------------------------------------------------------------------------


async def get_consecutive_inactive(n: int = 3) -> list[dict]:
    """Get members who voted 'Không đá' (option_id=1) in the last n closed polls.

    Only counts members who ACTIVELY voted skip — not voting doesn't count.
    Returns list of dicts with user_id, full_name, and vote history.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Get last n closed polls
        cursor = await db.execute(
            """
            SELECT poll_id, week_label
            FROM polls
            WHERE is_closed = 1
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (n,),
        )
        last_polls = await cursor.fetchall()

        if len(last_polls) < n:
            return []  # Not enough history

        poll_ids = [p["poll_id"] for p in last_polls]
        placeholders = ",".join("?" * n)

        # Find members who voted "Không đá" (option_id=1) in ALL last n polls
        cursor = await db.execute(
            f"""
            SELECT m.user_id, m.full_name
            FROM members m
            WHERE m.is_active = 1
              AND (
                  SELECT COUNT(*)
                  FROM votes v
                  WHERE v.user_id = m.user_id
                    AND v.poll_id IN ({placeholders})
                    AND v.option_id = 1
              ) = ?
            """,
            [*poll_ids, n],
        )
        inactive = await cursor.fetchall()

        # Build detailed vote history for each inactive member
        result = []
        for member in inactive:
            history = []
            for poll in reversed(last_polls):  # Oldest first
                vote_cursor = await db.execute(
                    "SELECT option_id FROM votes WHERE poll_id = ? AND user_id = ?",
                    (poll["poll_id"], member["user_id"]),
                )
                vote = await vote_cursor.fetchone()
                if vote is None:
                    history.append((poll["week_label"], "-"))
                elif vote["option_id"] == 1:
                    history.append((poll["week_label"], "no"))
                else:
                    history.append((poll["week_label"], "yes"))
            result.append(
                {
                    "user_id": member["user_id"],
                    "full_name": member["full_name"],
                    "history": history,
                }
            )

        return result
