const bootstrap = window.__CLAWLITE_DASHBOARD_BOOTSTRAP__ || {};
const auth = bootstrap.auth || {};
const paths = bootstrap.paths || {};
const tokenStorageKey = "clawlite.dashboard.token";
const refreshStorageKey = "clawlite.dashboard.refreshMs";
const defaultRefreshMs = 15000;
const maxFeedEntries = 18;

const state = {
  activeTab: "overview",
  token: window.localStorage.getItem(tokenStorageKey) || "",
  autoRefreshMs: Number(window.localStorage.getItem(refreshStorageKey) || defaultRefreshMs),
  ws: null,
  wsState: "offline",
  reconnectTimer: null,
  refreshTimer: null,
  refreshInFlight: false,
  heartbeatBusy: false,
  status: bootstrap.control_plane || null,
  dashboardState: null,
  diagnostics: null,
  tools: null,
  tokenInfo: null,
  lastSyncAt: null,
  eventFeed: [],
  wsPreview: "Waiting for live websocket frames...",
  sessionId: "dashboard:operator",
};

function byId(id) {
  return document.getElementById(id);
}

function safeJson(value) {
  return JSON.stringify(value, null, 2);
}

function authHeaders() {
  if (!state.token) {
    return {};
  }
  const headerName = auth.header_name || "Authorization";
  const value = headerName.toLowerCase() === "authorization" ? `Bearer ${state.token}` : state.token;
  return { [headerName]: value };
}

function tokenFromLocationHash() {
  const raw = String(window.location.hash || "").replace(/^#/, "").trim();
  if (!raw) {
    return "";
  }
  const params = new URLSearchParams(raw);
  return String(params.get("token") || "").trim();
}

function buildWsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${protocol}//${window.location.host}${paths.ws || "/ws"}`);
  if (state.token) {
    url.searchParams.set(auth.query_param || "token", state.token);
  }
  return url.toString();
}

function setText(id, value) {
  const node = byId(id);
  if (node) {
    node.textContent = value;
  }
}

function setCode(id, value) {
  const node = byId(id);
  if (node) {
    node.textContent = typeof value === "string" ? value : safeJson(value);
  }
}

function setBadge(id, text, tone = "") {
  const node = byId(id);
  if (!node) {
    return;
  }
  node.textContent = text;
  node.className = `badge${tone ? ` badge--${tone}` : ""}`;
}

function formatClock(value) {
  if (!value) {
    return "-";
  }
  try {
    return new Date(value).toLocaleTimeString();
  } catch (_error) {
    return String(value);
  }
}

function formatDuration(seconds) {
  const total = Number(seconds || 0);
  if (!Number.isFinite(total) || total <= 0) {
    return "0s";
  }
  if (total < 60) {
    return `${Math.round(total)}s`;
  }
  if (total < 3600) {
    return `${Math.floor(total / 60)}m ${Math.round(total % 60)}s`;
  }
  return `${Math.floor(total / 3600)}h ${Math.floor((total % 3600) / 60)}m`;
}

