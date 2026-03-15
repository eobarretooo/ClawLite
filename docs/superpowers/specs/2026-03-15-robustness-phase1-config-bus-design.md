# Robustness Phase 1 — config + bus

**Goal:** Make `config` and `bus` production-hardened: hot-reload, runtime health check, typed bus envelopes, persistence journal, and backpressure.

**References:** `clawlite/config/`, `clawlite/bus/`, `ref/nanobot/`

---

## Architecture

### config

Current state: Pydantic v2 schema, `load_config()` reads file once at startup. No mechanism to pick up changes without restart.

Changes:
- `ConfigWatcher` — uses `watchfiles` (already available via FastAPI deps) to detect file changes, calls a registered callback with the new `AppConfig`. Debounced (500ms). Opt-in via `config.watch_interval_s > 0`.
- `config_health()` — validates critical fields at runtime (provider key present, memory path writable, gateway port available) and returns `{"ok": bool, "issues": list[str]}`. Exposed as `GET /health/config`.
- `ConfigAudit` — thin wrapper that stores last 5 configs in memory with timestamps. `config diff` CLI command shows what changed between reloads.

No changes to `schema.py` or `loader.py` internals.

### bus

Current state: in-memory only, `asyncio.Queue` based. Events lost on restart. No wildcard subscriptions.

Changes:
- `BusJournal` — optional SQLite persistence layer. When enabled, every `publish_inbound` and `publish_outbound` appends to `bus_journal.db`. On startup, replays unacked events (events without a `acked_at`). Opt-in via config `bus.journal_enabled`.
- Wildcard subscriptions: `subscribe("*")` receives all inbound events regardless of channel. Useful for audit logging and debug.
- `BusFullError` — raised (not awaited-forever) when main queue is at capacity and caller sets `nowait=True`. Default behavior unchanged (blocks).
- Typed envelope: add `envelope_version: int = 1` and `correlation_id: str` to both `InboundEvent` and `OutboundEvent`. Enables tracing across bus hops.

---

## Components

| File | Action |
|------|--------|
| `clawlite/config/watcher.py` | New — `ConfigWatcher` with `watchfiles` |
| `clawlite/config/health.py` | New — `config_health()` function |
| `clawlite/config/audit.py` | New — `ConfigAudit` ring buffer |
| `clawlite/bus/events.py` | Modify — add `envelope_version`, `correlation_id` |
| `clawlite/bus/journal.py` | New — `BusJournal` SQLite persistence |
| `clawlite/bus/queue.py` | Modify — integrate journal hooks, wildcard subs, `BusFullError` |
| `clawlite/config/schema.py` | Modify — add `BusConfig` sub-schema (`journal_enabled`, `journal_path`) |
| `gateway/server.py` | Modify — register `GET /health/config` endpoint |
| `tests/config/test_watcher.py` | New |
| `tests/config/test_health.py` | New |
| `tests/bus/test_journal.py` | New |

---

## Data Flow

```
File change → watchfiles detects → ConfigWatcher debounce(500ms)
           → load_config() → validate → callback(new_config)
           → gateway re-registers changed sub-configs

publish_inbound(event) → BusJournal.append(event, acked=False)
                       → asyncio.Queue.put()
next_inbound() → event → BusJournal.ack(event.id)
```

---

## Error Handling

- Watcher file parse error → log warning, keep old config, emit bus event `config.reload_failed`
- Journal write failure → log error, continue without persistence (degraded mode, not crash)
- `BusFullError` → caller handles or drops; dead-letter queue unchanged

---

## Testing Strategy

- `test_watcher.py`: write config to tmpfile, mutate it, assert callback fires with new config; assert bad JSON keeps old config
- `test_health.py`: mock provider with no key → health returns issue; mock writable path → health ok
- `test_journal.py`: publish events, simulate restart (new `MessageQueue` with same journal), assert events replayed; assert ack removes from replay list

---

## Success Criteria

- [ ] Config hot-reload fires within 1s of file change
- [ ] `GET /health/config` returns structured health in <50ms
- [ ] Bus journal survives process restart and replays unacked events
- [ ] Wildcard subscription receives all inbound events
- [ ] All new tests pass, existing 1186 tests unchanged
