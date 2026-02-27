# WORKLOG CORE

## 2026-02-27 — Sprint 1 / P0 (Termux installer + onboarding + gateway bootstrap)

### Contexto
- Objetivo: estabilizar instalador Termux, onboarding em modo simples/Termux e bootstrap/start do gateway com erros acionáveis.
- Escopo aplicado somente em arquivos de instalação, onboarding, gateway/CLI e testes diretos.
- Mudanças locais não relacionadas já existentes no repositório foram preservadas.

### Falhas reais diagnosticadas
1. `clawlite onboarding` em `CLAWLITE_SIMPLE_UI=1` com stdin não interativo falhava com `EOFError`.
2. `clawlite start` com `gateway.port` inválida no config quebrava com traceback cru (`ValueError`) sem mensagem operacional.
3. Instalador Termux tinha fragilidades de robustez/idempotência:
   - exigência rígida de `python3` mesmo com `python` disponível;
   - launcher Termux com shebang `#!/usr/bin/env bash` (menos confiável no ambiente Termux);
   - `httpx` ausente na instalação de deps (incompatível com `pyproject`);
   - mensagens de erro sem contexto de comando.

### Mudanças implementadas
- `clawlite/onboarding.py`
  - Novo helper `_simple_prompt()` para fallback seguro em `EOFError`/`KeyboardInterrupt`.
  - Modo simples agora conclui mesmo sem stdin interativo, com defaults previsíveis.
  - Aceita resposta `y`/`s` para ativar Telegram.
  - Gera arquivos de identidade/workspace também no fluxo simples (`_save_identity_files`).

- `clawlite/gateway/server.py`
  - `run_gateway()` agora valida `gateway.host`/`gateway.port`.
  - Erro claro para porta inválida (tipo/faixa).
  - Tratamento de `OSError` com orientação operacional (porta em uso/permissão).

- `clawlite/cli.py`
  - Novo wrapper `_run_gateway_cli()` para `start`/`gateway`.
  - Erros de import/dependência (`fastapi`/`uvicorn`) retornam mensagem acionável em PT-BR.
  - Falhas de inicialização do gateway passam a sair via `_fail` (sem traceback cru para usuário final).

- `scripts/install.sh`
  - Bootstrap Termux para instalar dependências básicas ausentes (`python`, `git`, `curl`) antes da venv.
  - Fallback para usar `python` quando `python3` não existir.
  - Inclusão de `httpx` nas deps instaladas por pip (Termux e Linux).
  - Erros de execução agora incluem descrição + comando falho.
  - Launcher Termux em `$PREFIX/bin/clawlite` usa shebang do `bash` do próprio Termux quando disponível.
  - Escrita idempotente do launcher (só regrava se conteúdo mudou).

### Testes adicionados/ajustados
- `tests/test_configure_onboarding_status_doctor.py`
  - `test_onboarding_simple_mode_handles_non_interactive_input`
- `tests/test_cli_gateway_dashboard_integration.py`
  - `test_start_cli_invalid_gateway_port_is_actionable`

### Validações executadas
- Reproduções manuais:
  - `CLAWLITE_SIMPLE_UI=1 python -m clawlite.cli onboarding </dev/null` → sucesso, sem `EOFError`.
  - `python -m clawlite.cli start` com `gateway.port="abc"` → erro acionável em stdout, sem traceback.
  - `bash -n scripts/install.sh` → sintaxe OK.
- Testes:
  - `pytest -q tests/test_configure_onboarding_status_doctor.py tests/test_cli_gateway_dashboard_integration.py tests/test_gateway_dashboard.py`
  - Resultado: `15 passed`.

### Riscos pendentes
- Não foi executado teste E2E completo do instalador com `pkg` real em dispositivo Termux durante esta sessão.
- Fluxo de dependências opcionais do gateway em ambientes extremamente restritos ainda depende de conectividade para pip/pkg.
