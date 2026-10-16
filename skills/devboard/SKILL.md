---
name: devboard
description: Use when a project, a multi-session task or a multi-repo rollout needs a living progress board instead of a growing PROGRESS.md, and whenever several agents (or an agent and a person) share the work — "set up a board for this project", "update the board", "mark stage N done", "what is blocked", "check my messages on the board", "who is working on what", "take card N", "attach this PRD to the card", "open the board". One local Kanban board per project (cards + checklist + append-only history + attachments + messages + agent claims) that agents update with ONE deterministic command and people drive from a localhost page. Data lives in ~/.devboard, never in a repo. Also shows rollout ledgers (STATUS.json) read-only.
---

# devboard — the shared board for people and agents

One board per project, one card per stage, unit or deliverable. Every write — yours, another
agent's, a person's on the page — goes through the same door: lock, validate, compare, atomic write,
one event with who and when. That is what lets several agents and a person work on the same project
without stepping on each other and without anyone re-reading everything to catch up.

The CLI is `scripts/devboard.py` next to this file (or `devboard` when installed on the PATH). Below,
`devboard` means either.

## Who you are

Pick one stable name for the whole session, `<tool>-<role>`: `claude-main`, `codex-tests`,
`claude-review`. Export it once and every write and claim carries it:

```bash
export DEVBOARD_AGENT=claude-main
```

Without it, claims refuse to run and your writes are signed `agent`, which tells nobody anything. The first
word also picks the icon people see next to your claims (`claude`, `gemini`, `copilot`, `cursor`, `codex`).

## The round — do this every time you pick up work

1. **Orient.** The SessionStart line (or `devboard hint`) tells you if this folder has a board, how many
   messages wait for you and how many cards other agents hold. No board → stop here, or create one
   if the person asked (`devboard init`).
2. **Inbox first.** `devboard inbox`. Handle every message before your own plan: do what it asks, or
   explain why not, then `devboard reply <card> <n> "what you did"`. A reply closes the message; an
   unanswered message is the one thing a person checks first.
3. **See the board.** `devboard summary` (one line per card) and `devboard who` (active claims).
   Read `devboard show <card>` only for the card you will work on. Never open the board files.
4. **Claim before you work.** Choose a card nobody holds, highest priority first, then:
   `devboard claim <card> --note "what you are about to do"`. Default length 2 h (`--ttl 30m|4h|1d`).
   Claim again to renew while you keep working.
5. **Work and record as you go** — one command per fact, never a summary at the end:
   - a milestone: `devboard note <card> "migration 000190 merged"`
   - a checklist item done: `devboard check <card> <n>`
   - evidence: `devboard attach <card> report.pdf` (`--link` for a file that keeps changing in a repo)
   - state: `devboard set <card> --next "run the import in staging" --situation "code reviewed"`
6. **Blocked?** Say why and on whom, concretely: `devboard set <card> --wait "DBA: index on Orders"`
   (or `--block "..."` for an internal blocker). Then release with a note so nobody waits on you.
7. **Hand off when you stop.** `devboard release <card> --note "done: X; next: Y; watch out for Z"`.
   The next agent reads that note in `who`/`show` and starts where you stopped.

## Working with other agents

- **Never work on a card another agent holds.** `who` shows the owner, the note and the deadline.
  Pick another card, or leave a `note` on theirs if you found something they need.
- **Expired claims are free.** A claim that was not renewed stops counting, so a crashed agent never
  locks a card forever. Renew yours if you are still on it.
- **`--force` only when a person tells you to** take a card over. The takeover is logged
  (`forced_from`), and the previous owner sees it in the history.
- **Writes on someone else's card go through with a warning.** Claims coordinate; they never block a
  person or a fix. If you see the warning, you are probably on the wrong card.
- **Split work so claims make sense:** one card per piece that one agent can finish. A card two agents
  need at once should be two cards.

## The cost law

- **Write only through the CLI.** One command per update. Never edit `cards/*.json` by hand — `audit`
  replays the history and flags any file that does not match it.
- **Many changes → one `apply` file**, validated before any write (one bad op → zero writes).
- **Long text** (goal, context, decisions) lives in `cards/<id>.md`; editing it with your file tools is
  fine. Tick checklist boxes with `check` so the event is logged.
