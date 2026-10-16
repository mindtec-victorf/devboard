import http.client
import json
import threading

import pytest

from boardlib import server, store

H = {"X-Board": "1"}


@pytest.fixture
def srv():
    s = server.make_server(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s.server_address[1]
    s.shutdown()
    s.server_close()


@pytest.fixture
def card():
    return store.Board.init("p", "P").add("1", "A", md="- [ ] a\n")


def req(port, method, path, body=None, headers=None, host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    data = None if body is None else json.dumps(body).encode()
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    c.putheader("Host", host or f"127.0.0.1:{port}")
    for k, v in (headers or {}).items():
        c.putheader(k, v)
    if data is not None:
        c.putheader("Content-Type", "application/json")
        c.putheader("Content-Length", str(len(data)))
    c.endheaders(data)
    r = c.getresponse()
    raw = r.read()
    c.close()
    try:
        return r.status, json.loads(raw)
    except ValueError:
        return r.status, raw


def test_get_board_and_detail(srv, card):
    code, j = req(srv, "GET", "/api/b/p")
    assert code == 200 and j["cards"][0]["id"] == "1" and j["rev"] and j["readonly"] is False
    code, j = req(srv, "GET", "/api/b/p/cards/1")
    assert code == 200 and j["md"] == "- [ ] a\n" and j["events"][0]["kind"] == "create"
    assert req(srv, "GET", "/api/rev?board=p")[1]["rev"] == req(srv, "GET", "/api/b/p")[1]["rev"]


def test_static_and_traversal(srv):
    assert req(srv, "GET", "/")[0] == 200
    assert req(srv, "GET", "/app.js")[0] == 200
    assert req(srv, "GET", "/../SKILL.md")[0] == 404
    assert req(srv, "GET", "/web/app.js")[0] == 404


def test_bad_host_and_missing_header(srv, card):
    assert req(srv, "GET", "/api/boards", host="evil.com")[0] == 403
    assert req(srv, "GET", "/api/boards", host=f"evil.com:{srv}")[0] == 403
    assert req(srv, "POST", "/api/b/p/cards/1", {"etag": card["etag"], "changes": {}})[0] == 403


def test_post_set_then_stale_conflict(srv, card):
    code, j = req(srv, "POST", "/api/b/p/cards/1", {"etag": card["etag"], "changes": {"next": "x"}}, H)
    assert code == 200 and j["next"] == "x"
    assert store.Board("p").events("1")[-1]["by"] == "human"
    code, j = req(srv, "POST", "/api/b/p/cards/1", {"etag": card["etag"], "changes": {"next": "y"}}, H)
    assert code == 409 and j["card"]["next"] == "x"


def test_post_validation_etag_and_body(srv, card):
    assert req(srv, "POST", "/api/b/p/cards/1", {"etag": card["etag"], "changes": {"progress": 101}}, H)[0] == 400
    assert req(srv, "POST", "/api/b/p/cards/1", {"changes": {"next": "x"}}, H)[0] == 400
    assert req(srv, "POST", "/api/b/p/cards/1", [1, 2], H)[0] == 400


def test_post_check_and_create(srv, card):
    code, j = req(srv, "POST", "/api/b/p/cards/1/check", {"etag": card["etag"], "index": 1, "done": True}, H)
    assert code == 200 and j["progress"] == 100 and j["column"] == "done"
    code, j = req(srv, "POST", "/api/b/p/cards", {"id": "2", "title": "B"}, H)
    assert code == 201 and j["id"] == "2"
    assert req(srv, "POST", "/api/b/p/cards", {"id": "2", "title": "B"}, H)[0] == 400


def test_rollout_is_405_and_readonly(srv, board_home):
    d = board_home / "rollouts" / "r"
    d.mkdir(parents=True)
    (d / "STATUS.json").write_text(json.dumps({"meta": {"fases": ["a"]}, "unidades": {"u": {"fase": "a"}}}))
    assert req(srv, "POST", "/api/b/rollout-r/cards/u", {"etag": "", "changes": {}}, H)[0] == 405
    assert req(srv, "GET", "/api/b/rollout-r")[1]["readonly"] is True


def test_rollout_unit_with_hash(srv, board_home):
    d = board_home / "rollouts" / "logs"
    d.mkdir(parents=True)
    (d / "STATUS.json").write_text(json.dumps({"meta": {"fases": ["a"]}, "unidades": {"#1042": {"fase": "a"}}}))
    code, j = req(srv, "GET", "/api/b/rollout-logs/cards/%231042")
    assert code == 200 and j["id"] == "#1042"


def test_unknown_board_and_card_404(srv, card):
    assert req(srv, "GET", "/api/b/nope")[0] == 404
    assert req(srv, "GET", "/api/b/p/cards/9")[0] == 404


def test_unexpected_error_is_500_json(srv, board_home):
    d = board_home / "rollouts" / "bad"
    d.mkdir(parents=True)
    (d / "STATUS.json").write_text(json.dumps({"meta": {"fases": ["a"]}, "unidades": {"u": "x"}}))
    code, j = req(srv, "GET", "/api/b/rollout-bad")
    assert code == 500 and "error" in j
    assert req(srv, "GET", "/api/boards")[0] == 200


def raw_post(port, path, data, headers):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
    c.putheader("Host", f"127.0.0.1:{port}")
    for k, v in headers.items():
        c.putheader(k, v)
    c.endheaders(data)
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, json.loads(body)


def test_move_message_and_inbox(srv, card):
    code, j = req(srv, "POST", "/api/b/p/cards/1/move", {"etag": card["etag"], "status": "doing"}, H)
    assert code == 200 and j["column"] == "doing"
    assert req(srv, "POST", "/api/b/p/cards/1/move", {"etag": card["etag"], "status": "done"}, H)[0] == 409
    assert req(srv, "POST", "/api/b/p/cards/1/move", {"etag": j["etag"], "status": "zzz"}, H)[0] == 400
    code, m = req(srv, "POST", "/api/b/p/cards/1/message", {"text": "check this"}, H)
    assert code == 201 and m["n"] == 1 and m["by"] == "human"
    assert req(srv, "POST", "/api/b/p/cards/1/message", {"text": " "}, H)[0] == 400
    code, inbox = req(srv, "GET", "/api/b/p/inbox")
    assert code == 200 and inbox[0]["text"] == "check this"
    d = req(srv, "GET", "/api/b/p/cards/1")[1]
    assert d["messages"][0]["open"] is True and d["messages_open"] == 1


def test_upload_serve_range_and_detach(srv, card):
    data = b"0123456789"
    code, f = raw_post(srv, "/api/b/p/cards/1/files", data,
                       {"X-Board": "1", "X-Filename": "final%20video.mp4", "Content-Length": str(len(data))})
    assert code == 201 and f["name"] == "final video.mp4" and f["size"] == 10
    assert raw_post(srv, "/api/b/p/cards/1/files", data, {"Content-Length": "10", "X-Filename": "x"})[0] == 403
    c = http.client.HTTPConnection("127.0.0.1", srv, timeout=5)
    c.request("GET", "/api/b/p/cards/1/files/final%20video.mp4", headers={"Range": "bytes=2-5"})
    r = c.getresponse()
    assert r.status == 206 and r.read() == b"2345" and r.getheader("Content-Range") == "bytes 2-5/10"
    assert "sandbox" in r.getheader("Content-Security-Policy") and r.getheader("Content-Type") == "video/mp4"
    c.request("GET", "/api/b/p/cards/1/files/final%20video.mp4")
    r = c.getresponse()
    assert r.status == 200 and r.read() == data
    c.close()
    assert req(srv, "POST", "/api/b/p/cards/1/detach", {"name": "final video.mp4"}, H)[0] == 200
    assert req(srv, "GET", "/api/b/p/cards/1/files/final%20video.mp4")[0] == 404


def test_upload_needs_filename_and_length(srv, card):
    assert raw_post(srv, "/api/b/p/cards/1/files", b"x", {"X-Board": "1", "Content-Length": "1"})[0] == 400
    assert raw_post(srv, "/api/b/p/cards/1/files", b"", {"X-Board": "1", "X-Filename": "a", "Content-Length": "-1"})[0] == 400


def test_pdf_not_sandboxed_html_is(srv, card):
    for name, sandboxed in (("a.pdf", False), ("b.html", True)):
        raw_post(srv, "/api/b/p/cards/1/files", b"x", {"X-Board": "1", "X-Filename": name, "Content-Length": "1"})
        c = http.client.HTTPConnection("127.0.0.1", srv, timeout=5)
        c.request("GET", f"/api/b/p/cards/1/files/{name}")
        r = c.getresponse()
        r.read()
        c.close()
        assert ("sandbox" in (r.getheader("Content-Security-Policy") or "")) is sandboxed


def test_aborted_download_is_quiet(srv, card, capfd):
    import socket
    import time
    data = b"x" * (8 * 1024 * 1024)
    raw_post(srv, "/api/b/p/cards/1/files", data, {"X-Board": "1", "X-Filename": "v.mp4", "Content-Length": str(len(data))})
    s = socket.create_connection(("127.0.0.1", srv))
    s.sendall(f"GET /api/b/p/cards/1/files/v.mp4 HTTP/1.1\r\nHost: 127.0.0.1:{srv}\r\n\r\n".encode())
    s.recv(1024)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
    s.close()
    time.sleep(0.5)
    assert "Traceback" not in capfd.readouterr().err
    assert req(srv, "GET", "/api/b/p")[0] == 200


def test_text_attachments_open_inline_as_utf8_text(srv, card):
    body = "# PRD ç".encode()
    raw_post(srv, "/api/b/p/cards/1/files", body, {"X-Board": "1", "X-Filename": "prd.md", "Content-Length": str(len(body))})
    c = http.client.HTTPConnection("127.0.0.1", srv, timeout=5)
    c.request("GET", "/api/b/p/cards/1/files/prd.md")
    r = c.getresponse()
    assert r.read().decode() == "# PRD ç" and r.getheader("Content-Type") == "text/plain; charset=utf-8"
    c.close()


def test_archive_route(srv, card):
    assert req(srv, "POST", "/api/boards/p/archive", {"archived": True})[0] == 403
    code, j = req(srv, "POST", "/api/boards/p/archive", {"archived": True}, H)
    assert code == 200 and j["archived"] is True
    assert req(srv, "GET", "/api/boards")[1][0]["archived"] is True
    assert req(srv, "POST", "/api/boards/p/archive", {"archived": False}, H)[1]["archived"] is False
    assert req(srv, "POST", "/api/boards/nope/archive", {"archived": True}, H)[0] == 404
