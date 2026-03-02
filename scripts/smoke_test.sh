#!/usr/bin/env bash
# smoke_test.sh — Validação rápida pós-deploy do ClawLite
# Uso: bash scripts/smoke_test.sh [--gateway-port 8787]
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

# 1) Importação dos módulos críticos
echo "--- Módulos Python ---"
python -c "from clawlite.gateway import server" 2>/dev/null \
  && _ok "gateway.server importa" || _fail "gateway.server falhou"

python -c "from clawlite.core.engine import AgentEngine; from clawlite.scheduler.cron import CronService; from clawlite.tools.registry import ToolRegistry" 2>/dev/null \
  && _ok "core/scheduler/tools importam" || _fail "core/scheduler/tools falhou"

# 2) Testes unitários rápidos
echo ""
echo "--- Testes unitários ---"
if python -m pytest tests/ -q --tb=line -x 2>/dev/null | grep -q "passed"; then
  TOTAL=$(python -m pytest tests/ -q --tb=no 2>/dev/null | tail -1)
  _ok "Testes: $TOTAL"
else
  _fail "pytest falhou ou sem testes passando"
fi

# 3) Gateway health check (opcional — só se gateway estiver rodando)
echo ""
echo "--- Gateway (${BASE_URL}) ---"
if curl -sf "${BASE_URL}/health" -o /dev/null 2>/dev/null; then
  HEALTH=$(curl -sf "${BASE_URL}/health" 2>/dev/null)
  _ok "health: $HEALTH"
else
  echo "  ⚠️  Gateway não está rodando em ${BASE_URL} (ok se não iniciado)"
fi

# 4) Dependências opcionais
echo ""
echo "--- Dependências ---"
python -c "import httpx" 2>/dev/null && _ok "httpx disponível" || _fail "httpx ausente"
python -c "import fastapi" 2>/dev/null && _ok "fastapi disponível" || _fail "fastapi ausente"
python -c "import uvicorn" 2>/dev/null && _ok "uvicorn disponível" || _fail "uvicorn ausente"

echo ""
echo "=== Resultado: ${PASS} ok / ${FAIL} falha(s) ==="
if [ "${FAIL}" -gt 0 ]; then
  exit 1
fi
