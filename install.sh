#!/bin/sh
# devboard installer for any agent: puts the `devboard` CLI on the PATH, links the skill into the
# Agent Skills folders of the agents found on this machine, and writes their instruction blocks.
#   curl -fsSL https://raw.githubusercontent.com/mindtec-victorf/devboard/main/install.sh | sh
# Claude Code users: install the plugin instead (it also brings the SessionStart hook):
#   /plugin marketplace add mindtec-victorf/devboard  then  /plugin install devboard@devboard
set -eu
REPO="${DEVBOARD_REPO:-https://github.com/mindtec-victorf/devboard}"
APP="${DEVBOARD_APP:-$HOME/.local/share/devboard}"
BIN="${DEVBOARD_BIN:-$HOME/.local/bin}"

command -v python3 >/dev/null 2>&1 || { echo "devboard needs python3 (3.10+) on the PATH" >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "devboard needs Python 3.10+" >&2; exit 1; }

if [ -n "${DEVBOARD_SRC:-}" ]; then          # a local checkout (development, tests)
  mkdir -p "$(dirname "$APP")"; rm -rf "$APP"; ln -s "$DEVBOARD_SRC" "$APP"
elif [ -d "$APP/.git" ]; then
  git -C "$APP" pull --ff-only -q
else
  command -v git >/dev/null 2>&1 || { echo "devboard needs git to download" >&2; exit 1; }
  mkdir -p "$(dirname "$APP")"; git clone -q --depth 1 "$REPO" "$APP"
fi

mkdir -p "$BIN"
chmod +x "$APP/bin/devboard" 2>/dev/null || true
ln -sf "$APP/bin/devboard" "$BIN/devboard"
echo "devboard: CLI at $BIN/devboard"

for agent_home in "$HOME/.codex" "$HOME/.copilot"; do   # agents that read Agent Skills (SKILL.md) folders
  [ -d "$agent_home" ] || continue
  mkdir -p "$agent_home/skills"
  ln -sfn "$APP/skills/devboard" "$agent_home/skills/devboard"
  echo "devboard: skill linked into $agent_home/skills/devboard"
done
[ -d "$HOME/.codex" ] && "$BIN/devboard" setup-agent codex
[ -d "$HOME/.gemini" ] && "$BIN/devboard" setup-agent gemini

case ":$PATH:" in *":$BIN:"*) ;; *) echo "devboard: add $BIN to your PATH" ;; esac
echo "devboard: done. Per project: 'devboard setup-agent cursor|copilot|agents', then 'devboard init <id> --title ... --repo .'"
