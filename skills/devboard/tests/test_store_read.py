import json

import pytest

from boardlib import store


@pytest.fixture
def board(tmp_path):
    return store.Board.init("proj", "Project")


def test_history_newest_first_with_card(board):
    board.add("1", "A")
    board.add("2", "B")
    board.note("1", "milestone")
    h = board.history()
    assert [(e["card"], e["kind"]) for e in h] == [("1", "note"), ("2", "create"), ("1", "create")]


def test_pending_lists_blocked_and_waiting(board):
    board.add("1", "A", {"blocked": "ETL"})
    board.add("2", "B", {"waiting": "vendor"})
    board.add("3", "C")
    assert [c["id"] for c in board.pending()] == ["1", "2"]


def test_torn_event_line_is_skipped_and_reported(board):
    board.add("1", "A")
    with open(board.paths("1")[2], "a", encoding="utf-8") as f:
        f.write('{"ts": "2026')
    assert len(board.events("1")) == 1
    assert any("unreadable event line" in p for p in board.validate())


def test_rev_changes_on_write(board):
    board.add("1", "A")
    r = board.rev()
    board.set("1", {"next": "x"})
    assert board.rev() != r


def test_validate_flags_orphan_bad_json_and_missing_repo(tmp_path):
    b = store.Board.init("p2", "P", [str(tmp_path / "sumiu")])
    b.add("1", "A")
    (b.dir / "cards" / "2.md").write_text("x", encoding="utf-8")
    b.paths("1")[0].write_text("{nope", encoding="utf-8")
    probs = b.validate()
    assert any("orphan cards/2.md" in p for p in probs)
    assert any("invalid JSON" in p for p in probs)
    assert any("does not exist" in p for p in probs)


def test_validate_healthy_board_is_empty(board):
    board.add("1", "A")
    assert board.validate() == []


def test_audit_detects_hand_edit(board):
    board.add("1", "A", {"progress": 10})
    board.set("1", {"progress": 20})
    assert board.audit() == {}
    p = board.paths("1")[0]
    d = json.loads(p.read_text(encoding="utf-8"))
    d["progress"] = 99
    p.write_text(json.dumps(d), encoding="utf-8")
    assert board.audit() == {"1": ["progress"]}


def test_card_ids_sort_numeric_then_alpha(board):
    for cid in ["10", "2", "beta", "1"]:
        board.add(cid, cid)
    assert board.card_ids() == ["1", "2", "10", "beta"]


def test_overview_counts(board):
    board.add("1", "A", {"progress": 100})
    board.add("2", "B")
    row = store.overview()[0]
    assert {k: row[k] for k in ("id", "kind", "title", "cards", "done")} == \
        {"id": "proj", "kind": "board", "title": "Project", "cards": 2, "done": 1}


def test_overview_survives_malformed_rollout(board, board_home):
    d = board_home / "rollouts" / "bad"
    d.mkdir(parents=True)
    (d / "STATUS.json").write_text(json.dumps({"meta": {"fases": ["a"]}, "unidades": {"u": "x"}}), encoding="utf-8")
    rows = {r["id"]: r for r in store.overview()}
    assert rows["proj"]["cards"] == 0 and "error" in rows["rollout-bad"]
