import json

import pytest

from boardlib import rollout, store

STATUS = {
    "meta": {"projeto": "i18n", "fases": ["leitura", "aplicacao", "concluido"]},
    "unidades": {
        "repoA": {"fase": "aplicacao", "status": "em_progresso", "bloqueios": ["DB DEV fora"],
                  "resultado": {"unit": "25/25"}, "ts": "2026-10-16T10:00:00-03:00"},
        "repoB": {"fase": "concluido", "status": "falhou", "ts": "2026-10-16T11:00:00-03:00"},
        "#1042": {"fase": "revisao", "status": "pendente"},
    },
}


@pytest.fixture
def rollout_dir(board_home):
    d = board_home / "rollouts" / "I18n Generic"
    d.mkdir(parents=True)
    (d / "STATUS.json").write_text(json.dumps(STATUS), encoding="utf-8")
    return d


def test_rollout_listed_and_mapped(rollout_dir):
    assert ("rollout-i18n-generic", "rollout") in store.list_boards()
    b = store.open_board("rollout-i18n-generic")
    assert list(b.meta["columns"]) == ["leitura", "aplicacao", "concluido", "revisao"]
    a = b.card("repoA")
    assert a["column"] == "aplicacao" and a["progress"] == 50
    assert a["blocked"] == "DB DEV fora" and a["situation"] == "unit=25/25"
    assert b.card("repoB")["tags"] == ["failed"]
    assert [c["id"] for c in b.pending()] == ["repoA", "repoB"]
    assert b.history()[0]["card"] == "repoB"


def test_rollout_is_read_only(rollout_dir):
    with pytest.raises(store.ReadOnly):
        store.open_board("rollout-i18n-generic").set("repoA", {"next": "x"})


def test_link_rollout_idempotent_and_slug_collision(rollout_dir, tmp_path):
    other = tmp_path / "elsewhere" / "i18n generic"
    other.mkdir(parents=True)
    (other / "STATUS.json").write_text(json.dumps(STATUS), encoding="utf-8")
    assert rollout.link(other / "STATUS.json") == "rollout-i18n-generic-2"
    assert rollout.link(other / "STATUS.json") == "rollout-i18n-generic-2"
    assert json.loads((store.home() / "_rollouts.json").read_text(encoding="utf-8")) == \
        [str((other / "STATUS.json").resolve())]


def test_link_rejects_non_ledger(tmp_path):
    f = tmp_path / "x.json"
    f.write_text("{}", encoding="utf-8")
    with pytest.raises(store.BoardError, match="unidades"):
        rollout.link(f)


def test_unknown_rollout_is_not_found():
    with pytest.raises(store.NotFound):
        store.open_board("rollout-nope")


def test_rollout_has_no_messages_or_files_and_refuses_them(rollout_dir):
    b = store.open_board("rollout-i18n-generic")
    assert b.inbox() == [] and b.files("repoA") == [] and b.messages("repoA") == []
    for call in (lambda: b.move("repoA", "done"), lambda: b.message("repoA", "x"), lambda: b.attach("repoA", "/etc/hosts")):
        with pytest.raises(store.ReadOnly):
            call()


def test_english_ledger_keys(board_home):
    d = board_home / "rollouts" / "en-ledger"
    d.mkdir(parents=True)
    (d / "STATUS.json").write_text(json.dumps({
        "meta": {"project": "Rollout", "phases": ["read", "apply", "done"]},
        "units": {"repo-a": {"phase": "apply", "status": "failed", "blockers": ["DB down"], "result": {"tests": "9/9"},
                             "ts": "2026-10-16T10:00:00-03:00"}}}), encoding="utf-8")
    b = store.open_board("rollout-en-ledger")
    c = b.card("repo-a")
    assert b.meta["title"] == "Rollout" and list(b.meta["columns"]) == ["read", "apply", "done"]
    assert c["column"] == "apply" and c["progress"] == 50 and c["tags"] == ["failed"]
    assert c["blocked"] == "DB down" and c["situation"] == "tests=9/9"
    assert rollout.link(d / "STATUS.json") == "rollout-en-ledger"
