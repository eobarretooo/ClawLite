"""
ClawLite Plugin SDK — Interfaces para canais, ferramentas e hooks.

Inspirado na arquitetura do OpenClaw com 15+ adapter interfaces,
adaptado para Python com ABCs e dataclasses.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Tool Plugin SDK
# ──────────────────────────────────────────────

class ToolApproval(Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


@dataclass
class ToolDefinition:
    """Schema de uma ferramenta registrável por plugins."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    approval: ToolApproval = ToolApproval.ALLOW
    category: str = "general"
    dangerous: bool = False


@dataclass
class ToolResult:
    """Resultado da execução de uma ferramenta."""
    output: str
    success: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolPlugin(ABC):
    """Interface para plugins que expõem ferramentas ao agente."""

    @abstractmethod
    def get_tools(self) -> list[ToolDefinition]:
        """Retorna lista de ferramentas que este plugin expõe."""
        ...

    @abstractmethod
    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Executa uma ferramenta pelo nome com os argumentos dados."""
        ...


# ──────────────────────────────────────────────
# Channel Plugin SDK
# ──────────────────────────────────────────────

@dataclass
class InboundMessage:
    """Mensagem recebida de um canal, normalizada."""
    channel: str
    sender_id: str
    text: str
    session_id: str = ""
    thread_id: str = ""
    media_url: str = ""
    reply_to_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """Mensagem a ser enviada para um canal."""
    channel: str
    recipient_id: str
    text: str
    thread_id: str = ""
    media_url: str = ""
    reply_to_id: str = ""


class ChannelPlugin(ABC):
    """Interface para plugins de canal de comunicação."""

    @property
    @abstractmethod
    def channel_id(self) -> str:
        """Identificador único do canal (ex: 'telegram', 'discord')."""
        ...

    @property
    def display_name(self) -> str:
        """Nome amigável para exibição."""
        return self.channel_id.capitalize()

    @abstractmethod
    async def start(self, config: dict[str, Any], on_message: Callable[[InboundMessage], Awaitable[None]]) -> None:
        """Inicia o canal (polling, webhook, etc)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Para o canal graciosamente."""
        ...

    @abstractmethod
    async def send(self, message: OutboundMessage) -> bool:
        """Envia uma mensagem pelo canal. Retorna True se enviou."""
        ...

    def is_configured(self, config: dict[str, Any]) -> bool:
        """Verifica se o canal tem configuração mínima para funcionar."""
        return bool(config.get("token") or config.get("accounts"))

    def capabilities(self) -> dict[str, bool]:
        """Capacidades suportadas por este canal."""
        return {
            "text": True,
            "media": False,
            "voice": False,
            "threads": False,
            "reactions": False,
            "typing_indicator": False,
        }


# ──────────────────────────────────────────────
# Hook Plugin SDK
# ──────────────────────────────────────────────

class HookPhase(Enum):
    BEFORE_AGENT_START = "before_agent_start"
    BEFORE_PROMPT_BUILD = "before_prompt_build"
    AFTER_TOOL_CALL = "after_tool_call"
    AFTER_RESPONSE = "after_response"
    ON_ERROR = "on_error"


@dataclass
class HookContext:
    """Contexto passado para hooks."""
    phase: HookPhase
    session_id: str = ""
    prompt: str = ""
    response: str = ""
    tool_name: str = ""
    tool_result: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class HookPlugin(ABC):
    """Interface para plugins que interceptam o ciclo de vida do agente."""

    @property
    @abstractmethod
    def phases(self) -> list[HookPhase]:
        """Fases em que este hook deve ser chamado."""
        ...

    @abstractmethod
    def execute(self, context: HookContext) -> HookContext:
        """Processa o contexto e retorna (possivelmente modificado)."""
        ...


# ──────────────────────────────────────────────
# Plugin Registry
# ──────────────────────────────────────────────

@dataclass
class PluginManifest:
    """Manifesto de um plugin instalável."""
    id: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    channels: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)


class PluginRegistry:
    """Registro central de todos os plugins carregados."""

    def __init__(self):
        self._tool_plugins: dict[str, ToolPlugin] = {}
        self._channel_plugins: dict[str, ChannelPlugin] = {}
        self._hook_plugins: dict[str, HookPlugin] = {}

    def register_tool_plugin(self, plugin_id: str, plugin: ToolPlugin) -> None:
        self._tool_plugins[plugin_id] = plugin
        tools = plugin.get_tools()
        logger.info("Registered tool plugin '%s' with %d tools", plugin_id, len(tools))

    def register_channel_plugin(self, plugin_id: str, plugin: ChannelPlugin) -> None:
        self._channel_plugins[plugin_id] = plugin
        logger.info("Registered channel plugin '%s' (%s)", plugin_id, plugin.channel_id)

    def register_hook_plugin(self, plugin_id: str, plugin: HookPlugin) -> None:
        self._hook_plugins[plugin_id] = plugin
        logger.info("Registered hook plugin '%s' for phases %s", plugin_id, plugin.phases)

    def clear(self) -> None:
        self._tool_plugins.clear()
        self._channel_plugins.clear()
        self._hook_plugins.clear()

    def get_all_tools(self) -> list[ToolDefinition]:
        tools = []
        for p in self._tool_plugins.values():
            tools.extend(p.get_tools())
        return tools

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult | None:
        for p in self._tool_plugins.values():
            tool_names = [t.name for t in p.get_tools()]
            if tool_name in tool_names:
                return p.execute(tool_name, arguments)
        return None

    def get_channel(self, channel_id: str) -> ChannelPlugin | None:
        for p in self._channel_plugins.values():
            if p.channel_id == channel_id:
                return p
        return None

    def get_all_channels(self) -> list[ChannelPlugin]:
        return list(self._channel_plugins.values())

    def fire_hooks(self, context: HookContext) -> HookContext:
        for plugin_id, p in self._hook_plugins.items():
            if context.phase in p.phases:
                try:
                    context = p.execute(context)
                except Exception as e:
                    logger.warning("Hook plugin '%s' error: %s", plugin_id, e)
        return context

    @property
    def tool_count(self) -> int:
        return len(self.get_all_tools())

    @property
    def channel_count(self) -> int:
        return len(self._channel_plugins)

    @property
    def hook_count(self) -> int:
        return len(self._hook_plugins)


# Singleton global
_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
