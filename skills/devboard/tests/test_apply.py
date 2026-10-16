import json

import pytest

from boardlib import apply as batch
from boardlib import store

OPS = [
    {"op": "add", "card": "1", "title": "A", "md": "- [ ] x\n- [ ] y\n"},
    {"op": "check", "card": "1", "item": 1},
    {"op": "add", "card": "2", "title": "B", "fields": {"priority": 1}},
    {"op": "set", "card": "2", "changes": {"progress": 30}, "note": "started"},
    {"op": "note", "card": "2", "text": "milestone"},
]


@pytest.fixture
def board():
    return store.Board.init("proj", "Project")


def write(tmp_path, ops, board="proj"):
    f = tmp_path / "ops.json"
    f.write_text(json.dumps({"board": board, "ops": ops}), encoding="utf-8")
    return f


def test_apply_runs_all_and_tags_src(board, tmp_path):
    spec, src = batch.load(write(tmp_path, OPS))
    assert src.startswith("apply:") and len(src) == 14
    assert batch.run(board, batch.plan(board, spec["ops"]), src) == 5
    assert board.card("1")["progress"] == 50 and board.card("2")["progress"] == 30
    assert all(e["src"] == src for e in board.history())


def test_invalid_op_writes_nothing(board, tmp_path):
    spec, _ = batch.load(write(tmp_path, OPS + [{"op": "check", "card": "1", "item": 9}]))
    with pytest.raises(store.BoardError, match="op 6: checklist has 2"):
        batch.plan(board, spec["ops"])
    assert board.card_ids() == []


def test_rerun_fails_before_writing(board, tmp_path):
    spec, src = batch.load(write(tmp_path, OPS))
    batch.run(board, batch.plan(board, spec["ops"]), src)
    n = len(board.history())
    with pytest.raises(store.BoardError, match="op 1: card '1' already exists"):
        batch.plan(board, spec["ops"])
    assert len(board.history()) == n


def test_same_file_builds_same_board(tmp_path):
    a, b = store.Board.init("a", "A"), store.Board.init("b", "B")
    spec, src = batch.load(write(tmp_path, OPS))
    for bd in (a, b):
        batch.run(bd, batch.plan(bd, spec["ops"]), src)
    strip = lambda cs: [{k: v for k, v in c.items() if k not in ("updated", "etag")} for c in cs]  # noqa: E731
    assert strip(a.cards()) == strip(b.cards())


@pytest.mark.parametrize("op,msg", [
    ({"op": "set", "card": "9", "changes": {"next": "x"}}, "op 1: card '9' not found"),
    ({"op": "zap", "card": "1"}, "unknown op"),
    ({"op": "set", "card": "1"}, "needs changes or note"),
    ({"op": "add", "card": "Bad", "title": "x"}, "invalid card id"),
    ({"op": "set", "card": "1", "changes": {"progress": 5}}, "checklist"),
    ({"op": "note", "card": "1", "text": " "}, "needs text"),
])
def test_plan_errors(board, op, msg):
    board.add("1", "A", md="- [ ] a\n")
    with pytest.raises(store.BoardError, match=msg):
        batch.plan(board, [op])


def test_load_rejects_bad_shape(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("[]", encoding="utf-8")
    with pytest.raises(store.BoardError, match="expected"):
        batch.load(f)
