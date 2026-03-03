#!/usr/bin/env bash
# smoke_test.sh - Quick post-deploy validation for ClawLite
# Usage: bash scripts/smoke_test.sh [--gateway-port 8787]
set -euo pipefail

PORT="${CLAWLITE_PORT:-8787}"
BASE_URL="http://127.0.0.1:${PORT}"
PASS=0
FAIL=0

_ok()   { echo "  ✅ $1"; ((PASS++)) || true; }
_fail() { echo "  ❌ $1"; ((FAIL++)) || true; }

echo "=== ClawLite Smoke Test ==="
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# 1) Critical module imports
echo "--- Python Modules ---"
python -c "from clawlite.gateway import server" 2>/dev/null \
  && _ok "gateway.server import" || _fail "gateway.server failed"

python -c "from clawlite.core.engine import AgentEngine; from clawlite.scheduler.cron import CronService; from clawlite.tools.registry import ToolRegistry" 2>/dev/null \
  && _ok "core/scheduler/tools import" || _fail "core/scheduler/tools failed"

# 2) Quick unit tests
echo ""
echo "--- Unit Tests ---"
if python -m pytest tests/ -q --tb=line -x 2>/dev/null | grep -q "passed"; then
  TOTAL=$(python -m pytest tests/ -q --tb=no 2>/dev/null | tail -1)
  _ok "Tests: $TOTAL"
else
  _fail "pytest failed or no passing tests"
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
python -c "import httpx" 2>/dev/null && _ok "httpx available" || _fail "httpx missing"
python -c "import fastapi" 2>/dev/null && _ok "fastapi available" || _fail "fastapi missing"
python -c "import uvicorn" 2>/dev/null && _ok "uvicorn available" || _fail "uvicorn missing"

echo ""
echo "=== Result: ${PASS} ok / ${FAIL} failure(s) ==="
if [ "${FAIL}" -gt 0 ]; then
  exit 1
fi
