import pathlib
import re
from types import SimpleNamespace

import pytest
from prawcore import exceptions as pexc

from reddit_reader.client import (
    MIN_REQUEST_INTERVAL,
    Throttle,
    ThrottledRequestor,
    describe_error,
    make_reddit,
    user_agent,
)
from reddit_reader.config import Credentials


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def test_throttle_spaces_calls():
    clock = FakeClock()
    throttle = Throttle(2.0, clock=clock, sleep=clock.sleep)
    throttle.wait()
    throttle.wait()
    clock.t += 0.5
    throttle.wait()
    clock.t += 10
    throttle.wait()
    assert clock.sleeps == [2.0, 1.5]


def test_rate_target_at_most_30_per_minute():
    assert 60 / MIN_REQUEST_INTERVAL <= 30


def test_throttled_requestor_waits_before_each_request():
    clock = FakeClock()
    calls = []

    class FakeSession:
        headers = {}

        def request(self, *args, **kwargs):
            calls.append(clock.t)
            return SimpleNamespace(status_code=200)

    requestor = ThrottledRequestor(
        user_agent="reddit-reader/0.1 by u/tester",
        session=FakeSession(),
        throttle=Throttle(2.0, clock=clock, sleep=clock.sleep),
    )
    for _ in range(3):
        requestor.request("GET", "https://oauth.reddit.com/x")
    assert calls == [1000.0, 1002.0, 1004.0]


def test_user_agent_format():
    assert user_agent("me") == "reddit-reader/0.1 by u/me"


def test_make_reddit_uses_throttled_requestor_without_network():
    reddit = make_reddit(Credentials("cid", "csecret", "me", "pw"))
    requestor = reddit._core.requestor
    assert isinstance(requestor, ThrottledRequestor)
    assert requestor._http.headers["User-Agent"].startswith("reddit-reader/0.1 by u/me")


def test_credentials_repr_hides_secrets():
    text = repr(Credentials("cid", "csecret", "me", "hunter2"))
    assert "csecret" not in text and "hunter2" not in text and "cid" not in text


def response(status):
    return SimpleNamespace(status_code=status, headers={}, text="", json=lambda: {})


@pytest.mark.parametrize(
    "exc, needle",
    [
        (pexc.OAuthException(response(400), "invalid_grant", None), "password:123456"),
        (pexc.Forbidden(response(403)), "not been approved"),
        (pexc.ResponseException(response(401)), "HTTP 401"),
        (pexc.TooManyRequests(response(429)), "429"),
        (pexc.ResponseException(response(500)), "Reddit returned an error"),
        (pexc.RequestException(OSError("boom"), (), {}), "Network error"),
    ],
)
def test_describe_error(exc, needle):
    assert needle in describe_error(exc)


def test_describe_error_unknown():
    assert describe_error(ValueError("x")) is None


WRITE_METHODS = [
    "submit", "reply", "upvote", "downvote", "clear_vote", "subscribe",
    "unsubscribe", "edit", "delete", "save", "unsave", "hide", "unhide",
    "report", "crosspost", "message", "compose", "mark_read", "block",
]


def test_source_uses_no_write_api():
    """Cheap guard for the read-only constraint: no write methods are called."""
    src = pathlib.Path(__file__).resolve().parents[1] / "src" / "reddit_reader"
    pattern = re.compile(r"\.(" + "|".join(WRITE_METHODS) + r")\(")
    offenders = [
        f"{path.name}: {m.group(0)}"
        for path in src.glob("*.py")
        for m in pattern.finditer(path.read_text())
    ]
    assert offenders == []
