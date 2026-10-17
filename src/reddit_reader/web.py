"""Phase 2: a tiny local web UI, bound to 127.0.0.1 only.

Server-rendered HTML, no JavaScript, no external assets, no trackers.
"""

from __future__ import annotations

import html
import re
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

from . import db
from .reader import CAUGHT_UP
from .render import link_url, meta_line, truncate

HOST = "127.0.0.1"  # deliberately not configurable
DEFAULT_PORT = 8765
DEFAULT_BATCH = 20
MAX_FORM_BYTES = 64 * 1024
FULLNAME_RE = re.compile(r"^t3_[0-9a-z]+$")

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}

CSS = """
body { font: 16px/1.45 system-ui, sans-serif; max-width: 46rem; margin: 2rem auto;
       padding: 0 1rem; color: #1b1b1b; background: #fafafa; }
header { display: flex; justify-content: space-between; align-items: baseline; }
h1 { font-size: 1.2rem; margin: 0; }
article { background: #fff; border: 1px solid #ddd; border-radius: 6px;
          padding: .8rem 1rem; margin: .8rem 0; }
article h2 { font-size: 1.05rem; margin: .1rem 0 .3rem; }
article h2 a { color: inherit; text-decoration: none; }
article h2 a:hover { text-decoration: underline; }
.sub { color: #555; font-size: .85rem; font-weight: 600; }
.meta { color: #666; font-size: .85rem; }
.body { white-space: pre-wrap; margin: .5rem 0; }
.link { font-size: .9rem; word-break: break-all; }
.nsfw { color: #b00020; font-weight: 600; }
button { font-size: 1rem; padding: .6rem 2rem; cursor: pointer; }
.done { text-align: center; margin-top: 20vh; font-size: 1.4rem; }
@media (prefers-color-scheme: dark) {
  body { background: #121212; color: #e4e4e4; }
  article { background: #1e1e1e; border-color: #333; }
  .sub, .meta { color: #aaa; }
}
"""


def esc(text: object) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def safe_href(url: str | None) -> str | None:
    if url and urlsplit(url).scheme in ("http", "https"):
        return esc(url)
    return None


def page(title: str, body: str) -> bytes:
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{esc(title)}</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>\n"
    ).encode("utf-8")


def render_item(item: Mapping, now: float) -> str:
    permalink = safe_href(item["permalink"])
    title = esc(item["title"])
    if permalink:
        title = f'<a href="{permalink}" target="_blank" rel="noopener noreferrer">{title}</a>'
    parts = [
        "<article>",
        f'<div class="sub">r/{esc(item["subreddit"])}</div>',
        f"<h2>{title}</h2>",
        f'<div class="meta">{esc(meta_line(item, now))}</div>',
    ]
    preview = truncate(item["selftext"])
    if preview:
        parts.append(f'<div class="body">{esc(preview)}</div>')
    link = safe_href(link_url(item))
    if link:
        parts.append(
            f'<div class="link"><a href="{link}" target="_blank" '
            f'rel="noopener noreferrer">{link}</a></div>'
        )
    parts.append("</article>")
    return "\n".join(parts)


def render_batch(items: list, remaining: int, now: float | None = None) -> bytes:
    now = time.time() if now is None else now
    hidden = "".join(
        f'<input type="hidden" name="fullname" value="{esc(i["fullname"])}">' for i in items
    )
    body = (
        f"<header><h1>reddit-reader</h1><span class=\"meta\">{remaining} unseen</span></header>"
        + "\n".join(render_item(i, now) for i in items)
        + f'<form method="post" action="/next">{hidden}'
        f'<p style="text-align:center"><button type="submit" autofocus>Next</button></p></form>'
    )
    return page(f"reddit-reader ({remaining})", body)


def render_caught_up() -> bytes:
    return page("reddit-reader", f'<p class="done">{esc(CAUGHT_UP)}</p>')


def make_handler(
    db_path: Path | str,
    *,
    newest_first: bool = False,
    exclude_nsfw: bool = False,
    batch: int = DEFAULT_BATCH,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "reddit-reader"
        sys_version = ""

        def log_message(self, format: str, *args: object) -> None:  # quiet
            pass

        def _send(self, status: HTTPStatus, body: bytes = b"", headers: dict | None = None):
            self.send_response(status)
            for k, v in {**SECURITY_HEADERS, **(headers or {})}.items():
                self.send_header(k, v)
            if body:
                self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def _allowed_hosts(self) -> set[str]:
            port = self.server.server_address[1]
            return {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _host_ok(self) -> bool:
            # Blocks DNS-rebinding: only requests addressed to this local server.
            return self.headers.get("Host", "") in self._allowed_hosts()

        def _origin_ok(self) -> bool:
            # Blocks cross-site form posts from other web pages.
            origin = self.headers.get("Origin")
            if origin is None or origin == "null":
                return origin is None
            return urlsplit(origin).netloc in self._allowed_hosts()

        def do_GET(self) -> None:
            if not self._host_ok():
                return self._send(HTTPStatus.FORBIDDEN)
            if urlsplit(self.path).path != "/":
                return self._send(HTTPStatus.NOT_FOUND, page("Not found", "<p>Not found.</p>"))
            conn = db.connect(db_path)
            try:
                items = db.unseen_items(
                    conn, newest_first=newest_first, exclude_nsfw=exclude_nsfw, limit=batch
                )
                if not items:
                    return self._send(HTTPStatus.OK, render_caught_up())
                remaining = db.unseen_count(conn, exclude_nsfw=exclude_nsfw)
                self._send(HTTPStatus.OK, render_batch(items, remaining))
            finally:
                conn.close()

        do_HEAD = do_GET

        def do_POST(self) -> None:
            if not (self._host_ok() and self._origin_ok()):
                return self._send(HTTPStatus.FORBIDDEN)
            if urlsplit(self.path).path != "/next":
                return self._send(HTTPStatus.NOT_FOUND)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send(HTTPStatus.BAD_REQUEST)
            if not 0 <= length <= MAX_FORM_BYTES:
                return self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
            fullnames = [f for f in form.get("fullname", []) if FULLNAME_RE.match(f)]
            conn = db.connect(db_path)
            try:
                db.mark_seen(conn, fullnames)
            finally:
                conn.close()
            self._send(HTTPStatus.SEE_OTHER, headers={"Location": "/"})

    return Handler


def make_server(db_path: Path | str, port: int = DEFAULT_PORT, **options) -> HTTPServer:
    return HTTPServer((HOST, port), make_handler(db_path, **options))


def serve(db_path: Path | str, port: int = DEFAULT_PORT, **options) -> int:
    try:
        server = make_server(db_path, port, **options)
    except OSError as exc:
        print(f"reddit-reader: cannot listen on {HOST}:{port}: {exc}", file=sys.stderr)
        return 1
    print(f"reddit-reader web UI on http://{HOST}:{server.server_address[1]}/ (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
