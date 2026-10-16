import json
import os
import subprocess
import sys
from pathlib import Path

BOARD = Path(__file__).resolve().parents[1] / "scripts" / "devboard.py"


def run(*args, cwd=None):
    r = subprocess.run([sys.executable, str(BOARD), *args], capture_output=True, text=True,
                       cwd=cwd, env=os.environ.copy(), encoding="utf-8")
    return r.returncode, r.stdout, r.stderr


def test_flow_init_add_set_summary_show(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert run("init", "proj", "--title", "Project", "--repo", str(repo))[0] == 0
    assert run("add", "20", "--title", "Multi-tenant", "--priority", "3", cwd=repo)[0] == 0
    code, out, _ = run("set", "20", "--progress", "70", "--next", "close the scope", "--note", "phase 2b", cwd=repo)
    assert code == 0 and "doing" in out and "70%" in out
    code, out, _ = run("summary", cwd=repo)
    assert out.splitlines()[0].startswith("proj — Project · 1 cards · avg 70%")
    assert "20 doing    70% P3  Multi-tenant | next: close the scope" in out
    code, out, _ = run("show", "20", "--json", cwd=repo)
    d = json.loads(out)
    assert d["progress"] == 70 and d["events"][-1]["note"] == "phase 2b"


def test_tags_add_and_remove(tmp_path):
    run("init", "p", "--title", "P")
    run("add", "1", "--board", "p", "--title", "A", "--tag", "Critical", "--tag", "UI")
    run("set", "1", "--board", "p", "--untag", "UI")
    assert json.loads(run("show", "1", "--board", "p", "--json")[1])["tags"] == ["Critical"]


def test_errors_exit_2_with_message(tmp_path):
    code, _, err = run("summary", cwd=tmp_path)
    assert code == 2 and "no board for" in err
    run("init", "p", "--title", "P")
    code, _, err = run("set", "1", "--board", "p", "--next", "x")
    assert code == 2 and "not found" in err
    run("add", "1", "--board", "p", "--title", "A")
    code, _, err = run("set", "1", "--board", "p")
    assert code == 2 and "nothing to change" in err


def test_block_and_unblock_are_exclusive(tmp_path):
    run("init", "p", "--title", "P")
    run("add", "1", "--board", "p", "--title", "A")
    assert run("set", "1", "--board", "p", "--block", "x", "--unblock")[0] == 2


def test_hint_silent_without_board(tmp_path):
    code, out, _ = run("hint", "--cwd", str(tmp_path))
    assert code == 0 and out == ""


def test_hint_line(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    run("init", "p", "--title", "P", "--repo", str(repo))
    run("add", "1", "--board", "p", "--title", "A", "--block", "ETL")
    out = run("hint", "--cwd", str(repo))[1]
    assert out.startswith("Board p: 1 cards (0 in progress, 1 blocked)") and out.rstrip().endswith("summary")


def test_apply_dry_run_then_apply(tmp_path):
    run("init", "p", "--title", "P")
    f = tmp_path / "ops.json"
    f.write_text(json.dumps({"board": "p", "ops": [{"op": "add", "card": "1", "title": "A"}]}), encoding="utf-8")
    code, out, _ = run("apply", str(f), "--dry-run")
    assert code == 0 and "1 op(s) valid" in out
    assert run("summary", "--board", "p")[1].count("\n") == 1
    code, out, _ = run("apply", str(f))
    assert code == 0 and "applied 1 op(s)" in out


def test_validate_and_audit_exit_codes(tmp_path):
    run("init", "p", "--title", "P")
    run("add", "1", "--board", "p", "--title", "A")
    assert run("validate", "--board", "p")[0] == 0
    assert run("audit", "--board", "p")[0] == 0
    card = Path(os.environ["DEVBOARD_HOME"]) / "p" / "cards" / "1.json"
    d = json.loads(card.read_text(encoding="utf-8"))
    d["next"] = "by hand"
    card.write_text(json.dumps(d), encoding="utf-8")
    code, out, _ = run("audit", "--board", "p")
    assert code == 1 and "1: next" in out


def test_check_and_history(tmp_path):
    run("init", "p", "--title", "P")
    md = tmp_path / "c.md"
    md.write_text("- [ ] a\n- [ ] b\n", encoding="utf-8")
    run("add", "1", "--board", "p", "--title", "A", "--md-file", str(md))
    code, out, _ = run("check", "1", "2", "--board", "p")
    assert code == 0 and "50%" in out
    assert "[x] b" in run("history", "--board", "p")[1]


def test_status_move_inbox_reply_attach(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    run("init", "p", "--title", "P", "--repo", str(repo))
    run("add", "1", "--board", "p", "--title", "A", "--block", "ETL")
    code, out, _ = run("move", "1", "done", "--board", "p")
    assert code == 0 and " done " in out and "blocked" not in out
    assert " doing " in run("set", "1", "--board", "p", "--status", "doing")[1]
    assert " todo " in run("set", "1", "--board", "p", "--status", "auto")[1]
    from boardlib import store
    store.Board("p").message("1", "check the import")
    code, out, _ = run("inbox", "--board", "p")
    assert code == 0 and "1#1" in out and "check the import" in out
    assert "1 messages for the agent" in run("hint", "--cwd", str(repo))[1]
    assert run("reply", "1", "1", "done", "--board", "p")[0] == 0
    assert "nothing waiting" in run("inbox", "--board", "p")[1]
    f = tmp_path / "prd.pdf"
    f.write_bytes(b"%PDF-1.4")
    code, out, _ = run("attach", "1", str(f), "--board", "p")
    assert code == 0 and "prd.pdf" in out and "copy" in out
    assert "prd.pdf" in run("files", "1", "--board", "p")[1]
    d = json.loads(run("show", "1", "--board", "p", "--json")[1])
    assert d["files"][0]["name"] == "prd.pdf" and d["messages"][0]["reply"]["text"] == "done"
    assert run("detach", "1", "prd.pdf", "--board", "p")[0] == 0
    assert run("set", "1", "--board", "p", "--status", "feito")[0] == 2


def test_archive_hides_board(tmp_path):
    run("init", "p", "--title", "P")
    assert run("archive", "p")[0] == 0
    assert "p " not in run("boards")[1] and "archived" in run("boards", "--all")[1]
    assert run("unarchive", "p")[0] == 0 and "p  board" in run("boards")[1]