function numeric(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function truthy(value) {
  return value === true || value === "true" || value === "running" || value === "ready" || value === "online";
}

function toneForState(value) {
  if (truthy(value)) {
    return "ok";
  }
  if (value === false || value === "failed" || value === "stopped" || value === "offline") {
    return "danger";
  }
  return "warn";
}

function recordEvent(level, title, detail, meta = "") {
  const event = {
    level,
    title,
    detail,
    meta,
    ts: new Date().toISOString(),
  };
  state.eventFeed = [event, ...state.eventFeed].slice(0, maxFeedEntries);
  renderEventFeed();
}

function appendChatEntry(role, text, meta = "") {
  const log = byId("chat-log");
  if (!log) {
    return;
  }
  const entry = document.createElement("article");
  entry.className = `chat-entry chat-entry--${role}`;

  const metaRow = document.createElement("div");
  metaRow.className = "chat-entry__meta";
  const roleNode = document.createElement("span");
  roleNode.textContent = role;
  const timeNode = document.createElement("span");
  timeNode.textContent = meta || new Date().toLocaleTimeString();
  metaRow.append(roleNode, timeNode);

  const body = document.createElement("div");
  body.textContent = text;
  entry.append(metaRow, body);
  log.prepend(entry);
}

function renderEndpointList() {
  const endpointList = byId("endpoint-list");
  if (!endpointList) {
    return;
  }
  endpointList.innerHTML = "";
  const labels = {
    health: "health",
    status: "status",
    diagnostics: "diagnostics",
    message: "chat",
    token: "token",
    tools: "tools",
    heartbeat_trigger: "heartbeat",
    ws: "websocket",
  };
  Object.entries(paths).forEach(([label, path]) => {
    const item = document.createElement("li");
    const code = document.createElement("code");
    code.textContent = String(path);
    const text = document.createElement("span");
    text.textContent = labels[label] || label.replaceAll("_", " ");
    item.append(code, text);
    endpointList.appendChild(item);
  });
}

function summarizeQueue(queue) {
  if (!queue || typeof queue !== "object") {
    return "-";
  }
  const candidates = [
    queue.pending,
    queue.in_flight,
    queue.total,
    queue.outbound_pending,
    queue.dead_letter,
  ].map((value) => numeric(value, 0));
  const max = Math.max(...candidates, 0);
  return String(max);
}

function countEnabledChannels(channels) {
  if (!channels || typeof channels !== "object") {
    return "0";
  }
  let count = 0;
  Object.values(channels).forEach((value) => {
    if (value && typeof value === "object") {
      if (truthy(value.enabled) || truthy(value.running) || truthy(value.available) || truthy(value.connected)) {
        count += 1;
      }
    }
  });
  return String(count);
}

function heartbeatSummary(heartbeat) {
  if (!heartbeat || typeof heartbeat !== "object") {
    return "-";
  }
  if (heartbeat.last_decision && typeof heartbeat.last_decision === "object") {
    return `${heartbeat.last_decision.action || "skip"}:${heartbeat.last_decision.reason || "unknown"}`;
  }
  if (heartbeat.last_action || heartbeat.last_reason) {
    return `${heartbeat.last_action || "skip"}:${heartbeat.last_reason || "unknown"}`;
  }
  return "idle";
}

function componentEntries() {
  const components = (state.status || {}).components || {};
  return Object.entries(components);
}

function renderComponentBoard() {
  const container = byId("component-board");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  const entries = componentEntries();
  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "summary-card";
    empty.textContent = "No component telemetry available yet.";
    container.appendChild(empty);
    return;
  }

  entries.forEach(([name, payload]) => {
    const card = document.createElement("article");
    const tone = toneForState(payload && typeof payload === "object" ? payload.ready ?? payload.running ?? payload.connected : payload);
    card.className = `component-card component-card--${tone === "ok" ? "ready" : tone === "danger" ? "stopped" : "pending"}`;

    const title = document.createElement("span");
    title.className = "component-card__title";
    title.textContent = name;

    const meta = document.createElement("div");
    meta.className = "component-card__meta";
    if (payload && typeof payload === "object") {
      const parts = [];
      ["state", "worker_state", "reason", "last_status", "restored"].forEach((key) => {
        if (payload[key] !== undefined && payload[key] !== "") {
          parts.push(`${key}: ${payload[key]}`);
        }
      });
      meta.textContent = parts.length ? parts.join(" | ") : safeJson(payload);
    } else {
      meta.textContent = String(payload);
    }

    card.append(title, meta);
    container.appendChild(card);
  });
}

