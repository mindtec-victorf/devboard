"""Assignee (`--for`), requests from agents to the user (`ask`), the automatic "user" board, notices,
the per-prompt hook and the manual order of cards (`rank`)."""
import io
import json
import sys
from pathlib import Path

import pytest

import devboard
from boardlib import apply as batch
from boardlib import notify, store, userboard


@pytest.fixture
def board(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    b = store.Board.init("proj", "Project", [str(repo)])
    b.add("1", "Login")
    b.add("2", "Deploy")
    return b


def run(argv, capsys):
    code = devboard.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


# --- assignee ---

@pytest.mark.parametrize("value", ["user", "agent", "agent:codex-1", "agent:claude.main"])
def test_assignee_accepts_user_and_agents(board, value):
    assert board.set("1", {"assignee": value})["assignee"] == value


def test_assignee_repo_is_resolved(board, tmp_path):
    c = board.set("1", {"assignee": f"agent:codex@{tmp_path / 'repo'}"})
    assert c["assignee"] == f"agent:codex@{(tmp_path / 'repo').resolve()}"
    assert store.parse_assignee(c["assignee"])["name"] == "codex"


@pytest.mark.parametrize("value", ["igor", "users", "agent:", "agent:-x", "agent@", "agent:a b"])
def test_assignee_refuses_other_values(board, value):
    with pytest.raises(store.BoardError, match="assignee"):
        board.set("1", {"assignee": value})


def test_assignee_for_matches_name_and_folder(tmp_path):
    repo = tmp_path / "repo"
    (repo / "sub").mkdir(parents=True)
    assert store.assignee_for("agent", str(repo), "codex")
    assert store.assignee_for("agent:codex", str(repo), "codex")
    assert not store.assignee_for("agent:claude", str(repo), "codex")
    assert store.assignee_for(f"agent@{repo}", str(repo / "sub"), None)
    assert not store.assignee_for(f"agent@{repo}", str(tmp_path), None)
    assert not store.assignee_for("user", str(repo), "codex")
    assert not store.assignee_for(None, str(repo), "codex")


def test_cli_for_para_and_unassign(board, capsys):
    code, out, _ = run(["set", "1", "--board", "proj", "--for", "user"], capsys)
    assert code == 0 and "for: user" in out
    run(["set", "1", "--board", "proj", "--para", "agent:codex"], capsys)
    assert board.card("1")["assignee"] == "agent:codex"
    run(["set", "1", "--board", "proj", "--unassign"], capsys)
    assert board.card("1").get("assignee") is None
    code, _, err = run(["set", "1", "--board", "proj", "--for", "igor"], capsys)
    assert code == 2 and "assignee must be" in err


def test_assignee_survives_validate_and_audit(board):
    board.set("1", {"assignee": "agent:codex"})
    assert board.validate() == [] and board.audit() == {}


# --- requests (ask) ---

def test_ask_assigns_to_user_and_answer_hands_back(board):
    board.set("1", {"assignee": "agent:codex"}, by="codex")
    m = board.ask("1", "Which domain for the passkey?", by="codex")
    c = board.card("1")
    assert m["to"] == "user" and c["assignee"] == "user" and c["requests_open"] == 1 and c["messages_open"] == 0
    assert board.inbox() == [] and [r["n"] for r in board.requests()] == [m["n"]]
    board.reply("1", m["n"], "app.example.com", by="human")
    c = board.card("1")
    assert c["assignee"] == "agent:codex" and c["requests_open"] == 0
    assert board.audit() == {}


def test_answer_goes_back_to_the_asker_when_there_was_no_agent(board):
    m = board.ask("2", "OK to spend US$ 4?", by="claude-main")
    board.reply("2", m["n"], "yes", by="human")
    assert board.card("2")["assignee"] == "agent:claude-main"
    m = board.ask("1", "again?", by="agent")  # a generic writer: any agent of the board gets it back
    board.reply("1", m["n"], "no", by="human")
    assert board.card("1")["assignee"] == "agent"


def test_card_stays_with_user_while_another_request_is_open(board):
    a = board.ask("1", "first", by="codex")
    board.ask("1", "second", by="codex")
    board.reply("1", a["n"], "done", by="human")
    assert board.card("1")["assignee"] == "user" and board.card("1")["requests_open"] == 1


def test_messages_to_the_agent_are_unchanged(board):
    m = board.message("1", "check the import", by="human")
    assert m["to"] == "agent" and board.inbox()[0]["n"] == m["n"] and board.requests() == []
    board.reply("1", m["n"], "done", by="codex")
    assert board.card("1").get("assignee") is None


def test_cli_ask_requests_and_apply(board, capsys, tmp_path):
    code, out, _ = run(["ask", "1", "--board", "proj", "--by", "codex", "need the Render URL"], capsys)
    assert code == 0 and "asked the user" in out
    code, out, _ = run(["requests", "--board", "proj"], capsys)
    assert "1#1 " in out and "need the Render URL" in out
    code, out, _ = run(["requests", "--all"], capsys)
    assert "proj:1#1" in out
    f = tmp_path / "ops.json"
    f.write_text(json.dumps({"board": "proj", "ops": [{"op": "ask", "card": "2", "text": "price?"}]}), encoding="utf-8")
    spec, src = batch.load(f)
    batch.run(board, batch.plan(board, spec["ops"]), src, by="codex")
    assert board.card("2")["assignee"] == "user"


# --- the automatic user board ---

def test_user_board_collects_cards_for_the_user_across_boards(board, tmp_path):
    other = store.Board.init("other", "Other", [str(tmp_path)])
    other.add("7", "Contract", {"assignee": "user", "priority": 1})
    board.ask("2", "credential?", by="codex")
    board.add("3", "Done thing", {"assignee": "user", "status": "done"})
    board.add("4", "Agent work", {"assignee": "agent"})
    ub = store.open_board(store.USER_BOARD)
    ids = [c["id"] for c in ub.cards()]
    assert ids == ["other:7", "proj:2"]  # priority first; done and agent cards stay out
    c = ub.card("proj:2")
    assert c["source_board"] == "proj" and c["source_id"] == "2" and c["requests_open"] == 1
    assert ub.detail("proj:2")["md"].startswith("# Deploy")
    assert [r["card"] for r in ub.requests()] == ["proj:2"]
    assert ub.history(0) and ub.rev()
    with pytest.raises(store.ReadOnly):
        ub.set("proj:2", {"title": "x"})
    with pytest.raises(store.NotFound):
        ub.card("nocolon")


def test_user_board_in_overview_only_when_not_empty(board):
    assert store.USER_BOARD not in [r["id"] for r in store.overview()]
    board.set("1", {"assignee": "user"})
    rows = store.overview()
    assert rows[0]["id"] == store.USER_BOARD and rows[0]["kind"] == "user" and rows[0]["cards"] == 1


def test_user_board_skips_archived_boards(board):
    board.set("1", {"assignee": "user"})
    store.archive("proj")
    assert userboard.UserBoard().cards() == []


def test_user_id_is_reserved():
    with pytest.raises(store.BoardError, match="reserved"):
        store.Board.init("user", "x")


# --- notices ---

def test_notice_only_when_an_agent_hands_work_to_the_user(board, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(notify, "user", lambda title, body: sent.append((title, body)))
    board.set("1", {"assignee": "user"}, by="human")
    board.set("2", {"assignee": "agent"}, by="codex")
    assert sent == []
    board.set("2", {"assignee": "user"}, note="please test on staging", by="codex")
    board.ask("1", "domain?", by="codex")
    board.add("9", "New", {"assignee": "user"}, by="codex")
    assert [b for _, b in sent] == ["#2 Deploy: please test on staging", "#1 Login: domain?", "#9 New"]
    assert sent[0][0] == "Project"


def test_notify_runs_the_custom_command(monkeypatch, tmp_path):
    out = tmp_path / "notice.txt"
    script = tmp_path / "write.py"
    script.write_text("import os,sys;open(sys.argv[1],'w',encoding='utf-8').write("
                      "os.environ['DEVBOARD_NOTIFY_TITLE']+'|'+os.environ['DEVBOARD_NOTIFY_BODY'])", encoding="utf-8")
    monkeypatch.setenv("DEVBOARD_NOTIFY", "1")
    monkeypatch.setenv("DEVBOARD_NOTIFY_CMD", f'"{sys.executable}" "{script}" "{out}"')
    assert notify.user("Board", "#1 Login") is True
    import time
    for _ in range(100):
        if out.exists() and out.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    assert out.read_text(encoding="utf-8") == "devboard · Board|#1 Login"


def test_notify_off(monkeypatch):
    monkeypatch.setenv("DEVBOARD_NOTIFY", "0")
    monkeypatch.setenv("DEVBOARD_NOTIFY_CMD", "exit 1")
    assert notify.user("t", "b") is False


# --- the hook on every prompt ---

def hook(monkeypatch, capsys, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    devboard.main(["hook"])
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out.strip() else None


def test_prompt_hook_tells_only_what_is_new(board, monkeypatch, capsys, tmp_path):
    repo = str(tmp_path / "repo")
    start = hook(monkeypatch, capsys, {"hook_event_name": "SessionStart", "cwd": repo, "session_id": "s1"})
    assert start["hookEventName"] == "SessionStart" and "Board proj" in start["additionalContext"]
    assert hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "cwd": repo, "session_id": "s1"}) is None
    board.message("1", "check the import", by="human")
    board.set("2", {"assignee": "agent"}, by="human")
    news = hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "cwd": repo, "session_id": "s1"})
    assert news["hookEventName"] == "UserPromptSubmit"
    assert "human asks the agent: check the import" in news["additionalContext"]
    assert "card 2 is assigned to agent" in news["additionalContext"]
    assert hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "cwd": repo, "session_id": "s1"}) is None
    m = board.ask("1", "domain?", by="codex")
    board.reply("1", m["n"], "app.example.com", by="human")
    news = hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "cwd": repo, "session_id": "s1"})
    assert "the user answered codex's request" in news["additionalContext"] and "app.example.com" in news["additionalContext"]


