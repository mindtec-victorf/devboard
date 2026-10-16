import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from boardlib import store

ROOT = Path(__file__).resolve().parents[3]


def test_concurrent_writers_never_reuse_a_message_number():
    b = store.Board.init("p", "P")
    b.add("1", "A")
    errors = []

    def worker(i):
        try:
            store.Board("p").message("1", f"msg {i}")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert sorted(m["n"] for m in store.Board("p").messages("1")) == list(range(1, 13))


def test_hook_command_finds_a_python(tmp_path):
    if sys.platform == "win32":
        pytest.skip("hooks run in Git Bash on Windows; covered by the CI install step")
    cmd = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    repo = tmp_path / "repo"
    repo.mkdir()
    store.Board.init("p", "P", [str(repo)]).add("1", "A")
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
    r = subprocess.run(["sh", "-c", cmd], input=json.dumps({"cwd": str(repo)}), capture_output=True, text=True, env=env)
    assert r.returncode == 0 and json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].startswith("<devboard>")


def test_windows_launcher_and_installer_exist():
    cmd = (ROOT / "bin" / "devboard.cmd").read_text(encoding="utf-8")
    assert "py -3" in cmd and "python" in cmd
    ps1 = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "LOCALAPPDATA" in ps1 and "setup-agent" in ps1 and "Junction" in ps1