function renderEventFeed() {
  const container = byId("event-feed");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!state.eventFeed.length) {
    const empty = document.createElement("article");
    empty.className = "event-entry";
    empty.textContent = "No operator events yet. Refresh or send a chat message to populate this feed.";
    container.appendChild(empty);
    setBadge("event-feed-status", "quiet");
    return;
  }

  setBadge("event-feed-status", `${state.eventFeed.length} events`, state.eventFeed[0].level === "danger" ? "danger" : state.eventFeed[0].level);
  state.eventFeed.forEach((event) => {
    const entry = document.createElement("article");
    entry.className = "event-entry";

    const level = document.createElement("span");
    level.className = `event-entry__level event-entry__level--${event.level}`;
    level.textContent = event.level;

    const title = document.createElement("span");
    title.className = "event-entry__title";
    title.textContent = event.title;

    const detail = document.createElement("div");
    detail.className = "event-entry__meta";
    detail.textContent = event.detail;

    const meta = document.createElement("div");
    meta.className = "event-entry__meta";
    meta.textContent = `${formatClock(event.ts)}${event.meta ? ` | ${event.meta}` : ""}`;

    entry.append(level, title, detail, meta);
    container.appendChild(entry);
  });
}

function renderToolsSummary() {
  const groupsNode = byId("tool-groups");
  const aliasesNode = byId("tool-aliases");
  if (!groupsNode || !aliasesNode) {
    return;
  }
  groupsNode.innerHTML = "";
  aliasesNode.innerHTML = "";

  const tools = state.tools || {};
  const groups = Array.isArray(tools.groups) ? tools.groups : [];
  const aliases = tools.aliases && typeof tools.aliases === "object" ? tools.aliases : {};

  groups.slice(0, 12).forEach((group) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    const title = document.createElement("span");
    title.className = "summary-card__title";
    title.textContent = String(group.name || group.group || "group");
    const meta = document.createElement("div");
    meta.className = "summary-card__meta";
    meta.textContent = `${numeric(group.count, 0)} tools`;
    card.append(title, meta);
    groupsNode.appendChild(card);
  });

  Object.entries(aliases)
    .slice(0, 12)
    .forEach(([alias, target]) => {
      const card = document.createElement("article");
      card.className = "summary-card";
      const title = document.createElement("span");
      title.className = "summary-card__title";
      title.textContent = alias;
      const meta = document.createElement("div");
      meta.className = "summary-card__meta";
      meta.textContent = String(target);
      card.append(title, meta);
      aliasesNode.appendChild(card);
    });
}

function useSession(sessionId) {
  state.sessionId = sessionId;
  const input = byId("session-input");
  if (input) {
    input.value = sessionId;
  }
  setText("metric-session-route", `chat -> ${sessionId}`);
  setActiveTab("chat");
  recordEvent("ok", "Session selected", sessionId, "dashboard");
}

function renderSessions() {
  const payload = (state.dashboardState || {}).sessions || {};
  const items = Array.isArray(payload.items) ? payload.items : [];
  const grid = byId("sessions-grid");
  if (grid) {
    grid.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("article");
      empty.className = "summary-card";
      empty.textContent = "No persisted sessions yet. Send a message from the dashboard or a channel to populate this view.";
      grid.appendChild(empty);
    }
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "summary-card";

      const title = document.createElement("span");
      title.className = "summary-card__title";
      title.textContent = item.session_id || "session";

      const meta = document.createElement("div");
      meta.className = "summary-card__meta";
      meta.textContent = `${item.last_role || "unknown"}: ${item.last_preview || "No messages yet."}`;

      const subMeta = document.createElement("div");
      subMeta.className = "summary-card__meta";
      subMeta.textContent = `updated ${formatClock(item.updated_at)} | active subagents ${numeric(item.active_subagents, 0)}`;

      const actions = document.createElement("div");
      actions.className = "summary-card__actions";
      const useButton = document.createElement("button");
      useButton.className = "ghost-button";
      useButton.type = "button";
      useButton.textContent = "Use in chat";
      useButton.addEventListener("click", () => useSession(String(item.session_id || "dashboard:operator")));
      actions.appendChild(useButton);

      card.append(title, meta, subMeta, actions);
      grid.appendChild(card);
    });
  }

  setText("metric-session-count", String(numeric(payload.count, 0)));
  setText(
    "metric-session-subagents",
    String(items.reduce((total, item) => total + numeric(item.active_subagents, 0), 0)),
  );
  setText("metric-session-updated", items[0] ? formatClock(items[0].updated_at) : "-");
  setBadge("sessions-status", items.length ? `${items.length} recent` : "empty", items.length ? "ok" : "warn");
}

