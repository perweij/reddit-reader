import io

from conftest import make_item

from reddit_reader import db
from reddit_reader.reader import CAUGHT_UP, run_reader


def keys(*seq):
    it = iter(seq)
    return lambda: next(it, "")  # EOF once exhausted


def seen(conn):
    return {r["fullname"] for r in conn.execute("SELECT fullname FROM items WHERE seen = 1")}


def seed(conn, *items):
    for item in items:
        db.insert_item(conn, item)
    conn.commit()


def test_empty_prints_caught_up(conn):
    out = io.StringIO()
    assert run_reader(conn, getkey=keys(), out=out) == 0
    assert out.getvalue().strip() == CAUGHT_UP


def test_next_marks_seen_in_order_until_caught_up(conn):
    seed(conn, make_item(2), make_item(1))
    out = io.StringIO()
    assert run_reader(conn, getkey=keys("n", " "), out=out) == 0
    text = out.getvalue()
    assert text.index("Item 1") < text.index("Item 2")
    assert text.rstrip().endswith(CAUGHT_UP)
    assert seen(conn) == {"t3_item1", "t3_item2"}


def test_newest_first(conn):
    seed(conn, make_item(1), make_item(2))
    out = io.StringIO()
    run_reader(conn, newest_first=True, getkey=keys("n", "n"), out=out)
    text = out.getvalue()
    assert text.index("Item 2") < text.index("Item 1")


def test_quit_leaves_current_unseen(conn):
    seed(conn, make_item(1), make_item(2))
    run_reader(conn, getkey=keys("n", "q"), out=io.StringIO())
    assert seen(conn) == {"t3_item1"}


def test_eof_quits(conn):
    seed(conn, make_item(1))
    assert run_reader(conn, getkey=keys(), out=io.StringIO()) == 0
    assert seen(conn) == set()


def test_open_stays_on_item(conn):
    seed(conn, make_item(1))
    opened = []
    run_reader(conn, getkey=keys("o", "q"), open_url=opened.append, out=io.StringIO())
    assert opened == ["https://www.reddit.com/r/python/comments/item1/"]
    assert seen(conn) == set()


def test_skip_subreddit(conn):
    seed(
        conn,
        make_item(1, subreddit="python"),
        make_item(2, subreddit="rust"),
        make_item(3, subreddit="python"),
    )
    run_reader(conn, getkey=keys("s", "q"), out=io.StringIO())
    assert seen(conn) == {"t3_item1", "t3_item3"}


def test_mark_all_requires_confirmation(conn):
    seed(conn, make_item(1), make_item(2))
    run_reader(conn, getkey=keys("a", "n", "q"), out=io.StringIO())
    assert seen(conn) == set()
    out = io.StringIO()
    run_reader(conn, getkey=keys("a", "y"), out=out)
    assert seen(conn) == {"t3_item1", "t3_item2"}
    assert out.getvalue().rstrip().endswith(CAUGHT_UP)


def test_exclude_nsfw(conn):
    seed(conn, make_item(1, over_18=1), make_item(2))
    out = io.StringIO()
    run_reader(conn, exclude_nsfw=True, getkey=keys("n"), out=out)
    assert "Item 1" not in out.getvalue()
    assert seen(conn) == {"t3_item2"}


def test_unknown_keys_ignored(conn):
    seed(conn, make_item(1))
    run_reader(conn, getkey=keys("x", "?", "n"), out=io.StringIO())
    assert seen(conn) == {"t3_item1"}
