from __future__ import annotations

from clawlite.config.settings import load_config, save_config


def model_status() -> str:
    cfg = load_config()
    current = cfg.get("model", "openai/gpt-4o-mini")
    fb = cfg.get("model_fallback", ["openrouter/auto", "ollama/llama3.1:8b"])
    lines = [f"model.current: {current}", "model.fallback:"]
    lines.extend([f"- {m}" for m in fb])
    return "\n".join(lines)


def set_model_fallback(models: list[str]) -> None:
    cfg = load_config()
    cfg["model_fallback"] = [m.strip() for m in models if m.strip()]
    save_config(cfg)
