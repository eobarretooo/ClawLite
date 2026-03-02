---
name: tmux
description: Remote-control tmux sessions for interactive CLIs by sending keystrokes and capturing pane output.
always: false
metadata: {"clawlite":{"emoji":"🧵","requires":{"bins":["tmux"]},"os":["linux","darwin"]}}
command: tmux
---

# tmux

Use tmux only when an interactive TTY is required. Prefer `exec` background mode for non-interactive long jobs.

## Quick start

```bash
SOCKET_DIR="${CLAWLITE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/clawlite-tmux-sockets}"
mkdir -p "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/clawlite.sock"
SESSION=clawlite-shell

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- 'PYTHON_BASIC_REPL=1 python3 -q' Enter
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

## Useful commands

List sessions and panes:
```bash
tmux -S "$SOCKET" list-sessions
tmux -S "$SOCKET" list-panes -a
```

Send command safely:
```bash
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -l -- "pytest -q"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 Enter
```

Cleanup:
```bash
tmux -S "$SOCKET" kill-session -t "$SESSION"
tmux -S "$SOCKET" kill-server
```