- **Don't paste, attach.** PRDs, screenshots, PDFs and videos go on the card with `attach`.
- **The column:** a person's drag (or `set --status`) pins it; `--status auto` unpins it. Unpinned,
  it is derived: blocked/waiting → blocked · 100% → done · 90–99% → final · started or >0% → doing ·
  else todo. With a checklist, progress = ticked/total and `--progress` is refused. A new block from
  you unpins a dragged card so it shows as blocked.

## Writing cards people can trust

- **Title:** the deliverable, not the activity ("Fraud checks", not "Work on fraud").
- **Next:** one imperative action someone could start now ("wire the score API into checkout").
- **Situation:** one line of state ("hold queue in staging, threshold not tuned").
- **Checklist:** items a reviewer can verify; the progress comes from them.
- **Blocked/waiting:** who and what, never "blocked".

## A full session

```bash
export DEVBOARD_AGENT=codex-tests
devboard hint                       # Board checkout: 7 cards (3 in progress, 1 blocked) · 1 messages for the agent · 1 claimed by agents
devboard inbox                      # 3#1 human: can you check the hold rate on staging?
devboard who                        #    3 claude-main until 18:30 — tuning the threshold
devboard reply 3 1 "hold rate on staging: 4.2% over 2,180 orders (report attached to card 3)"
devboard attach 3 hold-rate.csv
devboard summary
devboard claim 6 --note "load test at 2x Black Friday"
devboard check 6 1
devboard note 6 "baseline: p95 410 ms at 300 rps"
devboard set 6 --next "rerun with the new cache" --situation "baseline done"
devboard release 6 --note "baseline in the card; next: cache on, same script (scripts/load.js)"
```

## Reference

| Command | Use |
|---|---|
| `init <id> --title T --repo <folder>` | new board (`--template stages`) |
| `add <card> --title T [--priority N --tag T --estimate T --due D --next T --md-file F]` | new card |
| `set <card> [--progress N --start --block T/--unblock --wait T/--unwait --next T --situation T --status S] [--note T]` | change fields |
| `note` · `check <card> <n> [--undo]` · `move <card> <column>` | milestone · tick item n · pin the column |
| `claim <card> [--as NAME --ttl 2h --note T --force]` · `release <card> [--note T]` · `who` | agent claims |
| `inbox` · `reply <card> <n> "text"` | messages from people · answer and close one |
| `attach <card> <file> [--link]` · `files <card>` · `detach <card> <name>` | attachments |
| `summary` · `show <card>` · `history` · `pending` · `boards [--all]` | read (`--json` for scripts) |
| `apply <ops.json> [--dry-run]` · `validate` · `audit` | batch · health · history vs files |
| `archive` · `unarchive` · `link-rollout <STATUS.json>` | board housekeeping · rollout ledgers |
| `serve [--port 8765]` · `hint` · `setup-agent <agent>` | the page · session-start line · instructions for other agents |

Exit codes: 0 ok · 1 findings (`validate`/`audit`) · 2 usage error · 3 conflict (stale write or a card
claimed by someone else).

Batch file for `apply`:

```json
{"board": "checkout", "ops": [
  {"op": "add", "card": "3", "title": "Fraud checks", "fields": {"priority": 1, "next": "wire the score API"}},
  {"op": "set", "card": "3", "changes": {"started": true}, "note": "phase 1 merged"},
  {"op": "check", "card": "3", "item": 2},
  {"op": "note", "card": "3", "text": "threshold agreed with the risk team"}
]}
```

Data: `$DEVBOARD_HOME` (default `~/.devboard`) — `<board>/board.json`, `cards/<id>.{json,md,jsonl}`,
`files/<id>/`, `_archive.jsonl`, `rollouts/*/STATUS.json`. The page: `devboard serve` →
`http://127.0.0.1:8765/` (people drag cards, tick the checklist, attach files, leave messages, see who
holds what). UI language: `DEVBOARD_LANG` (translations in `web/i18n/`).

## Starting from an existing progress file

Read the file once, write one `apply` file with an `add` per stage (title, next action,
blocked/waiting, estimate, due) and run it. From then on, update the board and stop editing the file.
