from conftest import NOW, make_item

from reddit_reader import db


def test_insert_or_ignore_keeps_existing_row(conn):
    assert db.insert_item(conn, make_item(1))
    db.mark_seen(conn, ["t3_item1"])
    assert not db.insert_item(conn, make_item(1, title="changed"))
    row = conn.execute("SELECT title, seen FROM items").fetchone()
    assert (row["title"], row["seen"]) == ("Item 1", 1)


def test_unseen_order_and_nsfw_filter(conn):
    db.insert_item(conn, make_item(3))
    db.insert_item(conn, make_item(1))
    db.insert_item(conn, make_item(2, over_18=1))
    oldest_first = [r["fullname"] for r in db.unseen_items(conn)]
    assert oldest_first == ["t3_item1", "t3_item2", "t3_item3"]
    newest_first = [r["fullname"] for r in db.unseen_items(conn, newest_first=True)]
    assert newest_first == ["t3_item3", "t3_item2", "t3_item1"]
    sfw = [r["fullname"] for r in db.unseen_items(conn, exclude_nsfw=True)]
    assert sfw == ["t3_item1", "t3_item3"]
    assert db.unseen_count(conn) == 3
    assert db.unseen_count(conn, exclude_nsfw=True) == 2


def test_mark_subreddit_and_all_seen(conn):
    db.insert_item(conn, make_item(1, subreddit="Python"))
    db.insert_item(conn, make_item(2, subreddit="rust"))
    db.insert_item(conn, make_item(3, subreddit="python"))
    assert db.mark_subreddit_seen(conn, "python") == 2
    assert db.unseen_counts(conn) == [("rust", 1)]
    assert db.mark_all_seen(conn) == 1
    assert db.unseen_counts(conn) == []


def test_connect_creates_parent_directory(tmp_path):
    path = tmp_path / "a" / "b" / "state.db"
    conn = db.connect(path)
    db.insert_item(conn, make_item(1))
    conn.commit()
    conn.close()
    assert db.unseen_count(db.connect(path)) == 1


def test_index_exists(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "items_seen_created" in names


def test_prune_watermarks(conn):
    db.set_watermark(conn, "a", NOW)
    db.set_watermark(conn, "b", NOW)
    db.prune_watermarks(conn, ["b"])
    assert db.get_watermark(conn, "a") is None
    assert db.get_watermark(conn, "b") == NOW
    db.prune_watermarks(conn, [])
    assert db.get_watermark(conn, "b") is None
