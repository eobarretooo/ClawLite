const bootstrap = window.__CLAWLITE_DASHBOARD_BOOTSTRAP__ || {};
const auth = bootstrap.auth || {};
const paths = bootstrap.paths || {};
const tokenStorageKey = "clawlite.dashboard.token";
const refreshStorageKey = "clawlite.dashboard.refreshMs";
const defaultRefreshMs = 15000;
const maxFeedEntries = 18;
const HATCH_MESSAGE = "Wake up, my friend!";

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

function appendSummaryCard(container, item) {
  const card = document.createElement("article");
  card.className = "summary-card";

  const title = document.createElement("span");
  title.className = "summary-card__title";
  title.textContent = String(item.title || "item");

  const body = document.createElement("div");
  body.className = "summary-card__meta";
  body.textContent = String(item.body || "");

  const detail = document.createElement("div");
  detail.className = "summary-card__meta";
  detail.textContent = String(item.detail || "");

  card.append(title, body, detail);
  container.appendChild(card);
}

function renderDeliveryBoard() {
  const grid = byId("delivery-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const payload = state.dashboardState || {};
  const queue = payload.queue || {};
  const delivery = payload.channels_delivery || {};
  const dispatcher = payload.channels_dispatcher || {};
  const recovery = payload.channels_recovery || {};
  const inbound = payload.channels_inbound || {};
  const total = delivery.total || {};
  const persistence = delivery.persistence || {};
  const startupReplay = persistence.startup_replay || {};
  const manualReplay = persistence.manual_replay || {};
  const inboundPersistence = inbound.persistence || {};
  const inboundStartupReplay = inboundPersistence.startup_replay || {};
  const inboundManualReplay = inboundPersistence.manual_replay || {};
  const recentDeadLetters = Array.isArray(queue.dead_letter_recent) ? queue.dead_letter_recent : [];
  const latestDeadLetter = recentDeadLetters[0] || {};

  const cards = [
    {
      title: "Outbound queue",
      body: `${numeric(queue.outbound_size, 0)} queued`,
      detail: `oldest ${formatDuration(queue.outbound_oldest_age_s || 0)}`,
    },
    {
      title: "Dead letters",
      body: `${numeric(queue.dead_letter_size, 0)} retained`,
      detail: latestDeadLetter.dead_letter_reason
        ? `${latestDeadLetter.dead_letter_reason} | oldest ${formatDuration(queue.dead_letter_oldest_age_s || 0)}`
        : `oldest ${formatDuration(queue.dead_letter_oldest_age_s || 0)}`,
    },
    {
      title: "Delivery totals",
      body: `${numeric(total.success, 0)} success / ${numeric(total.failures, 0)} failed`,
      detail: `${numeric(total.dead_lettered, 0)} dead-lettered | ${numeric(total.replayed, 0)} replayed`,
    },
    {
      title: "Startup replay",
      body: `${numeric(startupReplay.replayed, 0)} replayed`,
      detail: `${numeric(startupReplay.failed, 0)} failed | ${numeric(startupReplay.skipped, 0)} skipped`,
    },
    {
      title: "Manual replay",
      body: `${numeric(manualReplay.replayed, 0)} replayed | ${numeric(manualReplay.restored, 0)} restored`,
      detail: manualReplay.last_at
        ? `${formatClock(manualReplay.last_at)} | ${numeric(manualReplay.failed, 0)} failed | ${numeric(manualReplay.skipped, 0)} skipped`
        : "No manual replay has been triggered yet.",
    },
    {
      title: "Inbound journal",
      body: `${numeric(inboundPersistence.pending, 0)} pending | ${numeric(inboundStartupReplay.replayed, 0)} startup replayed`,
      detail: inboundManualReplay.last_at
        ? `${formatClock(inboundManualReplay.last_at)} | ${numeric(inboundManualReplay.replayed, 0)} manual replayed | ${numeric(inboundManualReplay.skipped_busy, 0)} busy skips`
        : "No manual inbound replay has been triggered yet.",
    },
    {
      title: "Dispatcher",
      body: `${String(dispatcher.task_state || "unknown")} | ${numeric(dispatcher.active_tasks, 0)} active tasks`,
      detail: `${numeric(dispatcher.active_sessions, 0)} active sessions | max ${numeric(dispatcher.max_concurrency, 0)} concurrency`,
    },
    {
      title: "Recovery loop",
      body: `${String(recovery.task_state || "unknown")} | ${numeric((recovery.total || {}).success, 0)} recovered`,
      detail: `${numeric((recovery.total || {}).failures, 0)} failed | ${numeric((recovery.total || {}).skipped_cooldown, 0)} cooldown skips`,
    },
  ];

  cards.forEach((item) => appendSummaryCard(grid, item));

  const deliveryHealthy = numeric(queue.dead_letter_size, 0) === 0 && String(dispatcher.task_state || "") === "running";
  setBadge("delivery-status", deliveryHealthy ? "healthy" : "attention", deliveryHealthy ? "ok" : "warn");
  const replayButton = byId("replay-dead-letters");
  if (replayButton) {
    const deadLetterCount = numeric(queue.dead_letter_size, 0);
    replayButton.disabled = deadLetterCount <= 0;
    replayButton.textContent = deadLetterCount > 0 ? `Replay dead letters (${deadLetterCount})` : "Replay dead letters";
  }
  const inboundReplayButton = byId("replay-inbound-journal");
  if (inboundReplayButton) {
    const inboundPending = numeric(inboundPersistence.pending, 0);
    inboundReplayButton.disabled = inboundPending <= 0;
    inboundReplayButton.textContent = inboundPending > 0 ? `Replay inbound journal (${inboundPending})` : "Replay inbound journal";
  }
}

function renderSupervisorBoard() {
  const grid = byId("supervisor-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const supervisor = ((state.dashboardState || {}).supervisor) || {};
  const componentRecovery = supervisor.component_recovery || {};
  const operator = supervisor.operator || {};
  const lastIncident = supervisor.last_incident || {};
  const cards = [
    {
      title: "Supervisor state",
      body: `${String(supervisor.worker_state || "unknown")} | ${numeric(supervisor.incident_count, 0)} incidents`,
      detail: `${numeric(supervisor.recovery_attempts, 0)} attempts | ${numeric(supervisor.recovery_success, 0)} recovered`,
    },
    {
      title: "Recovery skips",
      body: `${numeric(supervisor.recovery_skipped_cooldown, 0)} cooldown`,
      detail: `${numeric(supervisor.recovery_skipped_budget, 0)} budget | ${numeric(supervisor.recovery_failures, 0)} failures`,
    },
    {
      title: "Last incident",
      body: String(lastIncident.component || "none"),
      detail: lastIncident.reason ? `${lastIncident.reason} | ${formatClock(lastIncident.at)}` : "No incidents recorded.",
    },
    {
      title: "Operator recovery",
      body: `${numeric(operator.recovered, 0)} recovered | ${numeric(operator.failed, 0)} failed`,
      detail: operator.last_at
        ? `${formatClock(operator.last_at)} | ${numeric(operator.skipped_cooldown, 0)} cooldown skips | ${numeric(operator.skipped_budget, 0)} budget skips`
        : "No manual supervisor recovery has been triggered yet.",
    },
  ];

  Object.entries(componentRecovery)
    .sort((a, b) => numeric(b[1]?.incidents, 0) - numeric(a[1]?.incidents, 0))
    .slice(0, 3)
    .forEach(([name, row]) => {
      cards.push({
        title: `Budget: ${name}`,
        body: `${numeric(row.incidents, 0)} incidents | ${numeric(row.recovery_success, 0)} recovered`,
        detail: `remaining ${row.budget_remaining === null ? "unbounded" : numeric(row.budget_remaining, 0)} | cooldown ${formatDuration(row.cooldown_remaining_s || 0)}`,
      });
    });

  cards.forEach((item) => appendSummaryCard(grid, item));

  const healthy = String(supervisor.worker_state || "") === "running" && numeric(supervisor.recovery_failures, 0) === 0;
  setBadge("supervisor-status", healthy ? "steady" : "active", healthy ? "ok" : "warn");
  const button = byId("recover-supervisor-component");
  if (button) {
    const trackedComponents = Object.keys(componentRecovery).length;
    button.disabled = trackedComponents <= 0;
  }
}

function renderProviderRecoveryBoard() {
  const grid = byId("provider-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const provider = (state.dashboardState || {}).provider || {};
  const telemetry = provider.telemetry || {};
  const summary = telemetry.summary || {};
  const candidates = [];

  const suppressionReason = String(summary.suppression_reason || "");
  const coolingCandidates = Array.isArray(summary.cooling_candidates) ? summary.cooling_candidates : [];
  const suppressedCandidates = Array.isArray(summary.suppressed_candidates) ? summary.suppressed_candidates : [];

  candidates.push({
    title: "Provider state",
    body: `${String(summary.state || "unknown")} | ${String(provider.autonomy?.provider || telemetry.provider || "provider")}`,
    detail: String(provider.autonomy?.suppression_hint || summary.onboarding_hint || "No additional guidance yet."),
  });

  candidates.push({
    title: "Suppression reason",
    body: suppressionReason || "none",
    detail: suppressionReason
      ? `Backoff ${formatDuration(provider.autonomy?.suppression_backoff_s || provider.autonomy?.cooldown_remaining_s || 0)}`
      : "Provider calls are currently allowed.",
  });

  if (suppressedCandidates.length) {
    suppressedCandidates.slice(0, 4).forEach((item) => {
      candidates.push({
        title: `${item.role || "candidate"}: ${item.model || "unknown"}`,
        body: `suppressed by ${item.suppression_reason || "unknown"}`,
        detail: `cooldown ${formatDuration(item.cooldown_remaining_s || 0)}`,
      });
    });
  } else if (coolingCandidates.length) {
    coolingCandidates.slice(0, 4).forEach((item) => {
      candidates.push({
        title: `${item.role || "candidate"}: ${item.model || "unknown"}`,
        body: "temporary cooldown",
        detail: `cooldown ${formatDuration(item.cooldown_remaining_s || 0)}`,
      });
    });
  } else {
    candidates.push({
      title: "Candidates",
      body: "no active suppression",
      detail: "Primary and fallback candidates are currently available.",
    });
  }

  const hints = Array.isArray(summary.hints) ? summary.hints : [];
  if (hints.length) {
    candidates.push({
      title: "Operator hint",
      body: String(hints[0] || ""),
      detail: hints.length > 1 ? String(hints[1] || "") : "",
    });
  }

  candidates.slice(0, 6).forEach((item) => appendSummaryCard(grid, item));
}

function handoffPayload() {
  return (state.dashboardState || {}).handoff || {};
}

function hatchSessionId() {
  return String(handoffPayload().hatch_session_id || "hatch:operator");
}

function renderHandoffGuidance() {
  const grid = byId("handoff-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";
  const handoff = handoffPayload();
  const guidance = Array.isArray(handoff.guidance) ? handoff.guidance : [];
  if (!guidance.length) {
    const empty = document.createElement("article");
    empty.className = "summary-card";
    empty.textContent = "No onboarding guidance is available yet.";
    grid.appendChild(empty);
    setBadge("handoff-status", "empty", "warn");
    return;
  }

  guidance.forEach((item) => {
    const card = document.createElement("article");
    card.className = "summary-card";

    const title = document.createElement("span");
    title.className = "summary-card__title";
    title.textContent = String(item.title || item.id || "guidance");

    const detail = document.createElement("div");
    detail.className = "summary-card__meta";
    detail.textContent = String(item.body || "");

    card.append(title, detail);
    grid.appendChild(card);
  });

  setBadge("handoff-status", `${guidance.length} notes`, "ok");
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
  const channelsRecovery = payload.channels_recovery || {};
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

    const operatorRecovery = channelsRecovery.operator || {};
    appendSummaryCard(channelsGrid, {
      title: "Manual recovery",
      body: `${numeric(operatorRecovery.recovered, 0)} recovered | ${numeric(operatorRecovery.failed, 0)} failed`,
      detail: operatorRecovery.last_at
        ? `${formatClock(operatorRecovery.last_at)} | ${numeric(operatorRecovery.skipped_healthy, 0)} healthy skips | ${numeric(operatorRecovery.skipped_cooldown, 0)} cooldown skips`
        : "No operator recovery action has been triggered yet.",
    });
  }

  const recoverButton = byId("recover-channels");
  if (recoverButton) {
    const unhealthyCount = channels.filter((channel) => {
      const state = String(channel.state || "").toLowerCase();
      return channel.enabled && state !== "running";
    }).length;
    recoverButton.disabled = unhealthyCount <= 0;
    recoverButton.textContent = unhealthyCount > 0 ? `Recover unhealthy channels (${unhealthyCount})` : "Recover unhealthy channels";
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
  renderDeliveryBoard();
  renderSupervisorBoard();
  renderProviderRecoveryBoard();

  const selfEvolution = payload.self_evolution || {};
  setText("metric-self-evolution", selfEvolution.enabled ? "enabled" : "disabled");
  setCode("self-evolution-preview", selfEvolution);
  setBadge("self-evolution-status", selfEvolution.enabled ? "enabled" : "disabled", selfEvolution.enabled ? "ok" : "warn");

  const cronStatus = cronPayload.status || {};
  setText("metric-cron-jobs", String(numeric(cronStatus.jobs, cronJobs.length)));
  setBadge("cron-status", cronJobs.length ? `${cronJobs.length} jobs` : "idle", cronJobs.length ? "ok" : "warn");
  setBadge("channels-status", channels.length ? `${channels.length} channels` : "empty", channels.length ? "ok" : "warn");
}

function renderTelegramBoard() {
  const grid = byId("telegram-grid");
  const pairingGrid = byId("telegram-pairing-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";
  if (pairingGrid) {
    pairingGrid.innerHTML = "";
  }

  const telegram = ((state.dashboardState || {}).telegram) || {};
  const available = Boolean(telegram.available);
  const refreshButton = byId("refresh-telegram-transport");
  const approveButton = byId("approve-telegram-pairing");
  const rejectButton = byId("reject-telegram-pairing");
  const revokeButton = byId("revoke-telegram-pairing");
  const offsetButton = byId("commit-telegram-offset");
  const offsetSyncButton = byId("sync-telegram-offset");
  const offsetResetButton = byId("reset-telegram-offset");

  if (!available) {
    appendSummaryCard(grid, {
      title: "Telegram",
      body: "not configured",
      detail: telegram.last_error || "Enable Telegram to surface offset, pairing, and webhook diagnostics here.",
    });
    setBadge("telegram-status", "unavailable", "warn");
    if (refreshButton) {
      refreshButton.disabled = true;
    }
    if (approveButton) {
      approveButton.disabled = true;
    }
    if (rejectButton) {
      rejectButton.disabled = true;
    }
    if (revokeButton) {
      revokeButton.disabled = true;
    }
    if (offsetButton) {
      offsetButton.disabled = true;
    }
    if (offsetSyncButton) {
      offsetSyncButton.disabled = true;
    }
    if (offsetResetButton) {
      offsetResetButton.disabled = true;
    }
    return;
  }

  appendSummaryCard(grid, {
    title: "Transport",
    body: `${String(telegram.mode || "unknown")} | ${telegram.webhook_mode_active ? "webhook active" : "polling active"}`,
    detail: telegram.webhook_requested
      ? `path ${telegram.webhook_path || "-"} | url configured ${Boolean(telegram.webhook_url_configured)} | secret configured ${Boolean(telegram.webhook_secret_configured)}`
      : "webhook not requested",
  });

  appendSummaryCard(grid, {
    title: "Offset state",
    body: `next ${numeric(telegram.offset_next, 0)} | pending ${numeric(telegram.offset_pending_count, 0)}`,
    detail: `watermark ${telegram.offset_watermark_update_id ?? "-"} | highest ${telegram.offset_highest_completed_update_id ?? "-"}`,
  });

  appendSummaryCard(grid, {
    title: "Pairing",
    body: `${numeric(telegram.pairing_pending_count, 0)} pending | ${numeric(telegram.pairing_approved_count, 0)} approved`,
    detail: telegram.last_error ? `last error ${telegram.last_error}` : "pairing store healthy",
  });

  const hints = Array.isArray(telegram.hints) ? telegram.hints : [];
  if (hints.length) {
    hints.slice(0, 3).forEach((hint, index) => {
      appendSummaryCard(grid, {
        title: `Hint ${index + 1}`,
        body: String(hint),
        detail: "Use the Telegram controls below or the CLI telegram commands to resolve this safely.",
      });
    });
  }

  if (pairingGrid) {
    const pending = Array.isArray(telegram.pairing_pending) ? telegram.pairing_pending : [];
    const approved = Array.isArray(telegram.pairing_approved) ? telegram.pairing_approved : [];
    if (!pending.length) {
      appendSummaryCard(pairingGrid, {
        title: "Pending requests",
        body: "none",
        detail: "No Telegram pairing requests are currently waiting for approval.",
      });
    }
    pending.slice(0, 6).forEach((item) => {
      appendSummaryCard(pairingGrid, {
        title: item.code || "pairing",
        body: `${item.username ? `@${String(item.username).replace(/^@/, "")}` : item.user_id || "unknown user"}`,
        detail: `chat ${item.chat_id || "-"} | last seen ${formatClock(item.last_seen_at || item.created_at)}`,
      });
    });
    if (!approved.length) {
      appendSummaryCard(pairingGrid, {
        title: "Approved entries",
        body: "none",
        detail: "No Telegram pairing approvals are currently stored.",
      });
    }
    approved.slice(0, 6).forEach((item) => {
      appendSummaryCard(pairingGrid, {
        title: String(item),
        body: "approved",
        detail: "This entry is currently allowed through Telegram pairing policy.",
      });
    });
  }

  const healthy = numeric(telegram.offset_pending_count, 0) === 0 && !telegram.last_error;
  setBadge("telegram-status", healthy ? "healthy" : "attention", healthy ? "ok" : "warn");
  if (refreshButton) {
    refreshButton.disabled = false;
  }
  if (approveButton) {
    approveButton.disabled = false;
  }
  if (rejectButton) {
    rejectButton.disabled = false;
  }
  if (revokeButton) {
    revokeButton.disabled = false;
  }
  if (offsetButton) {
    offsetButton.disabled = false;
  }
  if (offsetSyncButton) {
    offsetSyncButton.disabled = false;
  }
  if (offsetResetButton) {
    offsetResetButton.disabled = false;
  }
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

function hatchPending() {
  const payload = state.dashboardState || {};
  const onboarding = payload.onboarding || {};
  const bootstrap = payload.bootstrap || {};
  return Boolean((bootstrap.pending || onboarding.bootstrap_exists) && !onboarding.completed);
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

  const hatchButton = byId("trigger-hatch");
  const hatchReady = hatchPending();
  if (hatchButton) {
    hatchButton.disabled = !hatchReady;
    hatchButton.textContent = hatchReady ? "Hatch agent" : "Bootstrap settled";
  }
  setText(
    "hatch-summary",
    hatchReady
      ? `Bootstrap is still pending. Click Hatch agent to send \"${HATCH_MESSAGE}\" through ${hatchSessionId()} and let ClawLite define itself without polluting your main dashboard session.`
      : "Bootstrap is already settled. Use chat normally or trigger a heartbeat when you want proactive checks.",
  );

  renderEndpointList();
  renderComponentBoard();
  renderHandoffGuidance();
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
  renderTelegramBoard();
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
  await sendHttpMessageText(text, { sessionId, source: "manual-http" });
  byId("chat-input").value = "";
}

async function sendHttpMessageText(text, options = {}) {
  const sessionId = String(options.sessionId || byId("session-input").value.trim() || state.sessionId || "dashboard:operator");
  const source = String(options.source || "http");
  const cleanText = String(text || "").trim();
  if (!cleanText) {
    return;
  }
  appendChatEntry("user", cleanText, sessionId);
  state.sessionId = sessionId;
  try {
    const payload = await fetchJson(paths.message || "/api/message", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ session_id: sessionId, text: cleanText }),
    });
    appendChatEntry("assistant", String(payload.text || ""), String(payload.model || "http"));
    recordEvent("ok", "HTTP chat request completed", cleanText.slice(0, 80), `${source} | ${payload.model || "http"}`);
  } catch (error) {
    appendChatEntry("assistant", `HTTP error: ${error.message}`, "http");
    recordEvent("danger", "HTTP chat request failed", error.message, `${source} | ${sessionId}`);
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

async function triggerDeadLetterReplay() {
  const queue = ((state.dashboardState || {}).queue) || {};
  const limit = Math.min(25, Math.max(1, numeric(queue.dead_letter_size, 0) || 1));
  const button = byId("replay-dead-letters");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.channels_replay || "/v1/control/channels/replay", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ limit }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.failed ? "warn" : "ok",
      "Dead-letter replay finished",
      `${numeric(summary.replayed, 0)} replayed | ${numeric(summary.failed, 0)} failed | ${numeric(summary.skipped, 0)} skipped`,
      "channels",
    );
    await refreshAll("delivery-replay");
  } catch (error) {
    recordEvent("danger", "Dead-letter replay failed", error.message, "channels");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerInboundReplay() {
  const inbound = (((state.dashboardState || {}).channels_inbound) || {}).persistence || {};
  const limit = Math.min(50, Math.max(1, numeric(inbound.pending, 0) || 1));
  const button = byId("replay-inbound-journal");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.channels_inbound_replay || "/v1/control/channels/inbound-replay", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ limit, force: false }),
    });
    const summary = payload.summary || {};
    recordEvent(
      numeric(summary.replayed, 0) > 0 ? "ok" : "warn",
      "Inbound replay finished",
      `${numeric(summary.replayed, 0)} replayed | ${numeric(summary.remaining, 0)} remaining | ${numeric(summary.skipped_busy, 0)} busy skips`,
      "channels",
    );
    await refreshAll("inbound-replay");
  } catch (error) {
    recordEvent("danger", "Inbound replay failed", error.message, "channels");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerChannelRecovery() {
  const button = byId("recover-channels");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.channels_recover || "/v1/control/channels/recover", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ force: true }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.failed ? "warn" : "ok",
      "Channel recovery finished",
      `${numeric(summary.recovered, 0)} recovered | ${numeric(summary.failed, 0)} failed | ${numeric(summary.skipped_healthy, 0)} already healthy`,
      "channels",
    );
    await refreshAll("channel-recovery");
  } catch (error) {
    recordEvent("danger", "Channel recovery failed", error.message, "channels");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerSupervisorRecovery() {
  const button = byId("recover-supervisor-component");
  const input = byId("supervisor-component-name");
  const component = String(input?.value || "").trim();
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.supervisor_recover || "/v1/control/supervisor/recover", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ component, force: true }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.failed ? "warn" : "ok",
      "Supervisor recovery finished",
      `${numeric(summary.recovered, 0)} recovered | ${numeric(summary.failed, 0)} failed | ${numeric(summary.skipped_budget, 0)} budget skips`,
      component || "all-components",
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("supervisor-recover");
  } catch (error) {
    recordEvent("danger", "Supervisor recovery failed", error.message, component || "all-components");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerTelegramRefresh() {
  const button = byId("refresh-telegram-transport");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.telegram_refresh || "/v1/control/channels/telegram/refresh", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.last_error ? "warn" : "ok",
      "Telegram transport refresh finished",
      `${summary.webhook_activated ? "webhook refreshed" : "offset reloaded"} | connected ${Boolean(summary.connected)}`,
      "telegram",
    );
    await refreshAll("telegram-refresh");
  } catch (error) {
    recordEvent("danger", "Telegram transport refresh failed", error.message, "telegram");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerTelegramPairingApprove() {
  const input = byId("telegram-pairing-code");
  const button = byId("approve-telegram-pairing");
  const code = String(input?.value || "").trim().toUpperCase();
  if (!code) {
    recordEvent("warn", "Telegram pairing approval skipped", "Enter a pending pairing code first.", "telegram");
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.telegram_pairing_approve || "/v1/control/channels/telegram/pairing/approve", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Telegram pairing approval finished",
      summary.ok === false ? String(summary.error || "unknown_error") : `${code} approved`,
      "telegram",
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-pairing-approve");
  } catch (error) {
    recordEvent("danger", "Telegram pairing approval failed", error.message, "telegram");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerTelegramPairingReject() {
  const input = byId("telegram-pairing-code");
  const button = byId("reject-telegram-pairing");
  const code = String(input?.value || "").trim().toUpperCase();
  if (!code) {
    recordEvent("warn", "Telegram pairing rejection skipped", "Enter a pending pairing code first.", "telegram");
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.telegram_pairing_reject || "/v1/control/channels/telegram/pairing/reject", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Telegram pairing rejection finished",
      summary.ok === false ? String(summary.error || "unknown_error") : `${code} rejected`,
      "telegram",
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-pairing-reject");
  } catch (error) {
    recordEvent("danger", "Telegram pairing rejection failed", error.message, "telegram");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerTelegramPairingRevoke() {
  const input = byId("telegram-approved-entry");
  const button = byId("revoke-telegram-pairing");
  const entry = String(input?.value || "").trim();
  if (!entry) {
    recordEvent("warn", "Telegram pairing revoke skipped", "Enter an approved Telegram entry first.", "telegram");
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.telegram_pairing_revoke || "/v1/control/channels/telegram/pairing/revoke", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ entry }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Telegram pairing revoke finished",
      summary.ok === false ? String(summary.error || "unknown_error") : `${entry} revoked`,
      "telegram",
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-pairing-revoke");
  } catch (error) {
    recordEvent("danger", "Telegram pairing revoke failed", error.message, "telegram");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerTelegramOffsetCommit() {
  const input = byId("telegram-offset-update-id");
  const button = byId("commit-telegram-offset");
  const raw = String(input?.value || "").trim();
  if (!raw) {
    recordEvent("warn", "Telegram offset advance skipped", "Enter a Telegram update_id first.", "telegram");
    return;
  }
  const updateId = Number(raw);
  if (!Number.isInteger(updateId) || updateId < 0) {
    recordEvent("warn", "Telegram offset advance skipped", "Telegram update_id must be a non-negative integer.", "telegram");
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.telegram_offset_commit || "/v1/control/channels/telegram/offset/commit", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ update_id: updateId }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Telegram offset advance finished",
      summary.ok === false ? String(summary.error || "unknown_error") : `watermark committed through update ${updateId}`,
      "telegram",
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-offset-commit");
  } catch (error) {
    recordEvent("danger", "Telegram offset advance failed", error.message, "telegram");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerTelegramOffsetSync() {
  const input = byId("telegram-next-offset");
  const button = byId("sync-telegram-offset");
  const raw = String(input?.value || "").trim();
  if (!raw) {
    recordEvent("warn", "Telegram next offset sync skipped", "Enter a Telegram next_offset first.", "telegram");
    return;
  }
  const nextOffset = Number(raw);
  if (!Number.isInteger(nextOffset) || nextOffset < 0) {
    recordEvent("warn", "Telegram next offset sync skipped", "Telegram next_offset must be a non-negative integer.", "telegram");
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.telegram_offset_sync || "/v1/control/channels/telegram/offset/sync", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ next_offset: nextOffset, allow_reset: false }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Telegram next offset sync finished",
      summary.ok === false ? String(summary.error || "unknown_error") : `next offset synced to ${nextOffset}`,
      "telegram",
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-offset-sync");
  } catch (error) {
    recordEvent("danger", "Telegram next offset sync failed", error.message, "telegram");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerTelegramOffsetReset() {
  const button = byId("reset-telegram-offset");
  const confirmed = typeof window.confirm === "function"
    ? window.confirm("Reset Telegram next_offset to zero? Use this only for deliberate recovery.")
    : true;
  if (!confirmed) {
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.telegram_offset_reset || "/v1/control/channels/telegram/offset/reset", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ confirm: true }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Telegram offset reset finished",
      summary.ok === false ? String(summary.error || "unknown_error") : "next offset reset to zero",
      "telegram",
    );
    await refreshAll("telegram-offset-reset");
  } catch (error) {
    recordEvent("danger", "Telegram offset reset failed", error.message, "telegram");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerHatch() {
  if (!hatchPending()) {
    recordEvent("warn", "Hatch action skipped", "Bootstrap is already settled for this workspace.", "hatch");
    return;
  }
  const hatchSession = hatchSessionId();
  useSession(hatchSession);
  setActiveTab("chat");
  await sendHttpMessageText(HATCH_MESSAGE, {
    sessionId: hatchSession,
    source: "hatch",
  });
  await refreshAll("hatch");
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
  byId("recover-supervisor-component").addEventListener("click", () => {
    void triggerSupervisorRecovery();
  });
  byId("recover-channels").addEventListener("click", () => {
    void triggerChannelRecovery();
  });
  byId("refresh-telegram-transport").addEventListener("click", () => {
    void triggerTelegramRefresh();
  });
  byId("approve-telegram-pairing").addEventListener("click", () => {
    void triggerTelegramPairingApprove();
  });
  byId("reject-telegram-pairing").addEventListener("click", () => {
    void triggerTelegramPairingReject();
  });
  byId("revoke-telegram-pairing").addEventListener("click", () => {
    void triggerTelegramPairingRevoke();
  });
  byId("commit-telegram-offset").addEventListener("click", () => {
    void triggerTelegramOffsetCommit();
  });
  byId("sync-telegram-offset").addEventListener("click", () => {
    void triggerTelegramOffsetSync();
  });
  byId("reset-telegram-offset").addEventListener("click", () => {
    void triggerTelegramOffsetReset();
  });
  byId("replay-inbound-journal").addEventListener("click", () => {
    void triggerInboundReplay();
  });
  byId("replay-dead-letters").addEventListener("click", () => {
    void triggerDeadLetterReplay();
  });
  byId("reconnect-ws").addEventListener("click", () => {
    recordEvent("warn", "WebSocket reconnect requested", "Operator manually restarted the transport.", "transport");
    connectWs();
  });
  byId("trigger-heartbeat").addEventListener("click", () => {
    void triggerHeartbeat();
  });
  byId("trigger-hatch").addEventListener("click", () => {
    void triggerHatch();
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
