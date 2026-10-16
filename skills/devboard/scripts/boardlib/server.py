"""Local HTTP API + static page for `devboard.py serve`. Binds 127.0.0.1 only.

Defences: the Host header must be 127.0.0.1:<port> or localhost:<port> (DNS rebinding);
every POST needs the header X-Board: 1 (a cross-site form cannot set it); body <= 256 KB.
All writes go through store.py, exactly like the CLI.
"""
import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import store

WEB = Path(__file__).resolve().parents[2] / "web"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/fonts/nunito-sans.woff2": ("fonts/nunito-sans.woff2", "font/woff2"),
    **{f"/i18n/{lang}.json": (f"i18n/{lang}.json", "application/json; charset=utf-8") for lang in ("en", "pt-BR")},
}
LANGS = ("en", "pt-BR")
MAX_BODY = 256_000
MAX_UPLOAD = 2 * 1024 ** 3  # 2 GiB: videos fit; bigger files go in with `devboard.py attach --link`
# Text formats browsers would download (text/markdown, text/yaml...) are shown inline as plain text.
TEXT_EXT = {".md", ".markdown", ".txt", ".log", ".json", ".jsonl", ".csv", ".yaml", ".yml", ".xml", ".sql", ".ini", ".toml"}
RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def config():
    """What the page needs before rendering: UI language ($DEVBOARD_LANG, en fallback) and the data folder."""
    want = os.environ.get("DEVBOARD_LANG", "en")
    lang = next((x for x in LANGS if x.lower() == want.lower()), None) or \
        next((x for x in LANGS if x.split("-")[0] == want.split("-")[0].lower()), "en")
    home_dir, data = str(Path.home()), str(store.home())
    return {"lang": lang, "home": "~" + data[len(home_dir):] if data.startswith(home_dir) else data}


def _int(q, key, default):
    try:
        return max(0, int(q.get(key, [default])[0]))
    except ValueError:
        return default


