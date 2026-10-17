"""Interactive terminal reader: one unseen item at a time."""

from __future__ import annotations

import sqlite3
import sys
import webbrowser
from typing import Callable, TextIO

from . import db
from .render import format_item

CAUGHT_UP = "All caught up."
HELP = "[n/space] next  [o] open  [s] skip r/{sub}  [a] mark all seen  [q] quit"
QUIT_KEYS = {"q", "\x03", "\x04", ""}  # q, Ctrl-C, Ctrl-D, EOF


def tty_getkey(stream: TextIO = sys.stdin) -> str:
    """Read one keypress without waiting for Enter (falls back to line input)."""
    if not stream.isatty():
        line = stream.readline()
        if line == "":
            return ""  # EOF
        return line.strip()[:1] or "\n"
    import termios
    import tty

    fd = stream.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return stream.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def run_reader(
    conn: sqlite3.Connection,
    *,
    newest_first: bool = False,
    exclude_nsfw: bool = False,
    getkey: Callable[[], str] = tty_getkey,
    open_url: Callable[[str], object] = webbrowser.open,
    out: TextIO = sys.stdout,
) -> int:
    def say(text: str = "") -> None:
        print(text, file=out, flush=True)

    while True:
        rows = db.unseen_items(conn, newest_first=newest_first, exclude_nsfw=exclude_nsfw, limit=1)
        if not rows:
            say(CAUGHT_UP)
            return 0
        item = rows[0]
        remaining = db.unseen_count(conn, exclude_nsfw=exclude_nsfw)
        say("─" * 72)
        say(format_item(item))
        say(f"\n({remaining} unseen) " + HELP.format(sub=item["subreddit"]))

        while True:
            key = getkey().lower()
            if key in ("n", " ", "\r", "\n"):
                db.mark_seen(conn, [item["fullname"]])
                break
            if key == "o":
                open_url(item["permalink"])
                continue
            if key == "s":
                n = db.mark_subreddit_seen(conn, item["subreddit"], exclude_nsfw=exclude_nsfw)
                say(f"Skipped {n} item(s) from r/{item['subreddit']}.")
                break
            if key == "a":
                say(f"Mark all {remaining} unseen item(s) as seen? [y/N]")
                if getkey().lower() == "y":
                    db.mark_all_seen(conn, exclude_nsfw=exclude_nsfw)
                    break
                say("Cancelled.")
                continue
            if key in QUIT_KEYS:
                return 0
