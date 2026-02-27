"""Task Tracker com aprendizado contínuo estilo Agent Lightning."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_DIR = Path.home() / ".clawlite"
DB_PATH = DB_DIR / "learning.db"
TEMPLATES_PATH = DB_DIR / "prompt_templates.json"

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    DB_DIR.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            prompt TEXT NOT NULL,
            result TEXT NOT NULL CHECK(result IN ('success','fail','partial')),
            duration_s REAL,
            model TEXT,
            tokens INTEGER DEFAULT 0,
            skill TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            retry_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    _conn.commit()
    return _conn


def _extract_keywords(text: str) -> list[str]:
    words = re.findall(r"[a-záàâãéêíóôõúçA-Z]{3,}", text.lower())
    stopwords = {"para", "com", "que", "uma", "por", "como", "mais", "isso", "esta", "este", "não"}
    return list(dict.fromkeys(w for w in words if w not in stopwords))[:20]


def record_task(
    prompt: str,
    result: str,
    duration_s: float = 0.0,
    model: str = "",
    tokens: int = 0,
    skill: str = "",
) -> str:
    conn = _get_conn()
    task_id = uuid.uuid4().hex[:12]
    keywords = json.dumps(_extract_keywords(prompt), ensure_ascii=False)
    conn.execute(
        "INSERT INTO tasks (id, prompt, result, duration_s, model, tokens, skill, keywords, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, prompt, result, duration_s, model, tokens, skill, keywords,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()

    if result == "success":
        _learn_template(prompt, skill)

    return task_id


def find_similar_tasks(prompt: str, limit: int = 5) -> list[dict[str, Any]]:
    conn = _get_conn()
    kw = _extract_keywords(prompt)
    if not kw:
        return []
    conditions = " OR ".join(["keywords LIKE ?"] * len(kw))
    params = [f"%{w}%" for w in kw]
    rows = conn.execute(
        f"SELECT * FROM tasks WHERE ({conditions}) ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


def get_retry_strategy(prompt: str, attempt: int) -> str | None:
    """Retorna prompt ajustado para retry (máx 3 tentativas)."""
    if attempt >= 3:
        return None
    similar = find_similar_tasks(prompt, limit=10)
    successful = [t for t in similar if t["result"] == "success"]

    strategies = [
        lambda p: f"Reformule e tente novamente: {p}",
        lambda p: f"Decomponha em passos menores: {p}",
        lambda p: f"Simplifique ao máximo: {p}",
    ]
    strategy = strategies[min(attempt, len(strategies) - 1)]
    adjusted = strategy(prompt)

    if successful:
        hint = successful[0]["prompt"][:200]
        adjusted += f"\n[Dica de task similar bem-sucedida: {hint}]"

    return adjusted


def get_stats(period: str = "all", skill: str | None = None) -> dict[str, Any]:
    conn = _get_conn()
    where_parts: list[str] = []
    params: list[Any] = []

    if period == "today":
        where_parts.append("date(created_at) = date('now')")
    elif period == "week":
        where_parts.append("created_at >= datetime('now', '-7 days')")
    elif period == "month":
        where_parts.append("created_at >= datetime('now', '-30 days')")

    if skill:
        where_parts.append("skill = ?")
        params.append(skill)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    row = conn.execute(
        f"SELECT COUNT(*) as total, "
        f"SUM(CASE WHEN result='success' THEN 1 ELSE 0 END) as successes, "
        f"AVG(duration_s) as avg_duration, "
        f"SUM(tokens) as total_tokens "
        f"FROM tasks {where}", params
    ).fetchone()

    total = row["total"] or 0
    successes = row["successes"] or 0

    # Top skills
    top_skills = conn.execute(
        f"SELECT skill, COUNT(*) as cnt FROM tasks {where} "
        f"AND skill != '' GROUP BY skill ORDER BY cnt DESC LIMIT 5"
        if where else
        "SELECT skill, COUNT(*) as cnt FROM tasks WHERE skill != '' GROUP BY skill ORDER BY cnt DESC LIMIT 5",
        params,
    ).fetchall()

    # Streak
    recent = conn.execute(
        "SELECT result FROM tasks ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    streak = 0
    for r in recent:
        if r["result"] == "success":
            streak += 1
        else:
            break

    return {
        "total_tasks": total,
        "successes": successes,
        "success_rate": round(successes / total * 100, 1) if total else 0.0,
        "avg_duration_s": round(row["avg_duration"] or 0, 2),
        "total_tokens": row["total_tokens"] or 0,
        "top_skills": [{"skill": s["skill"], "count": s["cnt"]} for s in top_skills],
        "streak": streak,
        "period": period,
    }


# --- Prompt Auto-Improvement ---

def _load_templates() -> dict[str, list[dict[str, Any]]]:
    if TEMPLATES_PATH.exists():
        try:
            return json.loads(TEMPLATES_PATH.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_templates(data: dict[str, list[dict[str, Any]]]) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _learn_template(prompt: str, skill: str) -> None:
    category = skill or "geral"
    templates = _load_templates()
    entries = templates.setdefault(category, [])
    # Dedupe by hash
    h = hashlib.md5(prompt.encode()).hexdigest()[:8]
    if any(e.get("hash") == h for e in entries):
        return
    entries.append({
        "hash": h,
        "prompt_snippet": prompt[:300],
        "learned_at": datetime.now(timezone.utc).isoformat(),
    })
    # Keep max 20 per category
    templates[category] = entries[-20:]
    _save_templates(templates)


def get_templates(category: str | None = None) -> dict[str, list[dict[str, Any]]]:
    data = _load_templates()
    if category:
        return {category: data.get(category, [])}
    return data
