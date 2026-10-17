from conftest import NOW, make_item

from reddit_reader.render import format_item, relative_age, truncate


def test_relative_age():
    assert relative_age(NOW, NOW + 5) == "just now"
    assert relative_age(NOW, NOW + 120) == "2m ago"
    assert relative_age(NOW, NOW + 3 * 3600) == "3h ago"
    assert relative_age(NOW, NOW + 2 * 86400 + 10) == "2d ago"
    assert relative_age(NOW + 100, NOW) == "just now"


def test_truncate():
    assert truncate(None) == ""
    assert truncate("  short  ") == "short"
    assert truncate("abcdef", 3) == "abc…"


def test_format_self_post():
    text = format_item(make_item(1, selftext="Hello body", score=1, num_comments=3), now=NOW)
    assert "r/python  Item 1" in text
    assert "u/someone" in text and "1 point" in text and "3 comments" in text
    assert "Hello body" in text
    assert "Link:" not in text
    assert "Post: https://www.reddit.com/r/python/comments/item1/" in text


def test_format_link_post_deleted_author_nsfw():
    item = make_item(1, is_self=0, url="https://example.com/x", author=None, over_18=1)
    text = format_item(item, now=NOW)
    assert "Link: https://example.com/x" in text
    assert "[deleted]" in text
    assert "NSFW" in text
