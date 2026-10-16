import json
import os
import subprocess
import sys
from pathlib import Path

from boardlib import server, store

CLI = Path(__file__).resolve().parents[1] / "scripts" / "devboard.py"


def test_default_home_is_dot_devboard(monkeypatch):
    monkeypatch.delenv("DEVBOARD_HOME")
    assert store.home() == Path.home() / ".devboard"


def test_default_template_is_english_and_pt_br_follows_lang(monkeypatch):
    b = store.Board.init("en", "EN")
    assert b.meta["template"] == "stages" and b.meta["columns"]["todo"] == "To do"
    assert (b.dir / "card.md.tmpl").read_text(encoding="utf-8").startswith("# {title}\n\n## Goal")
    monkeypatch.setenv("DEVBOARD_LANG", "pt-BR")
    assert store.Board.init("pt", "PT").meta["columns"]["todo"] == "A fazer"
    monkeypatch.setenv("DEVBOARD_TEMPLATE", "stages")
    assert store.Board.init("pt2", "PT2").meta["template"] == "stages"


def test_rollouts_dir_from_env(monkeypatch, tmp_path):
    d = tmp_path / "elsewhere" / "r1"
    d.mkdir(parents=True)
    (d / "STATUS.json").write_text(json.dumps({"meta": {"fases": ["a"]}, "unidades": {"u": {"fase": "a"}}}))
    monkeypatch.setenv("DEVBOARD_ROLLOUTS", str(tmp_path / "elsewhere"))
    assert ("rollout-r1", "rollout") in store.list_boards()


def test_hook_prints_session_context_only_inside_a_board(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    store.Board.init("p", "P", [str(repo)]).add("1", "A", {"started": True})
    store.Board("p").message("1", "check this")

    def hook(cwd):
        r = subprocess.run([sys.executable, str(CLI), "hook"], input=json.dumps({"cwd": str(cwd), "source": "startup"}),
                           capture_output=True, text=True, env=os.environ.copy())
        assert r.returncode == 0
        return r.stdout

    out = json.loads(hook(repo))["hookSpecificOutput"]
    assert out["hookEventName"] == "SessionStart"
    ctx = out["additionalContext"]
    assert "Board p: 1 cards (1 in progress, 0 blocked) · 1 messages for the agent" in ctx and "devboard.py inbox" in ctx
    assert hook(tmp_path) == ""


def test_config_route_reports_language(monkeypatch):
    import http.client
    import threading
    monkeypatch.setenv("DEVBOARD_LANG", "pt-BR")
    s = server.make_server(0)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        port = s.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/api/config")
        cfg = json.loads(c.getresponse().read())
        assert cfg["lang"] == "pt-BR" and cfg["home"]
        for lang in ("en", "pt-BR"):
            c.request("GET", f"/i18n/{lang}.json")
            r = c.getresponse()
            assert r.status == 200 and "Message for the agent" in r.read().decode() or lang == "pt-BR"
    finally:
        s.shutdown()
        s.server_close()


def test_unknown_language_falls_back_to_english(monkeypatch):
    monkeypatch.setenv("DEVBOARD_LANG", "xx")
    assert server.config()["lang"] == "en"


def test_safe_name_fallback_is_english():
    assert store.safe_name("...") == "file"
