# devboard

**One local board for all your development work — that your AI agent keeps up to date, and you drive from a page.**

devboard is a [Claude Code](https://claude.com/claude-code) plugin. Each project gets a Kanban board:
cards with a checklist, an append-only history, attachments and messages. Your agent updates it with
one deterministic command per change. You open `localhost`, drag cards, tick boxes, drop in a PRD or a
video, and leave a message. The agent reads your messages at the start of its next round and answers
them on the card.

You stop re-explaining where things are. Any session — today, after a `/clear`, next week, in another
repo — resumes from the board in a few hundred tokens.

![The board](docs/screenshots/board.png)

## Why

Long projects usually track progress in a Markdown file that only grows. The agent re-reads all of it
to resume and edits free text to update it; you can't see the state at a glance or hand work off
cleanly. devboard replaces that file with structured, cheap state:

| | Progress file | devboard |
|---|---|---|
| Resume | read the whole file (thousands of tokens) | `devboard.py summary` — one line per card |
| Update | edit free text | one command, validated, logged |
| See the state | scroll | a board, a home screen with all boards |
| Talk to the agent | in the chat, now | a message on the card, answered on its next round |
| Prove what happened | git blame on prose | every change is an event with author, time and diff; `audit` replays it |

## Features

- **Kanban that cannot lie.** The column is derived from the card (blocked → Blocked, 100% → Done,
  90–99% → Final touches…) unless a person pins it by dragging. A checklist drives the progress.
- **Async messages.** People leave messages on cards; the agent runs `devboard.py inbox`, acts and
  `reply`s. The SessionStart hook tells the agent how many are waiting as soon as the session opens.
- **Attachments.** PRDs, screenshots, PDFs, videos — copied into the board or linked in place
  (`--link`), with size and SHA-1 in the history. Images and videos preview inline.
- **One door for every write.** CLI and page go through the same store: lock → validate → etag check
  → atomic write → one event. Concurrent edits get a 409 instead of a silent overwrite.
- **Deterministic and auditable.** Canonical JSON (same content, same bytes). `apply` runs a batch of
  operations validated up front — one bad op, zero writes; the same file builds the same board.
  `audit` replays the history and flags any edit that bypassed the CLI.
- **Home screen.** Every board grouped by its origin repository, newest activity first, archive and
  unarchive. Rollout ledgers (`STATUS.json`) show up read-only.
- **Zero dependencies.** Python 3.10+ standard library and one HTML/JS/CSS page. No build, no CDN,
  no database. English and Brazilian Portuguese UI.

| Card detail | Home |
|---|---|
| ![Card](docs/screenshots/card.png) | ![Home](docs/screenshots/home.png) |

## Install

In Claude Code:

```
/plugin marketplace add mindtec-victorf/devboard
/plugin install devboard@devboard
```

Restart the session. The skill is `devboard:devboard`; the SessionStart hook is registered by the
plugin. The CLI runs from the plugin folder: `skills/devboard/scripts/devboard.py`.

Requirements: Python 3.10+ as `python3` on the `PATH` (the hook calls `python3`).

## Quickstart

Ask your agent: *"set up a devboard for this project"*. Or by hand:

```bash
DB="python3 <plugin dir>/skills/devboard/scripts/devboard.py"
$DB init checkout --title "Acme Checkout · v2 launch" --repo .
$DB add 3 --title "Fraud checks" --priority 1 --next "wire the risk score API"
$DB set 3 --start --note "phase 1 merged"
$DB serve            # http://127.0.0.1:8765/
```

From then on, inside that repo, the agent finds the board from the current folder — no `--board`
needed — and the SessionStart hook reminds it on every session.

## How the agent works with it

The skill teaches a short cost law:

1. Start every round with `devboard.py inbox`; answer each message with `devboard.py reply`.
2. Resume with `summary`, then `show <card>` for the card at hand. Never read the board files.
3. One command per update (`set`, `note`, `check`, `move`, `attach`); many changes → one `apply` file.
4. Keep the next action, blockers and estimates current — that is what makes a card delegable.

## CLI

| Command | What it does |
|---|---|
| `init <id> --title T --repo <folder>` | create a board (`--template stages`, or `etapas` in Portuguese) |
| `add` · `set` · `note` · `check` · `move` | write cards |
| `inbox` · `reply <card> <n> "text"` | messages from people · answer and close one |
| `attach <card> <file> [--link]` · `files` · `detach` | attachments |
| `summary` · `show` · `history` · `pending` · `boards [--all]` | read (`--json` for scripts) |
| `apply <ops.json> [--dry-run]` | batch of operations, validated before any write |
| `validate` · `audit` | health check · replay history against the files |
| `archive` · `unarchive` | hide a finished board (data stays) |
| `link-rollout <STATUS.json>` | show a rollout ledger from anywhere, read-only |
| `serve [--port 8765]` | the page |

Every command has `--help`. Exit codes: 0 ok · 1 findings (`validate`/`audit`) · 2 usage error · 3 conflict.

## Data

Everything lives in `~/.devboard/`, never inside your repositories:

```
~/.devboard/<board>/board.json         title, linked repos, column labels
~/.devboard/<board>/cards/<id>.json    short fields
~/.devboard/<board>/cards/<id>.md      long text: goal, context, checklist, decisions
~/.devboard/<board>/cards/<id>.jsonl   history, append-only
~/.devboard/<board>/files/<id>/        copied attachments
~/.devboard/_archive.jsonl             archive log
~/.devboard/rollouts/*/STATUS.json     rollout ledgers (read-only)
```

Plain files: back them up, sync them, or put `~/.devboard` in a private repo of its own.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DEVBOARD_HOME` | `~/.devboard` | where boards live |
| `DEVBOARD_LANG` | `en` | page language (`en`, `pt-BR`); `pt-BR` also makes `etapas` the default template |
| `DEVBOARD_TEMPLATE` | `stages` | board template for `init` |
| `DEVBOARD_ROLLOUTS` | `<home>/rollouts` | folders scanned for `*/STATUS.json` (`os.pathsep`-separated) |
| `BOARD_ACTOR` | `agent` | the `by` recorded for CLI writes |

In Claude Code you can set them in `settings.json` under `"env"`.

## Security model

The page is a local developer tool:

- the server binds to `127.0.0.1` only and refuses any other `Host` header (DNS rebinding);
- every write needs an `X-Board: 1` header, which a cross-site form cannot send (CSRF);
- attachments are served with `Content-Security-Policy: sandbox` and `nosniff`, so an attached HTML
  file cannot script the board (PDFs are exempt so the browser viewer works);
- attachment names are sanitized (path, control and invisible characters, Windows device names).

There is no authentication against other users on the same machine; don't run it on a shared host.

## Rollout ledgers

For work applied across many units (repositories, tickets), a ledger `STATUS.json` with
`{"meta": {"phases": [...]}, "units": {id: {"phase", "status", "blockers", "result"}}}` shows up as a
read-only board, one card per unit and one column per phase. Portuguese keys (`fases`, `unidades`,
`fase`, `bloqueios`, `resultado`) are read too.

## Development

```bash
cd skills/devboard
python3 -m pytest -q          # browser tests run when Playwright + Chromium are installed
python3 ../../docs/make-screenshots.py   # rebuild the README screenshots from docs/demo/
```

## Credits

The concept and the visual design come from **Rogério Dornelas**: a development-only progress page that
reads a JSON the AI keeps updated, which he shared with the team. devboard turns that idea into a
reusable plugin. Nunito Sans © The Nunito Sans Project Authors (SIL Open Font License 1.1).

## License

MIT — see [LICENSE](LICENSE).
