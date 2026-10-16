import json

import pytest

from boardlib import store


@pytest.fixture
def boards(tmp_path):
    repo = tmp_path / "acme-certificates"
    repo.mkdir()
    a = store.Board.init("cert", "Certificates", [str(repo)])
    a.add("1", "A", {"progress": 100})
    a.add("2", "B", {"blocked": "TI"})
    a.message("2", "look at this")
    b = store.Board.init("solto", "No repo")
    b.add("1", "X")
    return repo


def test_overview_has_group_counts_and_activity(boards):
    rows = {r["id"]: r for r in store.overview()}
    c = rows["cert"]
    assert c["group"] == str(boards.resolve()) and c["group_name"] == "acme-certificates"
    assert c["counts"] == {"todo": 0, "blocked": 1, "doing": 0, "final": 0, "done": 1}
    assert c["cards"] == 2 and c["done"] == 1 and c["avg"] == 100 and c["messages_open"] == 1
    assert c["archived"] is False and c["updated"]
    assert rows["solto"]["group"] is None and rows["solto"]["avg"] is None


def test_archive_unarchive_is_logged_and_replayed(boards):
    store.archive("cert", by="human")
    assert store.archived() == {"cert"}
    assert {r["id"]: r for r in store.overview()}["cert"]["archived"] is True
    store.unarchive("cert")
    assert store.archived() == set()
    log = [json.loads(l) for l in (store.home() / "_archive.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(e["board"], e["archived"], e["by"]) for e in log] == [("cert", True, "human"), ("cert", False, "agent")]


def test_archive_unknown_board_fails(boards):
    with pytest.raises(store.NotFound):
        store.archive("nope")


def test_archived_board_no_longer_resolves(boards):
    assert store.resolve(boards) == "cert"
    store.archive("cert")
    assert store.resolve(boards) is None


def test_group_label_uses_tilde_for_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    repo = tmp_path / "projetos" / "x"
    repo.mkdir(parents=True)
    store.Board.init("x", "X", [str(repo)])
    assert {r["id"]: r for r in store.overview()}["x"]["group_label"] == "~/projetos/x"
