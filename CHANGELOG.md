# Changelog

## 0.9.0
- Agents hear the person while idle: `devboard wait --board <id> --as <agent>` runs in the background
  and ends, waking the agent, when the person answers, writes to it, or moves, edits, ticks or attaches on
  its cards. `ask` prints the command.
- The hook on each prompt also reports what the person changed on the agent's cards. While a request is
  open, it reminds the agent to record on the card an answer the person gives in the chat.
- Two boards on the same folder (a project and its client) are both heard: the hook reads every board
  whose repo is the deepest match for the agent's folder (`store.resolve_all`), not only the first.

## 0.8.0
- The **For you** board takes drags. A drag to another column changes the source card's status. Dropping
  a card on Done delivers it: the source card is marked done and the card leaves For you. The Done column
  stays empty and only receives deliveries.
- Manual order on For you: a reorder is kept only there, in `<home>/_user.json`, so the source boards keep
  their own order. Every other write on For you is still made on the source card.
- Fixed card size: every card on a board has the same width (272 px columns; the board scrolls sideways
  when they don't fit) and the same height. Long text is cut and shows whole on hover.
- Answer an agent's request with files: pick them, paste a screenshot into the answer, or drop them on the
  box. They go to the card's attachments, and the answer lists their names.
- Shorter card history: the last 5 events, then "Show all (N)".

## 0.7.0
- Linked cards: a board can show cards of other boards next to its own, for example a delivery board.
  `devboard link-card --board <id> <board>/<card> ...` adds the links, and `unlink-card` removes them.
  board.json keeps only the references (`"links"`); nothing is copied.
- A linked card (`<board>:<card>`) shows its source card's status. Status, notes, checklist, messages,
  requests and files written through the delivery board, from the page or the CLI, go to the source card,
  and its history stays there. A manual reorder is not passed on, so the source board keeps its order.
- A source card that is gone shows in Blocked until it is unlinked, and `validate` reports it. `link-card`
  refuses missing cards, cards of the same board, and the `user` and rollout boards. `show` prints the source.

## 0.6.1
- No `bin/` folder: claude.ai-hosted marketplaces refuse plugins that ship one. The launcher moved to
  `scripts/devboard` (`install.sh` links it as before); the hooks run it with `bash`; in Claude Code the
  skill calls `devboard.py` by its full path.
- No `.cmd` in the repo (antivirus flags them): `install.ps1` writes the Windows shim itself.

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