function renderAutomation() {
  const payload = state.dashboardState || {};
  const cronPayload = payload.cron || {};
  const cronJobs = Array.isArray(cronPayload.jobs) ? cronPayload.jobs : [];
  const cronGrid = byId("cron-grid");
  if (cronGrid) {
    cronGrid.innerHTML = "";
    if (!cronJobs.length) {
      const empty = document.createElement("article");
      empty.className = "summary-card";
      empty.textContent = "No cron jobs are currently scheduled.";
      cronGrid.appendChild(empty);
    }
    cronJobs.forEach((job) => {
      const card = document.createElement("article");
      card.className = "summary-card";
      const title = document.createElement("span");
      title.className = "summary-card__title";
      title.textContent = job.name || job.id || "cron-job";
      const meta = document.createElement("div");
      meta.className = "summary-card__meta";
      meta.textContent = `${job.expression || job.schedule?.kind || "schedule"} | next ${job.next_run_iso || "pending"}`;
      const status = document.createElement("div");
      status.className = "summary-card__meta";
      status.textContent = `status ${job.last_status || "idle"} | session ${job.session_id || "-"}`;
      card.append(title, meta, status);
      cronGrid.appendChild(card);
    });
  }

  const channelsPayload = payload.channels || {};
  const channels = Array.isArray(channelsPayload.items) ? channelsPayload.items : [];
  const channelsGrid = byId("channels-grid");
  if (channelsGrid) {
    channelsGrid.innerHTML = "";
    if (!channels.length) {
      const empty = document.createElement("article");
      empty.className = "summary-card";
      empty.textContent = "No channel state available.";
      channelsGrid.appendChild(empty);
    }
    channels.forEach((channel) => {
      const card = document.createElement("article");
      card.className = "summary-card";
      const title = document.createElement("span");
      title.className = "summary-card__title";
      title.textContent = channel.name || "channel";
      const meta = document.createElement("div");
      meta.className = "summary-card__meta";
      meta.textContent = `${channel.enabled ? "enabled" : "disabled"} | ${channel.state || "unknown"}`;
      const summary = document.createElement("div");
      summary.className = "summary-card__meta";
      summary.textContent = channel.summary || "";
      card.append(title, meta, summary);
      channelsGrid.appendChild(card);
    });
  }

  const provider = payload.provider || {};
  const providerAutonomy = provider.autonomy || {};
  const providerTelemetry = provider.telemetry || {};
  setText("metric-provider-state", String(providerAutonomy.state || providerTelemetry.summary?.state || "unknown"));
  setText("metric-provider-backoff", formatDuration(providerAutonomy.suppression_backoff_s || providerAutonomy.cooldown_remaining_s || 0));
  setCode("provider-preview", {
    autonomy: providerAutonomy,
    summary: providerTelemetry.summary || {},
    counters: providerTelemetry.counters || {},
  });
  setBadge("provider-status", String(providerAutonomy.state || "unknown"), toneForState(providerAutonomy.state));

  const selfEvolution = payload.self_evolution || {};
  setText("metric-self-evolution", selfEvolution.enabled ? "enabled" : "disabled");
  setCode("self-evolution-preview", selfEvolution);
  setBadge("self-evolution-status", selfEvolution.enabled ? "enabled" : "disabled", selfEvolution.enabled ? "ok" : "warn");

  const cronStatus = cronPayload.status || {};
  setText("metric-cron-jobs", String(numeric(cronStatus.jobs, cronJobs.length)));
  setBadge("cron-status", cronJobs.length ? `${cronJobs.length} jobs` : "idle", cronJobs.length ? "ok" : "warn");
  setBadge("channels-status", channels.length ? `${channels.length} channels` : "empty", channels.length ? "ok" : "warn");
}

