"""
ClawLite RBAC — Role-Based Access Control + Tool Approval System.

Roles: operator (full access), viewer (read-only), agent (tool execution)
Scopes: admin, read, write, tools, approvals
Tool Policy: allow, review, deny per tool/category
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from clawlite.config.settings import load_config, save_config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Roles & Scopes
# ──────────────────────────────────────────────

class Role(Enum):
    OPERATOR = "operator"
    VIEWER = "viewer"
    AGENT = "agent"


class Scope(Enum):
    ADMIN = "admin"
    READ = "read"
    WRITE = "write"
    TOOLS = "tools"
    APPROVALS = "approvals"


# Mapping: role -> default scopes
ROLE_SCOPES: dict[Role, set[Scope]] = {
    Role.OPERATOR: {Scope.ADMIN, Scope.READ, Scope.WRITE, Scope.TOOLS, Scope.APPROVALS},
    Role.VIEWER: {Scope.READ},
    Role.AGENT: {Scope.READ, Scope.WRITE, Scope.TOOLS},
}


@dataclass
class Identity:
    """Identidade autenticada com role e scopes."""
    name: str
    role: Role
    scopes: set[Scope] = field(default_factory=set)
    token: str = ""

    def has_scope(self, scope: Scope) -> bool:
        return scope in self.scopes

    def is_admin(self) -> bool:
        return Scope.ADMIN in self.scopes

    def can_execute_tools(self) -> bool:
        return Scope.TOOLS in self.scopes


def resolve_identity(token: str) -> Identity:
    """Resolve token para identidade. Por enquanto, token match simples."""
    cfg = load_config()
    gateway_token = cfg.get("gateway", {}).get("token", "")
    security = cfg.get("security", {})
    rbac_config = security.get("rbac", {})

    if not gateway_token:
        # Sem token configurado: operador local
        return Identity(name="local-operator", role=Role.OPERATOR, scopes=ROLE_SCOPES[Role.OPERATOR])

    if token == gateway_token:
        return Identity(name="operator", role=Role.OPERATOR, scopes=ROLE_SCOPES[Role.OPERATOR])

    # Verificar tokens de viewer
    viewer_tokens = rbac_config.get("viewer_tokens", [])
    if token in viewer_tokens:
        return Identity(name="viewer", role=Role.VIEWER, scopes=ROLE_SCOPES[Role.VIEWER])

    # Token inválido
    return Identity(name="anonymous", role=Role.VIEWER, scopes=set())


def authorize(identity: Identity, required_scope: Scope) -> bool:
    """Verifica se a identidade tem o scope necessário."""
    if identity.has_scope(required_scope):
        return True
    logger.warning(
        "Authorization denied: '%s' (role=%s) lacks scope '%s'",
        identity.name, identity.role.value, required_scope.value,
    )
    return False


# ──────────────────────────────────────────────
# Tool Approval System
# ──────────────────────────────────────────────

class ToolPolicy(Enum):
    ALLOW = "allow"       # Executa direto
    REVIEW = "review"     # Loga e executa
    DENY = "deny"         # Bloqueia


@dataclass
class ToolApprovalEntry:
    """Registro de aprovação de ferramenta."""
    tool_name: str
    policy: ToolPolicy
    reason: str = ""
    timestamp: float = 0.0


# Tools classificadas como perigosas (precisam de review por padrão)
DANGEROUS_TOOLS = {
    "exec_cmd",          # Execução de comandos
    "write_file",        # Escrita em disco
    "ssh",               # Acesso remoto
    "docker",            # Containers
}

# Tools seguras (allow por padrão)
SAFE_TOOLS = {
    "read_file",
    "web_search",
    "web_fetch",
    "memory_search",
    "browser_read",
    "browser_goto",
    "healthcheck",
    "weather",
}

# Audit log
_audit_log: list[dict[str, Any]] = []


def get_tool_policy(tool_name: str, identity: Identity | None = None) -> ToolPolicy:
    """Determina a política de execução para uma ferramenta."""
    cfg = load_config()
    security = cfg.get("security", {})
    tool_policies = security.get("tool_policies", {})

    # 1. Política explícita na config
    explicit = tool_policies.get(tool_name)
    if explicit:
        try:
            return ToolPolicy(explicit)
        except ValueError:
            pass

    # 2. Identity sem scope de tools → deny
    if identity and not identity.can_execute_tools():
        return ToolPolicy.DENY

    # 3. Classificação padrão
    if tool_name in DANGEROUS_TOOLS:
        return ToolPolicy.REVIEW
    if tool_name in SAFE_TOOLS:
        return ToolPolicy.ALLOW

    # 4. Default: review para tools desconhecidas
    return ToolPolicy.REVIEW


def check_tool_approval(
    tool_name: str,
    arguments: dict[str, Any],
    identity: Identity | None = None,
) -> tuple[bool, str]:
    """
    Verifica se uma ferramenta pode ser executada.
    Retorna (aprovado, motivo).
    """
    policy = get_tool_policy(tool_name, identity)

    # Registrar no audit log
    entry = {
        "tool": tool_name,
        "policy": policy.value,
        "identity": identity.name if identity else "system",
        "arguments_preview": str(arguments)[:200],
        "timestamp": time.time(),
    }
    _audit_log.append(entry)

    # Manter audit log limitado
    if len(_audit_log) > 500:
        _audit_log.pop(0)

    if policy == ToolPolicy.DENY:
        reason = f"Ferramenta '{tool_name}' bloqueada pela política de segurança"
        logger.warning("Tool DENIED: %s", tool_name)
        return False, reason

    if policy == ToolPolicy.REVIEW:
        logger.info("Tool REVIEW (allowed): %s with args %s", tool_name, str(arguments)[:100])

    return True, policy.value


def get_audit_log(limit: int = 50) -> list[dict[str, Any]]:
    """Retorna as últimas entradas do log de auditoria."""
    return list(reversed(_audit_log[-limit:]))


def set_tool_policy(tool_name: str, policy: str) -> None:
    """Define política de execução para uma ferramenta na config."""
    cfg = load_config()
    security = cfg.setdefault("security", {})
    policies = security.setdefault("tool_policies", {})
    policies[tool_name] = policy
    save_config(cfg)
    logger.info("Tool policy set: %s -> %s", tool_name, policy)
