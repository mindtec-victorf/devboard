import json

import pytest

from boardlib import store


@pytest.fixture
def board(tmp_path):
    return store.Board.init("proj", "Project", [str(tmp_path / "repo")])


def test_init_copies_template_and_columns(board):
    assert (board.dir / "card.md.tmpl").read_text(encoding="utf-8").startswith("# {title}")
    assert list(board.meta["columns"]) == ["todo", "blocked", "doing", "final", "done"]
    assert board.meta["template"] == "stages"


def test_init_rejects_reserved_prefix_duplicate_and_unknown_template(board):
    with pytest.raises(store.BoardError, match="reserved"):
        store.Board.init("rollout-x", "x")
    with pytest.raises(store.BoardError, match="already exists"):
        store.Board.init("proj", "x")
    with pytest.raises(store.BoardError, match="unknown template 'nope'; available: etapas, stages"):
        store.Board.init("outro", "x", template="nope")


def test_unknown_board_is_not_found():
    with pytest.raises(store.NotFound):
        store.Board("nope")


def test_add_writes_trio_and_create_event(board):
    c = board.add("20", "Multi-tenant", {"priority": 3, "tags": ["Critical"]})
    j, m, e = board.paths("20")
    assert j.exists() and m.exists() and e.exists() and c["column"] == "todo"
    ev = board.events("20")[0]
    assert ev["kind"] == "create" and ev["by"] == "agent" and ev["changes"]["priority"] == [None, 3]
    assert m.read_text(encoding="utf-8").startswith("# Multi-tenant")


def test_card_file_is_canonical(board):
    board.add("1", "A", {"next": "x", "started": True})
    assert list(json.loads(board.paths("1")[0].read_text(encoding="utf-8"))) == \
        ["id", "title", "started", "next", "updated"]


def test_add_refuses_progress_with_checklist_md(board):
    with pytest.raises(store.BoardError, match="checklist"):
        board.add("1", "A", {"progress": 10}, md="- [ ] a\n")


def test_set_logs_diff_and_drops_empty(board):
    board.add("1", "A", {"blocked": "ETL"})
    c = board.set("1", {"blocked": None, "progress": 40}, note="unblocked")
    assert c["column"] == "doing"
    assert "blocked" not in json.loads(board.paths("1")[0].read_text(encoding="utf-8"))
    ev = board.events("1")[-1]
    assert ev["kind"] == "set" and ev["note"] == "unblocked"
    assert ev["changes"] == {"blocked": ["ETL", None], "progress": [None, 40]}


def test_set_noop_writes_nothing(board):
    board.add("1", "A", {"progress": 10})
    before = board.paths("1")[0].read_bytes()
    board.set("1", {"progress": 10})
    assert board.paths("1")[0].read_bytes() == before and len(board.events("1")) == 1


def test_set_note_only_is_note_event(board):
    board.add("1", "A")
    board.set("1", {}, note="milestone")
    assert board.events("1")[-1]["kind"] == "note"


def test_set_progress_refused_with_checklist(board):
    board.add("1", "A", md="- [ ] a\n")
    with pytest.raises(store.BoardError, match="checklist"):
        board.set("1", {"progress": 50})


def test_stale_etag_conflicts_even_after_direct_md_edit(board):
    etag = board.add("1", "A")["etag"]
    board.paths("1")[1].write_text("edited by hand\n", encoding="utf-8")
    with pytest.raises(store.Conflict) as exc:
        board.set("1", {"next": "x"}, etag=etag)
    assert exc.value.current["etag"] != etag


@pytest.mark.parametrize("changes,msg", [
    ({"progress": 101}, "0-100"), ({"progress": "50"}, "0-100"), ({"progress": True}, "0-100"),
    ({"priority": 0}, ">= 1"), ({"due": "2026-13-01"}, "YYYY-MM-DD"), ({"due": "20260924"}, "YYYY-MM-DD"),
    ({"cor": "azul"}, "unknown field"), ({"title": "  "}, "empty"), ({"tags": [""]}, "tags"),
    ({"started": "sim"}, "true/false"), ({"next": 3}, "text"),
])
def test_validation(board, changes, msg):
    board.add("1", "A")
    with pytest.raises(store.BoardError, match=msg):
        board.set("1", changes)


@pytest.mark.parametrize("bad", ["../x", "A1", "", "a" * 42, "x/y"])
def test_bad_card_id(board, bad):
    with pytest.raises(store.BoardError, match="invalid card id"):
        board.add(bad, "A")


def test_bad_actor(board):
    with pytest.raises(store.BoardError, match="by"):
        board.add("1", "A", by="")


def test_check_updates_md_and_logs_progress(board):
    board.add("1", "A", md="- [ ] a\n- [ ] b\n")
    c = board.check("1", 1)
    assert c["progress"] == 50
    assert board.paths("1")[1].read_text(encoding="utf-8").startswith("- [x] a")
    ev = board.events("1")[-1]
    assert ev["kind"] == "check" and ev["progress"] == [0, 50] and ev["note"] == "[x] a"
    with pytest.raises(store.BoardError, match="has 2 item"):
        board.check("1", 3)
    with pytest.raises(store.BoardError, match="done"):
        board.check("1", 1, done="sim")


def test_note_requires_text(board):
    board.add("1", "A")
    with pytest.raises(store.BoardError, match="empty"):
        board.note("1", "  ")