class Handler(BaseHTTPRequestHandler):
    server_version = "board/1"

    def log_message(self, fmt, *args):  # quiet: the page shows errors, the terminal stays clean
        pass

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _err(self, code, msg, **extra):
        self._send(code, {"error": msg, **extra})

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _route(self):
        u = urlparse(self.path)
        return u.path, [unquote(p) for p in u.path.split("/") if p], parse_qs(u.query)

    def do_GET(self):
        if not self._host_ok():
            return self._err(403, "bad Host header")
        path, parts, q = self._route()
        if path in STATIC:
            name, ctype = STATIC[path]
            return self._send(200, (WEB / name).read_bytes(), ctype)
        try:
            if parts == ["api", "config"]:
                return self._send(200, config())
            if parts == ["api", "boards"]:
                return self._send(200, store.overview())
            if parts == ["api", "rev"]:
                return self._send(200, {"rev": store.open_board(q.get("board", [""])[0]).rev()})
            if len(parts) >= 3 and parts[:2] == ["api", "b"]:
                b, rest = store.open_board(parts[2]), parts[3:]
                if not rest:
                    return self._send(200, {"board": b.meta, "kind": b.kind, "readonly": b.readonly,
                                            "rev": b.rev(), "cards": b.cards()})
                if rest == ["history"]:
                    return self._send(200, b.history(_int(q, "limit", 200)))
                if rest == ["pending"]:
                    return self._send(200, b.pending())
                if rest == ["inbox"]:
                    return self._send(200, b.inbox())
                if rest == ["claims"]:
                    return self._send(200, b.claims())
                if len(rest) == 4 and rest[0] == "cards" and rest[2] == "files":
                    return self._file(b.file_path(rest[1], rest[3]))
                if len(rest) == 2 and rest[0] == "cards":
                    return self._send(200, b.detail(rest[1], _int(q, "events", 0)))
        except store.NotFound as e:
            return self._err(404, str(e))
        except store.BoardError as e:
            return self._err(400, str(e))
        except Exception as e:  # noqa: BLE001 — malformed data on disk; answer instead of hanging
            return self._err(500, f"{type(e).__name__}: {e}")
        self._err(404, "not found")

    def _file(self, path):
        """Serve an attachment: inline, sandboxed (no script runs against this origin), with byte ranges."""
        if not path.is_file():
            raise store.NotFound(f"attachment file is missing: {path}")
        size = path.stat().st_size
        start, end, code = 0, size - 1, 200
        m = RANGE_RE.match(self.headers.get("Range", ""))
        if m and size:
            a, z = m.groups()
            start = int(a) if a else max(0, size - int(z or 0))
            end = min(int(z), size - 1) if a and z else size - 1
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            code = 206
        ctype = "text/plain; charset=utf-8" if path.suffix.lower() in TEXT_EXT else \
            (mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if ctype != "application/pdf":  # the browser's PDF viewer refuses sandboxed documents
            self.send_header("Content-Security-Policy", "sandbox")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(path, "rb") as fh:
            fh.seek(start)
            left = end - start + 1 if size else 0
            try:
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True  # the player seeked or the tab closed: not an error

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _upload(self, b, cid, n):
        name = unquote(self.headers.get("X-Filename") or "")
        if not name.strip():
            return self._err(400, "X-Filename header required")
        if n > MAX_UPLOAD:
            return self._err(413, "file too large for upload; use devboard.py attach --link")
        return self._send(201, b.attach_stream(cid, name, self.rfile, n, by="human"))

    def _archive(self, bid, n):
        try:
            body = json.loads(self.rfile.read(min(n, MAX_BODY)) or b"{}")
            on = body.get("archived") if isinstance(body, dict) else None
            if not isinstance(on, bool):
                return self._err(400, "archived must be true/false")
            return self._send(200, (store.archive if on else store.unarchive)(bid, by="human"))
        except ValueError:
            return self._err(400, "body is not JSON")
        except store.NotFound as e:
            return self._err(404, str(e))
        except store.BoardError as e:
            return self._err(400, str(e))

    def do_POST(self):
        if not self._host_ok():
            return self._err(403, "bad Host header")
        if self.headers.get("X-Board") != "1":
            return self._err(403, "missing X-Board header")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            return self._err(400, "bad Content-Length")
        _, parts, _ = self._route()
        if len(parts) == 4 and parts[:2] == ["api", "boards"] and parts[3] == "archive":
            return self._archive(parts[2], n)
        if len(parts) < 4 or parts[:2] != ["api", "b"] or parts[3] != "cards":
            return self._err(404, "not found")
        rest = parts[4:]
        try:
            b = store.open_board(parts[2])
            if b.readonly:
                raise store.ReadOnly("rollout boards are read-only")
            if len(rest) == 2 and rest[1] == "files":
                return self._upload(b, rest[0], n)
            if n > MAX_BODY:
                return self._err(413, "body too large")
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._err(400, "body is not JSON")
            if not isinstance(body, dict):
                return self._err(400, "body must be an object")
            if len(rest) == 2 and rest[1] == "message":
                return self._send(201, b.message(rest[0], body.get("text"), by="human"))
            if len(rest) == 2 and rest[1] == "detach":
                return self._send(200, b.detach(rest[0], body.get("name"), by="human"))
            if not rest:
                card = b.add(body.get("id"), body.get("title"), body.get("fields") or {}, body.get("md"), by="human")
                return self._send(201, card)
            if "etag" not in body:
                return self._err(400, "etag required")
            if len(rest) == 1:
                return self._send(200, b.set(rest[0], body.get("changes") or {}, note=body.get("note"),
                                             by="human", etag=body["etag"]))
            if len(rest) == 2 and rest[1] == "check":
                return self._send(200, b.check(rest[0], body.get("index"), body.get("done", True),
                                               by="human", etag=body["etag"]))
            if len(rest) == 2 and rest[1] == "move":
                return self._send(200, b.move(rest[0], body.get("status"), by="human", etag=body["etag"]))
        except store.Conflict as e:
            return self._err(409, str(e), card=e.current)
        except store.ReadOnly as e:
            return self._err(405, str(e))
        except store.NotFound as e:
            return self._err(404, str(e))
        except store.BoardError as e:
            return self._err(400, str(e))
        except Exception as e:  # noqa: BLE001
            return self._err(500, f"{type(e).__name__}: {e}")
        self._err(404, "not found")


def make_server(port=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    return srv


def serve(port=8765, open_browser=False):
    srv = make_server(port)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"board: serving {url} (Ctrl+C stops)", flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
