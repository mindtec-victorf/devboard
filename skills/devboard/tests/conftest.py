"""Every test gets its own DEVBOARD_HOME and a deterministic clock."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


@pytest.fixture(autouse=True)
def board_home(tmp_path, monkeypatch):
    home = tmp_path / "devboard"
    monkeypatch.setenv("DEVBOARD_HOME", str(home))
    for var in ("DEVBOARD_LANG", "DEVBOARD_TEMPLATE", "DEVBOARD_ROLLOUTS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("BOARD_ACTOR", raising=False)
    return home


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    try:
        from boardlib import store
    except ImportError:  # Task 1 runs before store.py exists
        return
    tick = {"n": 0}

    def fake_now():
        tick["n"] += 1
        n = tick["n"]
        return f"2026-10-16T12:{n // 60:02d}:{n % 60:02d}-03:00"

    monkeypatch.setattr(store, "now", fake_now)
