from pathlib import Path

import pytest

from reddit_reader import config


def test_defaults():
    assert config.db_path({}) == Path("~/.local/share/reddit-reader/state.db").expanduser()
    assert config.max_age_days({}) == 7


def test_overrides():
    env = {"REDDIT_READER_DB": "/tmp/x.db", "REDDIT_READER_MAX_AGE_DAYS": "3"}
    assert config.db_path(env) == Path("/tmp/x.db")
    assert config.max_age_days(env) == 3


@pytest.mark.parametrize("raw", ["abc", "0", "-2"])
def test_bad_max_age(raw):
    with pytest.raises(config.ConfigError):
        config.max_age_days({"REDDIT_READER_MAX_AGE_DAYS": raw})


def test_missing_credentials_listed():
    with pytest.raises(config.ConfigError) as err:
        config.credentials({"REDDIT_CLIENT_ID": "x", "REDDIT_USERNAME": "me"})
    assert "REDDIT_CLIENT_SECRET" in str(err.value)
    assert "REDDIT_PASSWORD" in str(err.value)
    assert "REDDIT_CLIENT_ID," not in str(err.value)


def test_credentials_ok():
    env = {n: "v" for n in config.CREDENTIAL_VARS}
    assert config.credentials(env).username == "v"
