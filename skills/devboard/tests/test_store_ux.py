import hashlib
import io
import json

import pytest

from boardlib import derive, store


@pytest.fixture
def board():
    return store.Board.init("proj", "Project")


# --- status: explicit column, set by a drag or by the agent ---

def test_explicit_status_wins_over_derived_column():
    assert derive.column({"status": "done"}, 40) == "done"
    assert derive.column({"status": "todo", "blocked": "x"}, 100) == "todo"
    assert derive.column({"status": None}, 100) == "done"


def test_status_validation(board):
    board.add("1", "A")
    with pytest.raises(store.BoardError, match="status must be one of"):
        board.set("1", {"status": "feito"})
    assert board.set("1", {"status": "final"})["column"] == "final"
    assert board.set("1", {"status": None})["column"] == "todo"
    assert "status" not in json.loads(board.paths("1")[0].read_text(encoding="utf-8"))


def test_move_out_of_blocked_clears_reason(board):
    board.add("1", "A", {"blocked": "ETL", "waiting": "TI"})
    c = board.move("1", "doing")
    assert c["column"] == "doing" and not c.get("blocked") and not c.get("waiting")
    ev = board.events("1")[-1]
    assert ev["by"] == "human" and ev["changes"]["status"] == [None, "doing"] and ev["changes"]["blocked"] == ["ETL", None]


def test_move_into_blocked_keeps_reason_and_checks_etag(board):
    etag = board.add("1", "A", {"waiting": "TI"})["etag"]
    assert board.move("1", "blocked", etag=etag)["waiting"] == "TI"
    with pytest.raises(store.Conflict):
        board.move("1", "done", etag=etag)
    with pytest.raises(store.BoardError, match="status must be one of"):
        board.move("1", "auto")


def test_audit_still_clean_after_moves(board):
    board.add("1", "A", {"blocked": "x"})
    board.move("1", "done")
    assert board.audit() == {}


# --- messages to the agent ---

def test_message_inbox_and_reply(board):
    board.add("1", "A")
    board.add("2", "B")
    m = board.message("2", "  check the import  ")
    board.message("1", "prioritize this")
    assert m["n"] == 1 and m["text"] == "check the import"
    assert [(i["card"], i["n"]) for i in board.inbox()] == [("2", 1), ("1", 1)]
    assert board.card("2")["messages_open"] == 1
    board.reply("2", 1, "ran at 7am, 12 certificates")
    assert [(i["card"], i["n"]) for i in board.inbox()] == [("1", 1)]
    msgs = board.messages("2")
    assert msgs[0]["open"] is False and msgs[0]["reply"]["text"] == "ran at 7am, 12 certificates"
    assert msgs[0]["reply"]["by"] == "agent" and board.card("2")["messages_open"] == 0


def test_message_errors(board):
    board.add("1", "A")
    with pytest.raises(store.BoardError, match="empty"):
        board.message("1", " ")
    with pytest.raises(store.NotFound, match="message 3"):
        board.reply("1", 3, "x")
    board.message("1", "a")
    board.reply("1", 1, "ok")
    with pytest.raises(store.BoardError, match="already answered"):
        board.reply("1", 1, "de novo")
    with pytest.raises(store.BoardError, match="reply is empty"):
        board.message("1", "b") and board.reply("1", 2, "")


# --- attachments ---

def test_attach_copy_dedupes_name_and_records_hash(board, tmp_path):
    board.add("1", "A")
    f = tmp_path / "prd v1.md"
    f.write_bytes(b"# PRD\n")  # bytes: no newline translation on Windows
    a = board.attach("1", f)
    b = board.attach("1", f)
    assert a["name"] == "prd v1.md" and b["name"] == "prd v1-2.md"
    assert a["sha1"] == hashlib.sha1(b"# PRD\n").hexdigest() and a["size"] == 6 and a["mode"] == "copy"
    assert board.file_path("1", "prd v1-2.md").read_text(encoding="utf-8") == "# PRD\n"
    assert board.card("1")["files_count"] == 2
    assert board.events("1")[-1]["kind"] == "attach"


def test_attach_link_points_to_original(board, tmp_path):
    board.add("1", "A")
    f = tmp_path / "video.mp4"
    f.write_bytes(b"\x00" * 10)
    a = board.attach("1", f, link=True)
    assert a["mode"] == "link" and board.file_path("1", "video.mp4") == f.resolve()
    assert not (board.dir / "files" / "1" / "video.mp4").exists()


def test_attach_stream_sanitizes_name(board):
    board.add("1", "A")
    a = board.attach_stream("1", "../../etc/pass\x00wd", io.BytesIO(b"abc"), 3, by="human")
    assert a["name"] == "passwd" and a["by"] == "human"
    assert (board.dir / "files" / "1" / "passwd").read_bytes() == b"abc"
    assert board.attach_stream("1", "...", io.BytesIO(b"x"), 1)["name"] == "file"


def test_attach_stream_rejects_short_body(board):
    board.add("1", "A")
    with pytest.raises(store.BoardError, match="upload ended early"):
        board.attach_stream("1", "a.txt", io.BytesIO(b"ab"), 5)
    assert board.files("1") == [] and list((board.dir / "files" / "1").iterdir()) == []


def test_detach_removes_copy_and_logs(board, tmp_path):
    board.add("1", "A")
    f = tmp_path / "x.png"
    f.write_bytes(b"png")
    board.attach("1", f)
    board.detach("1", "x.png")
    assert board.files("1") == [] and not (board.dir / "files" / "1" / "x.png").exists()
    assert f.exists()
    with pytest.raises(store.NotFound):
        board.file_path("1", "x.png")
    with pytest.raises(store.NotFound):
        board.detach("1", "x.png")


def test_attach_errors_and_validate(board, tmp_path):
    board.add("1", "A")
    with pytest.raises(store.BoardError, match="not a file"):
        board.attach("1", tmp_path / "sumiu.pdf")
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF")
    board.attach("1", f, link=True)
    f.unlink()
    assert any("doc.pdf" in p and "missing" in p for p in board.validate())


# --- final review fixes ---

def test_move_keeps_agent_reason_unless_leaving_blocked(board):
    board.add("1", "A")
    board.move("1", "doing")
    c = board.set("1", {"blocked": "waiting on the DBA"})
    assert c["column"] == "blocked" and c.get("status") is None  # agent's block unpins the column
    board.add("2", "B", {"status": "doing", "waiting": "TI"})
    assert board.move("2", "final")["waiting"] == "TI"  # was not in Bloqueada: reason kept


def test_pending_lists_cards_dragged_into_blocked(board):
    board.add("1", "A")
    board.move("1", "blocked")
    assert [c["id"] for c in board.pending()] == ["1"]


@pytest.mark.parametrize("raw,expected", [
    ("note.", "note"), ("CON.txt", "_CON.txt"), ("nul", "_nul"), ("a‮gpj.exe", "agpj.exe"),
    ("  rep. final .pdf . ", "rep. final .pdf"),
])
def test_safe_name_windows_rules(raw, expected):
    assert store.safe_name(raw) == expected


def test_safe_name_long_utf8_fits_and_keeps_extension():
    name = store.safe_name("文" * 100 + ".pdf")
    assert len(name.encode("utf-8")) <= 200 and name.endswith(".pdf")


def test_case_insensitive_names_do_not_collide(board):
    board.add("1", "A")
    board.attach_stream("1", "Photo.png", io.BytesIO(b"1"), 1)
    assert board.attach_stream("1", "photo.png", io.BytesIO(b"2"), 1)["name"] == "photo-2.png"