def test_prompt_hook_is_silent_outside_a_board_and_without_session(board, monkeypatch, capsys, tmp_path):
    assert hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path / "x"), "session_id": "s"}) is None
    board.message("1", "hi", by="human")
    assert hook(monkeypatch, capsys, {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path / "repo")}) is None


def test_hooks_json_runs_on_every_prompt():
    hooks = json.loads((Path(devboard.__file__).resolve().parents[3] / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert "UserPromptSubmit" in hooks["hooks"] and "SessionStart" in hooks["hooks"]


# --- manual order ---

def test_rank_reorders_inside_the_column_without_pinning(board):
    c = board.move("2", "todo", rank=-1)
    assert c["rank"] == -1 and c.get("status") is None and c["column"] == "todo"
    c = board.move("1", "doing", rank=0.5)
    assert c["status"] == "doing" and c["rank"] == 0.5


def test_move_without_rank_still_pins(board):
    assert board.move("1", "todo")["status"] == "todo"


@pytest.mark.parametrize("bad", [True, "1", float("nan"), 1e16])
def test_rank_must_be_a_number(board, bad):
    with pytest.raises(store.BoardError, match="rank"):
        board.set("1", {"rank": bad})


def test_cli_move_rank(board, capsys):
    code, _, _ = run(["move", "2", "todo", "--board", "proj", "--rank", "-3"], capsys)
    assert code == 0 and board.card("2")["rank"] == -3
