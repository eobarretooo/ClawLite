---
name: tmux
description: Remote-control tmux sessions for interactive CLIs by sending keystrokes and capturing pane output.
always: false
metadata: {"clawlite":{"emoji":"🧵","requires":{"bins":["tmux"]},"os":["linux","darwin"]}}
command: tmux
---

# tmux

Use tmux only when an interactive TTY is required. Prefer `exec` background mode for non-interactive long jobs.

## Socket convention

```bash
SOCKET_DIR="${CLAWLITE_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/clawlite-tmux-sockets}"
mkdir -p "$SOCKET_DIR"
SOCKET="$SOCKET_DIR/clawlite.sock"
SESSION=clawlite-shell

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -- 'PYTHON_BASIC_REPL=1 python3 -q' Enter
tmux -S "$SOCKET" capture-pane -p -J -t "$SESSION":0.0 -S -200
```

Keep one socket per workflow or agent. That makes discovery, retries, and cleanup deterministic.

## Finding sessions

Inspect one socket directly:
```bash
bash clawlite/skills/tmux/scripts/find-sessions.sh -S "$SOCKET"
```

Scan every socket under `CLAWLITE_TMUX_SOCKET_DIR`:
```bash
bash clawlite/skills/tmux/scripts/find-sessions.sh --all
```

The output is always `socket:session`, one row per line.

## Watching output

Wait for a prompt or completion marker:
```bash
bash clawlite/skills/tmux/scripts/wait-for-text.sh -S "$SOCKET" -t "$SESSION":0.0 -p '\$' -T 5
```

Use fixed-string mode when the marker should not be treated as regex:
```bash
bash clawlite/skills/tmux/scripts/wait-for-text.sh -S "$SOCKET" -t "$SESSION":0.0 -F 'BUILD SUCCESS' -T 30 -i 1 -l 400
```

## Orchestrating Coding Agents

Create a dedicated socket and session per agent:
```bash
SOCKET="$SOCKET_DIR/agent-1.sock"
SESSION=agent-1

tmux -S "$SOCKET" new -d -s "$SESSION" -n shell
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 -l -- "pytest -q"
tmux -S "$SOCKET" send-keys -t "$SESSION":0.0 Enter
bash clawlite/skills/tmux/scripts/wait-for-text.sh -S "$SOCKET" -t "$SESSION":0.0 -p 'passed|failed' -T 120 -l 500
```

Prefer `send-keys -l` for literal commands, then send `Enter` separately. Capture pane history before reusing or tearing down a session.

## Cleanup complete

Stop a single session:
```bash
tmux -S "$SOCKET" kill-session -t "$SESSION"
```

Stop the whole socket server when nothing else should remain:
```bash
tmux -S "$SOCKET" kill-server
```

Remove stale socket files only after `tmux -S "$SOCKET" list-sessions` or `has-session` confirms that no server is alive on that socket.
