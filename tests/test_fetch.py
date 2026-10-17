from conftest import NOW, FakeReddit, FakeSubmission

from reddit_reader import db
from reddit_reader.fetch import (
    CHUNK_SIZE,
    SELFTEXT_MAX,
    chunked,
    fetch_all,
    group_key,
    subscriptions,
    to_item,
)

DAY = 86400


def posts_every_minute(count: int, sub: str = "python", start: int = NOW) -> list[FakeSubmission]:
    return [FakeSubmission(created_utc=start - 60 * i, subreddit=sub) for i in range(count)]


def fullnames(conn) -> set[str]:
    return {r["fullname"] for r in conn.execute("SELECT fullname FROM items")}


def test_subscriptions_exclude_user_profiles_and_sort():
    reddit = FakeReddit(["zeta", "u_someone", "Alpha", "U_Other", "beta"])
    assert subscriptions(reddit) == ["Alpha", "beta", "zeta"]


def test_chunking_at_50():
    names = [f"s{i}" for i in range(120)]
    chunks = chunked(names)
    assert [len(c) for c in chunks] == [CHUNK_SIZE, CHUNK_SIZE, 20]
    assert sum(chunks, []) == names


def test_each_chunk_queried_as_multireddit(conn):
    names = [f"s{i:03d}" for i in range(60)]
    reddit = FakeReddit(names)
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW)
    assert stats.chunks == 2
    assert reddit.listing_calls == ["+".join(names[:50]), "+".join(names[50:])]


def test_first_fetch_inserts_items_within_max_age(conn):
    posts = [
        FakeSubmission(created_utc=NOW - 1 * DAY),
        FakeSubmission(created_utc=NOW - 6 * DAY),
        FakeSubmission(created_utc=NOW - 8 * DAY),  # older than max age
    ]
    reddit = FakeReddit(["python"], posts)
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW)
    assert stats.new_items == 2
    assert fullnames(conn) == {posts[0].fullname, posts[1].fullname}


def test_refetch_dedupes(conn):
    reddit = FakeReddit(["python"], posts_every_minute(10))
    assert fetch_all(conn, reddit, max_age_days=7, now=NOW).new_items == 10
    assert fetch_all(conn, reddit, max_age_days=7, now=NOW).new_items == 0
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 10


def test_watermark_stops_iteration(conn):
    reddit = FakeReddit(["python"], posts_every_minute(100))
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    assert db.get_watermark(conn, "python") == NOW

    # Three newer posts arrive. Second fetch stops at the watermark: it scans
    # the 3 new ones plus the one sitting exactly on the watermark.
    newer = [FakeSubmission(created_utc=NOW + 60 * i) for i in (1, 2, 3)]
    reddit.posts += newer
    reddit.yielded = 0
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW + 200)
    assert stats.new_items == 3
    assert reddit.yielded <= 5
    assert db.get_watermark(conn, "python") == NOW + 180


def test_stop_after_5_consecutive_known(conn):
    old = posts_every_minute(50)
    reddit = FakeReddit(["python"], old)
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    # Lose the watermark (e.g. subscription change re-keyed the chunk) so only
    # the known-items rule can stop the scan.
    conn.execute("DELETE FROM watermarks")
    reddit.posts.append(FakeSubmission(created_utc=NOW + 60))
    reddit.yielded = 0
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW + 100)
    assert stats.new_items == 1
    assert reddit.yielded == 1 + 5


def test_known_counter_resets_after_new_item(conn):
    # Known items interleaved with gaps (e.g. a previously stored post that
    # has since been deleted does not break the stop rule; a genuinely new
    # post in between resets the counter).
    posts = posts_every_minute(20)
    reddit = FakeReddit(["python"], posts)
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    conn.execute("DELETE FROM watermarks")
    # Remove one stored post from the DB so the listing has: 4 known, 1 "new", 5 known
    conn.execute("DELETE FROM items WHERE fullname = ?", (posts[4].fullname,))
    reddit.yielded = 0
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW)
    assert stats.new_items == 1
    assert reddit.yielded == 4 + 1 + 5


def test_deleted_post_at_previous_stop_point_is_tolerated(conn):
    posts = posts_every_minute(20)
    reddit = FakeReddit(["python"], posts)
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    conn.execute("DELETE FROM watermarks")
    # The newest stored post disappears from Reddit; new ones arrive.
    reddit.posts.remove(posts[0])
    reddit.posts += [FakeSubmission(created_utc=NOW + 60 * i) for i in (1, 2)]
    reddit.yielded = 0
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW + 200)
    assert stats.new_items == 2
    assert reddit.yielded == 2 + 5


def test_max_age_cap_applies_with_old_watermark(conn):
    db.set_watermark(conn, "python", NOW - 30 * DAY)
    posts = [FakeSubmission(created_utc=NOW - d * DAY) for d in (1, 5, 10, 20)]
    reddit = FakeReddit(["python"], posts)
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW)
    assert stats.new_items == 2


def test_listing_end_stops(conn):
    reddit = FakeReddit(["python"], posts_every_minute(3))
    stats = fetch_all(conn, reddit, max_age_days=7, now=NOW)
    assert stats.new_items == 3


def test_seen_state_survives_refetch(conn):
    posts = posts_every_minute(5)
    reddit = FakeReddit(["python"], posts)
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    db.mark_seen(conn, [posts[1].fullname, posts[3].fullname])
    posts[1].score = 9999  # changed upstream; must not reset anything
    conn.execute("DELETE FROM watermarks")
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    seen = {r["fullname"] for r in conn.execute("SELECT fullname FROM items WHERE seen = 1")}
    assert seen == {posts[1].fullname, posts[3].fullname}


def test_watermarks_keyed_per_chunk_and_pruned(conn):
    reddit = FakeReddit(["b", "a"], [FakeSubmission(created_utc=NOW, subreddit="a")])
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    assert db.get_watermark(conn, group_key(["a", "b"])) == NOW
    reddit.subscribed = ["a", "b", "c"]
    fetch_all(conn, reddit, max_age_days=7, now=NOW)
    keys = [r["group_key"] for r in conn.execute("SELECT group_key FROM watermarks")]
    assert keys == ["a+b+c"]


def test_watermark_never_moves_backwards(conn):
    db.set_watermark(conn, "k", 100)
    db.set_watermark(conn, "k", 50)
    assert db.get_watermark(conn, "k") == 100


def test_to_item_mapping_and_truncation():
    s = FakeSubmission(
        created_utc=NOW + 0.7,
        subreddit="Python",
        selftext="x" * (SELFTEXT_MAX + 500),
        author=None,
        over_18=True,
    )
    item = to_item(s, fetched_at=NOW)
    assert item["fullname"] == s.fullname
    assert item["created_utc"] == NOW
    assert len(item["selftext"]) == SELFTEXT_MAX
    assert item["author"] is None
    assert item["over_18"] == 1
    assert item["permalink"].startswith("https://www.reddit.com/r/Python/comments/")


def test_to_item_empty_selftext_stored_as_null():
    item = to_item(FakeSubmission(created_utc=NOW, selftext=""), fetched_at=NOW)
    assert item["selftext"] is None
