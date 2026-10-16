---
name: devboard
description: Use when a project, a multi-session task or a multi-repo rollout needs a living progress board instead of a growing PROGRESS.md — "set up a board for this project", "update the board", "mark stage N done", "what is blocked", "check my messages on the board", "attach this PRD to the card", "open the board". One local Kanban board per project (cards + checklist + append-only history + attachments + messages) that the agent updates with ONE deterministic command and the human drives from a localhost page (drag cards, tick the checklist, attach files, leave messages the agent reads on its next round). Data lives in ~/.devboard (never in a repo). Also shows rollout ledgers (STATUS.json) read-only.
---

# devboard — one board for all your development work

One board per project. One card per stage, unit or deliverable. The agent and the page write
through the same door (`scripts/boardlib/store.py`), so every change is validated, atomic and
logged with who did it and when. The CLI lives next to this file: `scripts/devboard.py`.

## The cost law (do not violate)

- **Start every round with `devboard.py inbox`.** People leave messages on cards for you. Read them,
  act, and answer each one with `devboard.py reply <card> <n> "what you did"` (it closes it). The
  SessionStart hook tells you how many are waiting when the session opens inside a board's repo.
- **Write only through `devboard.py`.** One command per update. Never Read a card file in order to
  update it, and never edit `cards/*.json` by hand (`audit` catches it).
- **Resume cheaply:** `devboard.py summary` (one line per card), then `devboard.py show <card>` for
  the one you work on. Never load the whole board folder.
- **Many changes → one `apply`.** Write an ops file and run `devboard.py apply ops.json`. All ops are
  validated before any write; one bad op aborts with zero writes.
- **Long text** (goal, context, decisions) lives in `cards/<id>.md`; editing it with Edit is fine.
  Tick checklist boxes with `devboard.py check` (it logs the event; a direct edit does not).
- **Attach, don't paste.** PRDs, screenshots, PDFs and videos go on the card with
  `devboard.py attach` (`--link` for a file that keeps changing in a repo, or a big video).
- **The column:** a drag on the page (or `set --status`) pins it; `--status auto` unpins it. Unpinned,
  it is derived: blocked/waiting → blocked · 100% → done · 90-99% → final · started or >0% → doing ·
  else todo. With a checklist, progress = ticked/total and `--progress` is refused. A new block from
  you (`--block`/`--wait`) unpins a dragged card so it shows as blocked.

## Where things are

```
~/.devboard/                    ($DEVBOARD_HOME)
  <board>/board.json            id, title, linked repos, column labels, template
  <board>/card.md.tmpl          copied from the template at init (stable if the skill changes)
  <board>/cards/<id>.json       short fields
  <board>/cards/<id>.md         long text
  <board>/cards/<id>.jsonl      history, append-only: set, note, check, message, reply, attach, detach
  <board>/files/<id>/           copied attachments (linked ones stay where they are)
  _archive.jsonl                archive/unarchive log
  rollouts/<name>/STATUS.json   rollout ledgers shown read-only ($DEVBOARD_ROLLOUTS)
```

The board is found from `--board`, or from the current folder (the deepest `repos` entry that
contains it). Archived boards are skipped.

## Commands (`python3 scripts/devboard.py <cmd> --help` for flags)

| Command | Use |
|---|---|
| `init <id> --title T --repo <folder>` | new board (`--template stages`; `etapas` in Portuguese) |
| `add <card> --title T [--priority N --tag T --estimate T --due D --next T --md-file F]` | new card |
| `set <card> [--progress N --start --block T/--unblock --wait T/--unwait --next T --status S ...] [--note T]` | change fields |
| `note <card> "text"` · `check <card> <n> [--undo]` | milestone · tick checklist item n (1-based) |
| `move <card> <todo/blocked/doing/final/done>` | pin the column (leaving blocked clears the reason) |
| `inbox` · `reply <card> <n> "text"` | messages from people · answer and close one |
| `attach <card> <file> [--link]` · `files <card>` · `detach <card> <name>` | attachments |
| `summary` · `show <card>` · `history` · `pending` · `boards [--all]` | read (`--json` for scripts) |
| `apply <ops.json> [--dry-run]` | batch, validated first |
| `validate` · `audit` | health: files/schema · history vs files (exit 1 on findings) |
| `archive <board>` · `unarchive <board>` | hide a finished board (data stays) |
| `link-rollout <path/STATUS.json>` | show a rollout ledger from anywhere |
| `serve [--port 8765]` | the page |

Exit codes: 0 ok · 1 findings · 2 usage error · 3 conflict.

## Batch file (`apply`)

```json
{"board": "checkout", "ops": [
  {"op": "add", "card": "3", "title": "Fraud checks", "fields": {"priority": 1, "next": "wire the score API"}},
  {"op": "set", "card": "3", "changes": {"started": true}, "note": "phase 1 merged"},
  {"op": "check", "card": "3", "item": 2},
  {"op": "note", "card": "3", "text": "score threshold agreed with risk team"}
]}
```

Every event of the batch carries `src: "apply:<sha1[:8]>"`. The same file on an empty board builds
the same board: keep the file to replay or audit a setup.

## The page

`devboard.py serve` → `http://127.0.0.1:8765/`. The home screen lists every board grouped by its
origin repo (rollouts apart), newest activity first, with archive/unarchive. Inside a board: Board,
History, Pending, Messages. People do only four things there: drag cards between columns, tick the
checklist, attach files and leave messages for you. Everything else — next action, blocked reason,
estimate, status line — is yours to keep current. A stale drag gets 409 and the card snaps back, so
your change is never overwritten. Attachments are served sandboxed (an attached HTML cannot script
the board). UI language: `DEVBOARD_LANG` (`en` default, `pt-BR`).

## Starting a board from an existing progress file

Read the file once, write one `apply` file with an `add` per stage (title, next action,
blocked/waiting, estimate, due) and run it. From then on, update the board and stop editing the file.
