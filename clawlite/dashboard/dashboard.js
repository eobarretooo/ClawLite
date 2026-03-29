const bootstrap = window.__CLAWLITE_DASHBOARD_BOOTSTRAP__ || {};
const auth = bootstrap.auth || {};
const paths = bootstrap.paths || {};
const tokenStorageKey = "clawlite.dashboard.token";
const dashboardSessionStorageKey = "clawlite.dashboard.sessionToken";
const dashboardClientStorageKey = "clawlite.dashboard.clientId";
const operatorStorageKey = "clawlite.dashboard.operatorId";
const chatSessionStorageKey = "clawlite.dashboard.chatSessionId";
const refreshStorageKey = "clawlite.dashboard.refreshMs";
const defaultRefreshMs = 15000;
const maxFeedEntries = 18;
const HATCH_MESSAGE = "Wake up, my friend!";

function storageGet(storage, key) {
  try {
    return String(storage && typeof storage.getItem === "function" ? storage.getItem(key) || "" : "");
  } catch (_error) {
    return "";
  }
}

function storageSet(storage, key, value) {
  try {
    if (storage && typeof storage.setItem === "function") {
      storage.setItem(key, String(value || ""));
    }
  } catch (_error) {
    // Ignore browser storage failures and keep the dashboard usable.
  }
}

function storageRemove(storage, key) {
  try {
    if (storage && typeof storage.removeItem === "function") {
      storage.removeItem(key);
    }
  } catch (_error) {
    // Ignore browser storage failures and keep the dashboard usable.
  }
}

function storedDashboardToken() {
  const current = storageGet(window.sessionStorage, tokenStorageKey).trim();
  if (current) {
    return current;
  }
  const legacy = storageGet(window.localStorage, tokenStorageKey).trim();
  if (!legacy) {
    return "";
  }
  storageSet(window.sessionStorage, tokenStorageKey, legacy);
  storageRemove(window.localStorage, tokenStorageKey);
  return legacy;
}

function storedDashboardSessionToken() {
  return storageGet(window.sessionStorage, dashboardSessionStorageKey).trim();
}

function createDashboardClientId() {
  const randomId =
    window.crypto && typeof window.crypto.randomUUID === "function"
      ? window.crypto.randomUUID().replace(/-/g, "").slice(0, 20)
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
  return `dshc1.${randomId}`;
}

function ensureDashboardClientId() {
  const current = storageGet(window.sessionStorage, dashboardClientStorageKey).trim();
  if (current) {
    return current;
  }
  const generated = createDashboardClientId();
  storageSet(window.sessionStorage, dashboardClientStorageKey, generated);
  return generated;
}

function createDashboardOperatorId() {
  const randomId =
    window.crypto && typeof window.crypto.randomUUID === "function"
      ? window.crypto.randomUUID().replace(/-/g, "").slice(0, 12)
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `dashboard:operator:${randomId}`;
}

function ensureDashboardOperatorId() {
  const current = storageGet(window.sessionStorage, operatorStorageKey).trim();
  if (current) {
    return current;
  }
  const generated = createDashboardOperatorId();
  storageSet(window.sessionStorage, operatorStorageKey, generated);
  return generated;
}

function ensureChatSessionId(defaultSessionId) {
  const current = storageGet(window.sessionStorage, chatSessionStorageKey).trim();
  if (current) {
    return current;
  }
  const fallback = String(defaultSessionId || "").trim();
  if (fallback) {
    storageSet(window.sessionStorage, chatSessionStorageKey, fallback);
  }
  return fallback;
}

const state = {
  activeTab: "overview",
  token: storedDashboardToken(),
  dashboardSessionToken: storedDashboardSessionToken(),
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
  providerStatus: null,
  toolApprovals: null,
  toolApprovalAudit: null,
  skillsManaged: null,
  memoryDoctor: null,
  memoryOverview: null,
  memoryQuality: null,
  tokenInfo: null,
  lastSyncAt: null,
  eventFeed: [],
  wsPreview: "Waiting for live websocket frames...",
  lastObservedGatewayWsOpenedAt: "",
  lastObservedGatewayWsErrorAt: "",
  lastObservedGatewayHttpErrorAt: "",
  dashboardClientId: ensureDashboardClientId(),
  operatorId: ensureDashboardOperatorId(),
  sessionId: "",
};
state.sessionId = ensureChatSessionId(state.operatorId) || state.operatorId;

function dashboardSessionHeaderName() {
  return String(auth.dashboard_session_header_name || "X-ClawLite-Dashboard-Session").trim() || "X-ClawLite-Dashboard-Session";
}

function dashboardSessionQueryParam() {
  return String(auth.dashboard_session_query_param || "dashboard_session").trim() || "dashboard_session";
}

function dashboardClientHeaderName() {
  return String(auth.dashboard_client_header_name || "X-ClawLite-Dashboard-Client").trim() || "X-ClawLite-Dashboard-Client";
}

function dashboardClientQueryParam() {
  return String(auth.dashboard_client_query_param || "dashboard_client").trim() || "dashboard_client";
}

function dashboardHandoffHeaderName() {
  return String(auth.dashboard_handoff_header_name || "X-ClawLite-Dashboard-Handoff").trim() || "X-ClawLite-Dashboard-Handoff";
}

function dashboardHandoffQueryParam() {
  return String(auth.dashboard_handoff_query_param || "dashboard_handoff").trim() || "dashboard_handoff";
}

function rawAuthHeaders(tokenValue) {
  const token = String(tokenValue || "").trim();
  if (!token) {
    return {};
  }
  const headerName = auth.header_name || "Authorization";
  const value = headerName.toLowerCase() === "authorization" ? `Bearer ${token}` : token;
  return { [headerName]: value };
}

function byId(id) {
  return document.getElementById(id);
}

function safeJson(value) {
  return JSON.stringify(value, null, 2);
}

function authHeaders() {
  if (state.dashboardSessionToken) {
    return {
      [dashboardSessionHeaderName()]: state.dashboardSessionToken,
      [dashboardClientHeaderName()]: state.dashboardClientId,
    };
  }
  if (!state.token) {
    return {};
  }
  return rawAuthHeaders(state.token);
}

function dashboardCredentialFromLocationHash() {
  const raw = String(window.location.hash || "").replace(/^#/, "").trim();
  if (!raw) {
    return { token: "", handoff: "" };
  }
  const params = new URLSearchParams(raw);
  return {
    token: String(params.get("token") || "").trim(),
    handoff: String(params.get("handoff") || "").trim(),
  };
}

function buildWsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${protocol}//${window.location.host}${paths.ws || "/ws"}`);
  if (state.dashboardSessionToken) {
    url.searchParams.set(dashboardSessionQueryParam(), state.dashboardSessionToken);
    url.searchParams.set(dashboardClientQueryParam(), state.dashboardClientId);
  } else if (state.token) {
    url.searchParams.set(auth.query_param || "token", state.token);
  }
  return url.toString();
}

function persistChatSession(nextSessionId) {
  const sessionId = String(nextSessionId || "").trim() || state.operatorId;
  state.sessionId = sessionId;
  storageSet(window.sessionStorage, chatSessionStorageKey, sessionId);
  return sessionId;
}

function persistDashboardSession(nextToken) {
  state.dashboardSessionToken = String(nextToken || "").trim();
  if (state.dashboardSessionToken) {
    storageSet(window.sessionStorage, dashboardSessionStorageKey, state.dashboardSessionToken);
  } else {
    storageRemove(window.sessionStorage, dashboardSessionStorageKey);
  }
}

function currentChatSessionId(fallback = state.sessionId) {
  const input = byId("session-input");
  const typed = input && typeof input.value === "string" ? input.value.trim() : "";
  return persistChatSession(typed || fallback || state.operatorId);
}

