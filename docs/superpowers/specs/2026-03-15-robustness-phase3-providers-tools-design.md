# Robustness Phase 3 — providers + tools

**Goal:** Unified timeout middleware for tools, per-model telemetry for providers, streaming error recovery, tool health checks, and standardized error classification.

**References:** `clawlite/providers/`, `clawlite/tools/`, `ref/nanobot/`

---

## Architecture

### providers

#### 3.1 Per-model Usage Telemetry

New `ProviderTelemetry` dataclass: `{model, requests, tokens_in, tokens_out, errors, latency_p50_ms, latency_p95_ms, last_used_at}`. Stored in-process (ring buffer, last 1000 calls per model). Exposed via `GET /metrics/providers`.

`LiteLLMProvider` records start/end time and token counts from LiteLLM response metadata. `FailoverProvider` records which candidate was actually used.

#### 3.2 Streaming Error Recovery

Current: if stream fails mid-way (e.g., network drop at chunk 15 of 20), exception propagates raw to caller.

Change: `LiteLLMProvider.stream()` wraps the generator in a try/except. On error after >0 chunks:
- If `accumulated` text is non-empty → yield final `ProviderChunk(text="", accumulated=accumulated, done=True, degraded=True)`
- Caller gets a partial-but-complete response instead of an exception
- `degraded=True` flag lets callers decide to retry or accept

`ProviderChunk` gains `degraded: bool = False` field.

#### 3.3 Provider Warmup Probe

`ProviderRegistry.warmup(provider_name)` sends a minimal no-op request ("say ok") to verify credentials and connectivity. Called optionally at startup. Result stored as `warmup_ok: bool` in provider status. `GET /health/providers` returns warmup status per provider.

---

### tools

#### 3.4 Centralized Timeout Middleware

Current: each tool handles timeout differently (exec tool reads `arguments["timeout"]`, MCP tool reads `timeout_s`, etc.).

Change: `ToolRegistry.execute()` wraps `tool.run()` in `asyncio.wait_for(tool.run(...), timeout=resolved_timeout)`. Timeout resolved from:
1. `arguments.get("timeout")` or `arguments.get("timeout_s")` — tool-level override
2. `tool.default_timeout_s` — tool class default
3. `config.tools.default_timeout_s` — global default (20s)

On `asyncio.TimeoutError` → raises `ToolTimeoutError(tool_name, timeout_s)` with standard error string `"tool_timeout:{name}:{timeout_s}s"`.

Each tool class removes its own timeout handling; it just does the work.

#### 3.5 Tool Result Cache

New `ToolResultCache`: LRU cache (max 256 entries, 5min TTL). Tools opt-in by setting `cacheable = True` class attribute. Cache key: `hash(tool_name + json(arguments))`.

Cacheable tools: `web_fetch`, `pdf_read`, `weather` (when/if added). Non-cacheable by default.

`ToolRegistry.execute()` checks cache before calling `tool.run()`. Cache stored in-process only (no persistence).

#### 3.6 Tool Health Check Protocol

New `Tool.health_check() -> ToolHealthResult` optional method. `ToolHealthResult`: `{ok: bool, latency_ms: float, detail: str}`.

`GET /health/tools` calls `health_check()` on all registered tools that implement it. Default: tools without `health_check` return `{ok: true, detail: "no_check"}`.

Implementations:
- `BrowserTool.health_check()` → launch chromium, navigate to `about:blank`, close. ok=True if <5s.
- `MCPTool.health_check()` → ping each configured server with a `tools/list` call.
- `ExecTool.health_check()` → run `echo ok`, assert exit=0.
- `PdfReadTool.health_check()` → call `pypdf.PdfReader` on a minimal in-memory 1-page PDF bytes object (generated via `pypdf.PdfWriter()`). ok=True if no exception; verifies pypdf import and basic functionality without touching disk.

#### 3.7 Standardized ToolError

New `ToolError(RuntimeError)` with fields: `tool_name: str`, `code: str`, `recoverable: bool`, `retry_hint: str`. Error codes: `timeout`, `blocked`, `invalid_args`, `not_found`, `execution_failed`.

`ToolRegistry.execute()` catches bare exceptions and wraps in `ToolError` before re-raising.

---

## Components

| File | Action |
|------|--------|
| `clawlite/providers/telemetry.py` | New — `ProviderTelemetry`, ring buffer |
| `clawlite/providers/litellm.py` | Modify — record telemetry, streaming degraded recovery |
| `clawlite/providers/failover.py` | Modify — record which candidate used |
| `clawlite/providers/base.py` | Modify — `ProviderChunk.degraded` field, `warmup()` method |
| `clawlite/tools/base.py` | Modify — `Tool.cacheable`, `Tool.health_check()`, `ToolError`, `ToolHealthResult` |
| `clawlite/tools/registry.py` | Modify — timeout middleware, cache, `ToolError` wrapping |
| `clawlite/tools/exec.py` | Modify — remove own timeout, add `health_check()` |
| `clawlite/tools/mcp.py` | Modify — remove own timeout, add `health_check()` |
| `clawlite/tools/browser.py` | Modify — add `health_check()` |
| `clawlite/tools/web.py` | Modify — add `cacheable = True` |
| `clawlite/tools/pdf.py` | Modify — add `cacheable = True`, `health_check()` |
| `gateway/server.py` | Modify — `GET /health/tools`, `GET /health/providers`, `GET /metrics/providers` |
| `tests/providers/test_telemetry.py` | New |
| `tests/providers/test_streaming_recovery.py` | New |
| `tests/tools/test_timeout_middleware.py` | New |
| `tests/tools/test_result_cache.py` | New |
| `tests/tools/test_health_check.py` | New |

---

## Error Handling

- Warmup probe failure → log warning, mark `warmup_ok=False`, do not block startup
- Streaming recovery partial response → emit log `provider.stream_degraded`, return partial with `degraded=True`
- Tool health check exception → `{ok: false, detail: str(exc)}`
- Cache serialization error → log, skip cache, call tool normally

---

## Testing Strategy

- `test_telemetry.py`: make N provider calls, assert telemetry counts, assert p50/p95 calculated
- `test_streaming_recovery.py`: mock stream that fails at chunk 5, assert `degraded=True` chunk received with accumulated text
- `test_timeout_middleware.py`: slow tool that sleeps, assert `ToolTimeoutError` raised at correct timeout; assert tool-level override works
- `test_result_cache.py`: call cacheable tool twice with same args, assert second call skips `tool.run()`; assert TTL expiry clears cache
- `test_health_check.py`: mock browser health check, mock MCP ping, assert `GET /health/tools` returns expected structure

---

## Success Criteria

- [ ] `GET /metrics/providers` returns per-model latency and error counts
- [ ] Stream degradation yields partial response instead of exception
- [ ] All tools use centralized timeout — no per-tool timeout logic remains
- [ ] Cache reduces calls for `web_fetch` on repeated identical requests
- [ ] `GET /health/tools` returns health for all tools with `health_check()`
- [ ] `ToolError` used consistently — no bare `RuntimeError` from registry
- [ ] 0 regressions on existing tool tests