function renderKnowledge() {
  const payload = state.dashboardState || {};
  const workspace = payload.workspace || {};
  const onboarding = payload.onboarding || {};
  const bootstrap = payload.bootstrap || {};
  const skills = payload.skills || {};
  const memory = payload.memory || {};
  const memoryMonitor = memory.monitor || {};

  setText(
    "metric-workspace-health",
    `${numeric(workspace.healthy_count, 0)}/${Object.keys(workspace.critical_files || {}).length || 0}`,
  );
  setText(
    "metric-bootstrap",
    onboarding.completed
      ? "completed"
      : bootstrap.pending
        ? "pending"
        : bootstrap.last_status || (bootstrap.completed_at ? "completed" : "idle"),
  );
  setText("metric-skills-runnable", String(numeric(((skills.summary || {}).runnable), 0)));
  setText("metric-memory-pending", String(numeric(memoryMonitor.pending, 0)));

  const workspaceGrid = byId("workspace-grid");
  if (workspaceGrid) {
    workspaceGrid.innerHTML = "";
    const files = workspace.critical_files || {};
    const entries = Object.entries(files);
    if (!entries.length) {
      const empty = document.createElement("article");
      empty.className = "summary-card";
      empty.textContent = "No workspace runtime health data available.";
      workspaceGrid.appendChild(empty);
    }
    entries.forEach(([name, row]) => {
      const card = document.createElement("article");
      card.className = "summary-card";
      const title = document.createElement("span");
      title.className = "summary-card__title";
      title.textContent = name;
      const meta = document.createElement("div");
      meta.className = "summary-card__meta";
      meta.textContent = `${row.status || "unknown"} | bytes ${numeric(row.bytes, 0)} | repaired ${Boolean(row.repaired)}`;
      const detail = document.createElement("div");
      detail.className = "summary-card__meta";
      detail.textContent = row.error || row.backup_path || "runtime file healthy";
      card.append(title, meta, detail);
      workspaceGrid.appendChild(card);
    });
  }

  setCode("bootstrap-preview", {
    onboarding,
    bootstrap,
  });
  setCode("skills-preview", {
    summary: skills.summary || {},
    watcher: skills.watcher || {},
    sources: skills.sources || {},
    missing_requirements: skills.missing_requirements || {},
  });
  setCode("memory-preview", {
    monitor: memoryMonitor,
    analysis: memory.analysis || {},
  });

  setBadge("workspace-status", workspace.failed_count ? "attention" : "healthy", workspace.failed_count ? "warn" : "ok");
  setBadge(
    "bootstrap-status",
    onboarding.completed ? "completed" : bootstrap.pending ? "pending" : bootstrap.last_status || "idle",
    onboarding.completed ? "ok" : bootstrap.pending ? "warn" : "ok",
  );
  setBadge("skills-status", `${numeric(((skills.summary || {}).available), 0)} available`, numeric(((skills.summary || {}).unavailable), 0) ? "warn" : "ok");
  setBadge("memory-status", memoryMonitor.enabled ? "monitoring" : "disabled", memoryMonitor.enabled ? "ok" : "warn");
}

