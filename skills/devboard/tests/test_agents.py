import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CLI = ROOT / "skills" / "devboard" / "scripts" / "devboard.py"


def run(*args, home, cwd=None):
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    r = subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, encoding="utf-8", env=env, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


@pytest.mark.parametrize("agent,where", [
    ("codex", ".codex/AGENTS.md"), ("gemini", ".gemini/GEMINI.md"),
])
def test_setup_agent_global_files_are_idempotent(tmp_path, agent, where):
    code, out, _ = run("setup-agent", agent, home=tmp_path)
    assert code == 0 and where in out
    f = tmp_path / where
    text = f.read_text(encoding="utf-8")
    assert "<!-- devboard:start -->" in text and "devboard inbox" in text and "devboard hint" in text
    f.write_text("# my rules\n\n" + text + "\nkeep me\n", encoding="utf-8")
    run("setup-agent", agent, home=tmp_path)
    again = f.read_text(encoding="utf-8")
    assert again.count("<!-- devboard:start -->") == 1 and again.startswith("# my rules") and "keep me" in again


@pytest.mark.parametrize("agent,where", [
    ("cursor", ".cursor/rules/devboard.mdc"), ("copilot", ".github/copilot-instructions.md"), ("agents", "AGENTS.md"),
])
def test_setup_agent_project_files(tmp_path, agent, where):
    proj = tmp_path / "proj"
    proj.mkdir()
    code, _, _ = run("setup-agent", agent, "--project", str(proj), home=tmp_path)
    assert code == 0 and "devboard summary" in (proj / where).read_text(encoding="utf-8")


def test_cursor_rule_has_frontmatter(tmp_path):
    run("setup-agent", "cursor", "--project", str(tmp_path), home=tmp_path)
    assert (tmp_path / ".cursor/rules/devboard.mdc").read_text(encoding="utf-8").startswith("---\ndescription:")


def test_print_writes_nothing(tmp_path):
    code, out, _ = run("setup-agent", "codex", "--print", home=tmp_path)
    assert code == 0 and "devboard inbox" in out and not (tmp_path / ".codex").exists()


def test_unknown_agent_is_usage_error(tmp_path):
    assert run("setup-agent", "nope", home=tmp_path)[0] == 2


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX installer")
def test_install_script_from_local_checkout(tmp_path):
    (tmp_path / ".codex").mkdir()
    env = dict(os.environ, HOME=str(tmp_path), DEVBOARD_SRC=str(ROOT))
    r = subprocess.run(["sh", str(ROOT / "install.sh")], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    exe = tmp_path / ".local" / "bin" / "devboard"
    assert exe.exists()
    out = subprocess.run([str(exe), "--help"], capture_output=True, text=True, env=env)
    assert out.returncode == 0 and "devboard.py" in out.stdout
    assert (tmp_path / ".codex" / "skills" / "devboard" / "SKILL.md").exists()
    assert "devboard inbox" in (tmp_path / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
