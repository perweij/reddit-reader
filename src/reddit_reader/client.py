"""Reddit client construction, request throttling and error descriptions.

This application is strictly read-only: it only ever lists the authenticated
user's subscriptions and reads subreddit "new" listings.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import praw
import prawcore
from prawcore import exceptions as pexc

from .config import Credentials

# At most one request every 2 seconds => <= 30 requests/minute, well under
# Reddit's 100/minute limit. PRAW's own header-based rate limiting still applies.
MIN_REQUEST_INTERVAL = 2.0


def user_agent(username: str) -> str:
    return f"reddit-reader/0.1 by u/{username}"


class Throttle:
    """Enforce a minimum interval between consecutive calls to `wait()`."""

    def __init__(
        self,
        min_interval: float = MIN_REQUEST_INTERVAL,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None:
            delay = self._last + self.min_interval - now
            if delay > 0:
                self._sleep(delay)
                now += delay
        self._last = now


class ThrottledRequestor(prawcore.Requestor):
    """prawcore Requestor that spaces out every HTTP request (auth included)."""

    def __init__(self, *args: Any, throttle: Throttle | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.throttle = throttle or Throttle()

    def request(self, *args: Any, **kwargs: Any):
        self.throttle.wait()
        return super().request(*args, **kwargs)


def make_reddit(creds: Credentials) -> praw.Reddit:
    return praw.Reddit(
        client_id=creds.client_id,
        client_secret=creds.client_secret,
        username=creds.username,
        password=creds.password,
        user_agent=user_agent(creds.username),
        requestor_class=ThrottledRequestor,
        check_for_updates=False,
        check_for_async=False,
    )


AUTH_HINT = (
    "Check that REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET belong to a 'script' app, "
    "that REDDIT_USERNAME/REDDIT_PASSWORD are correct, and, if the account uses "
    "two-factor authentication, that REDDIT_PASSWORD is in the form "
    "'password:123456' with a current one-time code."
)

ACCESS_HINT = (
    "Reddit refused the request. This usually means API access for this app "
    "has not been approved (yet), or the app is not a 'script' app owned by "
    "this account."
)


def describe_error(exc: BaseException) -> str | None:
    """Return a human-readable explanation for a Reddit/PRAW error, else None."""
    if isinstance(exc, pexc.OAuthException):
        return f"Authentication failed ({exc}). {AUTH_HINT}"
    if isinstance(exc, pexc.TooManyRequests):
        return "Reddit rate limit hit (HTTP 429). Wait a few minutes and try again."
    if isinstance(exc, pexc.ResponseException):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 401:
            return f"Authentication rejected (HTTP 401). {AUTH_HINT}"
        if status == 403:
            return f"Access forbidden (HTTP 403). {ACCESS_HINT}"
        return f"Reddit returned an error: {exc}"
    if isinstance(exc, pexc.RequestException):
        return f"Network error talking to Reddit: {exc.original_exception}"
    if isinstance(exc, pexc.PrawcoreException):
        return f"Reddit API error: {exc}"
    return None
