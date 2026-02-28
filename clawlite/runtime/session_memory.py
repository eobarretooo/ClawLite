from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from clawlite.runtime.workspace import init_workspace


@dataclass
class MemoryHit:
    path: str
    score: int
    snippet: str


def _workspace_root(path: str | None = None) -> Path:
    if path:
        return Path(path).expanduser()
    return Path(init_workspace())


def ensure_memory_layout(path: str | None = None) -> Path:
    root = _workspace_root(path)
    templates = {
        "AGENTS.md": "# AGENTS\n\nRegras operacionais do assistente.\n",
        "SOUL.md": "# SOUL\n\nTom: direto, técnico, confiável.\n",
        "USER.md": "# USER\n\nPreferências da pessoa usuária e contexto de trabalho.\n",
        "IDENTITY.md": "# IDENTITY\n\nClawLite Assistant 🦊\n",
        "TOOLS.md": "# TOOLS.md\n\nNotas do ambiente local.\n",
        "HEARTBEAT.md": "# HEARTBEAT.md\n\nChecklist proativo periódico.\n",
        "BOOT.md": "# BOOT.md\n\nChecklist pós-restart.\n",
        "BOOTSTRAP.md": "# BOOTSTRAP.md - Hello, World\n\nPrimeira conversa para definir identidade.\n",
        "MEMORY.md": "# MEMORY\n\nMemória de longo prazo (curada).\n",
    }
    for name, content in templates.items():
        p = root / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")
    (root / "memory").mkdir(parents=True, exist_ok=True)
    return root


def _daily_file(root: Path, day: datetime | None = None) -> Path:
    dt = (day or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return root / "memory" / f"{dt.strftime('%Y-%m-%d')}.md"


def append_daily_log(text: str, category: str = "event", path: str | None = None) -> Path:
    root = ensure_memory_layout(path)
    f = _daily_file(root)
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    if not f.exists():
        f.write_text(f"# {f.stem}\n\n", encoding="utf-8")
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"- [{ts}] [{category}] {text.strip()}\n")
    return f


def startup_context(path: str | None = None) -> dict[str, Any]:
    root = ensure_memory_layout(path)
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    files = [
        root / "AGENTS.md",
        root / "SOUL.md",
        root / "USER.md",
        root / "IDENTITY.md",
        root / "TOOLS.md",
        root / "HEARTBEAT.md",
        root / "BOOT.md",
        root / "BOOTSTRAP.md",
        root / "MEMORY.md",
        _daily_file(root, now),
        _daily_file(root, yesterday),
    ]

    loaded: dict[str, str] = {}
    for f in files:
        if f.exists():
            loaded[str(f)] = f.read_text(encoding="utf-8")[:6000]

    return {
        "root": str(root),
        "files_loaded": list(loaded.keys()),
        "context": loaded,
    }


def semantic_search_memory(query: str, max_results: int = 5, path: str | None = None) -> list[MemoryHit]:
    root = ensure_memory_layout(path)
    tokens = {t for t in re.findall(r"[a-zA-Z0-9_-]+", query.lower()) if len(t) > 2}
    targets = [
        root / "MEMORY.md",
        root / "USER.md",
        root / "SOUL.md",
        root / "AGENTS.md",
        root / "IDENTITY.md",
    ]
    targets.extend(sorted((root / "memory").glob("*.md"), reverse=True)[:14])

    hits: list[MemoryHit] = []
    for f in targets:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        low = text.lower()
        score = sum(1 for t in tokens if t in low)
        if score <= 0:
            continue
        idx = min((low.find(t) for t in tokens if t in low), default=0)
        start = max(0, idx - 120)
        end = min(len(text), idx + 220)
        snippet = text[start:end].replace("\n", " ").strip()
        hits.append(MemoryHit(path=str(f), score=score, snippet=snippet))

    hits.sort(key=lambda x: x.score, reverse=True)
    return hits[:max_results]


def save_session_summary(summary: str, important: bool = True, path: str | None = None) -> None:
    root = ensure_memory_layout(path)
    append_daily_log(summary, category="session-summary", path=str(root))
    if important:
        memory = root / "MEMORY.md"
        with memory.open("a", encoding="utf-8") as fh:
            fh.write(f"\n- {datetime.now(timezone.utc).strftime('%Y-%m-%d')}: {summary.strip()}\n")


def compact_daily_memory(max_daily_files: int = 21, path: str | None = None) -> dict[str, Any]:
    root = ensure_memory_layout(path)
    files = sorted((root / "memory").glob("*.md"))
    if len(files) <= max_daily_files:
        return {"compacted": 0, "kept": len(files)}

    old = files[: len(files) - max_daily_files]
    summary_lines: list[str] = []
    for f in old:
        text = f.read_text(encoding="utf-8")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("-")]
        if lines:
            summary_lines.append(f"## {f.stem}")
            summary_lines.extend(lines[:8])
        f.unlink(missing_ok=True)

    if summary_lines:
        mem = root / "MEMORY.md"
        with mem.open("a", encoding="utf-8") as fh:
            fh.write("\n\n## Compactação automática (histórico diário)\n")
            fh.write("\n".join(summary_lines[:400]))
            fh.write("\n")

    return {"compacted": len(old), "kept": max_daily_files}


def bootstrap_prompt_once(path: str | None = None) -> str:
    root = ensure_memory_layout(path)
    boot = root / "BOOTSTRAP.md"
    seen = root / ".bootstrap_seen"
    if not boot.exists() or seen.exists():
        return ""
    text = boot.read_text(encoding="utf-8")[:3000]
    seen.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    return text


def startup_context_text(path: str | None = None) -> str:
    ctx = startup_context(path)
    blocks = []
    for fp in ctx["files_loaded"]:
        content = ctx["context"][fp][:1200]
        blocks.append(f"[{Path(fp).name}]\n{content}")
    return "\n\n".join(blocks)


def read_recent_session_messages(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Reads the last N messages for a specific session_id from the JSONL log 
    in clawlite/gateway/state.py SESSIONS_FILE without importing it directly
    to avoid circular dependencies.
    """
    import json
    
    # Derivamos o caminho do gateway onde os JSONLs são armazenados
    cwd = Path(__file__).parent.parent / "gateway" / ".data"
    sessions_file = cwd / "sessions.jsonl"
    if not sessions_file.exists():
        return []

    lines = sessions_file.read_text(encoding="utf-8").splitlines()
    matches = []
    
    for ln in lines:
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
            if str(row.get("session_id")) == session_id:
                matches.append(row)
        except json.JSONDecodeError:
            pass

    return matches[-limit:]


def memory_hits_to_json(hits: list[MemoryHit]) -> str:
    return json.dumps([
        {"path": h.path, "score": h.score, "snippet": h.snippet} for h in hits
    ], ensure_ascii=False, indent=2)
