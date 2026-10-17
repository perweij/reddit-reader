"""SQLite storage for feed items, seen state and fetch watermarks."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    fullname      TEXT PRIMARY KEY,
    subreddit     TEXT NOT NULL,
    title         TEXT NOT NULL,
    author        TEXT,
    created_utc   INTEGER NOT NULL,
    score         INTEGER,
    num_comments  INTEGER,
    permalink     TEXT NOT NULL,
    url           TEXT,
    selftext      TEXT,
    is_self       INTEGER,
    over_18       INTEGER,
    seen          INTEGER NOT NULL DEFAULT 0,
    fetched_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS items_seen_created ON items(seen, created_utc);
CREATE TABLE IF NOT EXISTS watermarks (
    group_key     TEXT PRIMARY KEY,
    newest_utc    INTEGER NOT NULL
);
"""

ITEM_COLUMNS = (
    "fullname",
    "subreddit",
    "title",
    "author",
    "created_utc",
    "score",
    "num_comments",
    "permalink",
    "url",
    "selftext",
    "is_self",
    "over_18",
    "fetched_at",
)


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def item_exists(conn: sqlite3.Connection, fullname: str) -> bool:
    row = conn.execute("SELECT 1 FROM items WHERE fullname = ?", (fullname,)).fetchone()
    return row is not None


def insert_item(conn: sqlite3.Connection, item: dict) -> bool:
    """Insert an item if new. Never touches existing rows (so `seen` survives)."""
    placeholders = ", ".join("?" for _ in ITEM_COLUMNS)
    cur = conn.execute(
        f"INSERT OR IGNORE INTO items ({', '.join(ITEM_COLUMNS)}) VALUES ({placeholders})",
        tuple(item[c] for c in ITEM_COLUMNS),
    )
    return cur.rowcount == 1


def get_watermark(conn: sqlite3.Connection, group_key: str) -> int | None:
    row = conn.execute(
        "SELECT newest_utc FROM watermarks WHERE group_key = ?", (group_key,)
    ).fetchone()
    return None if row is None else row["newest_utc"]


def set_watermark(conn: sqlite3.Connection, group_key: str, newest_utc: int) -> None:
    """Store a watermark; it only ever moves forward."""
    conn.execute(
        "INSERT INTO watermarks (group_key, newest_utc) VALUES (?, ?) "
        "ON CONFLICT(group_key) DO UPDATE SET newest_utc = MAX(newest_utc, excluded.newest_utc)",
        (group_key, newest_utc),
    )


def prune_watermarks(conn: sqlite3.Connection, keep: Iterable[str]) -> None:
    keep = list(keep)
    placeholders = ", ".join("?" for _ in keep)
    if keep:
        conn.execute(f"DELETE FROM watermarks WHERE group_key NOT IN ({placeholders})", keep)
    else:
        conn.execute("DELETE FROM watermarks")


def unseen_items(
    conn: sqlite3.Connection,
    *,
    newest_first: bool = False,
    exclude_nsfw: bool = False,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM items WHERE seen = 0"
    if exclude_nsfw:
        sql += " AND NOT COALESCE(over_18, 0)"
    order = "DESC" if newest_first else "ASC"
    sql += f" ORDER BY created_utc {order}, fullname {order}"
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    return conn.execute(sql, params).fetchall()


def mark_seen(conn: sqlite3.Connection, fullnames: Iterable[str]) -> int:
    fullnames = list(fullnames)
    if not fullnames:
        return 0
    placeholders = ", ".join("?" for _ in fullnames)
    cur = conn.execute(
        f"UPDATE items SET seen = 1 WHERE seen = 0 AND fullname IN ({placeholders})", fullnames
    )
    conn.commit()
    return cur.rowcount


def mark_subreddit_seen(
    conn: sqlite3.Connection, subreddit: str, *, exclude_nsfw: bool = False
) -> int:
    sql = "UPDATE items SET seen = 1 WHERE seen = 0 AND subreddit = ? COLLATE NOCASE"
    if exclude_nsfw:
        sql += " AND NOT COALESCE(over_18, 0)"
    cur = conn.execute(sql, (subreddit,))
    conn.commit()
    return cur.rowcount


def mark_all_seen(conn: sqlite3.Connection, *, exclude_nsfw: bool = False) -> int:
    sql = "UPDATE items SET seen = 1 WHERE seen = 0"
    if exclude_nsfw:
        sql += " AND NOT COALESCE(over_18, 0)"
    cur = conn.execute(sql)
    conn.commit()
    return cur.rowcount


def unseen_counts(conn: sqlite3.Connection, *, exclude_nsfw: bool = False) -> list[tuple[str, int]]:
    sql = "SELECT subreddit, COUNT(*) AS n FROM items WHERE seen = 0"
    if exclude_nsfw:
        sql += " AND NOT COALESCE(over_18, 0)"
    sql += " GROUP BY subreddit ORDER BY n DESC, subreddit COLLATE NOCASE"
    return [(r["subreddit"], r["n"]) for r in conn.execute(sql)]


def unseen_count(conn: sqlite3.Connection, *, exclude_nsfw: bool = False) -> int:
    sql = "SELECT COUNT(*) FROM items WHERE seen = 0"
    if exclude_nsfw:
        sql += " AND NOT COALESCE(over_18, 0)"
    return conn.execute(sql).fetchone()[0]
