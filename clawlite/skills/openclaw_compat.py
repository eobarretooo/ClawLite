from __future__ import annotations

from importlib import import_module
from typing import Callable


# Skills OpenClaw com equivalente funcional direto no ClawLite.
_DELEGATES: dict[str, str] = {
    "apple-reminders": "clawlite.skills.cron:run",
    "blogwatcher": "clawlite.skills.rss:run",
    "gh-issues": "clawlite.skills.github:run",
    "goplaces": "clawlite.skills.maps:run",
    "nano-pdf": "clawlite.skills.pdf:run",
    "openai-image-gen": "clawlite.skills.image_gen:run",
    "openai-whisper": "clawlite.skills.whisper:run",
    "openai-whisper-api": "clawlite.skills.whisper:run",
    "session-logs": "clawlite.skills.memory_search:run",
    "xurl": "clawlite.skills.web_fetch:run",
}


# Skills sem backend equivalente no ClawLite (retornam guidance de fallback).
_UNSUPPORTED: dict[str, str] = {
    "1password": "Sem backend nativo no ClawLite. Use integração MCP/CLI externa de secret manager.",
    "apple-notes": "Sem backend nativo no Linux/Termux. Use 'obsidian' ou 'notion'.",
    "bear-notes": "Sem backend nativo no Linux/Termux. Use 'obsidian' ou 'notion'.",
    "blucli": "Sem backend nativo no ClawLite.",
    "bluebubbles": "Canal BlueBubbles não está exposto como skill Python nativa no ClawLite atual.",
    "camsnap": "Sem backend de captura de câmera exposto como skill no ClawLite atual.",
    "canvas": "Canvas não está exposto como skill Python nativa no ClawLite atual.",
    "clawhub": "Use 'clawlite skill search/install/update' para operações de marketplace.",
    "eightctl": "Sem backend nativo no ClawLite.",
    "gemini": "No ClawLite, Gemini é configurado como provider/modelo no onboarding/configure.",
    "gifgrep": "Sem backend dedicado. Use 'web-search' e 'web-fetch'.",
    "gog": "Sem backend nativo no ClawLite.",
    "himalaya": "Sem backend nativo. Para e-mail use skill 'gmail'.",
    "imsg": "iMessage não está exposto como skill Python nativa no ClawLite atual.",
    "mcporter": "Sem backend nativo no ClawLite.",
    "model-usage": "Sem skill dedicada. Use 'clawlite stats' e status do runtime.",
    "nano-banana-pro": "Sem backend nativo no ClawLite.",
    "openhue": "Sem backend nativo no ClawLite.",
    "oracle": "Sem backend nativo no ClawLite.",
    "ordercli": "Sem backend nativo no ClawLite.",
    "peekaboo": "Sem backend nativo no ClawLite.",
    "sag": "Sem backend nativo no ClawLite.",
    "sherpa-onnx-tts": "Sem backend nativo no ClawLite atual.",
    "songsee": "Sem backend nativo no ClawLite.",
    "sonoscli": "Sem backend nativo no ClawLite.",
    "spotify-player": "Sem backend nativo no ClawLite.",
    "summarize": "Sem skill dedicada. Use o agente principal para resumir texto/conteúdo.",
    "things-mac": "Sem backend nativo no Linux/Termux. Use 'cron' para lembretes/tarefas.",
    "tmux": "Sem backend nativo no ClawLite.",
    "trello": "Sem backend nativo. Use 'linear' ou 'notion' como alternativa.",
    "video-frames": "Sem backend nativo no ClawLite.",
    "wacli": "Sem skill dedicada. Configure canais e use comandos de channel/gateway.",
}


def _delegate_run(target: str, command: str) -> str:
    module_path, fn_name = target.split(":", 1)
    fn = getattr(import_module(module_path), fn_name)
    return str(fn(command))


def _build_runner(alias: str) -> Callable[[str], str]:
    if alias in _DELEGATES:
        target = _DELEGATES[alias]

        def _run(command: str = "") -> str:
            return _delegate_run(target, command)

        return _run

    guidance = _UNSUPPORTED.get(alias, "Skill OpenClaw sem mapeamento no ClawLite.")

    def _run(command: str = "") -> str:
        cmd = str(command or "").strip()
        details = f"\nComando recebido: {cmd}" if cmd else ""
        return (
            f"[openclaw-compat:{alias}] {guidance}{details}\n"
            "Alternativas: use `clawlite skill search <tema>` para encontrar uma skill equivalente."
        )

    return _run


OPENCLAW_COMPAT_SKILLS: dict[str, str] = {}
OPENCLAW_COMPAT_DESCRIPTIONS: dict[str, str] = {}

for _alias in sorted(set(_DELEGATES) | set(_UNSUPPORTED)):
    _fn_name = f"run_{_alias.replace('-', '_')}"
    globals()[_fn_name] = _build_runner(_alias)
    OPENCLAW_COMPAT_SKILLS[_alias] = f"clawlite.skills.openclaw_compat:{_fn_name}"
    if _alias in _DELEGATES:
        OPENCLAW_COMPAT_DESCRIPTIONS[_alias] = (
            f"Compat OpenClaw: alias mapeado para backend ClawLite ({_DELEGATES[_alias]})."
        )
    else:
        OPENCLAW_COMPAT_DESCRIPTIONS[_alias] = (
            "Compat OpenClaw: skill sem backend nativo no ClawLite, retorna guidance operacional."
        )

