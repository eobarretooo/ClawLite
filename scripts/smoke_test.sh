#!/usr/bin/env bash
# smoke_test.sh - Quick post-deploy validation for ClawLite
# Usage: bash scripts/smoke_test.sh [--gateway-port 8787]
set -euo pipefail

PORT="${CLAWLITE_PORT:-8787}"
BASE_URL="http://127.0.0.1:${PORT}"
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="${PYTHON_BIN:-python3}"
else
  PYTHON_BIN="${PYTHON_BIN:-python}"
fi
PASS=0
FAIL=0

_ok()   { echo "  ✅ $1"; ((PASS++)) || true; }
_fail() { echo "  ❌ $1"; ((FAIL++)) || true; }

echo "=== ClawLite Smoke Test ==="
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# 1) Critical module imports
echo "--- Python Modules ---"
"${PYTHON_BIN}" -c "from clawlite.gateway import server" 2>/dev/null \
  && _ok "gateway.server import" || _fail "gateway.server failed"

"${PYTHON_BIN}" -c "from clawlite.core.engine import AgentEngine; from clawlite.scheduler.cron import CronService; from clawlite.tools.registry import ToolRegistry" 2>/dev/null \
  && _ok "core/scheduler/tools import" || _fail "core/scheduler/tools failed"

# 2) Quick unit tests
echo ""
echo "--- Runtime Surface Smokes ---"
if clawlite --help >/dev/null 2>/dev/null; then
  TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/clawlite-smoke.XXXXXX")"
  CONFIG_PATH="${TMPDIR}/config.yaml"
  cat > "${CONFIG_PATH}" <<EOF
workspace_path: ${TMPDIR}/workspace
state_path: ${TMPDIR}/state
EOF
  if clawlite --config "${CONFIG_PATH}" status >/dev/null 2>/dev/null; then
    _ok "CLI entrypoint + YAML config"
  else
    _fail "CLI entrypoint + YAML config"
  fi
  rm -rf "${TMPDIR}"
else
  _fail "clawlite --help failed"
fi

if "${PYTHON_BIN}" -m pytest -q --tb=line \
  tests/cli/test_commands.py::test_provider_live_probe_ollama_success_detects_missing_model \
  tests/cli/test_commands.py::test_provider_live_probe_vllm_network_error_returns_runtime_hint \
  tests/cli/test_onboarding.py::test_run_onboarding_wizard_quickstart_uses_guided_defaults \
  tests/scheduler/test_cron.py::test_cron_service_add_and_run \
  tests/scheduler/test_cron.py::test_cron_loop_survives_callback_failure_and_tracks_job_health \
  tests/tools/test_browser_tool.py 2>/dev/null | grep -q "passed"; then
  _ok "Provider + wizard + cron + browser smoke tests"
else
  _fail "targeted smoke pytest failed"
fi

# 3) Gateway health check (optional - only if gateway is running)
echo ""
echo "--- Gateway (${BASE_URL}) ---"
if curl -sf "${BASE_URL}/health" -o /dev/null 2>/dev/null; then
  HEALTH=$(curl -sf "${BASE_URL}/health" 2>/dev/null)
  _ok "health: $HEALTH"
else
  echo "  ⚠️  Gateway is not running at ${BASE_URL} (ok if not started)"
fi

# 4) Optional dependencies
echo ""
echo "--- Dependencies ---"
"${PYTHON_BIN}" -c "import httpx" 2>/dev/null && _ok "httpx available" || _fail "httpx missing"
"${PYTHON_BIN}" -c "import fastapi" 2>/dev/null && _ok "fastapi available" || _fail "fastapi missing"
"${PYTHON_BIN}" -c "import uvicorn" 2>/dev/null && _ok "uvicorn available" || _fail "uvicorn missing"

echo ""
echo "=== Result: ${PASS} ok / ${FAIL} failure(s) ==="
if [ "${FAIL}" -gt 0 ]; then
  exit 1
fi
