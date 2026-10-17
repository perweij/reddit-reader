import pytest
from conftest import NOW, FakeReddit, FakeSubmission, make_item
from prawcore import exceptions as pexc
from types import SimpleNamespace

from reddit_reader import cli, config, db


@pytest.fixture
def dbfile(tmp_path, monkeypatch):
    for name in config.CREDENTIAL_VARS + ("REDDIT_READER_MAX_AGE_DAYS",):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "state.db"
    monkeypatch.setenv("REDDIT_READER_DB", str(path))
    return path


def test_status_empty(dbfile, capsys):
    assert cli.main(["status"]) == 0
    assert capsys.readouterr().out.strip() == "All caught up."


def test_status_counts(dbfile, capsys):
    conn = db.connect(dbfile)
    db.insert_item(conn, make_item(1, subreddit="python"))
    db.insert_item(conn, make_item(2, subreddit="python"))
    db.insert_item(conn, make_item(3, subreddit="rust", over_18=1))
    conn.commit()
    conn.close()
    cli.main(["status"])
    out = capsys.readouterr().out
    assert "r/python" in out and "r/rust" in out and "total" in out
    cli.main(["status", "--exclude-nsfw"])
    assert "r/rust" not in capsys.readouterr().out


def test_fetch_with_fake_reddit(dbfile, capsys):
    import time

    now = int(time.time())
    reddit = FakeReddit(["python"], [FakeSubmission(created_utc=now - 60)])
    assert cli.main(["fetch"], reddit_factory=lambda: reddit) == 0
    assert "Fetched 1 new item(s)." in capsys.readouterr().out


def test_fetch_missing_credentials(dbfile, capsys):
    assert cli.main(["fetch"]) == 2
    err = capsys.readouterr().err
    assert "REDDIT_CLIENT_ID" in err


def test_fetch_forbidden_reported(dbfile, capsys):
    def factory():
        raise pexc.Forbidden(SimpleNamespace(status_code=403, headers={}, text=""))

    assert cli.main(["fetch"], reddit_factory=factory) == 1
    assert "403" in capsys.readouterr().err


def test_run_fetches_then_reads_with_flags(dbfile):
    calls = []

    def reader(conn, **kwargs):
        calls.append(kwargs)
        return 0

    reddit = FakeReddit([])
    rc = cli.main(
        ["run", "--newest-first", "--exclude-nsfw"], reddit_factory=lambda: reddit, reader=reader
    )
    assert rc == 0
    assert calls == [{"newest_first": True, "exclude_nsfw": True}]


def test_run_stops_if_fetch_fails(dbfile):
    calls = []
    rc = cli.main(["run"], reader=lambda conn, **kw: calls.append(kw) or 0)
    assert rc == 2
    assert calls == []


def test_read_defaults(dbfile):
    calls = []
    cli.main(["read"], reader=lambda conn, **kw: calls.append(kw) or 0)
    assert calls == [{"newest_first": False, "exclude_nsfw": False}]


def test_db_flag_overrides_env(dbfile, tmp_path, capsys):
    other = tmp_path / "other.db"
    cli.main(["--db", str(other), "status"])
    assert other.exists()
