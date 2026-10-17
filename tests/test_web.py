import http.client
import threading
from urllib.parse import urlencode

import pytest
from conftest import make_item

from reddit_reader import cli, db, web


@pytest.fixture
def dbpath(tmp_path):
    return tmp_path / "state.db"


def seed(path, *items):
    conn = db.connect(path)
    for item in items:
        db.insert_item(conn, item)
    conn.commit()
    conn.close()


def seen(path):
    conn = db.connect(path)
    try:
        return {r["fullname"] for r in conn.execute("SELECT fullname FROM items WHERE seen = 1")}
    finally:
        conn.close()


@pytest.fixture
def start(dbpath):
    servers = []

    def _start(**options):
        server = web.make_server(dbpath, 0, **options)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server.server_address[1]

    yield _start
    for s in servers:
        s.shutdown()
        s.server_close()


def request(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    hdrs = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    hdrs.update(headers or {})
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    return resp, data


def test_binds_loopback_only(dbpath):
    server = web.make_server(dbpath, 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_caught_up_page(start):
    port = start()
    resp, body = request(port, "GET", "/")
    assert resp.status == 200
    assert "All caught up." in body


def test_batch_then_next_marks_exactly_shown(dbpath, start):
    seed(dbpath, *(make_item(i) for i in range(1, 6)))
    port = start(batch=2)
    resp, body = request(port, "GET", "/")
    assert resp.status == 200
    assert "Item 1" in body and "Item 2" in body and "Item 3" not in body
    assert "5 unseen" in body
    assert body.count('name="fullname"') == 2

    # An item fetched after the page was rendered must not be marked.
    form = urlencode([("fullname", "t3_item1"), ("fullname", "t3_item2")])
    resp, _ = request(port, "POST", "/next", body=form)
    assert resp.status == 303 and resp.getheader("Location") == "/"
    assert seen(dbpath) == {"t3_item1", "t3_item2"}

    _, body = request(port, "GET", "/")
    assert "Item 3" in body and "Item 1" not in body


def test_newest_first_and_nsfw_filter(dbpath, start):
    seed(dbpath, make_item(1), make_item(2, over_18=1), make_item(3))
    port = start(newest_first=True, exclude_nsfw=True)
    _, body = request(port, "GET", "/")
    assert body.index("Item 3") < body.index("Item 1")
    assert "Item 2" not in body


def test_html_is_escaped_and_unsafe_urls_dropped(dbpath, start):
    seed(
        dbpath,
        make_item(
            1,
            title="<script>alert(1)</script>",
            selftext="<b>bold</b>",
            is_self=0,
            url="javascript:alert(1)",
        ),
    )
    port = start()
    _, body = request(port, "GET", "/")
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body and "&lt;b&gt;bold&lt;/b&gt;" in body
    assert "javascript:" not in body


def test_no_external_assets(dbpath, start):
    seed(dbpath, make_item(1, is_self=0, url="https://example.com/a"))
    port = start()
    resp, body = request(port, "GET", "/")
    assert "<script" not in body and "<link" not in body and "<img" not in body
    assert "default-src 'none'" in resp.getheader("Content-Security-Policy")
    assert 'rel="noopener noreferrer"' in body


def test_foreign_host_rejected(start):
    port = start()
    resp, _ = request(port, "GET", "/", headers={"Host": "evil.example"})
    assert resp.status == 403


def test_cross_origin_post_rejected(dbpath, start):
    seed(dbpath, make_item(1))
    port = start()
    form = urlencode({"fullname": "t3_item1"})
    resp, _ = request(port, "POST", "/next", body=form, headers={"Origin": "https://evil.example"})
    assert resp.status == 403
    assert seen(dbpath) == set()
    resp, _ = request(
        port, "POST", "/next", body=form, headers={"Origin": f"http://localhost:{port}"}
    )
    assert resp.status == 303
    assert seen(dbpath) == {"t3_item1"}


def test_invalid_fullnames_ignored(dbpath, start):
    seed(dbpath, make_item(1))
    port = start()
    form = urlencode([("fullname", "x' OR 1=1 --"), ("fullname", "t3_item1")])
    request(port, "POST", "/next", body=form)
    assert seen(dbpath) == {"t3_item1"}


def test_unknown_paths(start):
    port = start()
    assert request(port, "GET", "/nope")[0].status == 404
    assert request(port, "POST", "/nope", body="")[0].status == 404


def test_cli_serve_passes_options(tmp_path):
    calls = []
    path = tmp_path / "s.db"
    rc = cli.main(
        ["--db", str(path), "serve", "--port", "9999", "--batch", "5", "--exclude-nsfw"],
        server=lambda p, **kw: calls.append((p, kw)) or 0,
    )
    assert rc == 0
    assert calls == [
        (str(path), {"port": 9999, "newest_first": False, "exclude_nsfw": True, "batch": 5})
    ]
