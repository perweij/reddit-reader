"""Formatting helpers shared by the CLI reader and the web UI."""

from __future__ import annotations

import time
from typing import Mapping

PREVIEW_CHARS = 600


def relative_age(created_utc: int, now: float | None = None) -> str:
    now = time.time() if now is None else now
    seconds = max(0, int(now - created_utc))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "just now"


def truncate(text: str | None, limit: int = PREVIEW_CHARS) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def plural(n: int | None, word: str) -> str:
    n = n or 0
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def meta_line(item: Mapping, now: float | None = None) -> str:
    author = f"u/{item['author']}" if item["author"] else "[deleted]"
    parts = [
        author,
        relative_age(item["created_utc"], now),
        plural(item["score"], "point"),
        plural(item["num_comments"], "comment"),
    ]
    if item["over_18"]:
        parts.append("NSFW")
    return " · ".join(parts)


def link_url(item: Mapping) -> str | None:
    """The external link of a link post, or None for self posts."""
    if item["is_self"] or not item["url"] or item["url"] == item["permalink"]:
        return None
    return item["url"]


def format_item(item: Mapping, now: float | None = None) -> str:
    lines = [f"r/{item['subreddit']}  {item['title']}", meta_line(item, now)]
    preview = truncate(item["selftext"])
    if preview:
        lines += ["", preview, ""]
    link = link_url(item)
    if link:
        lines.append(f"Link: {link}")
    lines.append(f"Post: {item['permalink']}")
    return "\n".join(lines)
