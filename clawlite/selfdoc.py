from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any

from clawlite.config.loader import DEFAULT_CONFIG_PATH, config_payload_path, load_config
from clawlite.config.schema import AppConfig
from clawlite.providers.catalog import default_provider_model, provider_profile
from clawlite.providers.registry import SPECS


_TOOL_MODULES = (
    "clawlite.tools.agents",
    "clawlite.tools.apply_patch",
    "clawlite.tools.browser",
    "clawlite.tools.cron",
    "clawlite.tools.discord_admin",
    "clawlite.tools.exec",
    "clawlite.tools.files",
    "clawlite.tools.gateway_admin",
    "clawlite.tools.jobs",
    "clawlite.tools.mcp",
    "clawlite.tools.memory",
    "clawlite.tools.message",
    "clawlite.tools.pdf",
    "clawlite.tools.process",
    "clawlite.tools.sessions",
    "clawlite.tools.skill",
    "clawlite.tools.spawn",
    "clawlite.tools.tts",
    "clawlite.tools.web",
)

_TOOL_CONFIG_NOTES: dict[str, str] = {
    "exec": "Usa `tools.restrict_to_workspace`, `tools.exec.*`, `tools.default_timeout_s` e `tools.timeouts.exec`.",
    "process": "Reusa as mesmas guardas de `exec`; não tem flag própria de enable.",
    "read_file": "Respeita `tools.restrict_to_workspace`.",
    "write_file": "Respeita `tools.restrict_to_workspace`.",
    "edit_file": "Respeita `tools.restrict_to_workspace`.",
    "read": "Alias de `read_file`; respeita `tools.restrict_to_workspace`.",
    "write": "Alias de `write_file`; respeita `tools.restrict_to_workspace`.",
    "edit": "Alias de `edit_file`; respeita `tools.restrict_to_workspace`.",
    "list_dir": "Respeita `tools.restrict_to_workspace`.",
    "web_fetch": "Usa `tools.web.proxy`, `timeout`, `max_redirects`, `max_chars`, `allowlist`, `denylist` e `block_private_addresses`.",
    "web_search": "Usa `tools.web.proxy`, `search_timeout`, `brave_api_key`, `brave_base_url` e `searxng_base_url`.",
    "mcp": "Usa `tools.mcp.default_timeout_s`, `tools.mcp.policy.*` e `tools.mcp.servers`.",
    "cron": "Não tem enable flag no config; usa o scheduler ativo do runtime.",
    "jobs": "Depende da fila de jobs do runtime; persistência vem de `jobs.persist_*`.",
    "message": "Não tem enable flag própria; depende dos canais ativos.",
    "discord_admin": "Fica registrado sempre, mas só funciona de verdade se `channels.discord.token` estiver configurado.",
    "run_skill": "Depende do loader de skills e da policy de memória; não há `tools.run_skill.enabled`.",
    "browser": "Não há bloco dedicado no schema; depende de Playwright/Chromium instalados.",
    "pdf_read": "Não há bloco dedicado no schema; depende de `pypdf`.",
    "tts": "Não há bloco dedicado no schema; depende de `edge-tts`.",
    "gateway_admin": "Usa allowlist interna e hoje só libera mudanças seguras ligadas a tools/gateway restart.",
}

_TOOL_BLOCKER_NOTES: dict[str, str] = {
    "exec": "Se a policy bloquear, a tool falha ou pede aprovação em Telegram/Discord.",
    "browser": "Se Playwright/Chromium não existirem, retorna erro da própria tool.",
    "mcp": "Sem servidores configurados em `tools.mcp.servers`, a chamada não encontra destino válido.",
    "discord_admin": "Sem token de Discord, retorna `discord_not_configured`.",
    "run_skill": "Skill desabilitada ou indisponível retorna erro explícito (`skill_disabled` ou `skill_unavailable`).",
}

