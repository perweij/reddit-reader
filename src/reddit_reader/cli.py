"""Command-line entry point."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from typing import Any, Callable

from . import config, db
from .config import ConfigError
from .reader import CAUGHT_UP, run_reader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reddit-reader",
        description="Personal, read-only, chronological reader for your subscribed subreddits.",
    )
    parser.add_argument(
        "--db", help="SQLite state file (default: $REDDIT_READER_DB or " + config.DEFAULT_DB + ")"
    )

    view = argparse.ArgumentParser(add_help=False)
    view.add_argument("--newest-first", action="store_true", help="show newest unseen items first")
    view.add_argument("--exclude-nsfw", action="store_true", help="hide NSFW (over_18) items")

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    sub.add_parser("fetch", help="pull new items into the database")
    sub.add_parser("read", parents=[view], help="read unseen items interactively")
    status = sub.add_parser("status", help="unseen count per subreddit")
    status.add_argument("--exclude-nsfw", action="store_true", help="ignore NSFW items")
    sub.add_parser("run", parents=[view], help="fetch, then read")
    return parser


def default_reddit_factory() -> Any:
    from .client import make_reddit

    return make_reddit(config.credentials())


def cmd_fetch(conn: sqlite3.Connection, reddit_factory: Callable[[], Any]) -> int:
    from .client import describe_error
    from .fetch import fetch_all

    try:
        reddit = reddit_factory()
        stats = fetch_all(
            conn,
            reddit,
            max_age_days=config.max_age_days(),
            progress=lambda msg: print(msg, flush=True),
        )
    except ConfigError as exc:
        print(f"reddit-reader: configuration error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        message = describe_error(exc)
        if message is None:
            raise
        print(f"reddit-reader: {message}", file=sys.stderr)
        return 1
    print(f"Fetched {stats.new_items} new item(s).")
    return 0


def cmd_status(conn: sqlite3.Connection, exclude_nsfw: bool) -> int:
    counts = db.unseen_counts(conn, exclude_nsfw=exclude_nsfw)
    if not counts:
        print(CAUGHT_UP)
        return 0
    width = max(len(name) for name, _ in counts) + 2
    for name, n in counts:
        print(f"r/{name:<{width}}{n:>6}")
    print(f"{'total':<{width + 2}}{sum(n for _, n in counts):>6}")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    reddit_factory: Callable[[], Any] = default_reddit_factory,
    reader: Callable[..., int] = run_reader,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        path = args.db or config.db_path()
        conn = db.connect(path)
    except (ConfigError, OSError, sqlite3.Error) as exc:
        print(f"reddit-reader: cannot open database: {exc}", file=sys.stderr)
        return 2

    try:
        if args.command == "fetch":
            return cmd_fetch(conn, reddit_factory)
        if args.command == "status":
            return cmd_status(conn, args.exclude_nsfw)
        if args.command == "run":
            rc = cmd_fetch(conn, reddit_factory)
            if rc != 0:
                return rc
        return reader(conn, newest_first=args.newest_first, exclude_nsfw=args.exclude_nsfw)
    except KeyboardInterrupt:
        return 130
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
