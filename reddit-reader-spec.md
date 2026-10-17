# reddit-reader: spec

A personal, single-user, read-only Reddit reader. It shows posts from the
subreddits my own account is subscribed to, in strict chronological order,
shows each item exactly once, and stops with "all caught up" when there is
nothing new. No algorithmic feed, no infinite scroll.

## Constraints (must hold; these are part of Reddit API approval)

- Read-only. Never post, comment, vote, message, or modify subscriptions.
- Single user: only my own account, authenticated as a Reddit "script" app.
- Non-commercial. No sharing, publishing, or redistribution of Reddit data.
- Do not store anything beyond what is needed to render the feed and track
  seen state. No user profiling, no inference about users, no AI/ML use of
  the data.
- Stay well under the limit of 100 queries/minute (target: <= 30/min).
- Descriptive User-Agent: `reddit-reader/0.1 by u/<REDDIT_USERNAME>`.
- Secrets (client id/secret/username/password) come from environment
  variables or a config file outside the repo. Never commit them.

## Stack

- Python 3.11+, `praw`, stdlib `sqlite3`.
- Dependency management with `uv` or plain `requirements.txt`.
- Phase 1: CLI. Phase 2: tiny local web UI bound to 127.0.0.1 only.

## Configuration (env vars)

- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- `REDDIT_USERNAME`, `REDDIT_PASSWORD`
- `REDDIT_READER_DB` (default `~/.local/share/reddit-reader/state.db`)
- `REDDIT_READER_MAX_AGE_DAYS` (default 7; first-run backfill cap)

## Data model (SQLite)

```
items(
  fullname      TEXT PRIMARY KEY,   -- e.g. t3_abc123
  subreddit     TEXT NOT NULL,
  title         TEXT NOT NULL,
  author        TEXT,
  created_utc   INTEGER NOT NULL,
  score         INTEGER,
  num_comments  INTEGER,
  permalink     TEXT NOT NULL,
  url           TEXT,
  selftext      TEXT,               -- truncated to ~2000 chars
  is_self       INTEGER,
  over_18       INTEGER,
  seen          INTEGER NOT NULL DEFAULT 0,
  fetched_at    INTEGER NOT NULL
)
INDEX items(seen, created_utc)

watermarks(
  group_key     TEXT PRIMARY KEY,   -- identifies a subreddit chunk
  newest_utc    INTEGER NOT NULL
)
```

## Fetch stage

1. Get subscriptions: `reddit.user.subreddits(limit=None)`. Exclude user
   profile subs (`u_*`). Refresh the list on every run.
2. Chunk into groups of ~50 names; each chunk is queried as a multireddit:
   `reddit.subreddit("a+b+c").new(limit=None)`. Listings are newest-first.
3. For each chunk, iterate and insert items until one of:
   - 5 consecutive items already exist in `items` (tolerates a deleted or
     removed post that was the previous stop point), or
   - `created_utc` is older than `max(watermark, now - MAX_AGE_DAYS)`, or
   - the listing ends (Reddit caps listings at ~1000 items).
4. Update the chunk watermark to the newest `created_utc` seen.
5. Insert with `INSERT OR IGNORE`. Never reset `seen` on existing rows.
6. Use PRAW's built-in rate limiting. Catch and report auth or HTTP errors
   clearly (403 or invalid_grant usually means API access was not approved or
   the 2FA password format is wrong).

## View stage

- Query: `SELECT ... FROM items WHERE seen = 0 ORDER BY created_utc ASC`
  (oldest unseen first, so the backlog reads like a timeline; make it a flag
  `--newest-first`).
- Each item shows: subreddit, title, author, relative age, score, comment
  count, truncated selftext, link URL, permalink.
- An item is marked seen when the user advances past it (not when fetched).
- When no unseen items remain, print `All caught up.` and exit with code 0.
- Include NSFW (`over_18`) by default; flag `--exclude-nsfw` to hide.

### CLI (phase 1)

```
reddit-reader fetch            # pull new items into the DB
reddit-reader read             # interactive: n/space=next, o=open permalink
                               #   in browser, s=skip all from this sub today,
                               #   a=mark all seen, q=quit (item stays unseen)
reddit-reader status           # unseen count per subreddit
reddit-reader run              # fetch, then read
```

### Local web UI (phase 2)

- One page, one item (or a small batch of ~20) at a time, "Next" button,
  and a final "All caught up" screen. Bind to 127.0.0.1 only. No auth.
- No external CDN assets, no third-party trackers.

## Out of scope (v1)

- Comments, images or video embedding, search, voting, posting, multiple
  accounts, any hosted or multi-user deployment.

## Tests

- Unit tests with a fake PRAW listing: dedupe, stop-after-5-known,
  watermark and max-age cutoffs, seen state surviving re-fetch.
- No network calls in tests.

## Repo deliverables

- `README.md`: purpose, the constraints above, setup (creating a script app,
  env vars), usage. This repo URL is linked from the Reddit API access
  request, so keep the README accurate and the purpose statement prominent.
- `LICENSE` (ApacheV2), `.gitignore` (db files, `.env`).
- Public repo, no secrets in history.
