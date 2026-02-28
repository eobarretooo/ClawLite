from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

from clawlite.config import settings as app_settings
from clawlite.core.plugin_sdk import (
    HookContext,
    HookPhase,
    ToolDefinition,
    ToolPlugin,
    ToolResult,
    get_plugin_registry,
)

logger = logging.getLogger(__name__)


class Plugin:
    """
    Legacy plugin base for backward compatibility.

    New plugins should prefer `plugin_sdk` and expose `register(registry)`.
    """

    name: str = "unnamed-plugin"
    version: str = "1.0.0"
    description: str = "A custom ClawLite plugin."

    def on_load(self) -> None:
        pass

    def on_unload(self) -> None:
        pass

    def register_tools(self) -> List[Dict[str, Any]]:
        return []

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str | None:
        return None

    def on_message(self, role: str, message: str, session_id: str) -> None:
        pass

    def on_thought(self, text: str, session_id: str) -> None:
        pass


class _LegacyToolAdapter(ToolPlugin):
    def __init__(self, plugin: Plugin):
        self._plugin = plugin

    def get_tools(self) -> list[ToolDefinition]:
        out: list[ToolDefinition] = []
        for item in self._plugin.register_tools() or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            out.append(
                ToolDefinition(
                    name=name,
                    description=str(item.get("description", "")).strip() or f"Plugin tool '{name}'",
                    parameters=item.get("parameters") if isinstance(item.get("parameters"), dict) else {},
                    category=str(item.get("category", "general")).strip() or "general",
                    dangerous=bool(item.get("dangerous", False)),
                )
            )
        return out

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        result = self._plugin.execute_tool(tool_name, arguments)
        if result is None:
            return ToolResult(output=f"Tool '{tool_name}' not handled by plugin", success=False)
        return ToolResult(output=str(result), success=True)


class PluginManager:
    """Loads plugins from workspace and bridges legacy + plugin_sdk styles."""

    _instance: "PluginManager | None" = None

    def __init__(self) -> None:
        self.plugins: Dict[str, Plugin] = {}
        self.registry = get_plugin_registry()

    @classmethod
    def get(cls) -> "PluginManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_plugins_dir(self) -> Path:
        base = Path(app_settings.CONFIG_DIR) / "workspace" / "plugins"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def load_all(self) -> None:
        self._unload_all()
        self.registry.clear()

        plugins_dir = self.get_plugins_dir()
        for filepath in plugins_dir.glob("*.py"):
            if filepath.name.startswith("_"):
                continue
            self._load_plugin_file(filepath)

    def _unload_all(self) -> None:
        for plugin in list(self.plugins.values()):
            try:
                plugin.on_unload()
            except Exception as exc:
                logger.warning("Plugin unload failure '%s': %s", getattr(plugin, "name", "?"), exc)
        self.plugins.clear()

    def _load_plugin_file(self, filepath: Path) -> None:
        module_name = f"clawlite_plugin_{filepath.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if not spec or not spec.loader:
                logger.warning("Plugin skipped (invalid spec): %s", filepath)
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Modern SDK style: register(registry) or register_plugin(registry)
            register_fn = getattr(module, "register", None) or getattr(module, "register_plugin", None)
            if callable(register_fn):
                register_fn(self.registry)

            # Legacy style: subclass of Plugin
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, Plugin) or obj is Plugin:
                    continue
                instance = obj()
                plugin_id = (getattr(instance, "name", obj.__name__) or obj.__name__).strip().lower()
                self.plugins[plugin_id] = instance
                instance.on_load()
                adapter = _LegacyToolAdapter(instance)
                if adapter.get_tools():
                    self.registry.register_tool_plugin(f"legacy:{plugin_id}", adapter)

            logger.info("Plugin loaded: %s", filepath.name)
        except Exception as exc:
            logger.warning("Failed to load plugin %s: %s", filepath.name, exc)

    def get_all_tool_definitions(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for tool in self.registry.get_all_tools():
            out.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "category": tool.category,
                    "dangerous": tool.dangerous,
                }
            )
        return out

    def try_execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str | None:
        result = self.registry.execute_tool(tool_name, args)
        if result is not None:
            return result.output

        for plugin in self.plugins.values():
            try:
                legacy_result = plugin.execute_tool(tool_name, args)
                if legacy_result is not None:
                    return str(legacy_result)
            except Exception as exc:
                return f"Plugin tool error: {exc}"
        return None

    def fire_hooks(self, phase: HookPhase, *, session_id: str = "", prompt: str = "", response: str = "", metadata: dict[str, Any] | None = None) -> HookContext:
        context = HookContext(
            phase=phase,
            session_id=session_id,
            prompt=prompt,
            response=response,
            metadata=metadata or {},
        )
        return self.registry.fire_hooks(context)

    def broadcast_message(self, role: str, msg: str, session_id: str) -> None:
        for name, plugin in self.plugins.items():
            try:
                plugin.on_message(role, msg, session_id)
            except Exception as exc:
                logger.warning("Plugin '%s' error in on_message: %s", name, exc)

    def broadcast_thought(self, text: str, session_id: str) -> None:
        for name, plugin in self.plugins.items():
            try:
                plugin.on_thought(text, session_id)
            except Exception as exc:
                logger.warning("Plugin '%s' error in on_thought: %s", name, exc)
