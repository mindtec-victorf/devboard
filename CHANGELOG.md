# Changelog

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