function buildDashboardChatPayload(sessionId, text) {
  return {
    session_id: sessionId,
    text,
  };
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

function parseTimestampMs(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return 0;
  }
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function numeric(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function truncateText(value, maxLength = 96) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;
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

function attachResponseMeta(payload, meta) {
  if (!payload || typeof payload !== "object") {
    return payload;
  }
  try {
    Object.defineProperty(payload, "__clawliteMeta", {
      value: meta || {},
      configurable: true,
      enumerable: false,
      writable: true,
    });
  } catch (_error) {
    // Ignore metadata decoration failures and keep the parsed payload usable.
  }
  return payload;
}

function requestIdFromValue(value) {
  if (!value || (typeof value !== "object" && typeof value !== "function")) {
    return "";
  }
  const meta = value.__clawliteMeta || {};
  return String(value.requestId || value.request_id || meta.requestId || "").trim();
}

function appendRequestIdMeta(meta, value) {
  const base = String(meta || "").trim();
  const requestId = requestIdFromValue(value);
  if (!requestId) {
    return base;
  }
  return base ? `${base} | req ${requestId}` : `req ${requestId}`;
}

function readManagedSkillsFilter() {
  return {
    status: String(byId("managed-skills-status-filter")?.value || "").trim(),
    query: String(byId("managed-skills-query-filter")?.value || "").trim(),
  };
}

function summarizeManagedFilter(summary) {
  const status = String((summary || {}).status_filter || "").trim();
  const query = String((summary || {}).query || "").trim();
  const parts = [];
  if (status) {
    parts.push(`status ${status}`);
  }
  if (query) {
    parts.push(`query ${query}`);
  }
  return parts.join(" | ");
}

function readToolApprovalsFilter() {
  const status = String(byId("tool-approvals-status-filter")?.value || "").trim().toLowerCase();
  return {
    status: status || "pending",
    tool: String(byId("tool-approvals-tool-filter")?.value || "").trim(),
    rule: String(byId("tool-approvals-rule-filter")?.value || "").trim(),
  };
}

function summarizeToolApprovalsFilter(summary) {
  const status = String((summary || {}).status || "").trim().toLowerCase();
  const tool = String((summary || {}).tool || "").trim();
  const rule = String((summary || {}).rule || "").trim();
  const parts = [];
  if (status) {
    parts.push(`status ${status}`);
  }
  if (tool) {
    parts.push(`tool ${tool}`);
  }
  if (rule) {
    parts.push(`rule ${rule}`);
  }
  return parts.join(" | ");
}

function readToolApprovalAuditFilter() {
  const action = String(byId("tool-approval-audit-action-filter")?.value || "").trim().toLowerCase();
  const requestId = String(byId("tool-approval-audit-request-id")?.value || "").trim();
  const approvals = readToolApprovalsFilter();
  return {
    action: action && action !== "all" ? action : "",
    request_id: requestId,
    tool: approvals.tool,
    rule: approvals.rule,
  };
}

function summarizeToolApprovalAuditFilter(summary) {
  const action = String((summary || {}).action || "").trim().toLowerCase();
  const requestId = String((summary || {}).request_id || "").trim();
  const tool = String((summary || {}).tool || "").trim();
  const rule = String((summary || {}).rule || "").trim();
  const parts = [];
  if (action) {
    parts.push(`action ${action}`);
  }
  if (requestId) {
    parts.push(`request ${requestId}`);
  }
  if (tool) {
    parts.push(`tool ${tool}`);
  }
  if (rule) {
    parts.push(`rule ${rule}`);
  }
  return parts.join(" | ");
}

function approvalRuleLabel(row) {
  const matched = Array.isArray((row || {}).matched_approval_specifiers) ? row.matched_approval_specifiers : [];
  return String(matched[0] || row?.rule || "").trim();
}

function approvalToolLabel(row) {
  const direct = String((row || {}).tool || "").trim();
  if (direct) {
    return direct;
  }
  const rule = String((row || {}).rule || approvalRuleLabel(row)).trim();
  if (!rule) {
    return "";
  }
  return String(rule.split(":", 1)[0] || "").trim();
}

function actionableApprovalRequests(rows) {
  return (Array.isArray(rows) ? rows : []).filter(
    (row) => String(row?.request_id || "").trim() && String(row?.status || "").trim().toLowerCase() === "pending",
  );
}

function actionableApprovalGrants(rows) {
  return (Array.isArray(rows) ? rows : []).filter((row) => {
    return Boolean(
      String(row?.session_id || "").trim()
      && String(row?.channel || "").trim()
      && String(row?.rule || "").trim()
      && String(row?.request_id || "").trim()
      && String(row?.scope || "").trim().toLowerCase() === "exact",
    );
  });
}

function populateToolApprovalSelection(rows, options = {}) {
  const input = byId("tool-approval-request-id");
  if (!input) {
    return "";
  }
  const actionable = actionableApprovalRequests(rows);
  const current = String(input.value || "").trim();
  const currentStillVisible = actionable.some((row) => String(row?.request_id || "").trim() === current);
  const top = String((actionable[0] || {}).request_id || "").trim();
  if ((options.force || !current || !currentStillVisible) && top) {
    input.value = top;
    return top;
  }
  if (!currentStillVisible && !top) {
    input.value = "";
    return "";
  }
  return currentStillVisible ? current : top;
}

function approvalContextSummary(row) {
  const context = (row && typeof row === "object" && row.approval_context && typeof row.approval_context === "object")
    ? row.approval_context
    : {};
  const parts = [];
  if (context.command_binary) {
    parts.push(`binary ${String(context.command_binary).trim()}`);
  }
  if (Array.isArray(context.env_keys) && context.env_keys.length) {
    parts.push(`env ${context.env_keys.length}`);
  }
  if (context.cwd) {
    parts.push(`cwd ${String(context.cwd).trim()}`);
  }
  if (context.action) {
    parts.push(`action ${String(context.action).trim()}`);
  }
  if (context.method) {
    parts.push(`method ${String(context.method).trim()}`);
  }
  if (context.host) {
    parts.push(`host ${String(context.host).trim()}`);
  }
  if (context.name) {
    parts.push(`skill ${String(context.name).trim()}`);
  }
  if (!parts.length && context.command_text) {
    parts.push(`cmd ${String(context.command_text).trim().slice(0, 48)}`);
  }
  if (!parts.length && context.url) {
    parts.push(`url ${String(context.url).trim().slice(0, 48)}`);
  }
  return parts.slice(0, 3).join(" | ");
}

function grantSelectionValue(row) {
  return [
    String(row?.request_id || "").trim(),
    String(row?.session_id || "").trim(),
    String(row?.channel || "").trim(),
    String(row?.rule || "").trim(),
    String(row?.scope || "").trim(),
  ].join("::");
}

function grantSelectionLabel(row) {
  const requestId = String(row?.request_id || "").trim();
  const shortRequestId = requestId ? requestId.slice(0, 8) : "grant";
  return [
    `req ${shortRequestId}`,
    approvalToolLabel(row) || "grant",
    String(row?.rule || "").trim(),
    String(row?.session_id || "").trim(),
  ].filter(Boolean).join(" | ");
}

function selectedToolGrant(rows) {
  const select = byId("tool-grant-selection");
  const actionable = actionableApprovalGrants(rows);
  if (!select) {
    return actionable[0] || null;
  }
  const current = String(select.value || "").trim();
  return actionable.find((row) => grantSelectionValue(row) === current) || actionable[0] || null;
}

function populateToolGrantSelection(rows, options = {}) {
  const select = byId("tool-grant-selection");
  const actionable = actionableApprovalGrants(rows);
  if (!select) {
    return actionable[0] || null;
  }
  const current = String(select.value || "").trim();
  const currentStillVisible = actionable.some((row) => grantSelectionValue(row) === current);
  const selectedValue = ((options.force || !current || !currentStillVisible) && actionable.length)
    ? grantSelectionValue(actionable[0])
    : currentStillVisible
      ? current
      : "";

  select.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = actionable.length ? "Select exact grant" : "No exact grant visible";
  select.appendChild(placeholder);

  actionable.forEach((row) => {
    const option = document.createElement("option");
    option.value = grantSelectionValue(row);
    option.textContent = grantSelectionLabel(row);
    select.appendChild(option);
  });

  select.value = selectedValue;
  if (!select.value && actionable.length) {
    select.value = grantSelectionValue(actionable[0]);
  }
  return selectedToolGrant(actionable);
}

function summarizeWsCorrelation(ws, includeRequest = true, options = {}) {
  const parts = [];
  const connectionId = String(
    options.connectionId !== undefined ? options.connectionId : (ws.last_error_connection_id || ws.last_connection_id || ""),
  ).trim();
  const requestId = String(
    options.requestId !== undefined ? options.requestId : (ws.last_error_request_id || ws.last_request_id || ""),
  ).trim();
  if (connectionId) {
    parts.push(`conn ${connectionId}`);
  }
  if (includeRequest && requestId) {
    parts.push(`req ${requestId}`);
  }
  return parts.join(" | ");
}

function syncGatewayWsEvents() {
  const ws = ((state.dashboardState || {}).ws) || {};
  const lastOpenedAt = String(ws.last_connection_opened_at || "").trim();
  const lastErrorAt = String(ws.last_error_at || "").trim();

  if (lastOpenedAt && lastOpenedAt !== state.lastObservedGatewayWsOpenedAt) {
    const detail = `${String(ws.last_connection_path || "/v1/ws")} opened`;
    recordEvent(
      "ok",
      "Gateway WebSocket observed",
      detail,
      summarizeWsCorrelation(ws, false, { connectionId: ws.last_connection_id, requestId: "" }) || "gateway",
    );
    state.lastObservedGatewayWsOpenedAt = lastOpenedAt;
  }

  if (lastErrorAt && lastErrorAt !== state.lastObservedGatewayWsErrorAt) {
    const code = String(ws.last_error_code || "ws_error");
    const message = String(ws.last_error_message || "gateway websocket error").trim();
    const status = Number(ws.last_error_status);
    const level = Number.isFinite(status) && status >= 500 ? "danger" : "warn";
    const detail = `${code}: ${message}`;
    recordEvent(
      level,
      "Gateway WebSocket error observed",
      detail,
      summarizeWsCorrelation(ws, true, {
        connectionId: ws.last_error_connection_id,
        requestId: ws.last_error_request_id,
      }) || "gateway",
    );
    state.lastObservedGatewayWsErrorAt = lastErrorAt;
  }
}

function syncGatewayHttpEvents() {
  const http = ((state.diagnostics || {}).http) || {};
  const lastErrorAt = String(http.last_error_at || "").trim();
  if (!lastErrorAt || lastErrorAt === state.lastObservedGatewayHttpErrorAt) {
    return;
  }
  const method = String(http.last_error_method || "HTTP").trim() || "HTTP";
  const path = String(http.last_error_path || "/").trim() || "/";
  const status = Number(http.last_error_status);
  const code = String(http.last_error_code || "http_error").trim() || "http_error";
  const message = String(http.last_error_message || "").trim();
  const detailParts = [`${method} ${path}`, Number.isFinite(status) ? `status ${status}` : code];
  if (code && (!Number.isFinite(status) || code !== `http_${status}`)) {
    detailParts.push(code);
  }
  if (message && message !== code) {
    detailParts.push(message);
  }
  const level = Number.isFinite(status) && status >= 500 ? "danger" : "warn";
  recordEvent(
    level,
    "Gateway HTTP error observed",
    detailParts.join(" | "),
    appendRequestIdMeta("gateway", { request_id: http.last_error_request_id }),
  );
  state.lastObservedGatewayHttpErrorAt = lastErrorAt;
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
  const signalsNode = byId("tool-signals");
  const groupsNode = byId("tool-groups");
  const aliasesNode = byId("tool-aliases");
  if (!signalsNode || !groupsNode || !aliasesNode) {
    return;
  }
  signalsNode.innerHTML = "";
  groupsNode.innerHTML = "";
  aliasesNode.innerHTML = "";

  const tools = state.tools || {};
  const groups = Array.isArray(tools.groups) ? tools.groups : [];
  const aliases = tools.aliases && typeof tools.aliases === "object" ? tools.aliases : {};
  const summary = tools.summary && typeof tools.summary === "object" ? tools.summary : {};
  const wsMethods = Array.isArray(tools.ws_methods) ? tools.ws_methods : [];
  const largestGroup = summary.largest_group && typeof summary.largest_group === "object" ? summary.largest_group : {};
  const derivedCacheableCount = groups.reduce((total, group) => {
    const toolsInGroup = Array.isArray(group.tools) ? group.tools : [];
    return total + toolsInGroup.filter((tool) => Boolean(tool && tool.cacheable)).length;
  }, 0);
  const derivedCustomTimeoutCount = groups.reduce((total, group) => {
    const toolsInGroup = Array.isArray(group.tools) ? group.tools : [];
    return total + toolsInGroup.filter((tool) => tool && tool.default_timeout_s != null).length;
  }, 0);
  const derivedLargestGroup = groups.reduce(
    (best, group) => {
      const count = numeric(group.count, Array.isArray(group.tools) ? group.tools.length : 0);
      if (count > best.count) {
        return {
          label: String(group.label || group.name || group.group || "group"),
          count,
        };
      }
      return best;
    },
    { label: "", count: 0 },
  );

  const signalCards = [
    {
      title: "Catalog shape",
      body: `${numeric(summary.group_count, groups.length)} groups`,
      detail: `${numeric(summary.alias_count, Object.keys(aliases).length)} aliases`,
    },
    {
      title: "Transport methods",
      body: `${numeric(summary.ws_method_count, wsMethods.length)} WebSocket methods`,
      detail: wsMethods.slice(0, 3).join(", ") || "No WebSocket methods exported.",
    },
    {
      title: "Cacheable tools",
      body: `${numeric(summary.cacheable_count, derivedCacheableCount)} cacheable`,
      detail: `${numeric(summary.custom_timeout_count, derivedCustomTimeoutCount)} tools publish a custom timeout`,
    },
    {
      title: "Largest group",
      body: String(largestGroup.label || derivedLargestGroup.label || "unknown"),
      detail: `${numeric(largestGroup.count, derivedLargestGroup.count)} tools`,
    },
  ];
  signalCards.forEach((item) => appendSummaryCard(signalsNode, item));

  groups.slice(0, 12).forEach((group) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    const title = document.createElement("span");
    title.className = "summary-card__title";
    title.textContent = String(group.label || group.name || group.group || "group");
    const meta = document.createElement("div");
    meta.className = "summary-card__meta";
    const toolsInGroup = Array.isArray(group.tools) ? group.tools : [];
    const cacheableCount = toolsInGroup.filter((tool) => Boolean(tool && tool.cacheable)).length;
    const timeoutCount = toolsInGroup.filter((tool) => tool && tool.default_timeout_s != null).length;
    meta.textContent = `${numeric(group.count, toolsInGroup.length)} tools`;
    const detail = document.createElement("div");
    detail.className = "summary-card__meta";
    detail.textContent = `${numeric(cacheableCount, 0)} cacheable | ${numeric(timeoutCount, 0)} custom timeouts`;
    card.append(title, meta, detail);
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

function renderToolApprovalsSummary() {
  const grid = byId("tool-approvals-grid");
  const preview = byId("tool-approvals-preview");
  const approveButton = byId("approve-tool-request");
  const rejectButton = byId("reject-tool-request");
  const revokeGrantButton = byId("revoke-tool-grant");
  const grantSelect = byId("tool-grant-selection");
  if (!grid || !preview) {
    return;
  }
  grid.innerHTML = "";

  const approvals = state.toolApprovals || null;
  if (!approvals) {
    appendSummaryCard(grid, {
      title: "Approval queue",
      body: "idle",
      detail: "Run Inspect approvals to fetch the live tool approval queue and active grants.",
    });
    setBadge("tool-approvals-status", "idle", "warn");
    setCode("tool-approvals-preview", { note: "Run Inspect approvals to fetch the live approval queue." });
    if (approveButton) {
      approveButton.disabled = true;
    }
    if (rejectButton) {
      rejectButton.disabled = true;
    }
    if (revokeGrantButton) {
      revokeGrantButton.disabled = true;
    }
    if (grantSelect) {
      grantSelect.innerHTML = '<option value="">No exact grant visible</option>';
      grantSelect.disabled = true;
    }
    return;
  }

  const requests = Array.isArray(approvals.requests) ? approvals.requests : [];
  const grants = Array.isArray(approvals.grants) ? approvals.grants : [];
  const actionable = actionableApprovalRequests(requests);
  const actionableGrants = actionableApprovalGrants(grants);
  const pendingVisible = requests.filter((row) => String(row?.status || "").trim().toLowerCase() === "pending").length;
  const toolsInQueue = new Set(
    requests
      .map((row) => String(row?.tool || "").trim())
      .filter(Boolean),
  );
  const rulesInQueue = new Set(
    requests
      .flatMap((row) => {
        const rule = approvalRuleLabel(row);
        return rule ? [rule] : [];
      })
      .concat(grants.map((row) => String(row?.rule || "").trim()).filter(Boolean)),
  );
  const actorBoundCount = requests.filter((row) => String(row?.requester_actor || "").trim()).length;
  const notifiedCount = requests.filter((row) => numeric(row?.notified_count, 0) > 0).length;
  const filterMeta = summarizeToolApprovalsFilter(approvals);
  const firstRequest = requests[0] || {};
  const selectedGrant = populateToolGrantSelection(grants) || null;
  const firstRequestRule = approvalRuleLabel(firstRequest);
  const firstRequestContext = approvalContextSummary(firstRequest);

  appendSummaryCard(grid, {
    title: "Queue",
    body: `${numeric(approvals.count, requests.length)} requests | ${numeric(approvals.grant_count, grants.length)} grants`,
    detail: filterMeta || "live approval queue snapshot",
  });
  appendSummaryCard(grid, {
    title: "Scope",
    body: `${toolsInQueue.size} tools | ${rulesInQueue.size} rules`,
    detail: `${actorBoundCount} actor-bound | ${notifiedCount} notified`,
  });
  appendSummaryCard(grid, {
    title: "Top request",
    body: requests.length
      ? `${String(firstRequest.tool || "tool")} | ${firstRequestRule || String(firstRequest.status || "pending")}`
      : "none",
    detail: requests.length
      ? [
          String(firstRequest.session_id || "session unknown"),
          `expires ${formatDuration(firstRequest.expires_in_s || 0)}`,
          String(firstRequest.requester_actor || ""),
          firstRequestContext,
        ].filter(Boolean).join(" | ")
      : "No approval requests matched the current live filter.",
  });
  appendSummaryCard(grid, {
    title: "Selected grant",
    body: selectedGrant
      ? `${approvalToolLabel(selectedGrant) || "grant"} | ${String(selectedGrant.rule || "rule")}`
      : "none",
    detail: selectedGrant
      ? [
          `req ${String(selectedGrant.request_id || "").trim().slice(0, 8) || "unknown"}`,
          `expires ${formatDuration(selectedGrant.expires_in_s || 0)}`,
          String(selectedGrant.scope || ""),
          String(selectedGrant.channel || ""),
          String(selectedGrant.session_id || "session unknown"),
        ].filter(Boolean).join(" | ")
      : grants.length
        ? "No exact grant can be selected from the current live filter."
        : "No active approval grants matched the current live filter.",
  });

  if (pendingVisible > 0) {
    setBadge("tool-approvals-status", `pending ${pendingVisible}`, "warn");
  } else if (numeric(approvals.grant_count, grants.length) > 0) {
    setBadge("tool-approvals-status", `grants ${numeric(approvals.grant_count, grants.length)}`, "ok");
  } else if (numeric(approvals.count, requests.length) > 0) {
    setBadge("tool-approvals-status", `${numeric(approvals.count, requests.length)} ${String(approvals.status || "items")}`, "ok");
  } else {
    setBadge("tool-approvals-status", "clear", "ok");
  }
  populateToolApprovalSelection(requests);
  if (approveButton) {
    approveButton.disabled = actionable.length <= 0;
  }
  if (rejectButton) {
    rejectButton.disabled = actionable.length <= 0;
  }
  if (revokeGrantButton) {
    revokeGrantButton.disabled = actionableGrants.length <= 0;
  }
  if (grantSelect) {
    grantSelect.disabled = actionableGrants.length <= 0;
  }
  setCode("tool-approvals-preview", approvals);
}

function renderToolApprovalAuditSummary() {
  const grid = byId("tool-approval-audit-grid");
  const preview = byId("tool-approval-audit-preview");
  if (!grid || !preview) {
    return;
  }
  grid.innerHTML = "";

  const audit = state.toolApprovalAudit || null;
  if (!audit) {
    appendSummaryCard(grid, {
      title: "Approval audit",
      body: "idle",
      detail: "Run Inspect audit to fetch recent approval review and grant revoke rows.",
    });
    setBadge("tool-approval-audit-status", "idle", "warn");
    setCode("tool-approval-audit-preview", { note: "Run Inspect audit to fetch recent approval audit rows." });
    return;
  }

  const entries = Array.isArray(audit.entries) ? audit.entries : [];
  const actionCounts = audit.action_counts && typeof audit.action_counts === "object" ? audit.action_counts : {};
  const statusCounts = audit.status_counts && typeof audit.status_counts === "object" ? audit.status_counts : {};
  const requestHistory = Array.isArray(audit.request_history) ? audit.request_history : [];
  const latest = entries[0] || {};
  const latestAction = String(latest.action || "").trim() || "unknown";
  const latestStatus = String(latest.status || "").trim() || "unknown";
  const latestTool = approvalToolLabel(latest) || "tool";
  const latestRule = approvalRuleLabel(latest);
  const latestRequestId = String(latest.request_id || "").trim();
  const latestTarget = [
    latestTool,
    latestRule,
    String(latest.scope || "").trim(),
    latestRequestId,
  ].filter(Boolean).join(" | ");
  const filterMeta = summarizeToolApprovalAuditFilter(audit);
  const errorCount = numeric(audit.error_count, 0);
  const latestReason = String(audit.latest_reason || latest.reason_summary || "").trim();
  const latestReasonSource = String(audit.latest_reason_source || latest.reason_source || "").trim();
  const requestHistoryRequestId = String(audit.request_history_request_id || "").trim();
  const historyPreview = requestHistory.slice(0, 3).map((row) => {
    const reason = String((row || {}).reason_summary || "").trim();
    const source = String((row || {}).reason_source || "").trim();
    const action = String((row || {}).action || "").trim();
    const status = String((row || {}).status || "").trim();
    return [action, status, source, reason].filter(Boolean).join(" | ");
  }).filter(Boolean).join(" || ");
  const badgeTone = errorCount > 0 ? "warn" : entries.length ? "ok" : "warn";

  appendSummaryCard(grid, {
    title: "Trail",
    body: `${numeric(audit.count, entries.length)} rows`,
    detail: filterMeta || "live approval/grant audit snapshot",
  });
  appendSummaryCard(grid, {
    title: "Changes",
    body: `${numeric(audit.changed_count, 0)} changed`,
    detail: `${numeric(audit.unchanged_count, 0)} unchanged | ${errorCount} with error`,
  });
  appendSummaryCard(grid, {
    title: "Actions",
    body: `${numeric(actionCounts.review, 0)} reviews | ${numeric(actionCounts.revoke_grant, 0)} revokes`,
    detail: Object.entries(statusCounts).map(([name, count]) => `${name} ${count}`).join(" | ") || "No status counts yet.",
  });
  appendSummaryCard(grid, {
    title: "Latest",
    body: `${latestAction} | ${latestStatus}`,
    detail: latestTarget || "No recent audit row.",
  });
  appendSummaryCard(grid, {
    title: "Request drill-down",
    body: latestRequestId || String(audit.request_id || "").trim() || "none",
    detail: String(audit.request_id || "").trim() ? "active request filter" : "Showing mixed recent request history.",
  });
  appendSummaryCard(grid, {
    title: "Latest reason",
    body: latestReasonSource || "none",
    detail: latestReason || "No explicit note/error/reason was recorded for the latest visible audit row.",
  });
  appendSummaryCard(grid, {
    title: "Reason history",
    body: `${numeric(audit.request_history_count, requestHistory.length)} rows`,
    detail: requestHistoryRequestId
      ? [requestHistoryRequestId, historyPreview || "No request-scoped reason history found."].filter(Boolean).join(" | ")
      : "Set a request id to inspect bounded review/revoke reason history for one request lineage.",
  });

  setBadge("tool-approval-audit-status", entries.length ? `${entries.length} rows` : "empty", badgeTone);
  setCode("tool-approval-audit-preview", audit);
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

function renderRuntimePostureBoard() {
  const grid = byId("runtime-posture-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const runtime = ((state.dashboardState || {}).runtime) || {};
  const posture = runtime.posture || {};
  const autonomy = posture.autonomy || {};
  const autonomyWake = posture.autonomy_wake || {};
  const evolution = posture.self_evolution || {};
  const supervisor = posture.supervisor || {};
  const cards = [];

  if (!Object.keys(posture).length) {
    appendSummaryCard(grid, {
      title: "Runtime posture",
      body: "not available",
      detail: "No compact posture snapshot is available yet.",
    });
    setBadge("runtime-posture-status", "pending", "warn");
    return;
  }

  cards.push({
    title: "Autonomy loop",
    body: `${String(posture.autonomy_posture || "unknown")} | ${String(autonomy.session_id || "autonomy:system")}`,
    detail: [
      autonomy.last_error ? String(autonomy.last_error) : String(autonomy.last_result_excerpt || "").trim(),
      autonomy.no_progress_reason
        ? `no-progress ${String(autonomy.no_progress_reason)} x${numeric(autonomy.no_progress_streak, 0)}`
        : "",
      autonomy.provider_backoff_remaining_s
        ? `provider backoff ${formatDuration(autonomy.provider_backoff_remaining_s)}`
        : (autonomy.cooldown_remaining_s ? `cooldown ${formatDuration(autonomy.cooldown_remaining_s)}` : ""),
    ].filter(Boolean).join(" | ") || "Autonomy loop is steady.",
  });

  cards.push({
    title: "Wake coordinator",
    body: `${String(posture.wake_posture || "unknown")} | ${numeric(autonomyWake.queue_depth, 0)} queued`,
    detail: [
      `${numeric(autonomyWake.pending_count, 0)} pending`,
      `${numeric(autonomyWake.dropped_backpressure, 0)} backpressure drops`,
      `${numeric(autonomyWake.dropped_quota, 0)} quota drops`,
      String(autonomyWake.last_error || "").trim(),
    ].filter(Boolean).join(" | ") || "No wake pressure recorded yet.",
  });

  cards.push({
    title: "Change review",
    body: `${String(posture.approval_posture || "unknown")} | ${String(evolution.activation_mode || "disabled")}`,
    detail: [
      evolution.enabled ? "engine enabled" : "engine disabled",
      evolution.background_enabled ? "background enabled" : "background disabled",
      evolution.enabled_for_sessions_count ? `${numeric(evolution.enabled_for_sessions_count, 0)} canary sessions` : "",
      evolution.last_review_status ? `review ${String(evolution.last_review_status)}` : "",
      evolution.cooldown_remaining_s ? `cooldown ${formatDuration(evolution.cooldown_remaining_s)}` : "",
    ].filter(Boolean).join(" | ") || "No self-evolution review posture available.",
  });

  cards.push({
    title: "Runtime hint",
    body: String(posture.operator_hint || "Runtime posture looks steady."),
    detail: [
      String(supervisor.worker_state || "").trim(),
      numeric(supervisor.incident_count, 0) ? `${numeric(supervisor.incident_count, 0)} supervisor incidents` : "",
      numeric(supervisor.consecutive_error_count, 0) ? `${numeric(supervisor.consecutive_error_count, 0)} consecutive supervisor errors` : "",
    ].filter(Boolean).join(" | "),
  });

  cards.forEach((item) => appendSummaryCard(grid, item));

  const statusLabel = String(posture.summary_posture || posture.wake_posture || posture.autonomy_posture || "unknown");
  const tone = String(posture.summary_tone || "").trim() || (
    ["running", "ready", "idle", "direct_commit"].includes(statusLabel)
      ? "ok"
      : (["disabled", "cooldown", "busy", "no_progress_backoff", "stopped", "approval_required"].includes(statusLabel)
        ? "warn"
        : "danger")
  );
  setBadge("runtime-posture-status", statusLabel, tone);
}

function renderRuntimePolicyBoard() {
  const grid = byId("runtime-policy-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const runtime = ((state.dashboardState || {}).runtime) || {};
  const policy = runtime.policy || {};
  const evolution = policy.self_evolution || {};
  const drift = (policy.drift && typeof policy.drift === "object") ? policy.drift : {};
  const driftConfigured = (drift.configured && typeof drift.configured === "object") ? drift.configured : {};
  const driftEffective = (drift.effective && typeof drift.effective === "object") ? drift.effective : {};
  const cards = [];

  if (!Object.keys(policy).length) {
    appendSummaryCard(grid, {
      title: "Runtime policy",
      body: "not available",
      detail: "No compact runtime policy snapshot is available yet.",
    });
    setBadge("runtime-policy-status", "pending", "warn");
    return;
  }

  cards.push({
    title: "Review gate",
    body: `${String(policy.approval_mode || "unknown")} | ${String(policy.activation_scope || "unknown")}`,
    detail: [
      evolution.enabled ? "engine enabled" : "engine disabled",
      evolution.background_enabled ? "background enabled" : "background disabled",
      evolution.last_review_status ? `review ${String(evolution.last_review_status)}` : "",
      evolution.cooldown_remaining_s ? `cooldown ${formatDuration(evolution.cooldown_remaining_s)}` : "",
    ].filter(Boolean).join(" | ") || "No runtime review policy available.",
  });

  cards.push({
    title: "Canary scope",
    body: `${numeric(evolution.enabled_for_sessions_count, 0)} allowlisted | ${String(evolution.autonomy_session_id || "unbound")}`,
    detail: [
      evolution.current_session_allowed ? "current session allowed" : "current session blocked",
      Array.isArray(evolution.enabled_for_sessions_sample) && evolution.enabled_for_sessions_sample.length
        ? `sample ${evolution.enabled_for_sessions_sample.map((value) => String(value)).join(", ")}`
        : "",
    ].filter(Boolean).join(" | ") || "No canary scope is configured.",
  });

  cards.push({
    title: "Policy block",
    body: `${String(policy.policy_posture || "unknown")} | ${String(policy.policy_block || "none")}`,
    detail: [
      String(evolution.activation_reason || "").trim(),
      !evolution.activation_reason ? "No active policy block." : "",
    ].filter(Boolean).join(" | "),
  });

  cards.push({
    title: "Policy hint",
    body: String(policy.policy_hint || "Runtime policy looks steady."),
    detail: [
      evolution.require_approval ? "approval before merge" : "no approval gate",
      String(policy.policy_tone || "").trim(),
    ].filter(Boolean).join(" | "),
  });

  cards.push({
    title: "Policy drift",
    body: `${String(drift.posture || "unknown")} | ${String(drift.reason || "aligned")}`,
    detail: [
      `${String(driftConfigured.activation_scope || "unknown")} -> ${String(driftEffective.activation_scope || "unknown")}`,
      Object.prototype.hasOwnProperty.call(driftConfigured, "require_approval")
        ? `${Boolean(driftConfigured.require_approval) ? "approval" : "direct"} -> ${Boolean(driftEffective.require_approval) ? "approval" : "direct"}`
        : "",
      String(drift.hint || "").trim(),
    ].filter(Boolean).join(" | ") || "No runtime policy drift snapshot is available.",
  });

  cards.forEach((item) => appendSummaryCard(grid, item));

  let statusLabel = String(policy.policy_posture || policy.approval_mode || "unknown");
  let tone = String(policy.policy_tone || "").trim() || (
    ["direct_commit"].includes(statusLabel)
      ? "ok"
      : (["approval_required", "manual_only", "session_canary", "blocked", "disabled"].includes(statusLabel)
        ? "warn"
        : "danger")
  );
  const toneSeverity = (value) => {
    const normalized = String(value || "").trim();
    if (normalized === "danger") {
      return 3;
    }
    if (normalized === "warn") {
      return 2;
    }
    if (normalized === "ok") {
      return 1;
    }
    return 0;
  };
  if (toneSeverity(drift.tone) > toneSeverity(tone)) {
    statusLabel = String(drift.posture || statusLabel || "unknown");
    tone = String(drift.tone || tone || "warn");
  }
  setBadge("runtime-policy-status", statusLabel, tone);
}

function deriveProviderHealthSnapshot(providerPayload, statusOverride) {
  const provider = providerPayload || {};
  const telemetry = provider.telemetry || {};
  const summary = telemetry.summary || {};
  const autonomy = provider.autonomy || {};
  const cachedHealth = provider.health || {};
  const status = (statusOverride && typeof statusOverride === "object") ? statusOverride : (provider.status || {});
  const liveProbe = (status.last_live_probe && typeof status.last_live_probe === "object") ? status.last_live_probe : {};
  const capability = (status.last_capability_probe && typeof status.last_capability_probe === "object") ? status.last_capability_probe : {};
  const selectedProvider = String(
    status.selected_provider || status.provider || ((cachedHealth.route || {}).selected_provider) || autonomy.provider || telemetry.provider || ""
  );
  const activeProvider = String(status.active_provider || ((cachedHealth.route || {}).active_provider) || "");
  const displayProvider = activeProvider || selectedProvider || String(cachedHealth.provider || "");
  const transport = String(status.transport || cachedHealth.transport || summary.transport || "");
  const summaryState = String(autonomy.state || summary.state || ((cachedHealth.autonomy || {}).state) || "healthy").toLowerCase();
  const suppressionReason = String(
    autonomy.suppression_reason || summary.suppression_reason || ((cachedHealth.autonomy || {}).suppression_reason) || ""
  ).toLowerCase();
  const suppressionHint = String(autonomy.suppression_hint || "").trim();
  const activeMatchesSelected = Object.prototype.hasOwnProperty.call(status, "active_matches_selected")
    ? Boolean(status.active_matches_selected)
    : Boolean((cachedHealth.route || {}).active_matches_selected);
  const liveProbeRecorded = Object.keys(liveProbe).length > 0;
  const capabilityRecorded = Object.keys(capability).length > 0;

  let healthPosture = String(cachedHealth.health_posture || "");
  let healthTone = String(cachedHealth.health_tone || "");
  let operatorHint = String(cachedHealth.operator_hint || "");

  if (!displayProvider) {
    healthPosture = "unconfigured";
    healthTone = "warn";
    operatorHint = "No provider route is configured yet.";
  } else if (status.ok === false) {
    healthPosture = "status_error";
    healthTone = "danger";
    operatorHint = String(status.error || "Provider status failed to load.");
  } else if (summaryState === "circuit_open") {
    healthPosture = "circuit_open";
    healthTone = "danger";
    operatorHint = suppressionHint || "Provider recovery is blocked by an open circuit; wait for cooldown or recover the route.";
  } else if (["auth", "quota", "config"].includes(suppressionReason)) {
    healthPosture = "suppressed";
    healthTone = "danger";
    operatorHint = suppressionHint || `Provider is suppressed by ${suppressionReason}; fix the route before retrying.`;
  } else if (liveProbeRecorded && liveProbe.ok === false) {
    healthPosture = "probe_error";
    healthTone = "danger";
    operatorHint = String(liveProbe.error || "The latest cached live probe failed for the active provider route.");
  } else if (liveProbeRecorded && (!activeMatchesSelected || !liveProbe.matches_current_model || !liveProbe.matches_current_base_url)) {
    healthPosture = "cache_stale";
    healthTone = "warn";
    operatorHint = "Cached probe posture no longer matches the active provider route.";
  } else if (capabilityRecorded && capability.checked && !capability.current_model_listed) {
    healthPosture = "model_not_listed";
    healthTone = "warn";
    operatorHint = "The active model is not present in the latest cached remote model list.";
  } else if (["cooldown", "degraded"].includes(summaryState)) {
    healthPosture = summaryState;
    healthTone = "warn";
    operatorHint = suppressionHint || String((Array.isArray(summary.hints) ? summary.hints[0] : "") || "Provider recovery is still in progress.");
  } else if (!liveProbeRecorded) {
    healthPosture = "probe_missing";
    healthTone = "warn";
    operatorHint = "No cached live probe is recorded yet for the selected provider.";
  } else if (!capabilityRecorded) {
    healthPosture = "capability_missing";
    healthTone = "warn";
    operatorHint = "No cached capability summary is recorded yet for the selected provider.";
  } else {
    healthPosture = "healthy";
    healthTone = "ok";
    operatorHint = String((Array.isArray(summary.hints) ? summary.hints[0] : "") || "Cached provider route and capability posture look steady.");
  }

  return {
    provider: displayProvider,
    transport,
    health_posture: healthPosture,
    health_tone: healthTone,
    operator_hint: operatorHint,
    route: {
      selected_provider: selectedProvider,
      active_provider: activeProvider,
      active_model: String(status.active_model || status.model || ((cachedHealth.route || {}).active_model) || ""),
      base_url: String(status.base_url || ((cachedHealth.route || {}).base_url) || ""),
      base_url_source: String(status.base_url_source || ((cachedHealth.route || {}).base_url_source) || ""),
      active_matches_selected: activeMatchesSelected,
    },
    probe: {
      recorded: liveProbeRecorded,
      posture: !liveProbeRecorded ? "missing" : (liveProbe.ok === false ? "error" : ((liveProbe.matches_current_model && liveProbe.matches_current_base_url) ? "matched" : "stale")),
      transport: String(liveProbe.transport || transport || ""),
      checked_at: String(liveProbe.checked_at || ""),
      ok: liveProbeRecorded ? Boolean(liveProbe.ok) : false,
      status_code: numeric(liveProbe.status_code, 0),
      error: String(liveProbe.error || ""),
      matches_current_model: liveProbeRecorded ? Boolean(liveProbe.matches_current_model) : false,
      matches_current_base_url: liveProbeRecorded ? Boolean(liveProbe.matches_current_base_url) : false,
    },
    capability: {
      recorded: capabilityRecorded,
      posture: !capabilityRecorded ? "missing" : (!capability.checked ? "unknown" : (capability.current_model_listed ? "listed" : "model_not_listed")),
      detail: String(capability.detail || ""),
      checked_at: String(capability.checked_at || ""),
      current_model_listed: capabilityRecorded ? Boolean(capability.current_model_listed) : false,
      matched_model: String(capability.matched_model || ""),
      listed_model_count: numeric(capability.listed_model_count, 0),
      listed_model_sample: Array.isArray(capability.listed_model_sample) ? capability.listed_model_sample : [],
    },
    autonomy: {
      state: summaryState,
      suppression_reason: suppressionReason,
      suppression_backoff_s: numeric(autonomy.suppression_backoff_s, numeric((cachedHealth.autonomy || {}).suppression_backoff_s, 0)),
      last_error_class: String(autonomy.last_error_class || ((cachedHealth.autonomy || {}).last_error_class) || ""),
    },
  };
}

function deriveProviderBudgetSnapshot(providerPayload, statusOverride) {
  const provider = providerPayload || {};
  const telemetry = provider.telemetry || {};
  const summary = telemetry.summary || {};
  const counters = telemetry.counters || {};
  const autonomy = provider.autonomy || {};
  const cachedBudget = provider.budget || {};
  const status = (statusOverride && typeof statusOverride === "object") ? statusOverride : (provider.status || {});
  const selectedProvider = String(
    status.selected_provider || status.provider || ((cachedBudget.route || {}).selected_provider) || autonomy.provider || telemetry.provider || ""
  );
  const activeProvider = String(status.active_provider || ((cachedBudget.route || {}).active_provider) || "");
  const displayProvider = activeProvider || selectedProvider || String(cachedBudget.provider || "");
  const transport = String(status.transport || cachedBudget.transport || summary.transport || "");
  const activeModel = String(
    status.active_model || status.model || ((cachedBudget.route || {}).active_model) || telemetry.model || ""
  );
  const summaryState = String(autonomy.state || summary.state || ((cachedBudget.telemetry || {}).summary_state) || "healthy").toLowerCase();
  const suppressionReason = String(
    autonomy.suppression_reason || summary.suppression_reason || ((cachedBudget.quota || {}).suppression_reason) || ""
  ).toLowerCase();
  const lastErrorClass = String(
    autonomy.last_error_class || telemetry.last_error_class || counters.last_error_class
      || ((cachedBudget.telemetry || {}).last_error_class) || ""
  ).toLowerCase();
  const suppressionHint = String(autonomy.suppression_hint || "").trim();
  const backoffSeconds = numeric(
    autonomy.suppression_backoff_s,
    numeric(autonomy.cooldown_remaining_s, numeric((cachedBudget.quota || {}).backoff_s, 0)),
  );
  const rateLimitErrors = numeric(counters.rate_limit_errors, numeric((cachedBudget.telemetry || {}).rate_limit_errors, 0));
  const authErrors = numeric(counters.auth_errors, numeric((cachedBudget.telemetry || {}).auth_errors, 0));
  const httpErrors = numeric(counters.http_errors, numeric((cachedBudget.telemetry || {}).http_errors, 0));
  const requests = numeric(counters.requests, numeric((cachedBudget.telemetry || {}).requests, 0));
  const successes = numeric(counters.successes, numeric((cachedBudget.telemetry || {}).successes, 0));
  const firstHint = Array.isArray(summary.hints) && summary.hints.length ? String(summary.hints[0] || "").trim() : "";

  const quotaSignaled = suppressionReason === "quota" || lastErrorClass === "quota";
  const rateLimitSignaled = suppressionReason === "rate_limit" || lastErrorClass === "rate_limit";
  const nonBudgetReason = [suppressionReason, lastErrorClass, summaryState]
    .map((value) => String(value || "").trim().toLowerCase())
    .find((value) => value && !["healthy", "ready", "ok"].includes(value)) || "";

  let budgetPosture = String(cachedBudget.budget_posture || "");
  let budgetTone = String(cachedBudget.budget_tone || "");
  let operatorHint = String(cachedBudget.operator_hint || "");

  if (!displayProvider) {
    budgetPosture = "unconfigured";
    budgetTone = "warn";
    operatorHint = "No provider route is configured yet.";
  } else if (status.ok === false) {
    budgetPosture = "unknown";
    budgetTone = "warn";
    operatorHint = String(status.error || "Provider status failed to load.");
  } else if (quotaSignaled) {
    budgetPosture = "quota_exhausted";
    budgetTone = "danger";
    operatorHint = suppressionHint || firstHint || "Provider quota or billing appears exhausted; restore credits or switch the route.";
  } else if (rateLimitSignaled) {
    budgetPosture = "rate_limited";
    budgetTone = "warn";
    operatorHint = suppressionHint || firstHint || "Provider is rate-limited; wait for the window or switch the route.";
  } else if (nonBudgetReason) {
    const nonBudgetMessages = {
      auth: "Current provider issue is authentication-related, not quota-related.",
      config: "Current provider issue is configuration-related, not quota-related.",
      network: "Current provider issue is network-related, not quota-related.",
      http_transient: "Current provider issue is transient HTTP failure, not quota-related.",
      retry_exhausted: "Current provider issue is retry exhaustion, not quota-related.",
      cooldown: "Provider is cooling down, but no quota or rate-limit signal is active.",
      degraded: "Provider is degraded, but no quota or rate-limit signal is active.",
      circuit_open: "Provider recovery is waiting on circuit cooldown, not quota or billing.",
    };
    budgetPosture = "non_budget_block";
    budgetTone = "warn";
    const nonBudgetPrefix = nonBudgetMessages[nonBudgetReason] || `Current provider issue is ${nonBudgetReason}, not quota-related.`;
    const trailingHint = suppressionHint || firstHint || "";
    operatorHint = trailingHint ? `${nonBudgetPrefix} ${trailingHint}` : nonBudgetPrefix;
  } else {
    budgetPosture = "clear";
    budgetTone = "ok";
    operatorHint = firstHint || "No quota or rate-limit pressure is visible in current provider telemetry.";
  }

  return {
    provider: displayProvider,
    transport,
    budget_posture: budgetPosture,
    budget_tone: budgetTone,
    operator_hint: operatorHint,
    route: {
      selected_provider: selectedProvider,
      active_provider: activeProvider,
      active_model: activeModel,
    },
    quota: {
      posture: !displayProvider ? "unknown" : (quotaSignaled ? "exhausted" : "clear"),
      suppression_reason: suppressionReason,
      last_error_class: lastErrorClass,
      backoff_s: quotaSignaled ? backoffSeconds : 0,
    },
    rate_limit: {
      posture: !displayProvider ? "unknown" : (rateLimitSignaled ? "limited" : "clear"),
      error_count: rateLimitErrors,
      suppression_reason: suppressionReason,
      last_error_class: lastErrorClass,
      backoff_s: rateLimitSignaled ? backoffSeconds : 0,
    },
    telemetry: {
      summary_state: summaryState,
      requests,
      successes,
      auth_errors: authErrors,
      rate_limit_errors: rateLimitErrors,
      http_errors: httpErrors,
      last_error_class: lastErrorClass,
    },
  };
}

function renderProviderHealthBoard() {
  const grid = byId("provider-health-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const provider = (state.dashboardState || {}).provider || {};
  const providerStatus = state.providerStatus || provider.status || {};
  const health = deriveProviderHealthSnapshot(provider, providerStatus);
  const route = health.route || {};
  const probe = health.probe || {};
  const capability = health.capability || {};
  const autonomy = health.autonomy || {};
  const cards = [];

  if (!Object.keys(health).length) {
    appendSummaryCard(grid, {
      title: "Provider health",
      body: "not available",
      detail: "No compact provider health snapshot is available yet.",
    });
    setBadge("provider-health-status", "pending", "warn");
    return;
  }

  cards.push({
    title: "Active route",
    body: `${String(route.active_provider || route.selected_provider || health.provider || "provider")} | ${String(health.transport || "unknown")}`,
    detail: [
      String(route.active_model || "").trim(),
      String(route.base_url || "").trim(),
      route.active_matches_selected ? "active route matched" : "active route differs from selection",
    ].filter(Boolean).join(" | ") || "No active provider route is available.",
  });

  cards.push({
    title: "Live probe",
    body: `${String(probe.posture || "unknown")} | ${probe.recorded ? "cached" : "missing"}`,
    detail: [
      String(probe.error || "").trim() || (numeric(probe.status_code, 0) ? `HTTP ${numeric(probe.status_code, 0)}` : ""),
      probe.matches_current_model ? "model matched" : (probe.recorded ? "model drift" : ""),
      probe.matches_current_base_url ? "base URL matched" : (probe.recorded ? "base URL drift" : ""),
      String(probe.checked_at || "").trim(),
    ].filter(Boolean).join(" | ") || "No cached live probe is recorded yet.",
  });

  cards.push({
    title: "Capability posture",
    body: `${String(capability.posture || "unknown")} | ${numeric(capability.listed_model_count, 0)} listed`,
    detail: [
      String(capability.detail || "").trim(),
      capability.current_model_listed ? `Current model listed${capability.matched_model ? ` as ${String(capability.matched_model)}` : ""}` : "",
      Array.isArray(capability.listed_model_sample) && capability.listed_model_sample.length
        ? `sample ${capability.listed_model_sample.map((value) => String(value)).join(", ")}`
        : "",
    ].filter(Boolean).join(" | ") || "No cached capability summary is available yet.",
  });

  cards.push({
    title: "Recovery hint",
    body: String(health.operator_hint || "Provider posture looks steady."),
    detail: [
      String(autonomy.state || "").trim(),
      String(autonomy.suppression_reason || "").trim(),
      autonomy.suppression_backoff_s ? `backoff ${formatDuration(autonomy.suppression_backoff_s)}` : "",
      String(autonomy.last_error_class || "").trim(),
    ].filter(Boolean).join(" | "),
  });

  cards.forEach((item) => appendSummaryCard(grid, item));

  const statusLabel = String(health.health_posture || "unknown");
  const tone = String(health.health_tone || "").trim() || (
    ["healthy"].includes(statusLabel)
      ? "ok"
      : (["probe_missing", "capability_missing", "cache_stale", "model_not_listed", "cooldown", "degraded", "unconfigured"].includes(statusLabel)
        ? "warn"
        : "danger")
  );
  setBadge("provider-health-status", statusLabel, tone);
}

function renderProviderBudgetBoard() {
  const grid = byId("provider-budget-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const provider = (state.dashboardState || {}).provider || {};
  const providerStatus = state.providerStatus || provider.status || {};
  const budget = deriveProviderBudgetSnapshot(provider, providerStatus);
  const route = budget.route || {};
  const quota = budget.quota || {};
  const rateLimit = budget.rate_limit || {};
  const telemetry = budget.telemetry || {};

  if (!Object.keys(budget).length) {
    appendSummaryCard(grid, {
      title: "Provider budget",
      body: "not available",
      detail: "No compact provider budget snapshot is available yet.",
    });
    setBadge("provider-budget-status", "pending", "warn");
    return;
  }

  const cards = [
    {
      title: "Budget posture",
      body: `${String(budget.budget_posture || "unknown")} | ${String(route.active_provider || route.selected_provider || budget.provider || "provider")}`,
      detail: [
        String(route.active_model || "").trim(),
        String(budget.transport || "").trim(),
      ].filter(Boolean).join(" | ") || "No active provider route is available.",
    },
    {
      title: "Quota signal",
      body: `${String(quota.posture || "unknown")} | ${quota.backoff_s ? formatDuration(quota.backoff_s) : "no backoff"}`,
      detail: [
        String(quota.suppression_reason || "").trim(),
        String(quota.last_error_class || "").trim(),
      ].filter(Boolean).join(" | ") || "No quota suppression is visible.",
    },
    {
      title: "Rate limit signal",
      body: `${String(rateLimit.posture || "unknown")} | ${numeric(rateLimit.error_count, 0)} errors`,
      detail: [
        rateLimit.backoff_s ? `backoff ${formatDuration(rateLimit.backoff_s)}` : "",
        `requests ${numeric(telemetry.requests, 0)}`,
        `successes ${numeric(telemetry.successes, 0)}`,
      ].filter(Boolean).join(" | "),
    },
    {
      title: "Operator hint",
      body: String(budget.operator_hint || "No budget guidance is available yet."),
      detail: [
        String(telemetry.summary_state || "").trim(),
        String(telemetry.last_error_class || "").trim(),
        `auth ${numeric(telemetry.auth_errors, 0)}`,
        `http ${numeric(telemetry.http_errors, 0)}`,
      ].filter(Boolean).join(" | "),
    },
  ];

  cards.forEach((item) => appendSummaryCard(grid, item));

  const statusLabel = String(budget.budget_posture || "unknown");
  const tone = String(budget.budget_tone || "").trim() || (
    ["clear"].includes(statusLabel)
      ? "ok"
      : (["rate_limited", "non_budget_block", "unconfigured", "unknown"].includes(statusLabel) ? "warn" : "danger")
  );
  setBadge("provider-budget-status", statusLabel, tone);
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
  const status = state.providerStatus || provider.status || {};
  const candidates = [];

  const suppressionReason = String(summary.suppression_reason || "");
  const coolingCandidates = Array.isArray(summary.cooling_candidates) ? summary.cooling_candidates : [];
  const suppressedCandidates = Array.isArray(summary.suppressed_candidates) ? summary.suppressed_candidates : [];
  const recoverButton = byId("recover-provider");

  candidates.push({
    title: "Provider state",
    body: `${String(summary.state || "unknown")} | ${String(provider.autonomy?.provider || telemetry.provider || "provider")}`,
    detail: String(provider.autonomy?.suppression_hint || summary.onboarding_hint || "No additional guidance yet."),
  });

  candidates.push({
    title: "Configured route",
    body: `${String(status.provider || status.selected_provider || provider.autonomy?.provider || telemetry.provider || "provider")} | ${String(status.transport || "unknown")}`,
    detail: [String(status.active_model || status.model || "").trim(), String(status.base_url || "").trim()].filter(Boolean).join(" | ")
      || "No configured provider route available.",
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

  const lastLiveProbe = status.last_live_probe || {};
  if (Object.keys(lastLiveProbe).length) {
    candidates.push({
      title: "Cached live probe",
      body: `${lastLiveProbe.ok === false ? "probe error" : "probe cached"} | ${String(lastLiveProbe.transport || status.transport || "unknown")}`,
      detail: [
        String(lastLiveProbe.error || "").trim() || `HTTP ${numeric(lastLiveProbe.status_code, 0) || 200}`,
        String(lastLiveProbe.checked_at || "").trim(),
      ].filter(Boolean).join(" | "),
    });
  } else {
    candidates.push({
      title: "Cached live probe",
      body: "not recorded",
      detail: "Run clawlite validate preflight --provider-live to persist a fresh runtime probe snapshot.",
    });
  }

  const lastCapabilityProbe = status.last_capability_probe || {};
  if (Object.keys(lastCapabilityProbe).length) {
    candidates.push({
      title: "Capability cache",
      body: `${String(lastCapabilityProbe.detail || "model_list_unavailable")} | ${numeric(lastCapabilityProbe.listed_model_count, 0)} listed`,
      detail: lastCapabilityProbe.current_model_listed
        ? `Current model listed${lastCapabilityProbe.matched_model ? ` as ${lastCapabilityProbe.matched_model}` : ""}.`
        : (Array.isArray(lastCapabilityProbe.listed_model_sample) && lastCapabilityProbe.listed_model_sample.length
            ? `Sample: ${lastCapabilityProbe.listed_model_sample.join(", ")}`
            : "No remote model list cached yet."),
    });
  } else {
    candidates.push({
      title: "Capability cache",
      body: "not recorded",
      detail: "No cached capability summary is available for the selected provider yet.",
    });
  }

  candidates.slice(0, 6).forEach((item) => appendSummaryCard(grid, item));

  if (recoverButton) {
    const blocked = suppressionReason || suppressedCandidates.length > 0 || coolingCandidates.length > 0;
    recoverButton.disabled = !blocked;
  }
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
  const resolved = persistChatSession(sessionId);
  const input = byId("session-input");
  if (input) {
    input.value = resolved;
  }
  setText("metric-session-route", `chat -> ${resolved}`);
  setActiveTab("chat");
  recordEvent("ok", "Session selected", resolved, "dashboard");
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
      useButton.addEventListener("click", () => useSession(String(item.session_id || state.operatorId)));
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
  const providerStatus = state.providerStatus || provider.status || {};
  const providerBudget = deriveProviderBudgetSnapshot(provider, providerStatus);
  setText("metric-provider-state", String(providerAutonomy.state || providerTelemetry.summary?.state || "unknown"));
  setText("metric-provider-backoff", formatDuration(providerAutonomy.suppression_backoff_s || providerAutonomy.cooldown_remaining_s || 0));
  setCode("provider-preview", {
    autonomy: providerAutonomy,
    summary: providerTelemetry.summary || {},
    counters: providerTelemetry.counters || {},
    status: providerStatus,
    budget: providerBudget,
  });
  setBadge("provider-status", String(providerAutonomy.state || "unknown"), toneForState(providerAutonomy.state));
  renderDeliveryBoard();
  renderSupervisorBoard();
  renderRuntimePostureBoard();
  renderRuntimePolicyBoard();
  renderProviderHealthBoard();
  renderProviderBudgetBoard();
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

function renderDiscordBoard() {
  const grid = byId("discord-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";
  const discord = ((state.dashboardState || {}).discord) || {};
  const available = Boolean(discord.available);
  const refreshButton = byId("refresh-discord-transport");

  if (!available) {
    appendSummaryCard(grid, {
      title: "Discord",
      body: "not configured",
      detail: discord.last_error || "Enable Discord to surface gateway session and reconnect diagnostics here.",
    });
    setBadge("discord-status", "unavailable", "warn");
    if (refreshButton) {
      refreshButton.disabled = true;
    }
    return;
  }

  const waitingFor = String(discord.gateway_session_waiting_for || "").trim();
  const sessionWatchdogState = String(discord.gateway_session_task_state || "unknown");
  const reconnectAttempt = numeric(discord.gateway_reconnect_attempt, 0);
  const reconnectRetryIn = Number(discord.gateway_reconnect_retry_in_s || 0);
  const reconnectState = String(discord.gateway_reconnect_state || "idle");
  const lifecycleOutcome = String(discord.gateway_last_lifecycle_outcome || "").trim();
  const lifecycleAt = String(discord.gateway_last_lifecycle_at || "").trim();
  const lastConnectAt = String(discord.gateway_last_connect_at || "").trim();
  const lastReadyAt = String(discord.gateway_last_ready_at || "").trim();
  const lastDisconnectAt = String(discord.gateway_last_disconnect_at || "").trim();
  const lastDisconnectReason = String(discord.gateway_last_disconnect_reason || "").trim();
  appendSummaryCard(grid, {
    title: "Gateway state",
    body: waitingFor
      ? `${discord.connected ? "connected" : "disconnected"} | ${String(discord.gateway_task_state || "unknown")} | waiting ${waitingFor.toUpperCase()}`
      : `${discord.connected ? "connected" : "disconnected"} | ${String(discord.gateway_task_state || "unknown")}`,
    detail: `heartbeat ${String(discord.heartbeat_task_state || "unknown")} | sequence ${discord.sequence ?? "-"}`,
  });
  appendSummaryCard(grid, {
    title: "Session",
    body: String(discord.session_id || "not established"),
    detail: waitingFor
      ? `waiting for ${waitingFor.toUpperCase()} | watchdog ${sessionWatchdogState}`
      : (discord.resume_url ? `resume ${discord.resume_url}` : "no resume url available"),
  });
  appendSummaryCard(grid, {
    title: "Runtime",
    body: `${numeric(discord.dm_cache_size, 0)} DM channels cached | ${numeric(discord.typing_tasks, 0)} typing tasks`,
    detail: discord.last_error ? `last error ${discord.last_error}` : "transport healthy",
  });
  if (reconnectAttempt || reconnectRetryIn > 0) {
    appendSummaryCard(grid, {
      title: "Reconnect",
      body: `attempt ${reconnectAttempt || 0}`,
      detail: reconnectRetryIn > 0
        ? `retry in ${reconnectRetryIn.toFixed(1)}s`
        : (reconnectState === "retrying" ? "retrying now" : "retry active"),
    });
  }
  if (lifecycleOutcome || lastConnectAt || lastReadyAt || lastDisconnectAt) {
    const lifecycleDetails = [];
    if (lastConnectAt) {
      lifecycleDetails.push(`connect ${lastConnectAt}`);
    }
    if (lastReadyAt) {
      lifecycleDetails.push(`ready ${lastReadyAt}`);
    }
    if (lastDisconnectAt) {
      lifecycleDetails.push(`disconnect ${lastDisconnectAt}`);
    }
    if (lastDisconnectReason) {
      lifecycleDetails.push(`reason ${lastDisconnectReason}`);
    }
    appendSummaryCard(grid, {
      title: "Lifecycle",
      body: lifecycleOutcome
        ? `${lifecycleOutcome}${lifecycleAt ? ` @ ${lifecycleAt}` : ""}`
        : "no lifecycle outcome recorded",
      detail: lifecycleDetails.length ? lifecycleDetails.join(" | ") : "no lifecycle timestamps recorded",
    });
  }

  const hints = Array.isArray(discord.hints) ? discord.hints : [];
  if (hints.length) {
    hints.slice(0, 3).forEach((hint, index) => {
      appendSummaryCard(grid, {
        title: `Hint ${index + 1}`,
        body: String(hint),
        detail: "Use the Discord transport refresh or channel recovery controls to resolve this safely.",
      });
    });
  }

  const healthy = Boolean(discord.connected) && !discord.last_error && !waitingFor && reconnectRetryIn <= 0;
  const badgeText = waitingFor
    ? `waiting ${waitingFor.toLowerCase()}`
    : ((reconnectRetryIn > 0 || reconnectState === "retrying") ? "reconnecting" : (healthy ? "healthy" : "attention"));
  setBadge("discord-status", badgeText, healthy ? "ok" : "warn");
  if (refreshButton) {
    refreshButton.disabled = false;
  }
}

function memoryTriageSummary({
  suggestionsCount,
  snapshotCount,
  liveOverview,
  liveDoctor,
  liveQuality,
  recommendationSummary,
  suggestionSummary,
}) {
  const reasons = [];
  let level = "ok";

  if (liveDoctor && liveDoctor.ok === false) {
    level = "danger";
    reasons.push("doctor failed");
  } else {
    const corruptLines = numeric((liveDoctor || {}).diagnostics?.history_read_corrupt_lines, 0);
    const repairedFiles = numeric((liveDoctor || {}).diagnostics?.history_repaired_files, 0);
    if (corruptLines > 0 || repairedFiles > 0) {
      level = "warn";
      reasons.push(`doctor flagged ${corruptLines} corrupt / ${repairedFiles} repaired`);
    }
  }

  if (liveQuality && liveQuality.ok === false) {
    level = "danger";
    reasons.push("quality failed");
  } else if (liveQuality) {
    const score = numeric((liveQuality.report || {}).score, numeric((liveQuality.state || {}).current?.score, 0));
    const drift = String(
      (((liveQuality.report || {}).drift || ((liveQuality.state || {}).current || {}).drift || {}).assessment
        || ((liveQuality.state || {}).trend || {}).assessment
        || ""),
    );
    if (drift === "degrading" || score < 65) {
      if (level !== "danger") {
        level = "warn";
      }
      const recommendation = String((recommendationSummary || {}).recommendation || "");
      reasons.push(recommendation ? truncateText(recommendation, 72) : `${score} quality / ${drift || "unknown"} drift`);
    }
  }

  if (liveOverview && liveOverview.ok === false) {
    level = "danger";
    reasons.push("overview failed");
  } else if (liveOverview) {
    const total = numeric((liveOverview.counts || {}).total, 0);
    const semanticCoverage = Number(liveOverview.semantic_coverage || 0);
    if (total > 0 && semanticCoverage < 0.4) {
      if (level !== "danger") {
        level = "warn";
      }
      reasons.push(`${Math.round(semanticCoverage * 100)}% semantic coverage`);
    }
  }

  if (numeric(suggestionsCount, 0) > 0) {
    if (level === "ok") {
      level = "warn";
    }
    const suggestionLead = String((suggestionSummary || {}).trigger || "");
    reasons.push(
      suggestionLead
        ? `${numeric(suggestionsCount, 0)} pending | ${suggestionLead}`
        : `${numeric(suggestionsCount, 0)} pending suggestions`,
    );
  } else if (String((suggestionSummary || {}).body || "") === "suggestions unavailable") {
    if (level === "ok") {
      level = "warn";
    }
    reasons.push("suggestions unavailable");
  }
  if (numeric(snapshotCount, 0) <= 0) {
    if (level === "ok") {
      level = "warn";
    }
    reasons.push("no snapshots yet");
  }

  if (!reasons.length) {
    return {
      level: "ok",
      body: "healthy",
      detail: "Doctor, quality, overview, and snapshot signals look steady.",
    };
  }

  return {
    level,
    body: level === "danger" ? "needs attention" : "watch closely",
    detail: reasons.slice(0, 3).join(" | "),
  };
}

function memoryRecommendationSummary({ liveQuality, quality }) {
  const liveReport = (liveQuality || {}).report || {};
  const liveState = (liveQuality || {}).state || {};
  const current = quality.current || {};
  const trend = quality.trend || {};
  const score = numeric(liveReport.score, numeric((liveState.current || {}).score, numeric(current.score, 0)));
  const drift = String(
    ((liveReport.drift || (liveState.current || {}).drift || {}).assessment || (liveState.trend || trend || {}).assessment || "stable"),
  );
  const recommendations = Array.isArray(liveReport.recommendations) ? liveReport.recommendations : [];
  const recommendation = String(recommendations[0] || "").trim();

  if (liveQuality && liveQuality.ok === false) {
    const error = (liveQuality || {}).error || {};
    return {
      body: "quality failed",
      detail: `${String(error.type || "error")} | ${String(error.message || "Memory quality snapshot failed.")}`,
      recommendation: "",
    };
  }
  if (recommendation) {
    return {
      body: truncateText(recommendation, 88),
      detail: `${score} score | ${drift} drift | ${numeric((liveReport.retrieval || {}).attempts, 0)} attempts`,
      recommendation,
    };
  }
  if (liveQuality) {
    return {
      body: "No explicit recommendation",
      detail: `${score} score | ${drift} drift | live snapshot ready`,
      recommendation: "",
    };
  }
  return {
    body: "Run memory quality",
    detail: `${numeric(current.score, 0)} cached score | ${String(trend.assessment || "unknown")} trend`,
    recommendation: "",
  };
}

function memorySuggestionSummary(suggest) {
  if (suggest && suggest.ok === false) {
    const error = suggest.error || {};
    return {
      body: "suggestions unavailable",
      detail: `${String(error.type || "error")} | ${String(error.message || "Memory suggestions snapshot failed.")}`,
      trigger: "",
      text: "",
    };
  }
  const rows = Array.isArray(suggest.suggestions) ? suggest.suggestions.slice() : [];
  if (!rows.length) {
    return {
      body: "No pending suggestions",
      detail: "No pending suggestions in the live dashboard snapshot.",
      trigger: "",
      text: "",
    };
  }
  rows.sort((left, right) => {
    const priorityDelta = numeric(right.priority, 0) - numeric(left.priority, 0);
    if (Math.abs(priorityDelta) > 0.0001) {
      return priorityDelta;
    }
    return parseTimestampMs(String(left.created_at || "")) - parseTimestampMs(String(right.created_at || ""));
  });
  const top = rows[0] || {};
  return {
    body: truncateText(String(top.text || "Pending suggestion ready for review."), 88),
    detail: `${String(top.trigger || "unknown")} | ${Math.round(numeric(top.priority, 0) * 100)}% | ${String(top.channel || "cli")} -> ${String(top.target || "default")}`,
    trigger: String(top.trigger || ""),
    text: String(top.text || ""),
  };
}

function memoryRemediationSnapshot({ memory, liveDoctor, liveOverview, liveQuality, recommendationSummary, suggestionSummary }) {
  const remediation = (memory.remediation && typeof memory.remediation === "object") ? memory.remediation : {};
  const doctor = (liveDoctor && typeof liveDoctor === "object") ? liveDoctor : {};
  const overview = (liveOverview && typeof liveOverview === "object") ? liveOverview : {};
  const quality = (liveQuality && typeof liveQuality === "object") ? liveQuality : {};
  const qualityReport = quality.report || {};
  const qualityState = quality.state || {};
  const qualityCurrent = qualityState.current || {};
  const qualityTrend = qualityState.trend || {};
  const doctorDiagnostics = doctor.diagnostics || {};
  const doctorCorrupt = numeric(doctorDiagnostics.history_read_corrupt_lines, 0);
  const doctorRepaired = numeric(doctorDiagnostics.history_repaired_files, 0);
  if (liveDoctor) {
    if (doctor.ok === false) {
      const error = doctor.error || {};
      return {
        posture: "doctor_failed",
        tone: "danger",
        priority: "run_doctor",
        summary: "doctor failed",
        hint: `${String(error.type || "error")} | ${String(error.message || "Memory doctor failed.")}`,
      };
    }
    if (doctorCorrupt > 0 || doctorRepaired > 0) {
      return {
        posture: "doctor_attention",
        tone: "warn",
        priority: "review_doctor",
        summary: `${doctorCorrupt} corrupt | ${doctorRepaired} repaired`,
        hint: "Review Memory doctor output before acting on lower-priority quality or suggestion work.",
      };
    }
  }
  if (liveQuality) {
    if (quality.ok === false) {
      const error = quality.error || {};
      return {
        posture: "quality_failed",
        tone: "danger",
        priority: "run_quality",
        summary: "quality failed",
        hint: `${String(error.type || "error")} | ${String(error.message || "Memory quality snapshot failed.")}`,
      };
    }
    if (String(recommendationSummary.recommendation || "").trim()) {
      return {
        posture: "quality_attention",
        tone: "warn",
        priority: "inspect_quality",
        summary: recommendationSummary.body,
        hint: "Start with the top quality recommendation before lower-priority cleanup.",
      };
    }
    const liveScore = numeric(qualityReport.score, numeric(qualityCurrent.score, 0));
    const liveDrift = String(
      ((qualityReport.drift || qualityCurrent.drift || {}).assessment || qualityTrend.assessment || ""),
    ).trim();
    if (liveScore > 0 && (liveDrift === "degrading" || liveScore < 65)) {
      return {
        posture: "quality_attention",
        tone: "warn",
        priority: "inspect_quality",
        summary: `${liveScore} score | ${liveDrift || "drift unknown"}`,
        hint: "Inspect memory quality before lower-priority cleanup even when no explicit recommendation was emitted.",
      };
    }
  }
  if (liveOverview) {
    if (overview.ok === false) {
      const error = overview.error || {};
      return {
        posture: "overview_failed",
        tone: "danger",
        priority: "run_overview",
        summary: "overview failed",
        hint: `${String(error.type || "error")} | ${String(error.message || "Memory overview failed.")}`,
      };
    }
    const total = numeric((overview.counts || {}).total, 0);
    const semanticCoverage = Number(overview.semantic_coverage || 0);
    if (total > 0 && semanticCoverage < 0.4) {
      return {
        posture: "coverage_attention",
        tone: "warn",
        priority: "inspect_overview",
        summary: `${Math.round(semanticCoverage * 100)}% semantic coverage`,
        hint: "Inspect memory overview and raise semantic coverage before relying on proactive recall.",
      };
    }
  }
  if (String(suggestionSummary.text || "").trim()) {
    return {
      posture: String(remediation.posture || "guided"),
      tone: String(remediation.tone || "warn"),
      priority: String(remediation.priority || "review_suggestion"),
      summary: suggestionSummary.body,
      hint: String(remediation.hint || "Review the highest-priority memory suggestion next."),
    };
  }
  return {
    posture: String(remediation.posture || "clear"),
    tone: String(remediation.tone || "ok"),
    priority: String(remediation.priority || "none"),
    summary: String(remediation.summary || "no immediate remediation"),
    hint: String(remediation.hint || "Current memory signals do not suggest immediate operator action."),
  };
}

function renderMemoryBoard() {
  const grid = byId("memory-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";
  const memory = ((state.dashboardState || {}).memory) || {};
  const profile = memory.profile || {};
  const suggest = memory.suggestions || {};
  const versions = memory.versions || {};
  const quality = memory.quality || {};
  const qualityCurrent = quality.current || {};
  const qualityTrend = quality.trend || {};
  const qualityRetrieval = qualityCurrent.retrieval || {};
  const qualitySemantic = qualityCurrent.semantic || {};
  const doctor = state.memoryDoctor || {};
  const liveOverview = state.memoryOverview || {};
  const liveOverviewCounts = liveOverview.counts || {};
  const liveOverviewPaths = liveOverview.paths || {};
  const liveOverviewError = liveOverview.error || {};
  const liveQualitySnapshot = state.memoryQuality;
  const liveQuality = liveQualitySnapshot || {};
  const liveQualityReport = liveQuality.report || {};
  const liveQualityState = liveQuality.state || {};
  const liveQualityCurrent = liveQualityState.current || {};
  const liveQualityTrend = liveQualityState.trend || {};
  const liveQualityDrift = (liveQualityReport.drift || liveQualityCurrent.drift || {});
  const liveQualityError = liveQuality.error || {};
  const doctorCounts = doctor.counts || {};
  const doctorDiagnostics = doctor.diagnostics || {};
  const doctorFiles = doctor.files || {};
  const doctorError = doctor.error || {};
  const profilePayload = profile.profile || {};
  const recommendationSummary = memoryRecommendationSummary({ liveQuality: liveQualitySnapshot, quality });
  const suggestionSummary = memorySuggestionSummary(suggest);
  const remediationSummary = memoryRemediationSnapshot({
    memory,
    liveDoctor: state.memoryDoctor,
    liveOverview: state.memoryOverview,
    liveQuality: state.memoryQuality,
    recommendationSummary,
    suggestionSummary,
  });
  const triage = memoryTriageSummary({
    suggestionsCount: numeric(suggest.count, 0),
    snapshotCount: numeric(versions.count, 0),
    liveOverview: state.memoryOverview,
    liveDoctor: state.memoryDoctor,
    liveQuality: state.memoryQuality,
    recommendationSummary,
    suggestionSummary,
  });

  appendSummaryCard(grid, {
    title: "Profile",
    body: `${Array.isArray(profile.keys) ? profile.keys.length : 0} keys`,
    detail: Array.isArray(profile.keys) && profile.keys.length ? profile.keys.slice(0, 4).join(", ") : "No profile keys captured yet.",
  });
  appendSummaryCard(grid, {
    title: "Triage",
    body: triage.body,
    detail: triage.detail,
  });
  appendSummaryCard(grid, {
    title: "Remediation",
    body: `${String(remediationSummary.priority || "none")} | ${String(remediationSummary.summary || "no immediate remediation")}`,
    detail: String(remediationSummary.hint || "Current memory signals do not suggest immediate operator action."),
  });
  appendSummaryCard(grid, {
    title: "Top recommendation",
    body: recommendationSummary.body,
    detail: recommendationSummary.detail,
  });
  appendSummaryCard(grid, {
    title: "Next suggestion",
    body: suggestionSummary.body,
    detail: suggestionSummary.detail,
  });
  appendSummaryCard(grid, {
    title: "Suggestions",
    body: `${numeric(suggest.count, 0)} pending`,
    detail: String(suggest.source || "pending"),
  });
  appendSummaryCard(grid, {
    title: "Quality",
    body: `${numeric(qualityCurrent.score, 0)} current | ${String(qualityTrend.assessment || "unknown")} trend`,
    detail: `${Number(qualityRetrieval.hit_rate || 0).toFixed(3)} hit rate | ${Number(qualitySemantic.coverage_ratio || 0).toFixed(3)} semantic | ${numeric(qualityTrend.degrading_streak, 0)} degrading streak`,
  });
  appendSummaryCard(grid, {
    title: "Snapshots",
    body: `${numeric(versions.count, 0)} versions`,
    detail: Array.isArray(versions.versions) && versions.versions.length ? versions.versions.slice(0, 2).join(", ") : "No snapshots created yet.",
  });
  appendSummaryCard(grid, {
    title: "Doctor",
    body: state.memoryDoctor
      ? (doctor.ok === false
        ? "error"
        : `${numeric(doctorCounts.total, 0)} entries | ${doctor.repair_applied ? "repair applied" : "read-only"}`)
      : "no live snapshot",
    detail: state.memoryDoctor
      ? (doctor.ok === false
        ? `${String(doctorError.type || "error")} | ${String(doctorError.message || "Memory doctor failed.")}`
        : `corrupt ${numeric(doctorDiagnostics.history_read_corrupt_lines, 0)} | repaired ${numeric(doctorDiagnostics.history_repaired_files, 0)} | history ${numeric((doctorFiles.history || {}).size_bytes, 0)} bytes`)
      : "Run Memory doctor to inspect file integrity and repair counters.",
  });
  appendSummaryCard(grid, {
    title: "Overview live",
    body: state.memoryOverview
      ? (liveOverview.ok === false
        ? "error"
        : `${numeric(liveOverviewCounts.total, 0)} entries | ${Math.round(Number(liveOverview.semantic_coverage || 0) * 100)}% semantic`)
      : "no live snapshot",
    detail: state.memoryOverview
      ? (liveOverview.ok === false
        ? `${String(liveOverviewError.type || "error")} | ${String(liveOverviewError.message || "Memory overview failed.")}`
        : `${numeric(liveOverviewCounts.history, 0)} history | ${numeric(liveOverviewCounts.curated, 0)} curated | proactive ${liveOverview.proactive_enabled ? "on" : "off"}`)
      : "Run memory overview to inspect coverage, counts, and proactive memory posture from the live runtime.",
  });
  appendSummaryCard(grid, {
    title: "Quality live",
    body: state.memoryQuality
      ? (liveQuality.ok === false
        ? "error"
        : `${numeric(liveQualityReport.score, numeric(liveQualityCurrent.score, 0))} score | ${String(liveQualityDrift.assessment || liveQualityTrend.assessment || "stable")}`)
      : "no live snapshot",
    detail: state.memoryQuality
      ? (liveQuality.ok === false
        ? `${String(liveQualityError.type || "error")} | ${String(liveQualityError.message || "Memory quality snapshot failed.")}`
        : `${numeric((liveQualityReport.retrieval || {}).attempts, 0)} attempts | ${numeric((liveQualityReport.turn_stability || {}).errors, 0)} errors | ${String((liveQualityReport.recommendations || [])[0] || "Quality snapshot persisted.")}`)
      : "Run memory quality to compute and persist a fresh quality-state report from the live runtime.",
  });
  appendSummaryCard(grid, {
    title: "Identity context",
    body: String(profilePayload.display_name || profilePayload.name || "unknown"),
    detail: state.memoryOverview && liveOverview.ok !== false
      ? `${String(profilePayload.timezone || "timezone not set")} | ${String(liveOverviewPaths.memory_home || "memory home unavailable")}`
      : String(profilePayload.timezone || "timezone not set"),
  });
}

function renderSkillsBoard() {
  const grid = byId("skills-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const skills = ((state.dashboardState || {}).skills) || {};
  const summary = skills.summary || {};
  const watcher = skills.watcher || {};
  const sources = skills.sources || {};
  const managed = skills.managed || {};
  const managedLive = state.skillsManaged || {};
  const executionKinds = skills.execution_kinds || {};
  const missingRequirements = skills.missing_requirements || {};
  const contractIssues = skills.contract_issues || {};
  const skillRows = Array.isArray(skills.skills) ? skills.skills : [];
  const managedItems = Array.isArray(managed.items) ? managed.items : [];
  const managedLiveItems = Array.isArray(managedLive.skills) ? managedLive.skills : [];
  const managedPreviewItems = managedLiveItems.length ? managedLiveItems : managedItems;
  const managedTrackedCount = numeric(managedLive.total_count, numeric(managed.count, 0));
  const managedReadyCount = numeric(managedLive.ready_count, numeric(managed.ready_count, 0));
  const managedBlockedCount = numeric(managedLive.blocked_count, numeric(managed.blocked_count, 0));
  const managedVisibleBlockedCount = numeric(
    managedLive.visible_blocked_count,
    numeric(managed.visible_blocked_count, managedBlockedCount),
  );
  const managedDisabledCount = numeric(managedLive.disabled_count, numeric(managed.disabled_count, 0));
  const managedVisibleCount = numeric(managedLive.count, managedTrackedCount);
  const managedFilterMeta = summarizeManagedFilter(managedLive);
  const managedBlockers = (managedLive.blockers && typeof managedLive.blockers === "object")
    ? managedLive.blockers
    : (managed.blockers || {});
  const managedBlockerKinds = (managedBlockers.by_kind && typeof managedBlockers.by_kind === "object")
    ? managedBlockers.by_kind
    : {};
  const managedRemediation = (managedBlockers.remediation && typeof managedBlockers.remediation === "object")
    ? managedBlockers.remediation
    : {};
  const managedRemediationPaths = Array.isArray(managedRemediation.paths) ? managedRemediation.paths : [];
  const managedBlockerExamples = Array.isArray(managedBlockers.examples) ? managedBlockers.examples : [];
  const blockedSkills = skillRows.filter((row) => {
    if (!row || row.enabled === false) {
      return false;
    }
    return row.available === false || (Array.isArray(row.contract_issues) && row.contract_issues.length > 0);
  });
  const topContractIssue = Object.entries(contractIssues.by_key || {}).sort((left, right) => numeric(right[1], 0) - numeric(left[1], 0))[0];

  appendSummaryCard(grid, {
    title: "Coverage",
    body: `${numeric(summary.available, 0)}/${numeric(summary.total, 0)} available | ${numeric(summary.runnable, 0)} runnable`,
    detail: `${numeric(summary.enabled, 0)} enabled | ${numeric(summary.disabled, 0)} disabled`,
  });
  appendSummaryCard(grid, {
    title: "Always-on",
    body: `${numeric(summary.always_on_unavailable, 0)} blocked | ${numeric(summary.pinned, 0)} pinned`,
    detail: `${numeric(summary.always_on_available, 0)} always-on available`,
  });
  appendSummaryCard(grid, {
    title: "Sources",
    body: `builtin ${numeric(sources.builtin, 0)} | workspace ${numeric(sources.workspace, 0)} | marketplace ${numeric(sources.marketplace, 0)}`,
    detail: `command ${numeric(executionKinds.command, 0)} | script ${numeric(executionKinds.script, 0)} | none ${numeric(executionKinds.none, 0)}`,
  });
  appendSummaryCard(grid, {
    title: "Managed marketplace",
    body: `${managedTrackedCount} tracked | ${managedReadyCount} ready`,
    detail: managedTrackedCount > 0
        ? [
          `${managedVisibleCount} visible`,
          managedFilterMeta ? `${managedVisibleBlockedCount} blocked visible` : `${managedBlockedCount} blocked`,
          managedFilterMeta ? `${managedBlockedCount} blocked total` : "",
          `${managedDisabledCount} disabled`,
          managedFilterMeta,
        ].filter(Boolean).join(" | ")
      : "No managed marketplace skills discovered.",
  });
  appendSummaryCard(grid, {
    title: "Managed blockers",
    body: `${numeric(managedBlockers.count, managedVisibleBlockedCount)} visible | ${String(managedBlockers.top_kind || "none")}`,
    detail: numeric(managedBlockers.count, managedVisibleBlockedCount) > 0
      ? [
          String(managedBlockers.top_detail || "").trim(),
          Object.entries(managedBlockerKinds)
            .map(([name, count]) => `${name} ${numeric(count, 0)}`)
            .join(" | "),
          String(managedBlockers.top_hint || "").trim(),
        ].filter(Boolean).join(" | ")
      : "No blocked managed marketplace skills are visible in the current slice.",
  });
  appendSummaryCard(grid, {
    title: "Managed remediation",
    body: numeric(managedBlockers.count, managedVisibleBlockedCount) > 0
      ? `${String(managedRemediation.kind || managedBlockers.top_kind || "unknown")} | ${numeric(managedRemediation.count, 0)} path`
      : "No remediation pending",
    detail: numeric(managedBlockers.count, managedVisibleBlockedCount) > 0
      ? [
          String(managedRemediation.summary || "").trim(),
          String(managedRemediation.next_step || "").trim(),
          managedRemediationPaths
            .slice(0, 2)
            .map((row) => {
              const kind = String(row.kind || "unknown").trim();
              const count = numeric(row.count, 0);
              const summary = String(row.summary || "").trim();
              return [kind && `${kind} ${count}`, summary].filter(Boolean).join(": ");
            })
            .filter(Boolean)
            .join(" | "),
        ].filter(Boolean).join(" | ")
      : "No safe remediation step is needed for the current managed blocker slice.",
  });

  const missingEnvItems = ((missingRequirements.env || {}).items) || [];
  const missingBinItems = ((missingRequirements.bin || {}).items) || [];
  const missingOsItems = ((missingRequirements.os || {}).items) || [];
  const missingOtherItems = ((missingRequirements.other || {}).items) || [];
  appendSummaryCard(grid, {
    title: "Missing requirements",
    body: `env ${numeric((missingRequirements.env || {}).count, 0)} | bin ${numeric((missingRequirements.bin || {}).count, 0)} | os ${numeric((missingRequirements.os || {}).count, 0)}`,
    detail: [missingEnvItems[0], missingBinItems[0], missingOsItems[0], missingOtherItems[0]].filter(Boolean).join(" | ") || "No missing runtime requirements recorded.",
  });
  appendSummaryCard(grid, {
    title: "Contract",
    body: `${numeric(contractIssues.total, 0)} issues`,
    detail: topContractIssue ? `${topContractIssue[0]} | ${numeric(topContractIssue[1], 0)} skills` : "No contract issues detected.",
  });
  appendSummaryCard(grid, {
    title: "Watcher",
    body: `${String(watcher.task_state || "stopped")} | ${String(watcher.backend || "polling")}`,
    detail: watcher.last_error
      ? `error ${String(watcher.last_error)}`
      : `interval ${formatDuration(watcher.interval_s || 0)} | pending ${Boolean(watcher.pending)} | debounced ${Boolean(watcher.debounced)}`,
  });

  managedPreviewItems.slice(0, 3).forEach((row) => {
    const blockerKind = String(row.blocker_kind || "").trim();
    const blockerDetail = String(row.blocker_detail || "").trim();
    appendSummaryCard(grid, {
      title: String(row.slug || row.name || "managed skill"),
      body: blockerKind
        ? `${String(row.status || "unknown")} | ${blockerKind}`
        : `${String(row.status || "unknown")} | ${String(row.version || "unversioned")}`,
      detail: [
        blockerDetail,
        String(row.hint || ""),
      ].filter(Boolean).join(" | ") || "Inspect this skill through managed live inventory for more lifecycle details.",
    });
  });

  managedBlockerExamples.slice(0, 2).forEach((row) => {
    appendSummaryCard(grid, {
      title: `Blocked: ${String(row.slug || row.name || "managed skill")}`,
      body: `${String(row.status || "unknown")} | ${String(row.blocker_kind || "unknown")}`,
      detail: [
        String(row.blocker_detail || "").trim(),
        String(row.hint || "").trim(),
      ].filter(Boolean).join(" | "),
    });
  });

  blockedSkills.slice(0, 3).forEach((row) => {
    const missing = Array.isArray(row.missing) ? row.missing : [];
    const issues = Array.isArray(row.contract_issues) ? row.contract_issues : [];
    const requirements = Array.isArray(row.runtime_requirements) ? row.runtime_requirements : [];
    appendSummaryCard(grid, {
      title: String(row.name || row.skill_key || "blocked skill"),
      body: row.available === false ? `blocked | ${String(row.execution_kind || "unknown")}` : "contract issue",
      detail: [
        missing[0],
        issues[0],
        requirements[0],
        row.fallback_hint || "",
      ].filter(Boolean).join(" | ") || "Inspect this skill through skills doctor for remediation details.",
    });
  });
}

function renderKnowledge() {
  const payload = state.dashboardState || {};
  const workspace = payload.workspace || {};
  const onboarding = payload.onboarding || {};
  const bootstrap = payload.bootstrap || {};
  const skills = payload.skills || {};
  const skillRows = Array.isArray(skills.skills) ? skills.skills : [];
  const managedBlockers = (((state.skillsManaged || {}).blockers) && typeof ((state.skillsManaged || {}).blockers) === "object")
    ? (state.skillsManaged || {}).blockers
    : (((skills.managed || {}).blockers) || {});
  const managedRemediation = (managedBlockers.remediation && typeof managedBlockers.remediation === "object")
    ? managedBlockers.remediation
    : {};
  const memory = payload.memory || {};
  const memoryMonitor = memory.monitor || {};
  const memoryRecommendation = memoryRecommendationSummary({ liveQuality: state.memoryQuality, quality: memory.quality || {} });
  const memoryNextSuggestion = memorySuggestionSummary(memory.suggestions || {});
  const remediationSummary = memoryRemediationSnapshot({
    memory,
    liveDoctor: state.memoryDoctor,
    liveOverview: state.memoryOverview,
    liveQuality: state.memoryQuality,
    recommendationSummary: memoryRecommendation,
    suggestionSummary: memoryNextSuggestion,
  });

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
    managed: skills.managed || {},
    managed_live: state.skillsManaged || {},
    managed_blockers: managedBlockers,
    managed_remediation: managedRemediation,
    sources: skills.sources || {},
    missing_requirements: skills.missing_requirements || {},
  });
  setCode("memory-preview", {
    monitor: memoryMonitor,
    analysis: memory.analysis || {},
    profile: memory.profile || {},
    suggestions: memory.suggestions || {},
    quality: memory.quality || {},
    remediation: memory.remediation || {},
    triage_guidance: {
      remediation: remediationSummary,
      recommendation: memoryRecommendation,
      next_suggestion: memoryNextSuggestion,
    },
    overview_live: state.memoryOverview || {},
    quality_live: state.memoryQuality || {},
    doctor_live: state.memoryDoctor || {},
  });

  setBadge("workspace-status", workspace.failed_count ? "attention" : "healthy", workspace.failed_count ? "warn" : "ok");
  setBadge(
    "bootstrap-status",
    onboarding.completed ? "completed" : bootstrap.pending ? "pending" : bootstrap.last_status || "idle",
    onboarding.completed ? "ok" : bootstrap.pending ? "warn" : "ok",
  );
  const skillsSummary = skills.summary || {};
  const skillsWatcher = skills.watcher || {};
  const skillsContract = skills.contract_issues || {};
  const enabledUnavailableCount = skillRows.filter((row) => row && row.enabled !== false && row.available === false).length;
  const skillsBlocked = enabledUnavailableCount > 0 || numeric(skillsSummary.always_on_unavailable, 0) > 0;
  const skillsWatcherFailed = String(skillsWatcher.task_state || "") === "failed" || Boolean(skillsWatcher.last_error);
  const skillsContractBroken = numeric(skillsContract.total, 0) > 0;
  const skillsTone = skillsWatcherFailed ? "danger" : (skillsBlocked || skillsContractBroken ? "warn" : "ok");
  const skillsBadge = skillsWatcherFailed
    ? "watcher failed"
    : skillsBlocked
      ? `${enabledUnavailableCount} blocked`
      : `${numeric(skillsSummary.available, 0)} available`;
  setBadge("skills-status", skillsBadge, skillsTone);
  const doctorLines = numeric((state.memoryDoctor || {}).diagnostics?.history_read_corrupt_lines, 0);
  const doctorRepairs = numeric((state.memoryDoctor || {}).diagnostics?.history_repaired_files, 0);
  const doctorHasIssues = Boolean(state.memoryDoctor) && (
    (state.memoryDoctor || {}).ok === false || doctorLines > 0 || doctorRepairs > 0
  );
  const qualityScore = numeric((state.memoryQuality || {}).report?.score, numeric((state.memoryQuality || {}).state?.current?.score, 0));
  const qualityDrift = String((((state.memoryQuality || {}).report || {}).drift || ((state.memoryQuality || {}).state || {}).current?.drift || {}).assessment || (((state.memoryQuality || {}).state || {}).trend || {}).assessment || "");
  const qualityHasIssues = Boolean(state.memoryQuality) && (
    (state.memoryQuality || {}).ok === false || qualityDrift === "degrading" || qualityScore < 65
  );
  const overviewCoverage = Number((state.memoryOverview || {}).semantic_coverage || 0);
  const overviewTotal = numeric((state.memoryOverview || {}).counts?.total, 0);
  const overviewHasIssues = Boolean(state.memoryOverview) && (
    (state.memoryOverview || {}).ok === false || (overviewTotal > 0 && overviewCoverage < 0.4)
  );
  const memoryBadge = (state.memoryDoctor || {}).ok === false
    ? "doctor failed"
    : ((state.memoryOverview || {}).ok === false
      ? "overview failed"
    : ((state.memoryQuality || {}).ok === false
      ? "quality failed"
      : (doctorHasIssues
        ? "doctor attention"
        : (overviewHasIssues ? "overview attention" : (qualityHasIssues ? "quality attention" : (memoryMonitor.enabled ? "monitoring" : "disabled"))))));
  const memoryTone = (state.memoryDoctor || {}).ok === false
    ? "danger"
    : ((state.memoryOverview || {}).ok === false
      ? "danger"
    : ((state.memoryQuality || {}).ok === false
      ? "danger"
      : (doctorHasIssues || overviewHasIssues || qualityHasIssues ? "warn" : (memoryMonitor.enabled ? "ok" : "warn"))));
  setBadge("memory-status", memoryBadge, memoryTone);
  renderSkillsBoard();
  renderMemoryBoard();
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
    `Gateway auth uses ${auth.header_name || "Authorization"} or query ${auth.query_param || "token"}, while the packaged dashboard prefers ${dashboardSessionHeaderName()} and query ${dashboardSessionQueryParam()} after the one-time exchange. Token configured: ${Boolean((status.auth || {}).token_configured)}. Loopback bypass: ${Boolean((status.auth || {}).allow_loopback_without_auth)}.`,
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
  renderControlPlaneCorrelationBoard();
  renderHandoffGuidance();
}

function renderRuntime() {
  setCode("status-json", state.status || { note: "status unavailable" });
  setCode("diagnostics-json", state.diagnostics || { note: "diagnostics unavailable" });
  setCode("tools-json", state.tools || { note: "tools catalog unavailable" });
  setCode("token-preview", state.tokenInfo || { token_saved: Boolean(state.token || state.dashboardSessionToken), auth_mode: auth.mode || "off" });

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
  renderHttpCorrelationBoard();
  renderToolsSummary();
  renderToolApprovalsSummary();
  renderToolApprovalAuditSummary();
}

function renderControlPlaneCorrelationBoard() {
  const grid = byId("control-plane-correlation-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";

  const diagnostics = state.diagnostics || {};
  const http = diagnostics.http || {};
  const ws = diagnostics.ws || {};
  const httpRequestId = String(http.last_request_id || "").trim();
  const httpRequestMethod = String(http.last_request_method || "").trim() || "GET";
  const httpRequestPath = String(http.last_request_path || "").trim() || "/";
  const httpRequestAt = String(http.last_request_started_at || "").trim();
  const httpErrorId = String(http.last_error_request_id || "").trim();
  const httpErrorMethod = String(http.last_error_method || "").trim() || "GET";
  const httpErrorPath = String(http.last_error_path || "").trim() || "/";
  const httpErrorAt = String(http.last_error_at || "").trim();
  const httpErrorCode = String(http.last_error_code || "").trim() || "http_error";
  const httpErrorMessage = String(http.last_error_message || "").trim();
  const httpErrorStatus = Number(http.last_error_status);
  const wsConnectionId = String(ws.last_connection_id || "").trim();
  const wsConnectionPath = String(ws.last_connection_path || "").trim() || (paths.ws || "/ws");
  const wsConnectionOpenedAt = String(ws.last_connection_opened_at || "").trim();
  const wsClosedId = String(ws.last_connection_closed_id || "").trim();
  const wsClosedAt = String(ws.last_connection_closed_at || "").trim();
  const wsErrorConnectionId = String(ws.last_error_connection_id || "").trim();
  const wsErrorRequestId = String(ws.last_error_request_id || "").trim();
  const wsErrorAt = String(ws.last_error_at || "").trim();
  const wsErrorCode = String(ws.last_error_code || "").trim() || "ws_error";
  const wsErrorMessage = String(ws.last_error_message || "").trim();
  const wsErrorStatus = Number(ws.last_error_status);

  appendSummaryCard(grid, {
    title: "HTTP request",
    body: httpRequestId ? `${httpRequestMethod} ${httpRequestPath}` : "no request yet",
    detail: httpRequestId
      ? `req ${httpRequestId} | ${formatClock(httpRequestAt)}`
      : "The next control-plane request will appear here.",
  });
  appendSummaryCard(grid, {
    title: "HTTP error",
    body: httpErrorAt
      ? `${httpErrorMethod} ${httpErrorPath} | status ${Number.isFinite(httpErrorStatus) ? httpErrorStatus : "-"}`
      : "no recent HTTP error",
    detail: httpErrorAt
      ? [
          `req ${httpErrorId || "-"}`,
          httpErrorCode,
          httpErrorMessage && httpErrorMessage !== httpErrorCode ? httpErrorMessage : "",
          formatClock(httpErrorAt),
        ]
          .filter(Boolean)
          .join(" | ")
      : "The next correlated HTTP failure will be surfaced here.",
  });
  appendSummaryCard(grid, {
    title: "WS connection",
    body: wsConnectionId ? `conn ${wsConnectionId}` : "no WS connection yet",
    detail: wsConnectionOpenedAt
      ? [
          wsConnectionPath,
          `opened ${formatClock(wsConnectionOpenedAt)}`,
          wsClosedAt ? `closed ${formatClock(wsClosedAt)}` : "",
          wsClosedId ? `last close ${wsClosedId}` : "",
        ]
          .filter(Boolean)
          .join(" | ")
      : "Open the chat tab or refresh diagnostics to watch the next gateway socket session.",
  });
  appendSummaryCard(grid, {
    title: "WS error",
    body: wsErrorAt
      ? `${wsErrorCode} | status ${Number.isFinite(wsErrorStatus) ? wsErrorStatus : "-"}`
      : "no recent WS error",
    detail: wsErrorAt
      ? [
          `conn ${wsErrorConnectionId || "-"}`,
          wsErrorRequestId ? `req ${wsErrorRequestId}` : "",
          wsErrorMessage && wsErrorMessage !== wsErrorCode ? wsErrorMessage : "",
          formatClock(wsErrorAt),
        ]
          .filter(Boolean)
          .join(" | ")
      : "The next correlated websocket failure will be surfaced here.",
  });

  const httpRequestMs = parseTimestampMs(httpRequestAt);
  const httpErrorMs = parseTimestampMs(httpErrorAt);
  const wsActivityMs = Math.max(parseTimestampMs(wsConnectionOpenedAt), parseTimestampMs(wsClosedAt));
  const wsErrorMs = parseTimestampMs(wsErrorAt);
  const httpErrorOutstanding = httpErrorMs > 0 && httpErrorMs >= httpRequestMs;
  const wsErrorOutstanding = wsErrorMs > 0 && wsErrorMs >= wsActivityMs;
  const hasOutstandingError = httpErrorOutstanding || wsErrorOutstanding;
  const hasActivity = Boolean(httpRequestMs || wsActivityMs || numeric(ws.active_connections, 0));
  if (hasOutstandingError) {
    const outstandingStatuses = [];
    if (httpErrorOutstanding && Number.isFinite(httpErrorStatus)) {
      outstandingStatuses.push(httpErrorStatus);
    }
    if (wsErrorOutstanding && Number.isFinite(wsErrorStatus)) {
      outstandingStatuses.push(wsErrorStatus);
    }
    const tone = outstandingStatuses.some((value) => value >= 500) ? "danger" : "warn";
    setBadge("control-plane-correlation-status", "attention", tone);
  } else if (hasActivity) {
    setBadge("control-plane-correlation-status", "live", "ok");
  } else {
    setBadge("control-plane-correlation-status", "idle", "warn");
  }
}

function renderHttpCorrelationBoard() {
  const grid = byId("http-correlation-grid");
  if (!grid) {
    return;
  }
  grid.innerHTML = "";
  const http = ((state.diagnostics || {}).http) || {};
  const lastRequestId = String(http.last_request_id || "").trim();
  const lastRequestMethod = String(http.last_request_method || "").trim() || "GET";
  const lastRequestPath = String(http.last_request_path || "").trim() || "/";
  const lastRequestAt = String(http.last_request_started_at || "").trim();
  const lastErrorId = String(http.last_error_request_id || "").trim();
  const lastErrorMethod = String(http.last_error_method || "").trim() || "GET";
  const lastErrorPath = String(http.last_error_path || "").trim() || "/";
  const lastErrorAt = String(http.last_error_at || "").trim();
  const lastErrorCode = String(http.last_error_code || "").trim() || "http_error";
  const lastErrorMessage = String(http.last_error_message || "").trim();
  const lastErrorStatus = Number(http.last_error_status);

  const requestCard = document.createElement("article");
  requestCard.className = "summary-card";
  const requestTitle = document.createElement("strong");
  requestTitle.className = "summary-card__title";
  requestTitle.textContent = "Last request";
  const requestMeta = document.createElement("div");
  requestMeta.className = "summary-card__meta";
  requestMeta.textContent = lastRequestId
    ? `${lastRequestMethod} ${lastRequestPath} | ${formatClock(lastRequestAt)}`
    : "No HTTP request recorded yet.";
  const requestDetail = document.createElement("div");
  requestDetail.className = "summary-card__meta";
  requestDetail.textContent = lastRequestId ? `req ${lastRequestId}` : "Waiting for the next control-plane request.";
  requestCard.append(requestTitle, requestMeta, requestDetail);
  grid.appendChild(requestCard);

  const errorCard = document.createElement("article");
  errorCard.className = "summary-card";
  const errorTitle = document.createElement("strong");
  errorTitle.className = "summary-card__title";
  errorTitle.textContent = "Last error";
  const errorMeta = document.createElement("div");
  errorMeta.className = "summary-card__meta";
  errorMeta.textContent = lastErrorAt
    ? `${lastErrorMethod} ${lastErrorPath} | status ${Number.isFinite(lastErrorStatus) ? lastErrorStatus : "-"} | ${formatClock(lastErrorAt)}`
    : "No recent HTTP error recorded.";
  const errorDetail = document.createElement("div");
  errorDetail.className = "summary-card__meta";
  if (lastErrorAt) {
    const detailParts = [`req ${lastErrorId || "-"}`, lastErrorCode];
    if (lastErrorMessage && lastErrorMessage !== lastErrorCode) {
      detailParts.push(lastErrorMessage);
    }
    errorDetail.textContent = detailParts.join(" | ");
  } else {
    errorDetail.textContent = "The dashboard will surface the next correlated HTTP failure here.";
  }
  errorCard.append(errorTitle, errorMeta, errorDetail);
  grid.appendChild(errorCard);

  if (lastErrorAt) {
    const tone = Number.isFinite(lastErrorStatus) && lastErrorStatus >= 500 ? "danger" : "warn";
    setBadge("http-correlation-status", "recent error", tone);
  } else if (lastRequestId) {
    setBadge("http-correlation-status", "requesting", "ok");
  } else {
    setBadge("http-correlation-status", "idle", "warn");
  }
}

function renderAll() {
  renderOverview();
  renderSessions();
  renderAutomation();
  renderDiscordBoard();
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
  const requestId = String(response.headers.get("X-Request-ID") || payload.request_id || "").trim();
  if (!response.ok) {
    const detail = payload.detail || payload.error || response.statusText;
    if (response.status === 401 && state.dashboardSessionToken && !state.token) {
      persistDashboardSession("");
    }
    const error = new Error(`${response.status} ${detail}`);
    error.requestId = requestId;
    error.status = response.status;
    throw error;
  }
  return attachResponseMeta(payload, { requestId, status: response.status });
}

async function refreshStatus() {
  state.status = await fetchJson(paths.status || "/api/status");
}

async function refreshDashboardState() {
  state.dashboardState = await fetchJson(paths.dashboard_state || "/api/dashboard/state");
  const provider = ((state.dashboardState || {}).provider) || {};
  state.providerStatus = provider.status && typeof provider.status === "object" ? provider.status : null;
  syncGatewayWsEvents();
}

async function refreshDiagnostics() {
  state.diagnostics = await fetchJson(paths.diagnostics || "/api/diagnostics");
  syncGatewayHttpEvents();
}

async function refreshTools() {
  state.tools = await fetchJson(paths.tools || "/api/tools/catalog");
}

async function refreshTokenInfo() {
  try {
    state.tokenInfo = await fetchJson(paths.token || "/api/token");
  } catch (error) {
    state.tokenInfo = { error: error.message, token_saved: Boolean(state.token || state.dashboardSessionToken) };
  }
}

async function refreshAll(reason = "manual") {
  if (state.refreshInFlight) {
    return;
  }
  state.refreshInFlight = true;
  try {
    await Promise.all([refreshStatus(), refreshDashboardState(), refreshDiagnostics(), refreshTools(), refreshTokenInfo()]);
    state.skillsManaged = null;
    state.lastSyncAt = new Date().toISOString();
    if (reason !== "auto") {
      recordEvent("ok", "Dashboard sync complete", "Status, dashboard state, diagnostics, tools, and token metadata refreshed.", reason);
    }
  } catch (error) {
    state.skillsManaged = null;
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

  socket.addEventListener("close", (event) => {
    if (event && event.code === 4401) {
      if (state.dashboardSessionToken && !state.token) {
        persistDashboardSession("");
      }
      updateWsStatus("auth-required");
      recordEvent("warn", "WebSocket auth required", "Paste the gateway token again to reconnect this tab.", "auth");
      return;
    }
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
    storageSet(window.sessionStorage, tokenStorageKey, state.token);
    storageRemove(window.localStorage, tokenStorageKey);
  } else {
    storageRemove(window.sessionStorage, tokenStorageKey);
    storageRemove(window.localStorage, tokenStorageKey);
  }
}

async function exchangeDashboardSession(params = {}) {
  if (typeof params === "string") {
    params = { rawToken: params, source: "auth" };
  }
  const options = params && typeof params === "object" ? params : {};
  const token = String(options.rawToken || "").trim();
  const handoff = String(options.handoffToken || "").trim();
  const source = String(options.source || "auth");
  if (!token && !handoff) {
    throw new Error("dashboard_auth_required");
  }
  const response = await fetch(paths.dashboard_session || "/api/dashboard/session", {
    method: "POST",
    headers: {
      ...(token ? rawAuthHeaders(token) : {}),
      ...(handoff ? { [dashboardHandoffHeaderName()]: handoff } : {}),
      [dashboardClientHeaderName()]: state.dashboardClientId,
    },
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
  const sessionToken = String(payload.session_token || "").trim();
  if (!sessionToken) {
    throw new Error("dashboard_session_missing");
  }
  persistDashboardSession(sessionToken);
  persistToken("");
  const tokenInput = byId("token-input");
  if (tokenInput) {
    tokenInput.value = "";
  }
  recordEvent(
    "ok",
    "Dashboard session established",
    payload.expires_at
      ? `Scoped dashboard session active until ${payload.expires_at}.`
      : "Scoped dashboard session stored for the current browser tab.",
    source,
  );
  return true;
}

async function bootstrapDashboardCredentialFromUrl() {
  const credential = dashboardCredentialFromLocationHash();
  if (!credential.token && !credential.handoff) {
    return false;
  }
  if (window.history && typeof window.history.replaceState === "function") {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
  } else {
    window.location.hash = "";
  }
  await exchangeDashboardSession({
    rawToken: credential.token,
    handoffToken: credential.handoff,
    source: "auth",
  });
  recordEvent(
    "ok",
    credential.handoff ? "Dashboard handoff bootstrapped" : "Gateway token bootstrapped",
    credential.handoff
      ? "Loaded the short-lived dashboard handoff from the URL fragment, exchanged it for a scoped dashboard session, and removed it from the address bar."
      : "Loaded the legacy gateway token from the dashboard URL fragment, exchanged it for a scoped dashboard session, and removed it from the address bar.",
    "auth",
  );
  return true;
}

async function migrateLegacyDashboardToken() {
  if (state.dashboardSessionToken || !state.token) {
    return false;
  }
  await exchangeDashboardSession({ rawToken: state.token, source: "auth" });
  recordEvent(
    "ok",
    "Dashboard token migrated",
    "Replaced the legacy raw gateway token stored in this tab with a scoped dashboard session.",
    "auth",
  );
  return true;
}

async function sendHttpMessage() {
  const sessionId = currentChatSessionId();
  const text = byId("chat-input").value.trim();
  if (!text) {
    return;
  }
  await sendHttpMessageText(text, { sessionId, source: "manual-http" });
  byId("chat-input").value = "";
}

async function sendHttpMessageText(text, options = {}) {
  const sessionId = persistChatSession(String(options.sessionId || currentChatSessionId()));
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
      body: JSON.stringify(buildDashboardChatPayload(sessionId, cleanText)),
    });
    appendChatEntry("assistant", String(payload.text || ""), String(payload.model || "http"));
    recordEvent(
      "ok",
      "HTTP chat request completed",
      cleanText.slice(0, 80),
      appendRequestIdMeta(`${source} | ${payload.model || "http"}`, payload),
    );
  } catch (error) {
    appendChatEntry("assistant", `HTTP error: ${error.message}`, "http");
    recordEvent("danger", "HTTP chat request failed", error.message, appendRequestIdMeta(`${source} | ${sessionId}`, error));
  }
}

function sendWsMessage() {
  const sessionId = currentChatSessionId();
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
  state.ws.send(JSON.stringify(buildDashboardChatPayload(sessionId, text)));
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
      appendRequestIdMeta("control", payload),
    );
    await refreshAll("heartbeat");
  } catch (error) {
    recordEvent("danger", "Heartbeat trigger failed", error.message, appendRequestIdMeta("control", error));
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
      appendRequestIdMeta("channels", payload),
    );
    await refreshAll("delivery-replay");
  } catch (error) {
    recordEvent("danger", "Dead-letter replay failed", error.message, appendRequestIdMeta("channels", error));
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
      appendRequestIdMeta("channels", payload),
    );
    await refreshAll("inbound-replay");
  } catch (error) {
    recordEvent("danger", "Inbound replay failed", error.message, appendRequestIdMeta("channels", error));
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
      appendRequestIdMeta("channels", payload),
    );
    await refreshAll("channel-recovery");
  } catch (error) {
    recordEvent("danger", "Channel recovery failed", error.message, appendRequestIdMeta("channels", error));
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
      appendRequestIdMeta(component || "all-components", payload),
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("supervisor-recover");
  } catch (error) {
    recordEvent(
      "danger",
      "Supervisor recovery failed",
      error.message,
      appendRequestIdMeta(component || "all-components", error),
    );
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerProviderRecovery() {
  const button = byId("recover-provider");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.provider_recover || "/v1/control/provider/recover", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.cleared ? "ok" : "warn",
      "Provider recovery finished",
      `${numeric(summary.cleared, 0)} suppression slot(s) cleared | ${numeric(summary.matched, 0)} matched`,
      appendRequestIdMeta("provider", payload),
    );
    await refreshAll("provider-recover");
  } catch (error) {
    recordEvent("danger", "Provider recovery failed", error.message, appendRequestIdMeta("provider", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerProviderStatusInspect() {
  const button = byId("inspect-provider-status");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.provider_status || "/api/provider/status");
    const lastLiveProbe = payload.last_live_probe || {};
    const lastCapabilityProbe = payload.last_capability_probe || {};
    state.providerStatus = payload;
    recordEvent(
      payload.ok === false ? "warn" : "ok",
      "Provider cache inspected",
      [
        String(payload.provider || payload.selected_provider || "provider"),
        String(payload.transport || "unknown"),
        Object.keys(lastLiveProbe).length ? String(lastLiveProbe.error || lastLiveProbe.detail || "live probe cached") : "no live probe cache",
        Object.keys(lastCapabilityProbe).length ? String(lastCapabilityProbe.detail || "capability cached") : "no capability cache",
      ].filter(Boolean).join(" | "),
      appendRequestIdMeta("provider", payload),
    );
    renderAll();
  } catch (error) {
    recordEvent("danger", "Provider cache inspection failed", error.message, appendRequestIdMeta("provider", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerToolApprovalsInspect() {
  const button = byId("inspect-tool-approvals");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchToolApprovalsSnapshot();
    const requests = Array.isArray(payload.requests) ? payload.requests : [];
    const grants = Array.isArray(payload.grants) ? payload.grants : [];
    const pendingVisible = requests.filter((row) => String(row?.status || "").trim().toLowerCase() === "pending").length;
    const topRequest = requests[0] || {};
    const filterMeta = summarizeToolApprovalsFilter(payload);
    state.toolApprovals = payload;
    recordEvent(
      pendingVisible > 0 ? "warn" : "ok",
      "Tool approvals inspected",
      requests.length
        ? [
            `${numeric(payload.count, requests.length)} requests`,
            `${numeric(payload.grant_count, grants.length)} grants`,
            filterMeta,
            `${String(topRequest.tool || "tool")} ${approvalRuleLabel(topRequest) || String(topRequest.status || "pending")}`,
          ].filter(Boolean).join(" | ")
        : [
            `${numeric(payload.grant_count, grants.length)} grants`,
            filterMeta,
            "No approval requests matched.",
          ].filter(Boolean).join(" | "),
      appendRequestIdMeta("tools-approvals", payload),
    );
    renderAll();
  } catch (error) {
    state.toolApprovals = null;
    recordEvent("danger", "Tool approvals inspection failed", error.message, appendRequestIdMeta("tools-approvals", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function fetchToolApprovalsSnapshot(filter = readToolApprovalsFilter()) {
  const url = new URL(paths.tools_approvals || "/api/tools/approvals", window.location.origin);
  if (filter.status) {
    url.searchParams.set("status", filter.status);
  }
  if (filter.tool) {
    url.searchParams.set("tool", filter.tool);
  }
  if (filter.rule) {
    url.searchParams.set("rule", filter.rule);
  }
  url.searchParams.set("include_grants", "true");
  url.searchParams.set("limit", "20");
  return await fetchJson(`${url.pathname}${url.search}`);
}

function toolApprovalReviewPath(requestId, decision) {
  const base = String(paths.tools_approvals || "/api/tools/approvals").replace(/\/+$/, "");
  const action = decision === "rejected" ? "reject" : "approve";
  return `${base}/${encodeURIComponent(String(requestId || "").trim())}/${action}`;
}

function toolApprovalAuditPath() {
  return String(paths.tools_approvals_audit || "/api/tools/approvals/audit").trim() || "/api/tools/approvals/audit";
}

function toolApprovalAuditExportPath() {
  return String(paths.tools_approvals_audit_export || "/api/tools/approvals/audit/export").trim() || "/api/tools/approvals/audit/export";
}

function toolGrantRevokePath() {
  return String(paths.tools_grants_revoke || "/api/tools/grants/revoke").trim() || "/api/tools/grants/revoke";
}

async function fetchText(path, options = {}) {
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
  const requestId = String(response.headers.get("X-Request-ID") || payload.request_id || "").trim();
  if (!response.ok) {
    const detail = payload.detail || payload.error || response.statusText || "request_failed";
    if (response.status === 401 && state.dashboardSessionToken && !state.token) {
      persistDashboardSession("");
    }
    const error = new Error(`${response.status} ${detail}`);
    error.requestId = requestId;
    error.status = response.status;
    throw error;
  }
  return { text, request_id: requestId, status: response.status };
}

function downloadTextFile(filename, text) {
  const blob = new Blob([String(text || "")], { type: "application/x-ndjson;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

async function fetchToolApprovalAuditSnapshot(filter = readToolApprovalAuditFilter()) {
  const url = new URL(toolApprovalAuditPath(), window.location.origin);
  if (filter.action) {
    url.searchParams.set("action", filter.action);
  }
  if (filter.request_id) {
    url.searchParams.set("request_id", filter.request_id);
  }
  if (filter.tool) {
    url.searchParams.set("tool", filter.tool);
  }
  if (filter.rule) {
    url.searchParams.set("rule", filter.rule);
  }
  url.searchParams.set("limit", "20");
  return await fetchJson(`${url.pathname}${url.search}`);
}

async function exportToolApprovalAudit() {
  const button = byId("export-tool-approval-audit");
  if (button) {
    button.disabled = true;
  }
  try {
    const filter = readToolApprovalAuditFilter();
    const url = new URL(toolApprovalAuditExportPath(), window.location.origin);
    if (filter.action) {
      url.searchParams.set("action", filter.action);
    }
    if (filter.request_id) {
      url.searchParams.set("request_id", filter.request_id);
    }
    if (filter.tool) {
      url.searchParams.set("tool", filter.tool);
    }
    if (filter.rule) {
      url.searchParams.set("rule", filter.rule);
    }
    url.searchParams.set("limit", "200");
    const payload = await fetchText(`${url.pathname}${url.search}`);
    const lineCount = payload.text ? payload.text.split(/\r?\n/).filter((line) => String(line || "").trim()).length : 0;
    const suffix = String(filter.request_id || "").trim() || String(filter.action || "").trim() || "latest";
    downloadTextFile(`clawlite-tools-approval-audit-${suffix}.ndjson`, payload.text || "");
    recordEvent(
      lineCount > 0 ? "ok" : "warn",
      "Tool approval audit exported",
      [`${lineCount} rows`, summarizeToolApprovalAuditFilter(filter) || "latest audit snapshot"].filter(Boolean).join(" | "),
      appendRequestIdMeta("tools-approval-audit-export", payload),
    );
  } catch (error) {
    recordEvent("danger", "Tool approval audit export failed", error.message, appendRequestIdMeta("tools-approval-audit-export", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerToolApprovalAuditInspect() {
  const button = byId("inspect-tool-approval-audit");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchToolApprovalAuditSnapshot();
    const entries = Array.isArray(payload.entries) ? payload.entries : [];
    const latest = entries[0] || {};
    const filterMeta = summarizeToolApprovalAuditFilter(payload);
    state.toolApprovalAudit = payload;
    recordEvent(
      numeric(payload.error_count, 0) > 0 ? "warn" : "ok",
      "Tool approval audit inspected",
      entries.length
        ? [
            `${numeric(payload.count, entries.length)} rows`,
            `${numeric(payload.changed_count, 0)} changed`,
            filterMeta,
            String(payload.latest_reason || "").trim() ? String(payload.latest_reason).trim() : "",
            `${String(latest.action || "review")} ${String(latest.status || "").trim() || "unknown"}`,
          ].filter(Boolean).join(" | ")
        : [filterMeta, "No approval audit rows matched."].filter(Boolean).join(" | "),
      appendRequestIdMeta("tools-approval-audit", payload),
    );
    renderAll();
  } catch (error) {
    state.toolApprovalAudit = null;
    recordEvent("danger", "Tool approval audit failed", error.message, appendRequestIdMeta("tools-approval-audit", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function reviewToolApproval(decision) {
  const requestInput = byId("tool-approval-request-id");
  const noteInput = byId("tool-approval-note");
  const approveButton = byId("approve-tool-request");
  const rejectButton = byId("reject-tool-request");
  const requestId = String(requestInput?.value || "").trim();
  const note = String(noteInput?.value || "").trim();
  if (!requestId) {
    recordEvent("warn", "Tool approval review skipped", "Enter a pending request id first.", "tools-approvals");
    return;
  }
  if (approveButton) {
    approveButton.disabled = true;
  }
  if (rejectButton) {
    rejectButton.disabled = true;
  }
  try {
    const payload = await fetchJson(toolApprovalReviewPath(requestId, decision), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ note }),
    });
    const summary = payload.summary || {};
    const changed = summary.changed !== false;
    const status = String(summary.status || decision || "").trim().toLowerCase();
    recordEvent(
      changed ? (decision === "rejected" ? "warn" : "ok") : "warn",
      changed
        ? (decision === "rejected" ? "Tool approval rejected" : "Tool approval approved")
        : "Tool approval already reviewed",
      [
        String(summary.request_id || requestId),
        approvalToolLabel(summary) || "tool",
        approvalRuleLabel(summary) || (changed ? String(summary.status || decision) : `already ${status || decision}`),
      ].filter(Boolean).join(" | "),
      appendRequestIdMeta("tools-approvals", payload),
    );
    if (requestInput) {
      requestInput.value = "";
    }
    if (noteInput) {
      noteInput.value = "";
    }
    try {
      state.toolApprovals = await fetchToolApprovalsSnapshot();
    } catch (refreshError) {
      state.toolApprovals = null;
      recordEvent(
        "warn",
        "Tool approvals refresh failed",
        refreshError.message,
        appendRequestIdMeta("tools-approvals", refreshError),
      );
    }
    if (state.toolApprovalAudit) {
      try {
        state.toolApprovalAudit = await fetchToolApprovalAuditSnapshot();
      } catch (refreshError) {
        state.toolApprovalAudit = null;
        recordEvent(
          "warn",
          "Tool approval audit refresh failed",
          refreshError.message,
          appendRequestIdMeta("tools-approval-audit", refreshError),
        );
      }
    }
    renderAll();
  } catch (error) {
    recordEvent(
      "danger",
      decision === "rejected" ? "Tool rejection failed" : "Tool approval failed",
      error.message,
      appendRequestIdMeta("tools-approvals", error),
    );
    renderAll();
  }
}

async function revokeSelectedToolGrant() {
  const revokeButton = byId("revoke-tool-grant");
  const approvals = state.toolApprovals || {};
  const grant = selectedToolGrant(approvals.grants);
  if (!grant) {
    recordEvent("warn", "Tool grant revoke skipped", "Select a visible exact grant first.", "tools-approvals");
    return;
  }
  if (revokeButton) {
    revokeButton.disabled = true;
  }
  try {
    const payload = await fetchJson(toolGrantRevokePath(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: String(grant.session_id || "").trim(),
        channel: String(grant.channel || "").trim(),
        rule: String(grant.rule || "").trim(),
        request_id: String(grant.request_id || "").trim(),
        scope: String(grant.scope || "").trim(),
      }),
    });
    const summary = payload.summary || {};
    const removedCount = numeric(summary.removed_count, 0);
    recordEvent(
      removedCount > 0 ? "ok" : "warn",
      removedCount > 0 ? "Tool grant revoked" : "Tool grant already cleared",
      [
        approvalToolLabel(grant) || "grant",
        String(grant.rule || ""),
        String(grant.scope || ""),
        String(grant.session_id || ""),
        String(grant.channel || ""),
      ].filter(Boolean).join(" | "),
      appendRequestIdMeta("tools-approvals", payload),
    );
    try {
      state.toolApprovals = await fetchToolApprovalsSnapshot();
    } catch (refreshError) {
      state.toolApprovals = null;
      recordEvent(
        "warn",
        "Tool approvals refresh failed",
        refreshError.message,
        appendRequestIdMeta("tools-approvals", refreshError),
      );
    }
    if (state.toolApprovalAudit) {
      try {
        state.toolApprovalAudit = await fetchToolApprovalAuditSnapshot();
      } catch (refreshError) {
        state.toolApprovalAudit = null;
        recordEvent(
          "warn",
          "Tool approval audit refresh failed",
          refreshError.message,
          appendRequestIdMeta("tools-approval-audit", refreshError),
        );
      }
    }
    renderAll();
  } catch (error) {
    recordEvent(
      "danger",
      "Tool grant revoke failed",
      error.message,
      appendRequestIdMeta("tools-approvals", error),
    );
    renderAll();
  }
}

async function triggerSkillsRefresh() {
  const button = byId("refresh-skills-inventory");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.skills_refresh || "/v1/control/skills/refresh", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ force: true }),
    });
    const summary = payload.summary || {};
    recordEvent(
      Boolean((summary.watcher || {}).last_error) ? "warn" : "ok",
      "Skills refresh finished",
      `${summary.refresh?.refreshed ? "refreshed" : "unchanged"} | ${numeric((summary.skills || {}).available, 0)} available | ${numeric((summary.skills || {}).runnable, 0)} runnable`,
      appendRequestIdMeta("skills", payload),
    );
    await refreshAll("skills-refresh");
  } catch (error) {
    recordEvent("danger", "Skills refresh failed", error.message, appendRequestIdMeta("skills", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerSkillsDoctor() {
  const button = byId("doctor-skills-inventory");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.skills_doctor || "/v1/control/skills/doctor", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ include_all: false }),
    });
    const summary = payload.summary || {};
    const recommendations = Array.isArray(summary.recommendations) ? summary.recommendations : [];
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Skills doctor finished",
      `${numeric(summary.count, 0)} actionable | ${recommendations[0] || "No blocking skills detected."}`,
      appendRequestIdMeta("skills-doctor", payload),
    );
  } catch (error) {
    recordEvent("danger", "Skills doctor failed", error.message, appendRequestIdMeta("skills-doctor", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerSkillsValidate() {
  const button = byId("validate-skills-inventory");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.skills_validate || "/v1/control/skills/validate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ force: true, include_all: false }),
    });
    const summary = payload.summary || {};
    const refresh = summary.refresh || {};
    const recommendations = Array.isArray(summary.recommendations) ? summary.recommendations : [];
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Skills validate finished",
      `${refresh.refreshed ? "refreshed" : "unchanged"} | ${numeric(summary.count, 0)} actionable | ${recommendations[0] || "No blocking skills detected."}`,
      appendRequestIdMeta("skills-validate", payload),
    );
    await refreshAll("skills-validate");
  } catch (error) {
    recordEvent("danger", "Skills validate failed", error.message, appendRequestIdMeta("skills-validate", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerSkillsSync() {
  const button = byId("sync-managed-skills");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.skills_sync || "/v1/control/skills/sync", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const summary = payload.summary || {};
    const managed = summary.managed || {};
    if (summary.ok === false) {
      state.skillsManaged = null;
      recordEvent(
        "danger",
        "Managed skills sync failed",
        String(summary.stderr || summary.error || "Managed marketplace sync failed."),
        appendRequestIdMeta("skills-sync", payload),
      );
      renderAll();
      return;
    }
    recordEvent(
      numeric(summary.blocked_count, 0) > 0 ? "warn" : "ok",
      "Managed skills sync finished",
      [
        (summary.refresh || {}).refreshed ? "refreshed" : "unchanged",
        `${numeric(summary.managed_count, numeric(managed.total_count, 0))} tracked`,
        `${numeric(summary.ready_count, numeric(managed.ready_count, 0))} ready`,
        `${numeric(summary.blocked_count, numeric(managed.blocked_count, 0))} blocked`,
      ].join(" | "),
      appendRequestIdMeta("skills-sync", payload),
    );
    await refreshAll("skills-sync");
    state.skillsManaged = managed;
    renderAll();
  } catch (error) {
    state.skillsManaged = null;
    recordEvent("danger", "Managed skills sync failed", error.message, appendRequestIdMeta("skills-sync", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerSkillsManagedInspect() {
  const button = byId("inspect-managed-skills");
  const filter = readManagedSkillsFilter();
  const url = new URL(paths.skills_managed || "/v1/control/skills/managed", window.location.origin);
  if (filter.status) {
    url.searchParams.set("status", filter.status);
  }
  if (filter.query) {
    url.searchParams.set("query", filter.query);
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(`${url.pathname}${url.search}`);
    const summary = payload.summary || {};
    const rows = Array.isArray(summary.skills) ? summary.skills : [];
    const topRow = rows[0] || {};
    const blockers = (summary.blockers && typeof summary.blockers === "object") ? summary.blockers : {};
    const filterMeta = summarizeManagedFilter(summary);
    state.skillsManaged = summary;
    recordEvent(
      numeric(summary.visible_blocked_count, numeric(blockers.count, 0)) > 0 ? "warn" : "ok",
      "Managed skills inspected",
      rows.length
        ? [
            `${numeric(summary.count, 0)} visible`,
            `${numeric(summary.total_count, 0)} total`,
            filterMeta,
            numeric(summary.visible_blocked_count, numeric(blockers.count, 0)) > 0
              ? `${numeric(summary.visible_blocked_count, numeric(blockers.count, 0))} blocker(s) visible`
              : "",
            filterMeta ? `${numeric(summary.blocked_count, 0)} blocker(s) total` : "",
            String(blockers.top_kind || "").trim() ? `${String(blockers.top_kind)}:${String(blockers.top_detail || "top")}` : "",
            `${String(topRow.slug || topRow.name || "managed skill")} ${String(topRow.status || "unknown")}`,
          ].filter(Boolean).join(" | ")
        : [
            `${numeric(summary.total_count, 0)} tracked`,
            filterMeta,
            "No managed skills discovered.",
          ].filter(Boolean).join(" | "),
      appendRequestIdMeta("skills-managed", payload),
    );
    renderAll();
  } catch (error) {
    state.skillsManaged = null;
    recordEvent("danger", "Managed skills inspection failed", error.message, appendRequestIdMeta("skills-managed", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerAutonomyWake() {
  const button = byId("trigger-autonomy-wake");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.autonomy_wake || "/v1/control/autonomy/wake", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ kind: "proactive" }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.result?.status && String(summary.result.status).startsWith("wake_") ? "warn" : "ok",
      "Autonomy wake finished",
      `${summary.kind || "proactive"} | ${safeJson(summary.result || {})}`,
      appendRequestIdMeta("autonomy", payload),
    );
    await refreshAll("autonomy-wake");
  } catch (error) {
    recordEvent("danger", "Autonomy wake failed", error.message, appendRequestIdMeta("autonomy", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerMemorySuggestRefresh() {
  const button = byId("refresh-memory-suggestions");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.memory_suggest_refresh || "/v1/control/memory/suggest/refresh", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Memory suggestion refresh finished",
      `${numeric(summary.count, 0)} suggestions | source ${String(summary.source || "unknown")}`,
      appendRequestIdMeta("memory", payload),
    );
    await refreshAll("memory-suggest-refresh");
  } catch (error) {
    recordEvent("danger", "Memory suggestion refresh failed", error.message, appendRequestIdMeta("memory", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerMemoryDoctor() {
  const button = byId("run-memory-doctor");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.memory_doctor || "/v1/control/memory/doctor", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ repair: false }),
    });
    const summary = payload.summary || {};
    const diagnostics = summary.diagnostics || {};
    state.memoryDoctor = summary;
    recordEvent(
      summary.ok === false ? "danger" : (numeric(diagnostics.history_read_corrupt_lines, 0) > 0 ? "warn" : "ok"),
      summary.ok === false ? "Memory doctor failed" : "Memory doctor finished",
      summary.ok === false
        ? String((summary.error || {}).message || (summary.error || {}).type || "Memory doctor failed.")
        : `${numeric((summary.counts || {}).total, 0)} entries | corrupt ${numeric(diagnostics.history_read_corrupt_lines, 0)} | repaired ${numeric(diagnostics.history_repaired_files, 0)}`,
      appendRequestIdMeta("memory-doctor", payload),
    );
    renderAll();
  } catch (error) {
    state.memoryDoctor = null;
    recordEvent("danger", "Memory doctor failed", error.message, appendRequestIdMeta("memory-doctor", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerMemoryOverview() {
  const button = byId("run-memory-overview");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.memory_overview || "/v1/control/memory/overview", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const summary = payload.summary || {};
    const total = numeric((summary.counts || {}).total, 0);
    const semanticCoverage = Math.round(Number(summary.semantic_coverage || 0) * 100);
    state.memoryOverview = summary;
    recordEvent(
      summary.ok === false ? "danger" : (total > 0 && Number(summary.semantic_coverage || 0) < 0.4 ? "warn" : "ok"),
      summary.ok === false ? "Memory overview failed" : "Memory overview updated",
      summary.ok === false
        ? String((summary.error || {}).message || (summary.error || {}).type || "Memory overview failed.")
        : `${total} entries | ${semanticCoverage}% semantic | proactive ${summary.proactive_enabled ? "on" : "off"}`,
      appendRequestIdMeta("memory-overview", payload),
    );
    renderAll();
  } catch (error) {
    state.memoryOverview = null;
    recordEvent("danger", "Memory overview failed", error.message, appendRequestIdMeta("memory-overview", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerMemoryQuality() {
  const button = byId("run-memory-quality");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.memory_quality || "/v1/control/memory/quality", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const summary = payload.summary || {};
    const report = summary.report || {};
    const statePayload = summary.state || {};
    const drift = String((report.drift || {}).assessment || (statePayload.trend || {}).assessment || "stable");
    const score = numeric(report.score, numeric((statePayload.current || {}).score, 0));
    state.memoryQuality = summary;
    if (summary.ok !== false && state.dashboardState && state.dashboardState.memory) {
      state.dashboardState.memory.quality = statePayload;
    }
    recordEvent(
      summary.ok === false ? "danger" : (drift === "degrading" || score < 65 ? "warn" : "ok"),
      summary.ok === false ? "Memory quality failed" : "Memory quality updated",
      summary.ok === false
        ? String((summary.error || {}).message || (summary.error || {}).type || "Memory quality snapshot failed.")
        : `${score} score | ${drift} drift | ${String((report.recommendations || [])[0] || "Quality snapshot persisted.")}`,
      appendRequestIdMeta("memory-quality", payload),
    );
    renderAll();
  } catch (error) {
    state.memoryQuality = null;
    recordEvent("danger", "Memory quality failed", error.message, appendRequestIdMeta("memory-quality", error));
    renderAll();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerMemorySnapshotCreate() {
  const button = byId("create-memory-snapshot");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.memory_snapshot_create || "/v1/control/memory/snapshot/create", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ tag: "dashboard" }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Memory snapshot created",
      `${String(summary.version_id || "unknown")} | tag ${String(summary.tag || "")}`,
      appendRequestIdMeta("memory", payload),
    );
    state.memoryDoctor = null;
    state.memoryOverview = null;
    state.memoryQuality = null;
    await refreshAll("memory-snapshot-create");
  } catch (error) {
    recordEvent("danger", "Memory snapshot creation failed", error.message, appendRequestIdMeta("memory", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerMemorySnapshotRollback() {
  const input = byId("memory-rollback-version-id");
  const button = byId("rollback-memory-snapshot");
  const versionId = String(input?.value || "").trim();
  if (!versionId) {
    recordEvent("warn", "Memory snapshot rollback skipped", "Enter a snapshot version_id first.", "memory");
    return;
  }
  const confirmed = typeof window.confirm === "function"
    ? window.confirm(`Rollback memory to snapshot ${versionId}? Use this only for deliberate recovery.`)
    : true;
  if (!confirmed) {
    return;
  }
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.memory_snapshot_rollback || "/v1/control/memory/snapshot/rollback", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ version_id: versionId, confirm: true }),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Memory snapshot rollback finished",
      summary.ok === false ? String(summary.error || "unknown_error") : `${versionId} restored`,
      appendRequestIdMeta("memory", payload),
    );
    state.memoryDoctor = null;
    state.memoryOverview = null;
    state.memoryQuality = null;
    if (input) {
      input.value = "";
    }
    await refreshAll("memory-snapshot-rollback");
  } catch (error) {
    recordEvent("danger", "Memory snapshot rollback failed", error.message, appendRequestIdMeta("memory", error));
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
      appendRequestIdMeta("telegram", payload),
    );
    await refreshAll("telegram-refresh");
  } catch (error) {
    recordEvent("danger", "Telegram transport refresh failed", error.message, appendRequestIdMeta("telegram", error));
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function triggerDiscordRefresh() {
  const button = byId("refresh-discord-transport");
  if (button) {
    button.disabled = true;
  }
  try {
    const payload = await fetchJson(paths.discord_refresh || "/v1/control/channels/discord/refresh", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });
    const summary = payload.summary || {};
    recordEvent(
      summary.ok === false ? "warn" : "ok",
      "Discord transport refresh finished",
      `${summary.gateway_restarted ? "gateway restarted" : "state refreshed"} | running ${Boolean(summary.status?.running)}`,
      appendRequestIdMeta("discord", payload),
    );
    await refreshAll("discord-refresh");
  } catch (error) {
    recordEvent("danger", "Discord transport refresh failed", error.message, appendRequestIdMeta("discord", error));
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
      appendRequestIdMeta("telegram", payload),
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-pairing-approve");
  } catch (error) {
    recordEvent("danger", "Telegram pairing approval failed", error.message, appendRequestIdMeta("telegram", error));
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
      appendRequestIdMeta("telegram", payload),
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-pairing-reject");
  } catch (error) {
    recordEvent("danger", "Telegram pairing rejection failed", error.message, appendRequestIdMeta("telegram", error));
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
      appendRequestIdMeta("telegram", payload),
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-pairing-revoke");
  } catch (error) {
    recordEvent("danger", "Telegram pairing revoke failed", error.message, appendRequestIdMeta("telegram", error));
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
      appendRequestIdMeta("telegram", payload),
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-offset-commit");
  } catch (error) {
    recordEvent("danger", "Telegram offset advance failed", error.message, appendRequestIdMeta("telegram", error));
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
      appendRequestIdMeta("telegram", payload),
    );
    if (input) {
      input.value = "";
    }
    await refreshAll("telegram-offset-sync");
  } catch (error) {
    recordEvent("danger", "Telegram next offset sync failed", error.message, appendRequestIdMeta("telegram", error));
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
      appendRequestIdMeta("telegram", payload),
    );
    await refreshAll("telegram-offset-reset");
  } catch (error) {
    recordEvent("danger", "Telegram offset reset failed", error.message, appendRequestIdMeta("telegram", error));
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

  byId("token-input").value = "";
  const sessionInput = byId("session-input");
  sessionInput.value = state.sessionId;
  setText("metric-session-route", `chat -> ${state.sessionId}`);
  sessionInput.addEventListener("change", () => {
    const sessionId = persistChatSession(sessionInput.value);
    sessionInput.value = sessionId;
    setText("metric-session-route", `chat -> ${sessionId}`);
  });

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
    try {
      await exchangeDashboardSession({ rawToken: byId("token-input").value, source: "auth" });
      connectWs();
      await refreshAll("token-save");
    } catch (error) {
      recordEvent("danger", "Dashboard session exchange failed", error.message, "auth");
      renderAll();
    }
  });

  byId("clear-token").addEventListener("click", async () => {
    persistToken("");
    persistDashboardSession("");
    byId("token-input").value = "";
    recordEvent("warn", "Dashboard token cleared", "Dashboard returned to anonymous mode.", "auth");
    connectWs();
    await refreshAll("token-clear");
  });

  byId("refresh-all").addEventListener("click", () => {
    void refreshAll("manual");
  });
  byId("trigger-autonomy-wake").addEventListener("click", () => {
    void triggerAutonomyWake();
  });
  byId("run-memory-doctor").addEventListener("click", () => {
    void triggerMemoryDoctor();
  });
  byId("run-memory-overview").addEventListener("click", () => {
    void triggerMemoryOverview();
  });
  byId("run-memory-quality").addEventListener("click", () => {
    void triggerMemoryQuality();
  });
  byId("refresh-memory-suggestions").addEventListener("click", () => {
    void triggerMemorySuggestRefresh();
  });
  byId("create-memory-snapshot").addEventListener("click", () => {
    void triggerMemorySnapshotCreate();
  });
  byId("rollback-memory-snapshot").addEventListener("click", () => {
    void triggerMemorySnapshotRollback();
  });
  byId("recover-provider").addEventListener("click", () => {
    void triggerProviderRecovery();
  });
  byId("inspect-provider-status").addEventListener("click", () => {
    void triggerProviderStatusInspect();
  });
  byId("inspect-tool-approvals").addEventListener("click", () => {
    void triggerToolApprovalsInspect();
  });
  byId("inspect-tool-approval-audit").addEventListener("click", () => {
    void triggerToolApprovalAuditInspect();
  });
  byId("export-tool-approval-audit").addEventListener("click", () => {
    void exportToolApprovalAudit();
  });
  byId("approve-tool-request").addEventListener("click", () => {
    void reviewToolApproval("approved");
  });
  byId("reject-tool-request").addEventListener("click", () => {
    void reviewToolApproval("rejected");
  });
  byId("tool-grant-selection").addEventListener("change", () => {
    renderToolApprovalsSummary();
  });
  byId("revoke-tool-grant").addEventListener("click", () => {
    void revokeSelectedToolGrant();
  });
  byId("tool-approval-request-id").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void reviewToolApproval("approved");
    }
  });
  byId("tool-approvals-tool-filter").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void triggerToolApprovalsInspect();
    }
  });
  byId("tool-approvals-rule-filter").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void triggerToolApprovalsInspect();
    }
  });
  byId("tool-approval-audit-action-filter").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void triggerToolApprovalAuditInspect();
    }
  });
  byId("tool-approval-audit-request-id").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void triggerToolApprovalAuditInspect();
    }
  });
  byId("tool-approval-note").addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      void reviewToolApproval("approved");
    }
  });
  byId("refresh-skills-inventory").addEventListener("click", () => {
    void triggerSkillsRefresh();
  });
  byId("doctor-skills-inventory").addEventListener("click", () => {
    void triggerSkillsDoctor();
  });
  byId("validate-skills-inventory").addEventListener("click", () => {
    void triggerSkillsValidate();
  });
  byId("sync-managed-skills").addEventListener("click", () => {
    void triggerSkillsSync();
  });
  byId("inspect-managed-skills").addEventListener("click", () => {
    void triggerSkillsManagedInspect();
  });
  byId("managed-skills-query-filter").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void triggerSkillsManagedInspect();
    }
  });
  byId("recover-supervisor-component").addEventListener("click", () => {
    void triggerSupervisorRecovery();
  });
  byId("recover-channels").addEventListener("click", () => {
    void triggerChannelRecovery();
  });
  byId("refresh-discord-transport").addEventListener("click", () => {
    void triggerDiscordRefresh();
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

async function initializeDashboard() {
  bindEvents();
  setActiveTab(state.activeTab);
  renderAll();
  recordEvent("ok", "Dashboard booted", "Packaged shell loaded with gateway bootstrap metadata.", "ui");
  try {
    await bootstrapDashboardCredentialFromUrl();
    await migrateLegacyDashboardToken();
  } catch (error) {
    recordEvent("danger", "Dashboard auth bootstrap failed", error.message, "auth");
  }
  await refreshAll("initial");
  scheduleAutoRefresh();
  connectWs();
}

void initializeDashboard();