_CHANNEL_FACTS: list[dict[str, str]] = [
    {
        "name": "telegram",
        "status": "funcional",
        "summary": "Polling + webhook, streaming, reactions, topics, callbacks, pairing e refresh dedicado.",
    },
    {
        "name": "discord",
        "status": "funcional",
        "summary": "HTTP outbound, gateway inbound, slash commands, threads, webhooks, voz, presence e refresh dedicado.",
    },
    {
        "name": "slack",
        "status": "funcional",
        "summary": "Web API outbound e Socket Mode opcional para inbound.",
    },
    {
        "name": "whatsapp",
        "status": "funcional",
        "summary": "Bridge HTTP/websocket + webhook inbound + retry outbound.",
    },
    {
        "name": "email",
        "status": "funcional",
        "summary": "Polling IMAP inbound e SMTP outbound.",
    },
    {
        "name": "irc",
        "status": "funcional",
        "summary": "Loop asyncio com PING/PONG e envio básico.",
    },
    {
        "name": "signal",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
    {
        "name": "googlechat",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
    {
        "name": "matrix",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
    {
        "name": "imessage",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
    {
        "name": "dingtalk",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
    {
        "name": "feishu",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
    {
        "name": "mochat",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
    {
        "name": "qq",
        "status": "stub",
        "summary": "Canal passivo; `send()` levanta `<name>_not_implemented`.",
    },
]

_PROVIDER_ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "openai_codex": ("CLAWLITE_CODEX_ACCESS_TOKEN", "OPENAI_CODEX_ACCESS_TOKEN", "OPENAI_ACCESS_TOKEN"),
    "gemini_oauth": ("CLAWLITE_GEMINI_ACCESS_TOKEN", "GEMINI_ACCESS_TOKEN", "CLAWLITE_GEMINI_AUTH_PATH"),
    "qwen_oauth": ("CLAWLITE_QWEN_ACCESS_TOKEN", "QWEN_ACCESS_TOKEN", "CLAWLITE_QWEN_AUTH_PATH"),
}

_SAMPLE_BY_DEST: dict[str, str] = {
    "prompt": "\"olá\"",
    "session_id": "cli:default",
    "timeout": "10",
    "gateway_url": "http://127.0.0.1:8787",
    "token": "dev-token",
    "tool": "exec",
    "name": "github",
    "slug": "github",
    "query": "\"discord moderation\"",
    "channel": "telegram",
    "code": "ABCD12",
    "entry": "telegram:user:123",
    "request_id": "req-1",
    "provider": "openai",
    "api_key": "sk-demo",
    "api_base": "https://api.openai.com/v1",
    "model": "openai/gpt-4o-mini",
    "fallback_model": "openai/gpt-4o-mini",
    "component": "channels",
    "reason": "operator_recover",
    "id": "snapshot-1",
    "file": "backup.json",
    "job_id": "job-1",
    "expression": "\"every 300\"",
    "update_id": "12345",
    "next_offset": "12346",
    "user": "alice",
    "enabled": "true",
    "tag": "manual",
    "version": "1.0.0",
    "source": "workspace",
    "flow": "quickstart",
    "section": "memory",
    "assistant_name": "ClawLite",
    "assistant_emoji": "🦊",
    "assistant_creature": "fox",
    "assistant_vibe": "\"direct, pragmatic, autonomous\"",
    "assistant_backstory": "\"An autonomous personal assistant focused on execution.\"",
    "user_name": "Owner",
    "user_timezone": "America/Sao_Paulo",
    "user_context": "\"Projetos locais\"",
    "user_preferences": "\"respostas diretas\"",
    "kind": "proactive",
    "status": "pending",
    "role": "primary",
    "actor": "control-plane",
    "note": "\"aprovado pelo operador\"",
    "limit": "5",
    "header": "\"X-Test: 1\"",
}

_CLI_EXAMPLE_OVERRIDES: dict[str, str] = {
    "clawlite start": "clawlite start",
    "clawlite gateway": "clawlite gateway",
    "clawlite status": "clawlite status",
    "clawlite dashboard": "clawlite dashboard --no-open",
    "clawlite configure": "clawlite configure",
    "clawlite onboard": "clawlite onboard --assistant-name ClawLite --user-name Owner",
    "clawlite validate provider": "clawlite validate provider",
    "clawlite validate channels": "clawlite validate channels",
    "clawlite validate onboarding": "clawlite validate onboarding --fix",
    "clawlite validate config": "clawlite validate config",
    "clawlite validate preflight": "clawlite validate preflight --gateway-url http://127.0.0.1:8787",
    "clawlite tools catalog": "clawlite tools catalog --gateway-url http://127.0.0.1:8787",
    "clawlite tools approvals": "clawlite tools approvals --gateway-url http://127.0.0.1:8787",
    "clawlite tools approval-audit": "clawlite tools approval-audit --gateway-url http://127.0.0.1:8787",
    "clawlite tools approve": "clawlite tools approve req-1 --gateway-url http://127.0.0.1:8787",
    "clawlite tools reject": "clawlite tools reject req-1 --gateway-url http://127.0.0.1:8787",
    "clawlite tools revoke-grant": "clawlite tools revoke-grant --session-id telegram:123 --gateway-url http://127.0.0.1:8787",
    "clawlite provider login": "clawlite provider login openai-codex",
    "clawlite provider status": "clawlite provider status openai-codex",
    "clawlite provider logout": "clawlite provider logout openai-codex",
    "clawlite provider use": "clawlite provider use openai --model openai/gpt-4o-mini",
    "clawlite provider set-auth": "clawlite provider set-auth openai --api-key sk-demo",
    "clawlite provider clear-auth": "clawlite provider clear-auth openai",
    "clawlite provider recover": "clawlite provider recover --gateway-url http://127.0.0.1:8787",
    "clawlite autonomy wake": "clawlite autonomy wake --gateway-url http://127.0.0.1:8787",
    "clawlite supervisor recover": "clawlite supervisor recover --gateway-url http://127.0.0.1:8787",
    "clawlite heartbeat trigger": "clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787",
    "clawlite self-evolution status": "clawlite self-evolution status --gateway-url http://127.0.0.1:8787",
    "clawlite self-evolution trigger": "clawlite self-evolution trigger --gateway-url http://127.0.0.1:8787 --dry-run",
    "clawlite telegram status": "clawlite telegram status --gateway-url http://127.0.0.1:8787",
    "clawlite telegram refresh": "clawlite telegram refresh --gateway-url http://127.0.0.1:8787",
    "clawlite discord status": "clawlite discord status --gateway-url http://127.0.0.1:8787",
    "clawlite discord refresh": "clawlite discord refresh --gateway-url http://127.0.0.1:8787",
    "clawlite diagnostics": "clawlite diagnostics --gateway-url http://127.0.0.1:8787",
    "clawlite memory": "clawlite memory",
    "clawlite memory doctor": "clawlite memory doctor",
    "clawlite memory quality": "clawlite memory quality",
    "clawlite memory suggest": "clawlite memory suggest",
    "clawlite memory snapshot": "clawlite memory snapshot --tag manual",
    "clawlite memory rollback": "clawlite memory rollback snapshot-1",
    "clawlite cron add": "clawlite cron add --session-id cli:cron --expression \"every 300\" --prompt \"ping\"",
    "clawlite cron list": "clawlite cron list --session-id cli:cron",
    "clawlite cron run": "clawlite cron run job-1",
    "clawlite jobs list": "clawlite jobs list",
    "clawlite skills list": "clawlite skills list",
    "clawlite skills doctor": "clawlite skills doctor",
    "clawlite skills validate": "clawlite skills validate --gateway-url http://127.0.0.1:8787",
    "clawlite skills managed": "clawlite skills managed --status missing_requirements --query jira",
    "clawlite skills sync": "clawlite skills sync",
    "clawlite skills install": "clawlite skills install github",
    "clawlite generate-self": "clawlite generate-self",
    "clawlite restart-gateway": "clawlite restart-gateway --gateway-url http://127.0.0.1:8787",
}

_FILE_MAP: list[tuple[str, str]] = [
    ("clawlite/config/schema.py", "Schema tipado de todo o config; altere aqui quando criar ou remover campo."),
    ("clawlite/config/loader.py", "Carrega, mescla env, valida, salva JSON/YAML e resolve profiles."),
    ("clawlite/core/engine.py", "Loop principal do agente, execução de tools, memória e persistência de turno."),
    ("clawlite/core/prompt.py", "Monta o prompt final antes da chamada ao provider."),
    ("clawlite/core/memory.py", "Memória persistente, busca, consolidação, versões e privacidade."),
    ("clawlite/providers/registry.py", "Resolve provider/base URL/auth e constrói o provider ativo."),
    ("clawlite/providers/litellm.py", "Provider OpenAI-compatible e Anthropic-compatible com retry/telemetria."),
    ("clawlite/providers/failover.py", "Encadeia provider principal + fallbacks."),
    ("clawlite/channels/manager.py", "Instancia canais, roteia outbound/inbound e faz recovery."),
    ("clawlite/channels/telegram.py", "Adapter Telegram completo."),
    ("clawlite/channels/discord.py", "Adapter Discord completo."),
    ("clawlite/tools/registry.py", "Registro, cache, timeouts, safety, approvals e auditoria de tools."),
    ("clawlite/tools/gateway_admin.py", "Mudanças seguras de config via chat + preview + restart."),
    ("clawlite/scheduler/cron.py", "Scheduler de cron/jobs persistidos."),
    ("clawlite/scheduler/heartbeat.py", "Loop de heartbeat e estado persistido."),
    ("clawlite/gateway/server.py", "Gateway FastAPI, dashboard, rotas HTTP/WS e bootstrap do runtime."),
    ("clawlite/gateway/runtime_builder.py", "Monta engine, memory, tools, channels, cron, heartbeat e jobs."),
    ("clawlite/cli/__init__.py", "Entrypoint real do console script `clawlite`."),
    ("clawlite/cli/commands.py", "Parser argparse e handlers da CLI."),
    ("clawlite/workspace/loader.py", "Workspace runtime, templates e contexto do prompt."),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _tilde(value: str | Path) -> str:
    path = Path(str(value)).expanduser()
    home = Path.home().expanduser()
    try:
        relative = path.resolve().relative_to(home.resolve())
    except Exception:
        return str(path)
    if not str(relative):
        return "~"
    return f"~/{relative.as_posix()}"


def _fmt_default(value: Any) -> str:
    if isinstance(value, str):
        text = value
        if text.startswith(str(Path.home())):
            text = _tilde(text)
        return f"`{text}`" if text else "`\"\"`"
    if isinstance(value, Path):
        return f"`{_tilde(value)}`"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if value is None:
        return "`null`"
    if isinstance(value, (int, float)):
        return f"`{value}`"
    return f"`{json.dumps(value, ensure_ascii=False)}`"


def _iter_leaf_fields(model: Any, prefix: str = "") -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    model_fields = getattr(model.__class__, "model_fields", {})
    for name in model_fields:
        value = getattr(model, name)
        full = f"{prefix}.{name}" if prefix else name
        if hasattr(value, "__class__") and hasattr(value.__class__, "model_fields"):
            rows.extend(_iter_leaf_fields(value, full))
        else:
            rows.append((full, value))
    return rows


def _group_key(path: str) -> str:
    parts = path.split(".")
    if len(parts) == 1:
        return "root"
    if parts[0] in {"gateway", "provider", "auth", "scheduler", "bus", "observability", "jobs"}:
        return ".".join(parts[: min(2, len(parts))])
    if parts[0] in {"channels", "tools", "providers"}:
        return ".".join(parts[: min(2, len(parts))])
    if parts[0] == "agents":
        return ".".join(parts[: min(3, len(parts))])
    return parts[0]


def _scope_label(path: str) -> str:
    group = _group_key(path)
    mapping = {
        "root": "o config raiz",
        "provider": "o provider principal",
        "providers.openrouter": "o override do provider OpenRouter",
        "providers.gemini": "o override do provider Gemini",
        "providers.openai": "o override do provider OpenAI",
        "providers.anthropic": "o override do provider Anthropic",
        "providers.deepseek": "o override do provider DeepSeek",
        "providers.groq": "o override do provider Groq",
        "providers.ollama": "o override do runtime local Ollama",
        "providers.vllm": "o override do runtime local vLLM",
        "providers.custom": "o provider custom",
        "providers.extra": "os providers extras fora da lista tipada",
        "auth.providers": "a autenticação OAuth persistida",
        "agents.defaults": "o agente padrão",
        "agents.defaults.memory": "a memória do agente padrão",
        "gateway": "o gateway HTTP/WS",
        "gateway.heartbeat": "o heartbeat do gateway",
        "gateway.auth": "a autenticação HTTP do gateway",
        "gateway.diagnostics": "o bloco de diagnostics do gateway",
        "gateway.supervisor": "o supervisor do runtime",
        "gateway.autonomy": "o loop de autonomia",
        "gateway.websocket": "o websocket do gateway",
        "gateway.rate_limit": "o rate limit do gateway",
        "scheduler": "o scheduler",
        "channels": "o bloco de canais",
        "channels.telegram": "o canal Telegram",
        "channels.discord": "o canal Discord",
        "channels.email": "o canal Email",
        "channels.slack": "o canal Slack",
        "channels.whatsapp": "o canal WhatsApp",
        "channels.irc": "o canal IRC",
        "channels.extra": "os canais extras fora da lista tipada",
        "tools": "o bloco de tools",
        "tools.web": "as tools web",
        "tools.exec": "a tool exec",
        "tools.mcp": "a tool MCP",
        "tools.loop_detection": "a proteção contra loops de tools",
        "tools.safety": "a safety policy de tools",
        "bus": "o message bus",
        "observability": "a observabilidade",
        "jobs": "a fila de jobs",
    }
    return mapping.get(group, f"o bloco `{group}`")


def _field_note(path: str, value: Any) -> str:
    parts = path.split(".")
    leaf = parts[-1]
    scope = _scope_label(path)
    if path == "workspace_path":
        return "Caminho do workspace que o prompt builder e o loader usam."
    if path == "state_path":
        return "Caminho base do estado persistente do runtime."
    if path == "provider.model":
        return "Modelo principal resolvido pelo runtime."
    if path == "provider.litellm_base_url":
        return "Base URL global para providers compatíveis com LiteLLM/OpenAI."
    if path == "provider.litellm_api_key":
        return "API key global de fallback para providers compatíveis."
    if path == "provider.fallback_model":
        return "Modelo fallback usado pelo failover quando configurado."
    if path == "tools.timeouts":
        return "Overrides de timeout por nome de tool."
    if path == "tools.safety.risky_tools":
        return "Lista de tools consideradas arriscadas pela safety policy."
    if path == "tools.safety.approval_specifiers":
        return "Specifiers que exigem aprovação explícita."
    if path == "tools.safety.approval_channels":
        return "Canais que participam do fluxo de aprovação."
    if path == "tools.mcp.servers":
        return "Mapa de servidores MCP nomeados."
    if path == "channels.extra":
        return "Canais extras fora da lista tipada do schema."
    if path == "providers.extra":
        return "Overrides extras de providers fora da lista tipada."
    if path == "gateway.autonomy.self_evolution_enabled_for_sessions":
        return "Sessões autorizadas para self-evolution quando a feature estiver ligada."
    if path == "gateway.auth.mode":
        return "Modo de autenticação HTTP do gateway."
    if path == "channels.telegram.allow_from":
        return "Allowlist global de remetentes aceitos no Telegram."
    if path == "channels.telegram.dm_allow_from":
        return "Allowlist específica para DM no Telegram."
    if path == "channels.telegram.group_allow_from":
        return "Allowlist específica para grupos no Telegram."
    if path == "channels.telegram.topic_allow_from":
        return "Allowlist específica para tópicos no Telegram."
    if path == "channels.telegram.group_overrides":
        return "Overrides por grupo/tópico no Telegram."
    if path == "channels.telegram.token":
        return "Token do bot Telegram."
    if path == "channels.discord.token":
        return "Token do bot Discord."
    if path == "channels.slack.bot_token":
        return "Token do bot Slack."
    if path == "channels.slack.app_token":
        return "Token de app Slack para Socket Mode."
    if path == "channels.whatsapp.bridge_token":
        return "Token usado para autenticar com a bridge de WhatsApp."
    if path == "channels.whatsapp.bridge_url":
        return "Endpoint da bridge de WhatsApp."
    if path == "channels.email.imap_password":
        return "Senha da conta IMAP."
    if path == "channels.email.smtp_password":
        return "Senha da conta SMTP."
    if path == "channels.irc.channels_to_join":
        return "Lista de canais IRC que o bot deve entrar."
    if path == "gateway.host":
        return "Host HTTP do gateway."
    if path == "gateway.port":
        return "Porta HTTP do gateway."
    if leaf == "enabled":
        return f"Ativa ou desativa {scope}."
    if leaf == "host":
        return f"Host usado por {scope}."
    if leaf == "port":
        return f"Porta usada por {scope}."
    if leaf == "token":
        return f"Token de autenticação de {scope}."
    if leaf == "api_key":
        return f"API key usada por {scope}."
    if leaf == "api_base":
        return f"Base URL explícita usada por {scope}."
    if leaf == "base_url":
        return f"Base URL usada por {scope}."
    if leaf == "extra_headers":
        return f"Headers extras enviados por {scope}."
    if leaf == "timeout":
        return f"Timeout padrão usado por {scope}."
    if leaf.endswith("_timeout_s") or leaf.endswith("_timeout"):
        return f"Timeout em segundos usado por {scope}."
    if leaf.endswith("_interval_s") or leaf.endswith("_interval_seconds"):
        return f"Intervalo em segundos usado por {scope}."
    if leaf.endswith("_cooldown_s"):
        return f"Cooldown em segundos usado por {scope}."
    if leaf.endswith("_backoff_s") or leaf.endswith("_backoff_base_s") or leaf.endswith("_backoff_max_s"):
        return f"Backoff usado por {scope}."
    if leaf.endswith("_path"):
        return f"Caminho de arquivo usado por {scope}."
    if leaf.endswith("_dir"):
        return f"Diretório usado por {scope}."
    if leaf == "model":
        return f"Modelo configurado em {scope}."
    if leaf == "provider":
        return f"Provider selecionado em {scope}."
    if leaf == "temperature":
        return "Temperatura enviada ao modelo."
    if leaf == "max_tokens":
        return "Limite de tokens da resposta do modelo."
    if leaf == "context_token_budget":
        return "Orçamento de tokens reservado para o prompt."
    if leaf == "max_tool_iterations":
        return "Máximo de iterações do loop por turno."
    if leaf == "memory_window":
        return "Quantidade de mensagens recentes mantidas no contexto."
    if leaf == "reasoning_effort":
        return "Nível de raciocínio pedido ao provider, quando suportado."
    if leaf == "allow_from":
        return f"Allowlist principal de remetentes de {scope}."
    if leaf.endswith("_allow_from"):
        return f"Allowlist específica usada por {scope}."
    if leaf == "mode":
        return f"Modo de operação de {scope}."
    if leaf == "policy" or leaf.endswith("_policy"):
        return f"Policy usada por {scope}."
    if leaf == "webhook_path":
        return f"Caminho HTTP do webhook de {scope}."
    if leaf == "webhook_url":
        return f"URL pública de webhook usada por {scope}."
    if leaf == "webhook_secret":
        return f"Segredo de webhook usado por {scope}."
    if leaf == "allowlist":
        return f"Allowlist usada por {scope}."
    if leaf == "denylist":
        return f"Denylist usada por {scope}."
    if leaf.endswith("_retry_attempts"):
        return f"Número de tentativas de retry de {scope}."
    if leaf.endswith("_failure_threshold"):
        return f"Limiar de falhas seguidas antes de abrir circuito em {scope}."
    if leaf == "headers":
        return f"Headers extras usados por {scope}."
    if leaf == "servers":
        return f"Servidores nomeados usados por {scope}."
    if leaf == "backend":
        return f"Backend configurado para {scope}."
    if leaf == "timezone":
        return f"Timezone usada por {scope}."
    if leaf == "service_name":
        return "Nome do serviço enviado para observabilidade."
    if leaf == "service_namespace":
        return "Namespace do serviço enviado para observabilidade."
    if leaf == "otlp_endpoint":
        return "Endpoint OTLP de observabilidade."
    if leaf == "persist_enabled":
        return "Ativa persistência de jobs em disco."
    if leaf == "persist_path":
        return "Arquivo usado para persistir jobs."
    if leaf == "worker_concurrency":
        return "Concorrência de workers da fila de jobs."
    if leaf == "redis_url":
        return "URL do Redis do bus."
    if leaf == "redis_prefix":
        return "Prefixo das chaves do Redis do bus."
    if leaf == "journal_enabled":
        return f"Ativa journal persistente de {scope}."
    if leaf == "journal_path":
        return f"Arquivo de journal usado por {scope}."
    if leaf == "account_id":
        return f"Conta/organização usada por {scope}."
    if leaf == "access_token":
        return f"Access token usado por {scope}."
    if leaf == "source":
        return f"Origem persistida do segredo/token de {scope}."
    return f"Campo `{leaf}` de {scope}."


def _render_config_fields() -> str:
    cfg = AppConfig()
    rows = _iter_leaf_fields(cfg)
    groups: dict[str, list[tuple[str, Any]]] = {}
    for path, value in rows:
        groups.setdefault(_group_key(path), []).append((path, value))

    ordered_groups = list(groups.keys())
    parts: list[str] = []
    for group in ordered_groups:
        parts.append(f"#### `{group}`")
        parts.append("| Campo | Padrão | O que faz |")
        parts.append("|---|---|---|")
        for path, value in groups[group]:
            parts.append(f"| `{path}` | {_fmt_default(value)} | {_field_note(path, value)} |")
    return "\n".join(parts)


def _import_tool_classes() -> list[type[Any]]:
    for module_name in _TOOL_MODULES:
        importlib.import_module(module_name)
    from clawlite.tools.base import Tool

    discovered: dict[str, type[Any]] = {}
    pending = list(Tool.__subclasses__())
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        name = getattr(cls, "name", "")
        if not name or cls is Tool:
            continue
        discovered[str(name)] = cls
    return [discovered[name] for name in sorted(discovered)]


def _render_tools() -> str:
    parts = [
        "Hoje não existe `tools.<nome>.enabled` no schema. As tools são registradas no runtime e o bloqueio real acontece por policy, falta de config, dependência opcional ou indisponibilidade do backend da tool.",
        "",
        "| Tool | O que faz | Config / limite real | Quando falha ou fica indisponível |",
        "|---|---|---|---|",
    ]
    for cls in _import_tool_classes():
        name = str(getattr(cls, "name", "") or "")
        description = " ".join(str(getattr(cls, "description", "") or "").split())
        config_note = _TOOL_CONFIG_NOTES.get(name, "Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime.")
        blocker_note = _TOOL_BLOCKER_NOTES.get(name, "Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado.")
        parts.append(f"| `{name}` | {description} | {config_note} | {blocker_note} |")
    parts.append("")
    parts.append("Aliases publicados no catálogo do gateway: `bash -> exec`, `apply-patch -> apply_patch`, `read_file -> read`, `write_file -> write`, `edit_file -> edit`, `memory_recall -> memory_search`.")
    return "\n".join(parts)


def _provider_auth_mode(spec_name: str, spec: Any) -> str:
    if bool(getattr(spec, "is_oauth", False)):
        return "oauth"
    if spec_name in {"ollama", "vllm"}:
        return "local"
    if bool(getattr(spec, "native_transport", "")) == "anthropic":
        return "anthropic_compatible"
    return "openai_compatible"


def _provider_config_keys(spec_name: str, spec: Any) -> str:
    if bool(getattr(spec, "is_oauth", False)):
        return f"`provider.model`, `auth.providers.{spec_name}.access_token`, `auth.providers.{spec_name}.account_id`"
    if spec_name == "custom":
        return "`provider.model`, `providers.custom.api_base`, `providers.custom.api_key`, `providers.custom.extra_headers`"
    return f"`provider.model`, `providers.{spec_name}.api_key`, `providers.{spec_name}.api_base`, `providers.{spec_name}.extra_headers`"


def _provider_secret_locations(spec_name: str, spec: Any) -> str:
    if bool(getattr(spec, "is_oauth", False)):
        envs = ", ".join(f"`{item}`" for item in _PROVIDER_ENV_OVERRIDES.get(spec_name, ()))
        if spec_name == "openai_codex":
            file_hint = "`~/.codex/auth.json` ou `CLAWLITE_CODEX_AUTH_PATH`"
        elif spec_name == "gemini_oauth":
            file_hint = "`~/.gemini/oauth_creds.json` ou `CLAWLITE_GEMINI_AUTH_PATH`"
        else:
            file_hint = "`~/.qwen/oauth_creds.json`, `~/.qwen/auth.json` ou `CLAWLITE_QWEN_AUTH_PATH`"
        return f"Config em `auth.providers.{spec_name}.*`; env {envs}; arquivo local {file_hint}."
    if spec_name in {"ollama", "vllm"}:
        return "Sem API key obrigatória; o essencial é a base URL do runtime local."
    envs = ", ".join(f"`{item}`" for item in getattr(spec, "key_envs", ()) or ())
    extras = "`CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`"
    return f"Config em `providers.{spec_name}.api_key`; env {envs or '(nenhum específico)'}; fallback global {extras}."


def _render_providers() -> str:
    parts = [
        "| Provider | Tipo | Como configurar | Onde fica a credencial | Base URL padrão / observação |",
        "|---|---|---|---|---|",
    ]
    for spec in SPECS:
        name = str(spec.name)
        auth_mode = _provider_auth_mode(name, spec)
        profile = provider_profile(name)
        base_url = str(getattr(spec, "default_base_url", "") or "")
        if not base_url and name == "azure_openai":
            base_url = "Sem default; precisa de endpoint `https://<resource>.../openai/v1`."
        elif not base_url:
            base_url = "Sem base URL padrão fixa."
        hint = str(profile.onboarding_hint or "")
        note = f"`{base_url}`. {hint}".strip()
        parts.append(
            f"| `{name}` | `{auth_mode}` | {_provider_config_keys(name, spec)} | {_provider_secret_locations(name, spec)} | {note} |"
        )
    parts.append("")
    parts.append("Troca de provider no código atual é build-time. Não existe hot-swap genérico sem reinício do gateway. O caminho prático é atualizar config com `clawlite provider use` / `clawlite provider set-auth`, validar, e reiniciar o gateway.")
    return "\n".join(parts)


def _render_channels() -> str:
    parts = [
        "| Canal | Status real | Observação |",
        "|---|---|---|",
    ]
    for row in _CHANNEL_FACTS:
        parts.append(f"| `{row['name']}` | `{row['status']}` | {row['summary']} |")
    parts.extend(
        [
            "",
            "Telegram usa principalmente `channels.telegram.*`. Os campos críticos do bot são `channels.telegram.enabled`, `channels.telegram.token`, `channels.telegram.mode`, `channels.telegram.webhook_*`, `channels.telegram.allow_from`, `channels.telegram.dm_policy`, `channels.telegram.group_policy`, `channels.telegram.topic_policy`, `channels.telegram.dm_allow_from`, `channels.telegram.group_allow_from`, `channels.telegram.topic_allow_from`, e `channels.telegram.group_overrides`.",
            "",
            "Para adicionar um usuário autorizado no Telegram, hoje existem três caminhos reais no código:",
            "1. Colocar o identificador em `channels.telegram.allow_from` para uma allowlist global.",
            "2. Colocar em `channels.telegram.dm_allow_from`, `group_allow_from` ou `topic_allow_from` se você usa policy por escopo.",
            "3. Se a policy estiver em `pairing`, aprovar o código com `clawlite pairing approve telegram <codigo>`.",
            "",
            "Para canais que têm `allow_from` tipado no schema, o campo exato fica no bloco do próprio canal, por exemplo `channels.discord.allow_from`, `channels.slack.allow_from`, `channels.whatsapp.allow_from` e `channels.email.allow_from`.",
            "",
            "Se um canal não conectar:",
            "- Primeiro rode `clawlite validate channels`.",
            "- Depois consulte `clawlite telegram status` ou `clawlite discord status` quando o canal tiver status dedicado.",
            "- Se for problema de transporte sem mudança de config, use `clawlite telegram refresh` ou `clawlite discord refresh`.",
            "- Se a config mudou em disco, faça restart do gateway; refresh não relê o config inteiro.",
        ]
    )
    return "\n".join(parts)


def _render_file_map() -> str:
    parts = [
        "```text",
        "clawlite/",
        "  config/        schema, loader, watcher e health",
        "  core/          engine, prompt, memory, subagents, skills",
        "  providers/     registry, auth, failover, probe, telemetry",
        "  channels/      adapters reais e stubs",
        "  tools/         tools do agente e registry",
        "  scheduler/     cron e heartbeat",
        "  gateway/       servidor FastAPI, dashboard, control-plane, websocket",
        "  cli/           parser e handlers da CLI",
        "  workspace/     templates e loader do contexto do prompt",
        "tests/           regressões",
        "docs/            documentação do repositório",
        "workspace/       cópia de SELF.md pedida para este checkout",
        "```",
        "",
        "| Arquivo | O que faz / quando mexer |",
        "|---|---|",
    ]
    for path, note in _FILE_MAP:
        parts.append(f"| `{path}` | {note} |")
    parts.extend(
        [
            "",
            "- Entrypoint real da CLI: `clawlite.cli:main` em `pyproject.toml`; o arquivo `clawlite/cli.py` não existe neste repositório.",
            "- O pacote `clawlite/gateway.py` também não existe; o servidor real está em `clawlite/gateway/server.py`.",
            "- Logs: por padrão vão para `stderr`. Arquivo de log só existe se `CLAWLITE_LOG_FILE` estiver configurado.",
            f"- Workspace do agente: `{_tilde(Path.home() / '.clawlite' / 'workspace')}` por padrão, ou o valor de `workspace_path`.",
            f"- Estado persistente geral: `{_tilde(Path.home() / '.clawlite' / 'state')}` por padrão, ou o valor de `state_path`.",
            f"- Memória persistente principal: `{_tilde(Path.home() / '.clawlite' / 'state' / 'memory.jsonl')}` e `{_tilde(Path.home() / '.clawlite' / 'memory')}`.",
            f"- Sessões persistidas: `{_tilde(Path.home() / '.clawlite' / 'state' / 'sessions')}`.",
            f"- Cron persistido: `{_tilde(Path.home() / '.clawlite' / 'state' / 'cron_jobs.json')}`.",
            f"- Cache de probes de provider: `{_tilde(Path.home() / '.clawlite' / 'state' / 'provider-probes.json')}`.",
        ]
    )
    return "\n".join(parts)


def _build_parser() -> argparse.ArgumentParser:
    from clawlite.cli.commands import build_parser

    return build_parser()


def _collect_cli_entries() -> list[tuple[str, str, argparse.ArgumentParser]]:
    parser = _build_parser()
    entries: list[tuple[str, str, argparse.ArgumentParser]] = []

    def walk(current: argparse.ArgumentParser, prefix: str = "clawlite") -> None:
        handler = getattr(current, "get_default", None)
        if callable(handler):
            bound_handler = current.get_default("handler")
            if callable(bound_handler):
                help_text = (current.description or "").strip()
                if not help_text:
                    help_text = current.format_help().splitlines()[0].strip()
                entries.append((prefix, help_text, current))
        for action in getattr(current, "_actions", []):
            if action.__class__.__name__ != "_SubParsersAction":
                continue
            for name, subparser in action.choices.items():
                walk(subparser, f"{prefix} {name}")

    walk(parser)
    return entries


def _example_for_action(path: str, parser: argparse.ArgumentParser) -> str:
    if path in _CLI_EXAMPLE_OVERRIDES:
        return _CLI_EXAMPLE_OVERRIDES[path]
    argv: list[str] = path.split()[1:]
    for action in parser._actions:
        if action.dest in {"help", "command"}:
            continue
        if action.__class__.__name__ == "_SubParsersAction":
            continue
        option_strings = list(getattr(action, "option_strings", []))
        if option_strings:
            if getattr(action, "required", False):
                sample = _SAMPLE_BY_DEST.get(action.dest, "demo")
                argv.extend([option_strings[0], sample])
            continue
        nargs = getattr(action, "nargs", None)
        if nargs == 0:
            continue
        sample = _SAMPLE_BY_DEST.get(action.dest, action.dest)
        if nargs in ("?", "*"):
            continue
        argv.append(sample)
    return " ".join(["clawlite", *argv])


def _render_cli_commands() -> str:
    parts = [
        "| Comando | O que faz | Exemplo válido |",
        "|---|---|---|",
    ]
    for path, help_text, parser in _collect_cli_entries():
        description = " ".join(str(help_text or "").split())
        example = _example_for_action(path, parser)
        parts.append(f"| `{path}` | {description} | `{example}` |")
    return "\n".join(parts)


def _render_engine_section() -> str:
    return "\n".join(
        [
            "- O loop principal fica em `clawlite/core/engine.py` e roda enquanto ainda houver iterações disponíveis.",
            "- O limite padrão por turno é `40`, vindo de `agents.defaults.max_tool_iterations`.",
            "- Em cada iteração, o engine:",
            "  1. lê histórico da sessão;",
            "  2. consulta a policy de memória e planeja snippets relevantes;",
            "  3. monta o prompt com workspace + perfil do usuário + skills + memória + resumo de histórico + contexto runtime;",
            "  4. chama o provider atual;",
            "  5. se vierem `tool_calls`, executa cada tool via `ToolRegistry`, grava o resultado e volta ao loop;",
            "  6. se vier texto final suficiente, persiste turno/histórico/memória e encerra.",
            "- As tools são validadas por schema JSON, passam por timeout/safety/approval/cache no `ToolRegistry`, e só então executam.",
            "- Histórico de conversa fica no `SessionStore` em `~/.clawlite/state/sessions`.",
            "- Memória persistente fica no `MemoryStore`, com histórico principal em `~/.clawlite/state/memory.jsonl` e artefatos em `~/.clawlite/memory`.",
            "- O prompt final é montado pelo `PromptBuilder`. A ordem prática é: contexto do workspace -> guard rails de identidade/execução -> perfil estruturado do usuário -> memória -> skills -> resumo de histórico -> emoção/memory hints -> histórico recente -> mensagem atual com contexto runtime.",
        ]
    )


def _render_config_intro() -> str:
    default_json = _tilde(DEFAULT_CONFIG_PATH)
    yaml_path = _tilde(Path.home() / ".clawlite" / "config.yaml")
    return "\n".join(
        [
            f"- Caminho padrão real no código: `{default_json}`.",
            f"- YAML também é aceito pelo loader, por exemplo `{yaml_path}`, mas não é o default.",
            "- Profiles são overlays do mesmo arquivo base, por exemplo `config.prod.json` ou `config.prod.yaml`.",
            "- Não existe hot reload geral de config sem reinício no parser atual. O que existe hoje é:",
            "  - `clawlite validate config` para validar o arquivo;",
            "  - `clawlite telegram refresh` e `clawlite discord refresh` para refresh de transporte específico;",
            "  - `clawlite restart-gateway` para aplicar mudança estrutural de config no runtime em execução.",
            "- Na inicialização, o runtime chama `load_config()`: lê o arquivo base, aplica overlay de profile, mescla env vars suportadas, e valida o resultado com `AppConfig.model_validate(...)`.",
            "- A checagem estrita de chaves desconhecidas só roda com `strict=True` ou `CLAWLITE_CONFIG_STRICT=1`; o comando exato da CLI é `clawlite validate config`.",
        ]
    )


def _render_provider_switch_section() -> str:
    return "\n".join(
        [
            "- Não existe hot-swap genérico de provider sem reinício do gateway.",
            "- Para trocar o provider de forma suportada hoje:",
            "  1. `clawlite provider use <provider> --model <provider/model>`",
            "  2. se o provider usar API key, rode `clawlite provider set-auth <provider> --api-key ...`",
            "  3. se usar OAuth, rode `clawlite provider login <provider>`",
            "  4. valide com `clawlite validate config` e `clawlite validate provider`",
            "  5. aplique no processo atual com `clawlite restart-gateway`.",
        ]
    )


def _render_tool_enable_section() -> str:
    return "\n".join(
        [
            "- Não há `tools.<nome>.enabled` para a maioria das tools.",
            "- O estado prático de uma tool hoje depende de um destes fatores:",
            "  - safety policy (`tools.safety.*`);",
            "  - timeout/restrição (`tools.default_timeout_s`, `tools.timeouts`, `tools.restrict_to_workspace`);",
            "  - bloco de config específico (`tools.web.*`, `tools.exec.*`, `tools.mcp.*`, `tools.loop_detection.*`);",
            "  - credencial/canal externo (`channels.discord.token` para `discord_admin`);",
            "  - dependência opcional (`browser`, `pdf_read`, `tts`).",
            "- Quando uma tool está indisponível, o comportamento não é um `enabled: false` genérico; o erro real vem do motivo concreto do bloqueio.",
            "- O caminho correto do agente é sugerir o campo exato que destrava a tool, ou dizer claramente que não existe enable flag específica para ela.",
        ]
    )


def _render_cron_section() -> str:
    return "\n".join(
        [
            "- Criar job via CLI: `clawlite cron add --session-id cli:cron --expression \"every 300\" --prompt \"ping\"`.",
            "- Listar: `clawlite cron list --session-id cli:cron`.",
            "- Rodar na hora: `clawlite cron run job-1`.",
            "- Sintaxe aceita no código:",
            "  - `every 120` -> a cada 120 segundos",
            "  - `at 2026-03-02T20:00:00` -> execução única em ISO datetime",
            "  - `0 9 * * *` -> expressão cron normal, mas só funciona se `croniter` estiver instalado",
            "- Não existe lista de jobs cron dentro do `config` tipado. O schema só define defaults do scheduler (`scheduler.*`). Os jobs em si ficam no store persistido do `CronService`.",
            "- Heartbeat usa `gateway.heartbeat.interval_s` como valor real. `scheduler.heartbeat_interval_seconds` ainda existe por compatibilidade legada e é migrado para o bloco do gateway.",
            f"- Estado do heartbeat: `{_tilde(Path.home() / '.clawlite' / 'state' / 'heartbeat-state.json')}`.",
            f"- Estado do cron: `{_tilde(Path.home() / '.clawlite' / 'state' / 'cron_jobs.json')}`.",
        ]
    )


def _render_limits_section() -> str:
    return "\n".join(
        [
            "- Nunca altero sem confirmação explícita: `gateway.auth.*`, `auth.*`, `provider.*`, `providers.*`, `channels.*`, e caminhos protegidos do `gateway_admin`.",
            "- Em mudanças por chat, prefiro `config_schema_lookup`, `config_intent_catalog`, `config_intent_preview` ou `config_patch_preview` antes do apply real.",
            "- Não tento inventar `enabled: true` para tools que não têm esse campo no schema.",
            "- Não tento hot reload genérico que o runtime não suporta; quando a mudança é estrutural, faço restart do gateway.",
            "- Para evitar loop de restart, só disparo um restart por vez e não repito mudanças enquanto já existe restart pendente.",
            "- Para evitar loop de execução de tools, respeito `tools.loop_detection.*` e não forço reexecuções cegas do mesmo plano.",
        ]
    )


def _render_status_section() -> str:
    return "\n".join(
        [
            "- Funcional no código hoje:",
            "  - gateway FastAPI + dashboard + websocket",
            "  - engine com tools + memória persistente + histórico",
            "  - cron + heartbeat",
            "  - failover de providers",
            "  - Telegram funcional",
            "  - Discord funcional/operável",
            "  - Slack, WhatsApp, Email e IRC funcionais",
            "  - fluxo via chat para preview/apply de config segura + restart + aviso pós-boot",
            "- Em desenvolvimento parcial, mas usável:",
            "  - Discord ainda é mais complexo e tem mais superfícies operacionais do que os outros canais",
            "  - skills gerenciadas, automation e dashboard têm bastante cobertura, mas seguem evoluindo",
            "- Stub/não implementado como adapter real:",
            "  - `signal`, `googlechat`, `matrix`, `imessage`, `dingtalk`, `feishu`, `mochat`, `qq`.",
        ]
    )


def _render_operator_instructions() -> str:
    return "\n".join(
        [
            "### Trocar token do Telegram",
            "1. Eu localizo o campo exato `channels.telegram.token` no config ativo.",
            "2. Eu altero o valor nesse arquivo.",
            "3. Eu valido com `clawlite validate config`.",
            "4. Como o runtime não faz hot reload geral de config, eu reinicio com `clawlite restart-gateway`.",
            "5. Depois eu confirmo com `clawlite validate channels` e, se o gateway já estiver de pé, `clawlite telegram status`.",
            "",
            "### Ativar uma tool que o usuário pediu",
            "1. Eu identifico primeiro se existe mesmo um campo de enable no código.",
            "2. Hoje, na maioria das tools, esse campo não existe. Então eu informo o motivo real do bloqueio: policy, credencial, dependência, servidor MCP, ou canal/provedor não configurado.",
            "3. Eu peço confirmação uma única vez antes de mudar config ou policy.",
            "4. Se houver campo seguro suportado pelo `gateway_admin`, eu faço preview e depois apply com restart.",
            "5. Se não houver enable flag tipada, eu explico o desbloqueio real com o campo exato e só então executo a tarefa original.",
            "",
            "### Trocar de provider",
            "1. Eu listo os providers suportados pelo runtime.",
            "2. Eu peço a credencial certa do novo provider: API key ou login OAuth, dependendo do caso.",
            "3. Eu atualizo `provider.model` e, se necessário, `providers.<provider>.api_key` / `api_base` ou `auth.providers.<provider>.*`.",
            "4. Eu valido com `clawlite validate config` e `clawlite validate provider`.",
            "5. Eu aplico no processo atual com `clawlite restart-gateway`.",
            "",
            "### Quando a tarefa precisa de uma tool indisponível",
            "1. Eu identifico a tool realmente necessária.",
            "2. Eu digo ao usuário por que ela não está disponível: bloqueio de safety, config faltando, credencial faltando, dependência faltando, ou feature não implementada.",
            "3. Eu informo o campo exato quando existir, ou digo claramente que não existe `enabled` genérico para aquela tool.",
            "4. Eu aguardo confirmação uma única vez antes de mudar config.",
            "5. Depois de destravar o bloqueio real, eu executo a tarefa original.",
        ]
    )


def generate_self_markdown(*, config_path: str | Path | None = None, profile: str | None = None) -> str:
    cfg = load_config(config_path, profile=profile)
    runtime_workspace = Path(cfg.workspace_path).expanduser()
    target_config = config_payload_path(config_path, profile=profile)

    sections = [
        "# SELF.md",
        "",
        "Documento gerado a partir do código atual do ClawLite. Este arquivo existe para o próprio agente se orientar sem inventar comportamento que o runtime não implementa.",
        "",
        "## 1. O que é o ClawLite",
        "",
        "- ClawLite é um runtime de agente autônomo local-first, com gateway FastAPI, memória persistente, tools, skills, cron, heartbeat e canais reais de chat.",
        "- O projeto roda em Linux e também tem caminho documentado para Android via Termux + `proot-distro` Ubuntu.",
        "- A filosofia real do código é local-first: o runtime, o estado e o workspace ficam na sua máquina. O projeto pode usar APIs externas de LLM, mas também suporta runtimes locais como Ollama e vLLM.",
        "",
        "## 2. Como o agente funciona",
        "",
        _render_engine_section(),
        "",
        "## 3. Arquivo de configuração",
        "",
        _render_config_intro(),
        "",
        f"- Arquivo alvo desta sessão/profile: `{_tilde(target_config)}`.",
        f"- Workspace configurado agora: `{_tilde(runtime_workspace)}`.",
        "",
        _render_config_fields(),
        "",
        "## 4. Providers disponíveis",
        "",
        _render_providers(),
        "",
        "### Troca de provider sem parar o agente",
        "",
        _render_provider_switch_section(),
        "",
        "## 5. Canais",
        "",
        _render_channels(),
        "",
        "## 6. Tools disponíveis",
        "",
        _render_tools(),
        "",
        "### Habilitar, desabilitar e sugerir ativação",
        "",
        _render_tool_enable_section(),
        "",
        "## 7. Cron e Heartbeat",
        "",
        _render_cron_section(),
        "",
        "## 8. Comandos CLI",
        "",
        _render_cli_commands(),
        "",
        "Comandos de referência rápida:",
        "- Validar config: `clawlite validate config`",
        "- Ver status: `clawlite status`",
        "- Reiniciar gateway: `clawlite restart-gateway`",
        "",
        "## 9. Estrutura de arquivos do projeto",
        "",
        _render_file_map(),
        "",
        "## 10. Como o agente deve agir quando o usuário pedir mudanças",
        "",
        _render_operator_instructions(),
        "",
        "## 11. Limites e o que não fazer",
        "",
        _render_limits_section(),
        "",
        "## 12. Status atual do projeto",
        "",
        _render_status_section(),
    ]
    return "\n".join(sections).strip() + "\n"


def write_self_markdown(
    *,
    targets: list[str | Path],
    config_path: str | Path | None = None,
    profile: str | None = None,
) -> list[Path]:
    content = generate_self_markdown(config_path=config_path, profile=profile)
    written: list[Path] = []
    for item in targets:
        path = Path(item).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


__all__ = [
    "generate_self_markdown",
    "write_self_markdown",
]
