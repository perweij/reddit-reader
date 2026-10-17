"""Configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB = "~/.local/share/reddit-reader/state.db"
DEFAULT_MAX_AGE_DAYS = 7

CREDENTIAL_VARS = (
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "REDDIT_USERNAME",
    "REDDIT_PASSWORD",
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str
    username: str
    password: str

    def __repr__(self) -> str:  # never leak secrets into logs or tracebacks
        return f"Credentials(username={self.username!r})"


def db_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return Path(env.get("REDDIT_READER_DB") or DEFAULT_DB).expanduser()


def max_age_days(env: dict[str, str] | None = None) -> int:
    env = os.environ if env is None else env
    raw = env.get("REDDIT_READER_MAX_AGE_DAYS")
    if not raw:
        return DEFAULT_MAX_AGE_DAYS
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"REDDIT_READER_MAX_AGE_DAYS must be an integer, got {raw!r}")
    if value < 1:
        raise ConfigError("REDDIT_READER_MAX_AGE_DAYS must be >= 1")
    return value


def credentials(env: dict[str, str] | None = None) -> Credentials:
    env = os.environ if env is None else env
    missing = [name for name in CREDENTIAL_VARS if not env.get(name)]
    if missing:
        raise ConfigError("missing environment variables: " + ", ".join(missing))
    return Credentials(
        client_id=env["REDDIT_CLIENT_ID"],
        client_secret=env["REDDIT_CLIENT_SECRET"],
        username=env["REDDIT_USERNAME"],
        password=env["REDDIT_PASSWORD"],
    )
