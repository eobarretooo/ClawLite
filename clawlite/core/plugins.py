from __future__ import annotations
import inspect
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Type

class Plugin:
    """
    Base class for ClawLite Plugins (Sprint 6).
    Extensions should inherit from this class to inject custom tools
    and listen to agent lifecycle events.
    """
    name: str = "unnamed-plugin"
    version: str = "1.0.0"
    description: str = "A custom ClawLite plugin."
    
    def on_load(self) -> None:
        """Called when the plugin is first loaded into memory."""
        pass

    def on_unload(self) -> None:
        """Called if the plugin is disabled or the host shuts down."""
        pass

    def register_tools(self) -> List[Dict[str, Any]]:
        """
        Return a list of tool definitions (JSON Schema format) that this 
        plugin exposes to the LLM agent.
        """
        return []

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str | None:
        """
        If the LLM calls a tool registered by this plugin, this method handles it.
        Return None if the tool_name doesn't belong to this plugin.
        """
        return None

    def on_message(self, role: str, message: str, session_id: str) -> None:
        """
        Hook: Triggered every time a message is added to the session history.
        `role` can be 'user', 'agent' or 'system'.
        """
        pass
        
    def on_thought(self, text: str, session_id: str) -> None:
        """
        Hook: Triggered during token streaming when the agent thinks.
        """
        pass


class PluginManager:
    """Manages the lifecycle and discovery of ClawLite plugins."""
    _instance = None

    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self.tools_cache: List[Dict[str, Any]] = []
        
    @classmethod
    def get(cls) -> "PluginManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_plugins_dir(self) -> Path:
        base = Path.home() / ".clawlite" / "workspace" / "plugins"
        base.mkdir(parents=True, exist_ok=True)
        return base

    def load_all(self):
        """Scans the plugins directory and loads all valid Python modules containing Plugins."""
        plugins_dir = self.get_plugins_dir()
        if not plugins_dir.exists():
            return
            
        for filepath in plugins_dir.glob("*.py"):
            if filepath.name.startswith("_"):
                continue
            self._load_plugin_file(filepath)
            
        self._rebuild_caches()

    def _load_plugin_file(self, filepath: Path):
        try:
            module_name = f"clawlite_plugin_{filepath.stem}"
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, Plugin) and obj is not Plugin:
                        instance = obj()
                        plugin_id = getattr(instance, "name", name).lower()
                        self.plugins[plugin_id] = instance
                        instance.on_load()
        except Exception as e:
            print(f"⚠️ Failed to load plugin {filepath.name}: {e}")

    def _rebuild_caches(self):
        """Aggregate all tool definitions from all registered plugins"""
        self.tools_cache = []
        for p in self.plugins.values():
            try:
                tools = p.register_tools()
                if tools:
                    self.tools_cache.extend(tools)
            except Exception:
                pass

    def get_all_tool_definitions(self) -> List[Dict[str, Any]]:
        return self.tools_cache

    def try_execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str | None:
        """Passes the tool execution broadcast to all plugins."""
        for p in self.plugins.values():
            try:
                result = p.execute_tool(tool_name, args)
                if result is not None:
                    return result
            except Exception as e:
                return f"❌ Plugin Tool Error: {e}"
        return None

    def broadcast_message(self, role: str, msg: str, session_id: str):
        for p in self.plugins.values():
            try:
                p.on_message(role, msg, session_id)
            except: pass

    def broadcast_thought(self, text: str, session_id: str):
        for p in self.plugins.values():
            try:
                p.on_thought(text, session_id)
            except: pass
