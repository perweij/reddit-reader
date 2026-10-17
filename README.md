# reddit-reader

**A personal, single-user, read-only Reddit reader.** It shows posts from the
subreddits my own Reddit account is subscribed to, in strict chronological
order, shows each item exactly once, and stops with "All caught up." when
there is nothing new. No algorithmic feed, no infinite scroll.

It is a private tool for one person (the repository owner), running locally
on their own machine with their own account. It is not a service, has no
other users and is not deployed anywhere.

## Constraints

These are deliberate design rules and part of the Reddit API access request
for this app:

- **Read-only.** It never posts, comments, votes, messages, or modifies
  subscriptions. It only lists the account's subscribed subreddits and reads
  their "new" listings.
- **Single user.** Only the owner's own account, authenticated as a Reddit
  "script" app.
- **Non-commercial.** No sharing, publishing, or redistribution of Reddit
  data.
- **Minimal storage.** Only what is needed to render the feed and remember
  what has been seen is stored, in a local SQLite file. No user profiling, no
  inference about users, no AI/ML use of the data.
- **Gentle on the API.** Every HTTP request is spaced at least 2 seconds
  apart (at most 30 requests/minute, well under Reddit's limit of 100), on
  top of PRAW's built-in rate limiting.
- **Descriptive User-Agent:** `reddit-reader/0.1 by u/<REDDIT_USERNAME>`.
- **No secrets in the repository.** Credentials come from environment
  variables only.

## How it works

1. **Fetch:** reads the list of subscribed subreddits (user profile subs
   `u_*` are skipped), groups them into chunks of about 50, and reads each
   chunk's newest posts as a multireddit (`r/a+b+c/new`). It stops reading a
   chunk as soon as it reaches posts it has already stored, posts older than
   the previous fetch, or posts older than `REDDIT_READER_MAX_AGE_DAYS`.
2. **Read:** shows unseen posts one at a time, oldest first, like a
   timeline. A post is marked seen only when you move past it. When nothing
   is left it prints `All caught up.` and exits.

Stored per post: fullname, subreddit, title, author name, creation time,
score, comment count, permalink, link URL, self text (truncated to 2000
characters), self/NSFW flags, seen flag and fetch time.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) (or plain `pip`).

1. Create a Reddit app at <https://www.reddit.com/prefs/apps>: choose
   **script**, any name, redirect URI `http://localhost:8080` (unused). Note
   the client ID (under the app name) and the secret.
2. Set environment variables (e.g. in a file outside the repository that you
   `source`):

   | Variable | Meaning |
   |---|---|
   | `REDDIT_CLIENT_ID` | script app client ID |
   | `REDDIT_CLIENT_SECRET` | script app secret |
   | `REDDIT_USERNAME` | your Reddit username |
   | `REDDIT_PASSWORD` | your Reddit password (see 2FA note) |
   | `REDDIT_READER_DB` | optional, default `~/.local/share/reddit-reader/state.db` |
   | `REDDIT_READER_MAX_AGE_DAYS` | optional, default `7`: how far back the first fetch goes |

   With two-factor authentication enabled, set `REDDIT_PASSWORD` to
   `yourpassword:123456`, where `123456` is a current one-time code. The code
   is only checked when a token is obtained at the start of a run (tokens
   last about an hour), so update it before each run.
3. Install:

   ```sh
   uv sync            # or: pip install .
   ```

## Usage

```sh
uv run reddit-reader fetch     # pull new items into the local database
uv run reddit-reader read      # read unseen items interactively
uv run reddit-reader status    # unseen count per subreddit
uv run reddit-reader run       # fetch, then read
uv run reddit-reader serve     # local web UI on 127.0.0.1 (see below)
```

Keys in `read`:

| Key | Action |
|---|---|
| `n`, space, Enter | mark seen, next item |
| `o` | open the post in your browser (stays on the item) |
| `s` | mark all unseen items from this subreddit as seen |
| `a` | mark all unseen items as seen (asks for confirmation) |
| `q` | quit; the current item stays unseen |

Options for `read` and `run`: `--newest-first` (default is oldest first) and
`--exclude-nsfw` (NSFW posts are shown by default). `--db PATH` overrides
`REDDIT_READER_DB`.

### Local web UI

```sh
uv run reddit-reader serve     # then open http://127.0.0.1:8765/
```

Shows a page of up to 20 unseen items (`--batch N`) with a **Next** button
that marks exactly those items as seen, and an "All caught up." page when
nothing is left. It reads only the local database (run `fetch` separately)
and makes no Reddit API calls. It always binds to `127.0.0.1` (port via
`--port`), has no authentication, loads no external assets or scripts, and
rejects requests with a foreign `Host` or `Origin` header. `--newest-first`
and `--exclude-nsfw` work as in `read`.

### Troubleshooting

- **HTTP 403 / "Access forbidden":** API access for the app has not been
  approved (yet), or the app is not a script app owned by this account.
- **"invalid_grant":** wrong username/password, or with 2FA the password is
  not in `password:123456` form or the code has expired.

## Development

```sh
uv sync
uv run pytest
```

Tests use a fake PRAW listing and never touch the network.

## License

Apache License 2.0, see [LICENSE](LICENSE).
