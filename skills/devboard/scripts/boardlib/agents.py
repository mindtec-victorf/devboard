"""Instructions for agents without the Claude Code plugin: Codex, Gemini CLI, Cursor, GitHub Copilot,
or anything that reads AGENTS.md. One short block, written idempotently between markers, so running
`devboard setup-agent` again replaces it instead of piling up copies.
"""
from pathlib import Path

START, END = "<!-- devboard:start -->", "<!-- devboard:end -->"
# agent -> (scope, path); "global" is relative to $HOME, "project" to --project (default: current folder)
TARGETS = {
    "codex": ("global", ".codex/AGENTS.md"),
    "gemini": ("global", ".gemini/GEMINI.md"),
    "cursor": ("project", ".cursor/rules/devboard.mdc"),
    "copilot": ("project", ".github/copilot-instructions.md"),
    "agents": ("project", "AGENTS.md"),
}
CURSOR_HEAD = "---\ndescription: devboard — the project board (inbox first, then summary; write only through the CLI)\nalwaysApply: true\n---\n\n"


def snippet(cli_path):
    return f"""{START}
## devboard — the project board

This machine tracks development work with devboard (https://github.com/mindtec-victorf/devboard).
In any folder that has a board:

1. At the start of a session run `devboard hint`. If it prints a board, run `devboard inbox` and answer
   every message with `devboard reply <card> <n> "what you did"` before anything else.
2. Resume with `devboard summary` and `devboard show <card>`. Never read or edit the board files.
3. Write only through the CLI: `set`, `note`, `check`, `move`, `attach`; many changes go in one `apply` file.
4. Keep each card's next action and blockers current. `devboard --help` lists every command.

If `devboard` is not on the PATH, use `python3 "{cli_path}"` instead.
{END}
"""


def target_path(agent, home, project):
    scope, rel = TARGETS[agent]
    return (Path(home) if scope == "global" else Path(project)) / rel


def merge(existing, block):
    """Replace the marked block when present, otherwise append it after one blank line."""
    if START in existing and END in existing:
        head, rest = existing.split(START, 1)
        tail = rest.split(END, 1)[1]
        return head + block.rstrip("\n") + tail
    return (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + block


def setup(agent, home, project, cli_path):
    path = target_path(agent, home, project)
    block = snippet(cli_path)
    if agent == "cursor":
        text = CURSOR_HEAD + block
    else:
        text = merge(path.read_text(encoding="utf-8") if path.exists() else "", block)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
