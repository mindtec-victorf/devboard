# Changelog

## 0.6.0
- Who a card is for: `--for user|agent|agent:<name>|agent@<repo>|agent:<name>@<repo>` on `add` and `set`
  (`--para` is an alias, `--unassign` clears it), shown on the card and changeable from the page.
- Agents ask the person: `devboard ask <card> "text"` assigns the card to the user until they answer on the page;
  the answer hands the card back to the agent that asked. `devboard requests` (`--all` for every board) lists them;
  `apply` takes an `ask` op.
- The automatic **For you** board (`user`, read-only, built on each read): every open card from every active board
  that is for the user or waits for their answer. It comes first on the home screen while it has cards. The board
  id `user` is now reserved.
- Desktop notice when an agent hands something to the person (Windows toast, macOS Notification Center,
  `notify-send`), or any command in `DEVBOARD_NOTIFY_CMD`; `DEVBOARD_NOTIFY=0` turns it off.
- The Claude Code hook also runs on every prompt and tells the agent only what is new: messages from people,
  cards assigned to it, and the person's answers to its requests.
- Manual order: drag a card up or down inside its column (`rank`; `move --rank` in the CLI). A reorder inside the
  card's own column does not pin it there.
- Columns scroll on their own, so a long column no longer stretches the page.

## 0.5.0
- Agent icons on claims and in the history, picked from the first word of the agent's name (Claude, Gemini,
  GitHub Copilot, Cursor; Codex and unknown names get a neutral icon). Built by `docs/make-agent-icons.py`
  from Simple Icons (CC0) at a pinned version.

## 0.4.1
- French, German, Italian, Japanese and Simplified Chinese; default column names follow the page language.
- A test checks that every translation keeps the placeholders and the markup of the English text.
- Font stack falls back to the system's Japanese and Chinese fonts.

## 0.4.0
- Logo and favicon (original pixel mascot holding a kanban card), light and dark.
- Page polish: tab title with the board and waiting messages, keyboard shortcuts (`/`, `Esc`, `Ctrl/Cmd+Enter`),
  drop hint in empty columns, a flash on the moved card, relative times, focus rings, reduced-motion support.
- Languages are discovered from `web/i18n/*.json`; Spanish added.

## 0.3.0
- Agents claim cards: `claim` (renew by claiming again, expires after `--ttl`, `--force` logged), `release --note`
  for handoffs, `who`; shown on the page, in `summary` and in the session-start line. Writes on a card held by
  another agent warn instead of failing.
- Windows: `msvcrt` lock, `devboard.cmd`, `install.ps1` (`irm … | iex`); the hook finds `python3`, `python` or `py`.
  CI on Linux, macOS and Windows.
- The skill ships a full working protocol (identity, inbox first, claim, record, hand off); `setup-agent` blocks carry it.

## 0.2.0
- Works with other agents: `install.sh` (CLI on the PATH, skill linked for Codex and Copilot, blocks for
  Codex and Gemini) and `devboard setup-agent <codex|gemini|cursor|copilot|agents>`.
- `devboard hint` defaults to the current folder.

## 0.1.0
- First public release: board, home screen, async messages, attachments, rollout ledgers, SessionStart hook,
  translatable UI.
