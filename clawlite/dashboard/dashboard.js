const bootstrap = window.__CLAWLITE_DASHBOARD_BOOTSTRAP__ || {};
const auth = bootstrap.auth || {};
const paths = bootstrap.paths || {};
const tokenStorageKey = "clawlite.dashboard.token";

const state = {
  activeTab: "overview",
  token: window.localStorage.getItem(tokenStorageKey) || "",
  ws: null,
  wsState: "offline",
  reconnectTimer: null,
  status: bootstrap.control_plane || null,
  diagnostics: null,
  tools: null,
  tokenInfo: null,
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

function appendChatEntry(role, text, meta = "") {
  const log = byId("chat-log");
  if (!log) {
    return;
  }
  const entry = document.createElement("article");
  entry.className = `chat-entry chat-entry--${role}`;
  const timestamp = new Date().toLocaleTimeString();
  entry.innerHTML = `
    <div class="chat-entry__meta">
      <span>${role}</span>
      <span>${meta || timestamp}</span>
    </div>
    <div>${text}</div>
  `;
  log.prepend(entry);
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
  setText("auth-badge", String((status.auth || {}).posture || auth.posture || "open"));
  setText(
    "auth-summary",
    `Header ${auth.header_name || "Authorization"} or query ${auth.query_param || "token"}. Token configured: ${Boolean((status.auth || {}).token_configured)}.`,
  );

  const endpointList = byId("endpoint-list");
  if (endpointList) {
    endpointList.innerHTML = "";
    Object.entries(paths).forEach(([label, path]) => {
      const item = document.createElement("li");
      item.innerHTML = `<code>${path}</code><span>${label}</span>`;
      endpointList.appendChild(item);
    });
  }
}

function renderRuntime() {
  setCode("status-json", state.status || { note: "status unavailable" });
  setCode("diagnostics-json", state.diagnostics || { note: "diagnostics unavailable" });
  setCode("tools-json", state.tools || { note: "tools catalog unavailable" });
  setCode("token-preview", state.tokenInfo || { token_saved: Boolean(state.token), auth_mode: auth.mode || "off" });

  const components = (state.status || {}).components || {};
  setCode("components-preview", components);
  if (state.diagnostics) {
    setText("diag-status", "live");
    setCode("runtime-preview", {
      queue: state.diagnostics.queue,
      channels: state.diagnostics.channels,
      heartbeat: state.diagnostics.heartbeat,
      autonomy: state.diagnostics.autonomy,
      supervisor: state.diagnostics.supervisor,
    });
  }
}

function renderAll() {
  renderOverview();
  renderRuntime();
}

async function fetchJson(path) {
  const response = await fetch(path, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function refreshStatus() {
  try {
    state.status = await fetchJson(paths.status || "/api/status");
  } catch (error) {
    appendChatEntry("assistant", `Status refresh failed: ${error.message}`, "status");
  }
}

async function refreshDiagnostics() {
  try {
    state.diagnostics = await fetchJson(paths.diagnostics || "/api/diagnostics");
  } catch (error) {
    setText("diag-status", "auth required");
    setCode("runtime-preview", { error: error.message });
  }
}

async function refreshTools() {
  try {
    state.tools = await fetchJson(paths.tools || "/api/tools/catalog");
  } catch (error) {
    setCode("tools-json", { error: error.message });
  }
}

async function refreshTokenInfo() {
  try {
    state.tokenInfo = await fetchJson(paths.token || "/api/token");
  } catch (error) {
    state.tokenInfo = { error: error.message, token_saved: Boolean(state.token) };
  }
}

async function refreshAll() {
  await Promise.all([refreshStatus(), refreshDiagnostics(), refreshTools(), refreshTokenInfo()]);
  renderAll();
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

function connectWs() {
  if (state.ws) {
    state.ws.close();
  }
  state.wsState = "connecting";
  renderAll();
  const socket = new WebSocket(buildWsUrl());
  state.ws = socket;

  socket.addEventListener("open", () => {
    state.wsState = "online";
    renderAll();
  });

  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(String(event.data || "{}"));
      if (payload.text) {
        appendChatEntry("assistant", String(payload.text), String(payload.model || "ws"));
      } else if (payload.error) {
        appendChatEntry("assistant", `Gateway error: ${payload.error}`, "ws");
      } else {
        appendChatEntry("assistant", safeJson(payload), "ws");
      }
    } catch (_error) {
      appendChatEntry("assistant", String(event.data || ""), "ws");
    }
  });

  socket.addEventListener("close", () => {
    state.wsState = "offline";
    renderAll();
    window.clearTimeout(state.reconnectTimer);
    state.reconnectTimer = window.setTimeout(connectWs, 1400);
  });

  socket.addEventListener("error", () => {
    state.wsState = "error";
    renderAll();
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

async function sendHttpMessage() {
  const sessionId = byId("session-input").value.trim() || state.sessionId;
  const text = byId("chat-input").value.trim();
  if (!text) {
    return;
  }
  appendChatEntry("user", text, sessionId);
  byId("chat-input").value = "";
  const response = await fetch(paths.message || "/api/message", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({ session_id: sessionId, text }),
  });
  const payload = await response.json();
  if (!response.ok) {
    appendChatEntry("assistant", `HTTP error: ${payload.detail || response.statusText}`, "http");
    return;
  }
  appendChatEntry("assistant", String(payload.text || ""), String(payload.model || "http"));
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
    appendChatEntry("assistant", "WebSocket is not connected. Use Refresh or save the token and retry.", "ws");
    return;
  }
  state.ws.send(JSON.stringify({ session_id: sessionId, text }));
}

function bindEvents() {
  document.querySelectorAll("[data-tab-target]").forEach((node) => {
    node.addEventListener("click", () => setActiveTab(node.dataset.tabTarget || "overview"));
  });
  byId("token-input").value = state.token;
  byId("save-token").addEventListener("click", async () => {
    persistToken(byId("token-input").value);
    connectWs();
    await refreshAll();
  });
  byId("clear-token").addEventListener("click", async () => {
    persistToken("");
    byId("token-input").value = "";
    connectWs();
    await refreshAll();
  });
  byId("refresh-all").addEventListener("click", refreshAll);
  byId("send-chat").addEventListener("click", sendWsMessage);
  byId("send-rest").addEventListener("click", sendHttpMessage);
}

bindEvents();
renderAll();
refreshAll();
connectWs();
