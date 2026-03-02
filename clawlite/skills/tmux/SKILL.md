---
name: tmux
description: Manage long-running interactive terminal workflows with tmux.
always: false
metadata: {"clawlite":{"emoji":"🧵","requires":{"bins":["tmux"]},"os":["linux","darwin"]}}
command: tmux
---

# tmux

Use tmux when the task needs an interactive TTY that must stay alive across commands.

## Quick start
```bash
SOCKET_DIR="${TMPDIR:-/tmp}/clawlite-tmux"
mkdir -p "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/main.sock"
SESSION="clawlite"

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- 'python3 -q' Enter
```

Prefer `exec` tool for non-interactive tasks; use tmux only when interactivity is required.
