"""Linked cards: a delivery board shows cards of other boards; every write goes to the source board."""
import http.client
import json
import threading

import pytest

import devboard
from boardlib import links, server, store, userboard


@pytest.fixture
def pair():
    src = store.Board.init("src", "Source")
    src.add("a1", "Alpha", md="- [ ] one\n- [ ] two\n")
    src.add("a2", "Beta")
    dev = store.Board.init("dev", "Delivery")
    dev.add("own", "Mine")
    links.link("dev", "src/a1")
    links.link("dev", "src:a2")
    return src, store.open_board("dev")


def cli(argv, capsys):
    code = devboard.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_link_unlink_and_refusals(pair):
    src, dev = pair
    assert isinstance(dev, links.LinkedBoard) and dev.links() == ["src:a1", "src:a2"]
    links.link("dev", "src/a1")  # twice: no-op
    assert store.open_board("dev").links() == ["src:a1", "src:a2"]
    for bad in ("src/nope", "dev/own", "user/x", "rollout-x/1", "noslash"):
        with pytest.raises(store.BoardError):
            links.link("dev", bad)
    with pytest.raises(store.NotFound):
        links.unlink("dev", "src/zzz")
    links.unlink("dev", "src/a1")
    links.unlink("dev", "src/a2")
    assert "links" not in json.loads((store.Board("dev").dir / "board.json").read_text("utf-8"))
    assert type(store.open_board("dev")) is store.Board


def test_cards_order_and_view(pair):
    src, dev = pair
    cards = dev.cards()
    assert [c["id"] for c in cards] == ["own", "src:a1", "src:a2"]
    c = cards[1]
    assert (c["source_board"], c["source_id"], c["source_title"], c["rank"]) == ("src", "a1", "Source", None)
    assert c["etag"] == src.card("a1")["etag"] and c["title"] == "Alpha"
    assert "source_board" not in cards[0]


def test_writes_land_on_source(pair):
    src, dev = pair
    dev.set("src:a1", {"priority": 2}, note="hi", by="agent")
    dev.check("src:a1", 1)
    dev.note("src:a1", "plain note")
    dev.message("src:a1", "ping", by="human")
    s = src.card("a1")
    assert s["priority"] == 2 and s["checklist"] == [2, 1]
    kinds = [e["kind"] for e in src.events("a1")]
    assert kinds[-4:] == ["set", "check", "note", "message"]
    assert dev.card("src:a1")["priority"] == 2
    assert not [p for p in (dev.dir / "cards").iterdir() if ":" in p.name or p.stem == "a1"]
    assert [p.stem for p in (dev.dir / "cards").glob("*.json")] == ["own"]


def test_move_ignores_rank(pair):
    src, dev = pair
    before = src.card("a1").get("rank")
    v = dev.move("src:a1", "doing", etag=dev.card("src:a1")["etag"], rank=5)
    s = src.card("a1")
    assert s["status"] == "doing" and s.get("rank") == before and v["id"] == "src:a1"


def test_unlinked_ref_not_found(pair):
    _, dev = pair
    with pytest.raises(store.NotFound):
        dev.card("src:zzz")
    store.Board("src").add("a3", "Gamma")
    with pytest.raises(store.NotFound):
        dev.set("src:a3", {"priority": 1})


def test_missing_source_placeholder_and_validate(pair):
    src, dev = pair
    (src.dir / "cards" / "a2.json").unlink()
    ph = [c for c in dev.cards() if c["id"] == "src:a2"][0]
    assert ph["column"] == "blocked" and ph["missing"] is True
    assert any("src:a2" in p for p in dev.validate())
    assert "src:a2" not in dev.card_ids()


def test_history_and_inbox_include_linked(pair):
    src, dev = pair
    dev.message("src:a1", "ping", by="human")
    assert any(e["card"] == "src:a1" and e["kind"] == "message" for e in dev.history())
    assert [m["card"] for m in dev.inbox()] == ["src:a1"]


def test_for_you_board_counts_linked_card_once(pair):
    src, dev = pair
    src.set("a1", {"assignee": "user"})
    ids = [c["id"] for c in store.open_board("user").cards()]
    assert ids == ["src:a1"]
    assert userboard.wanted(src.card("a1"))


def test_rev_follows_source(pair):
    src, dev = pair
    r = dev.rev()
    src.note("a1", "change")
    assert dev.rev() != r


@pytest.fixture
def srv():
    s = server.make_server(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s.server_address[1]
    s.shutdown()
    s.server_close()


def req(port, method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    data = None if body is None else json.dumps(body).encode()
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    c.putheader("Host", f"127.0.0.1:{port}")
    c.putheader("X-Board", "1")
    if data is not None:
        c.putheader("Content-Type", "application/json")
        c.putheader("Content-Length", str(len(data)))
    c.endheaders(data)
    r = c.getresponse()
    raw = r.read()
    c.close()
    return r.status, json.loads(raw)


@pytest.mark.parametrize("colon", [":", "%3A"])
def test_server_lists_and_updates_linked(srv, pair, colon):
    src, _ = pair
    code, j = req(srv, "GET", "/api/b/dev")
    assert code == 200 and [c["id"] for c in j["cards"]] == ["own", "src:a1", "src:a2"]
    etag = src.card("a1")["etag"]
    code, j = req(srv, "POST", f"/api/b/dev/cards/src{colon}a1", {"etag": etag, "changes": {"priority": 4}})
    assert code == 200 and j["id"] == "src:a1" and src.card("a1")["priority"] == 4
    code, _ = req(srv, "POST", f"/api/b/dev/cards/src{colon}a1", {"etag": etag, "changes": {"priority": 1}})
    assert code == 409


def test_cli_link_card_and_show(pair, capsys):
    store.Board.init("d2", "D2")
    code, out, _ = cli(["link-card", "src/a1", "--board", "d2"], capsys)
    assert code == 0 and "1 linked" in out
    code, out, _ = cli(["show", "src:a1", "--board", "d2"], capsys)
    assert code == 0 and "source: src/a1 (Source)" in out
    assert cli(["link-card", "d2/x", "--board", "d2"], capsys)[0] == 2
    assert cli(["unlink-card", "src:a1", "--board", "d2"], capsys)[0] == 0
    assert cli(["unlink-card", "src:a1", "--board", "d2"], capsys)[0] == 2
