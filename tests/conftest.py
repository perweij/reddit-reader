"""Shared fakes. No test touches the network."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import pytest

from reddit_reader import db

NOW = 1_700_000_000
_ids = itertools.count(1)


@dataclass
class FakeSubmission:
    created_utc: float
    subreddit: str = "python"
    title: str = "A post"
    author: str | None = "someone"
    score: int = 10
    num_comments: int = 2
    selftext: str = ""
    is_self: bool = True
    over_18: bool = False
    id: str = field(default_factory=lambda: f"id{next(_ids)}")
    url: str | None = None

    @property
    def fullname(self) -> str:
        return f"t3_{self.id}"

    @property
    def permalink(self) -> str:
        return f"/r/{self.subreddit}/comments/{self.id}/a_post/"

    def __post_init__(self) -> None:
        if self.url is None:
            self.url = "https://www.reddit.com" + self.permalink


@dataclass
class FakeSubreddit:
    display_name: str


class FakeListingSource:
    def __init__(self, reddit: "FakeReddit", name: str) -> None:
        self.reddit = reddit
        self.name = name

    def new(self, limit=None):
        self.reddit.listing_calls.append(self.name)
        members = {n.lower() for n in self.name.split("+")}
        posts = [p for p in self.reddit.posts if p.subreddit.lower() in members]
        posts.sort(key=lambda p: p.created_utc, reverse=True)
        for p in posts:
            self.reddit.yielded += 1
            yield p


class FakeUser:
    def __init__(self, reddit: "FakeReddit") -> None:
        self.reddit = reddit

    def subreddits(self, limit=None):
        return [FakeSubreddit(n) for n in self.reddit.subscribed]


class FakeReddit:
    """Mimics the tiny read-only slice of praw.Reddit that reddit-reader uses."""

    def __init__(self, subscribed: list[str], posts: list[FakeSubmission] | None = None) -> None:
        self.subscribed = subscribed
        self.posts = list(posts or [])
        self.listing_calls: list[str] = []
        self.yielded = 0
        self.user = FakeUser(self)

    def subreddit(self, name: str) -> FakeListingSource:
        return FakeListingSource(self, name)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def make_item(n: int, **overrides) -> dict:
    item = {
        "fullname": f"t3_item{n}",
        "subreddit": "python",
        "title": f"Item {n}",
        "author": "someone",
        "created_utc": NOW - 1000 + n,
        "score": 1,
        "num_comments": 0,
        "permalink": f"https://www.reddit.com/r/python/comments/item{n}/",
        "url": f"https://www.reddit.com/r/python/comments/item{n}/",
        "selftext": None,
        "is_self": 1,
        "over_18": 0,
        "fetched_at": NOW,
    }
    item.update(overrides)
    return item
