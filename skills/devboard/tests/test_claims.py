import pytest

from boardlib import store


@pytest.fixture
def board():
    b = store.Board.init("p", "P")
    b.add("1", "A")
    b.add("2", "B")
    return b


def test_claim_shows_on_card_and_who(board):
    c = board.claim("1", "codex-1", ttl="2h", note="writing the migration")
    assert c["claimed_by"]["agent"] == "codex-1" and c["claimed_by"]["note"] == "writing the migration"
    assert board.card("1")["claimed_by"]["agent"] == "codex-1" and board.card("2").get("claimed_by") is None
    assert [(w["card"], w["agent"]) for w in board.claims()] == [("1", "codex-1")]


def test_other_agent_is_refused_unless_forced(board):
    board.claim("1", "codex-1")
    with pytest.raises(store.Claimed, match="codex-1"):
        board.claim("1", "claude-a")
    c = board.claim("1", "claude-a", force=True)
    assert c["claimed_by"]["agent"] == "claude-a"
    assert board.events("1")[-1]["forced_from"] == "codex-1"


def test_same_agent_renews(board):
    first = board.claim("1", "codex-1", ttl="10m")["claimed_by"]["until"]
    again = board.claim("1", "codex-1", ttl="3h")["claimed_by"]["until"]
    assert again > first


def test_release_and_wrong_agent_release(board):
    board.claim("1", "codex-1")
    with pytest.raises(store.Claimed, match="codex-1"):
        board.release("1", "claude-a")
    assert board.release("1", "codex-1", note="done for today").get("claimed_by") is None
    with pytest.raises(store.BoardError, match="not claimed"):
        board.release("1", "codex-1")


def test_expired_claim_no_longer_counts(board, monkeypatch):
    board.claim("1", "codex-1", ttl="1m")
    monkeypatch.setattr(store, "_now_ts", lambda: 4 * 10 ** 9)  # year 2096
    assert board.card("1").get("claimed_by") is None and board.claims() == []
    assert board.claim("1", "claude-a")["claimed_by"]["agent"] == "claude-a"


@pytest.mark.parametrize("bad", ["0m", "abc", "-1h", "10x", ""])
def test_ttl_validation(board, bad):
    with pytest.raises(store.BoardError, match="ttl"):
        board.claim("1", "codex-1", ttl=bad)


@pytest.mark.parametrize("bad", ["", " ", "a b", "x" * 41])
def test_agent_name_validation(board, bad):
    with pytest.raises(store.BoardError, match="agent name"):
        board.claim("1", bad)


def test_claims_do_not_disturb_audit(board):
    board.claim("1", "codex-1")
    board.release("1", "codex-1")
    assert board.audit() == {}


def test_times_are_short_and_readable(board):
    board.claim("1", "codex-1", note="x")
    until = board.card("1")["claimed_by"]["until"]
    with pytest.raises(store.Claimed) as e:
        board.claim("1", "claude-a")
    assert f"until {until[11:16]} (x)" in str(e.value) and "T" not in str(e.value).split("until ")[1][:6]
    assert store.short_time("2001-02-03T04:05:06-03:00") == "2001-02-03 04:05"
