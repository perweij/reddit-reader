"""Fetch stage: pull new posts from subscribed subreddits into the database."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import db

CHUNK_SIZE = 50
KNOWN_STOP = 5
SELFTEXT_MAX = 2000
REDDIT_BASE = "https://www.reddit.com"


@dataclass
class FetchStats:
    subreddits: int = 0
    chunks: int = 0
    new_items: int = 0
    scanned: int = 0
    per_chunk: list[int] = field(default_factory=list)


def subscriptions(reddit: Any) -> list[str]:
    """Display names of subscribed subreddits, excluding user profiles (u_*)."""
    names = {sr.display_name for sr in reddit.user.subreddits(limit=None)}
    return sorted((n for n in names if not n.lower().startswith("u_")), key=str.lower)


def chunked(names: list[str], size: int = CHUNK_SIZE) -> list[list[str]]:
    return [names[i : i + size] for i in range(0, len(names), size)]


def group_key(names: list[str]) -> str:
    return "+".join(n.lower() for n in names)


def to_item(submission: Any, fetched_at: int) -> dict:
    """Map a PRAW Submission to an `items` row, keeping only what is rendered."""
    author = submission.author
    selftext = submission.selftext or ""
    return {
        "fullname": submission.fullname,
        "subreddit": str(submission.subreddit),
        "title": submission.title,
        "author": None if author is None else str(author),
        "created_utc": int(submission.created_utc),
        "score": submission.score,
        "num_comments": submission.num_comments,
        "permalink": REDDIT_BASE + submission.permalink,
        "url": submission.url,
        "selftext": selftext[:SELFTEXT_MAX] or None,
        "is_self": int(bool(submission.is_self)),
        "over_18": int(bool(submission.over_18)),
        "fetched_at": fetched_at,
    }


def fetch_chunk(
    conn: sqlite3.Connection,
    reddit: Any,
    names: list[str],
    *,
    now: int,
    max_age_days: int,
) -> tuple[int, int]:
    """Fetch one multireddit chunk. Returns (new_items, scanned)."""
    key = group_key(names)
    cutoff = now - max_age_days * 86400
    watermark = db.get_watermark(conn, key)
    if watermark is not None:
        cutoff = max(cutoff, watermark)

    new = scanned = consecutive_known = 0
    newest: int | None = None
    for submission in reddit.subreddit("+".join(names)).new(limit=None):
        created = int(submission.created_utc)
        if created < cutoff:
            break
        scanned += 1
        newest = created if newest is None else max(newest, created)
        if db.insert_item(conn, to_item(submission, now)):
            new += 1
            consecutive_known = 0
        else:
            consecutive_known += 1
            if consecutive_known >= KNOWN_STOP:
                break

    if newest is not None:
        db.set_watermark(conn, key, newest)
    conn.commit()
    return new, scanned


def fetch_all(
    conn: sqlite3.Connection,
    reddit: Any,
    *,
    max_age_days: int,
    now: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> FetchStats:
    now = int(time.time()) if now is None else now
    say = progress or (lambda _msg: None)
    names = subscriptions(reddit)
    chunks = chunked(names)
    stats = FetchStats(subreddits=len(names), chunks=len(chunks))
    say(f"{len(names)} subscribed subreddits in {len(chunks)} chunk(s).")
    for i, chunk in enumerate(chunks, 1):
        new, scanned = fetch_chunk(conn, reddit, chunk, now=now, max_age_days=max_age_days)
        stats.new_items += new
        stats.scanned += scanned
        stats.per_chunk.append(new)
        say(f"  chunk {i}/{len(chunks)}: {new} new")
    db.prune_watermarks(conn, (group_key(c) for c in chunks))
    conn.commit()
    return stats