function renderOverview() {
  const status = state.status || bootstrap.control_plane || {};
  const ready = Boolean(status.ready);

  setText("pill-connection", state.wsState);
  setText("pill-phase", String(status.phase || "created"));
  setText("pill-auth", String((status.auth || {}).mode || auth.mode || "off"));
  setText("metric-ready", ready ? "ready" : "starting");
  setText("metric-phase", String(status.phase || "created"));
  setText("metric-contract", String(status.contract_version || "-"));
  setText("metric-server-time", String(status.server_time || "-"));

  const diagnostics = state.diagnostics || {};
  setText("metric-uptime", formatDuration(diagnostics.uptime_s));
  setText("metric-queue", summarizeQueue(diagnostics.queue));
  setText("metric-channels", countEnabledChannels(diagnostics.channels));
  setText("metric-heartbeat", heartbeatSummary(diagnostics.heartbeat));

  setText("auth-badge", String((status.auth || {}).posture || auth.posture || "open"));
  setText(
    "auth-summary",
    `Header ${auth.header_name || "Authorization"} or query ${auth.query_param || "token"}. Token configured: ${Boolean((status.auth || {}).token_configured)}. Loopback bypass: ${Boolean((status.auth || {}).allow_loopback_without_auth)}.`,
  );

  setText("nav-refresh-state", state.autoRefreshMs > 0 ? formatDuration(state.autoRefreshMs / 1000) : "manual");
  setText("nav-last-sync", state.lastSyncAt ? formatClock(state.lastSyncAt) : "pending");

  renderEndpointList();
  renderComponentBoard();
}

function renderRuntime() {
  setCode("status-json", state.status || { note: "status unavailable" });
  setCode("diagnostics-json", state.diagnostics || { note: "diagnostics unavailable" });
  setCode("tools-json", state.tools || { note: "tools catalog unavailable" });
  setCode("token-preview", state.tokenInfo || { token_saved: Boolean(state.token), auth_mode: auth.mode || "off" });

  const components = (state.status || {}).components || {};
  setCode("components-preview", components);
  if (state.diagnostics) {
    setBadge("diag-status", "live", "ok");
    setCode("runtime-preview", {
      queue: state.diagnostics.queue,
      channels: state.diagnostics.channels,
      heartbeat: state.diagnostics.heartbeat,
      autonomy: state.diagnostics.autonomy,
      supervisor: state.diagnostics.supervisor,
      ws: state.diagnostics.ws,
      http: state.diagnostics.http,
    });
  }

  setText("metric-schema", String((state.diagnostics || {}).schema_version || "-"));
  setText("metric-http", String(numeric(((state.diagnostics || {}).http || {}).total_requests, 0)));
  setText("metric-ws", String(numeric((((state.diagnostics || {}).ws || {}).frames_in), 0) + numeric((((state.diagnostics || {}).ws || {}).frames_out), 0)));
  setText("metric-tool-count", String(numeric((state.tools || {}).tool_count, 0)));
  setCode("ws-event-preview", state.wsPreview);
  renderToolsSummary();
}

function renderAll() {
  renderOverview();
  renderSessions();
  renderAutomation();
  renderKnowledge();
  renderRuntime();
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
    method: options.method || "GET",
    body: options.body,
  });
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (_error) {
    payload = { raw: text };
  }
  if (!response.ok) {
    const detail = payload.detail || payload.error || response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return payload;
}

async function refreshStatus() {
  state.status = await fetchJson(paths.status || "/api/status");
}

async function refreshDashboardState() {
  state.dashboardState = await fetchJson(paths.dashboard_state || "/api/dashboard/state");
}

async function refreshDiagnostics() {
  state.diagnostics = await fetchJson(paths.diagnostics || "/api/diagnostics");
}

async function refreshTools() {
  state.tools = await fetchJson(paths.tools || "/api/tools/catalog");
}

async function refreshTokenInfo() {
  try {
    state.tokenInfo = await fetchJson(paths.token || "/api/token");
  } catch (error) {
    state.tokenInfo = { error: error.message, token_saved: Boolean(state.token) };
  }
}

async function refreshAll(reason = "manual") {
  if (state.refreshInFlight) {
    return;
  }
  state.refreshInFlight = true;
  try {
    await Promise.all([refreshStatus(), refreshDashboardState(), refreshDiagnostics(), refreshTools(), refreshTokenInfo()]);
    state.lastSyncAt = new Date().toISOString();
    if (reason !== "auto") {
      recordEvent("ok", "Dashboard sync complete", "Status, dashboard state, diagnostics, tools, and token metadata refreshed.", reason);
    }
  } catch (error) {
    recordEvent("danger", "Dashboard sync failed", error.message, reason);
    setBadge("diag-status", "auth required", "warn");
  } finally {
    state.refreshInFlight = false;
    renderAll();
  }
}

function setActiveTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll("[data-tab-target]").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.tabTarget === tab);
  });
  document.querySelectorAll("[data-tab-panel]").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.tabPanel === tab);
  });
}

function scheduleAutoRefresh() {
  window.clearInterval(state.refreshTimer);
  if (state.autoRefreshMs > 0) {
    state.refreshTimer = window.setInterval(() => {
      void refreshAll("auto");
    }, state.autoRefreshMs);
  }
  setText("nav-refresh-state", state.autoRefreshMs > 0 ? formatDuration(state.autoRefreshMs / 1000) : "manual");
}

function updateWsStatus(nextState) {
  state.wsState = nextState;
  const tone = nextState === "online" ? "ok" : nextState === "error" ? "danger" : "warn";
  setBadge("ws-status", nextState, tone);
  renderAll();
}

function connectWs() {
  if (state.ws) {
    state.ws.close();
  }
  updateWsStatus("connecting");
  const socket = new WebSocket(buildWsUrl());
  state.ws = socket;

  socket.addEventListener("open", () => {
    updateWsStatus("online");
    recordEvent("ok", "WebSocket connected", buildWsUrl(), "live channel ready");
  });

  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(String(event.data || "{}"));
      state.wsPreview = safeJson(payload);
      setBadge("ws-event-state", payload.error ? "gateway-error" : "frame", payload.error ? "danger" : "ok");
      if (payload.text) {
        appendChatEntry("assistant", String(payload.text), String(payload.model || "ws"));
      } else if (payload.error) {
        appendChatEntry("assistant", `Gateway error: ${payload.error}`, "ws");
        recordEvent("warn", "WebSocket returned gateway error", String(payload.error), "chat");
      } else {
        recordEvent("ok", "WebSocket frame received", payload.type || "message", "live stream");
      }
    } catch (_error) {
      state.wsPreview = String(event.data || "");
      setBadge("ws-event-state", "raw-frame", "warn");
    }
    setCode("ws-event-preview", state.wsPreview);
  });

  socket.addEventListener("close", () => {
    updateWsStatus("offline");
    recordEvent("warn", "WebSocket closed", "Attempting reconnect in 1.4s", "transport");
    window.clearTimeout(state.reconnectTimer);
    state.reconnectTimer = window.setTimeout(connectWs, 1400);
  });

  socket.addEventListener("error", () => {
    updateWsStatus("error");
    recordEvent("danger", "WebSocket transport error", "Browser transport signalled an error before close.", "transport");
  });
}

function persistToken(nextToken) {
  state.token = nextToken.trim();
  if (state.token) {
    window.localStorage.setItem(tokenStorageKey, state.token);
  } else {
    window.localStorage.removeItem(tokenStorageKey);
  }
}

function bootstrapTokenFromUrl() {
  const hashToken = tokenFromLocationHash();
  if (!hashToken) {
    return;
  }
  persistToken(hashToken);
  if (window.history && typeof window.history.replaceState === "function") {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  } else {
    window.location.hash = "";
  }
  const tokenInput = byId("token-input");
  if (tokenInput) {
    tokenInput.value = state.token;
  }
  recordEvent("ok", "Gateway token bootstrapped", "Loaded token from dashboard URL fragment and removed it from the address bar.", "auth");
}

async function sendHttpMessage() {
  const sessionId = byId("session-input").value.trim() || state.sessionId;
  const text = byId("chat-input").value.trim();
  if (!text) {
    return;
  }
  appendChatEntry("user", text, sessionId);
  byId("chat-input").value = "";
  try {
    const payload = await fetchJson(paths.message || "/api/message", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ session_id: sessionId, text }),
    });
    appendChatEntry("assistant", String(payload.text || ""), String(payload.model || "http"));
    recordEvent("ok", "HTTP chat request completed", sessionId, payload.model || "http");
  } catch (error) {
    appendChatEntry("assistant", `HTTP error: ${error.message}`, "http");
    recordEvent("danger", "HTTP chat request failed", error.message, sessionId);
  }
}

