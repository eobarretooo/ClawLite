# WORKLOG — Sprint 1 (Skills Core)

Data: 2026-02-27
Escopo: robustez de skills críticas (`github`, `whisper`, `cron`, `ollama`) + bridge MCP.

## Entregas realizadas

### 1) `skills/github.py`
- Removido fallback inseguro com `shell=True` no `run()` para comandos não mapeados.
- Novo fallback usa `shlex.split(...)` + `_run_gh(...)` (execução estruturada, sem shell).
- Melhor tratamento de erro para comando malformado.

**Benefício:** reduz risco de injeção e aumenta previsibilidade do parser de comandos.

### 2) `skills/whisper.py`
- Adicionada validação explícita de modelo em `whisper_transcribe(...)`.
- Retorno de erro claro em PT-BR para modelos inválidos.

**Benefício:** falha rápida e consistente antes de tentar backend local/API.

### 3) `skills/cron.py`
- `_parse_interval(...)` agora normaliza entrada (`strip().lower()`).
- Presets como `1H`, ` 1h ` passam a funcionar de forma robusta.

**Benefício:** menos erros por variação de formato de entrada do usuário.

### 4) `skills/ollama.py`
- Parsing de `generate` refeito com `shlex.split(...)`.
- Suporte robusto para prompt com aspas + flag `--model`.
- Mensagem de erro amigável para argumentos inválidos.

**Benefício:** evita parsing frágil por substring e melhora confiabilidade CLI-like.

### 5) `mcp_server.py`
- `handle_mcp_jsonrpc(...)` agora valida payload não-objeto e retorna `-32600` (invalid request) de forma explícita.

**Benefício:** conformidade JSON-RPC melhor e erro previsível para clientes MCP.

## Testes adicionados/ajustados

Arquivo: `tests/test_skills_stability.py`
- `test_github_unknown_command_uses_safe_argument_parsing`
- `test_github_run_gh_timeout_is_reported`
- `test_cron_parse_interval_accepts_uppercase_presets`
- `test_ollama_run_generate_parses_model_flag_with_quotes`
- `test_whisper_invalid_model_returns_ptbr_error`

Arquivo: `tests/test_mcp.py`
- `test_mcp_jsonrpc_invalid_payload_is_graceful`

## Validação local

Comando:
```bash
pytest -q tests/test_skills_stability.py tests/test_mcp.py
```

Resultado:
- **14 passed**

## Plano para escalar para 100+ skills (próxima fase)

1. **Contrato mínimo padrão (Skill Contract v1)**
   - Toda skill com `run(command: str) -> str`, `info() -> str`, `status` obrigatório.
   - Erros padronizados (`{"error": ..., "code": ...}` interno + render amigável no `run`).

2. **Harness de testes parametrizado por skill**
   - `tests/skills_contract/` com suíte genérica (smoke, help, status, invalid args, timeout).
   - Fixtures para monkeypatch de dependências externas (CLI/API/network).

3. **Matriz de confiabilidade por classe de skill**
   - CLI wrappers (gh, docker, etc.), HTTP APIs, runtime/system.
   - Políticas de timeout/retry/circuit-breaker por classe.

4. **Observabilidade e SLO por skill**
   - Métricas por execução: latência, taxa de erro, categoria de falha.
   - Dashboard com Top N skills mais instáveis e regressões por release.

5. **Gate de CI para skills críticas**
   - Label `critical-skill` exige suite completa + cobertura mínima.
   - Testes de regressão obrigatórios para parser e fallback paths.

6. **Kit de scaffolding de skill**
   - Template único com validações, parser robusto, e testes padrão.
   - Linters/checkers para impedir anti-patterns (`shell=True`, exceções engolidas sem contexto, etc.).

---

Status Sprint 1: **concluído (hardening inicial + base de teste fortalecida)**.
