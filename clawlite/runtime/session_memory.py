from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from clawlite.runtime.workspace import (
    BOOTSTRAP_COMPLETED_MARKER,
    BOOTSTRAP_TEMPLATE_NAME,
    init_workspace,
    is_bootstrap_completed,
    render_workspace_templates,
)


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
    templates = render_workspace_templates()
    bootstrap_done = is_bootstrap_completed(root)
    if bootstrap_done:
        (root / BOOTSTRAP_TEMPLATE_NAME).unlink(missing_ok=True)
    for name, content in templates.items():
        if name == BOOTSTRAP_TEMPLATE_NAME and bootstrap_done:
            continue
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
        root / "MEMORY.md",
        _daily_file(root, now),
        _daily_file(root, yesterday),
    ]
    if not is_bootstrap_completed(root):
        files.append(root / BOOTSTRAP_TEMPLATE_NAME)

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


def auto_consolidate_session(
    session_id: str,
    *,
    reason: str = "session-end",
    path: str | None = None,
) -> dict[str, Any]:
    """Consolida memória ao término de sessão (ex.: comando /stop)."""
    sid = str(session_id or "").strip()
    if not sid:
        return {"ok": False, "reason": "missing-session-id"}

    rows = read_recent_session_messages(sid, limit=30)
    last_user = ""
    last_assistant = ""
    for row in rows:
        role = str(row.get("role", "")).strip().lower()
        text = str(row.get("text", "")).strip()
        if not text:
            continue
        if role == "user":
            last_user = text
        elif role == "assistant":
            last_assistant = text

    if rows:
        summary = (
            f"Sessão {sid} encerrada ({reason}). "
            f"Último pedido: {last_user[:220] or 'n/d'}. "
            f"Última resposta: {last_assistant[:220] or 'n/d'}."
        )
    else:
        summary = f"Sessão {sid} encerrada ({reason}). Sem histórico estruturado disponível."

    save_session_summary(summary, important=True, path=path)
    compact_result = compact_daily_memory(path=path)
    return {
        "ok": True,
        "session_id": sid,
        "reason": reason,
        "messages": len(rows),
        "summary": summary,
        "compact": compact_result,
    }


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
    boot = root / BOOTSTRAP_TEMPLATE_NAME
    marker = root / BOOTSTRAP_COMPLETED_MARKER
    if not boot.exists() or marker.exists():
        return ""
    text = boot.read_text(encoding="utf-8")[:3000]
    marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    boot.unlink(missing_ok=True)
    return text


def startup_context_text(path: str | None = None) -> str:
    ctx = startup_context(path)
    blocks = []
    for fp in ctx["files_loaded"]:
        content = ctx["context"][fp][:1200]
        blocks.append(f"[{Path(fp).name}]\n{content}")
    return "\n\n".join(blocks)


def read_recent_session_messages(session_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Lê histórico recente por sessão usando SessionStore unificado."""
    from clawlite.session.manager import SessionStore

    store = SessionStore()
    return store.recent(session_id, limit=limit)


def memory_hits_to_json(hits: list[MemoryHit]) -> str:
    return json.dumps([
        {"path": h.path, "score": h.score, "snippet": h.snippet} for h in hits
    ], ensure_ascii=False, indent=2)