function sendWsMessage() {
  const sessionId = byId("session-input").value.trim() || state.sessionId;
  const text = byId("chat-input").value.trim();
  if (!text) {
    return;
  }
  appendChatEntry("user", text, sessionId);
  byId("chat-input").value = "";
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    appendChatEntry("assistant", "WebSocket is not connected. Use Reconnect WS or save the token and retry.", "ws");
    recordEvent("warn", "WebSocket send blocked", "No live connection available.", sessionId);
    return;
  }
  state.ws.send(JSON.stringify({ session_id: sessionId, text }));
  recordEvent("ok", "WebSocket chat request sent", sessionId, "queued");
}

async function triggerHeartbeat() {
  if (state.heartbeatBusy) {
    return;
  }
  state.heartbeatBusy = true;
  byId("trigger-heartbeat").disabled = true;
  setBadge("diag-status", "triggering", "warn");
  try {
    const payload = await fetchJson(paths.heartbeat_trigger || "/v1/control/heartbeat/trigger", {
      method: "POST",
    });
    const decision = payload.decision || {};
    recordEvent(
      decision.action === "run" ? "warn" : "ok",
      "Heartbeat trigger completed",
      `${decision.action || "skip"}:${decision.reason || "unknown"}`,
      "control",
    );
    await refreshAll("heartbeat");
  } catch (error) {
    recordEvent("danger", "Heartbeat trigger failed", error.message, "control");
  } finally {
    state.heartbeatBusy = false;
    byId("trigger-heartbeat").disabled = false;
  }
}

function bindEvents() {
  document.querySelectorAll("[data-tab-target]").forEach((node) => {
    node.addEventListener("click", () => setActiveTab(node.dataset.tabTarget || "overview"));
  });

  byId("token-input").value = state.token;
  byId("session-input").value = state.sessionId;

  const refreshSelect = byId("refresh-interval");
  refreshSelect.value = String(state.autoRefreshMs);
  refreshSelect.addEventListener("change", async () => {
    state.autoRefreshMs = Number(refreshSelect.value || 0);
    window.localStorage.setItem(refreshStorageKey, String(state.autoRefreshMs));
    scheduleAutoRefresh();
    recordEvent("ok", "Autorefresh updated", state.autoRefreshMs > 0 ? formatDuration(state.autoRefreshMs / 1000) : "manual", "dashboard");
    renderAll();
  });

  byId("save-token").addEventListener("click", async () => {
    persistToken(byId("token-input").value);
    recordEvent("ok", "Gateway token saved", state.token ? "Operator token stored in local browser storage." : "Token cleared.", "auth");
    connectWs();
    await refreshAll("token-save");
  });

  byId("clear-token").addEventListener("click", async () => {
    persistToken("");
    byId("token-input").value = "";
    recordEvent("warn", "Gateway token cleared", "Dashboard returned to anonymous mode.", "auth");
    connectWs();
    await refreshAll("token-clear");
  });

  byId("refresh-all").addEventListener("click", () => {
    void refreshAll("manual");
  });
  byId("reconnect-ws").addEventListener("click", () => {
    recordEvent("warn", "WebSocket reconnect requested", "Operator manually restarted the transport.", "transport");
    connectWs();
  });
  byId("trigger-heartbeat").addEventListener("click", () => {
    void triggerHeartbeat();
  });
  byId("send-chat").addEventListener("click", sendWsMessage);
  byId("send-rest").addEventListener("click", () => {
    void sendHttpMessage();
  });
  byId("chat-input").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      sendWsMessage();
    }
  });
}

bindEvents();
bootstrapTokenFromUrl();
setActiveTab(state.activeTab);
renderAll();
recordEvent("ok", "Dashboard booted", "Packaged shell loaded with gateway bootstrap metadata.", "ui");
void refreshAll("initial");
scheduleAutoRefresh();
connectWs();
