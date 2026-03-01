from __future__ import annotations

from pathlib import Path

from clawlite.runtime.session_memory import (
    auto_consolidate_session,
    append_daily_log,
    compact_daily_memory,
    ensure_memory_layout,
    semantic_search_memory,
    startup_context,
)


def test_memory_layout_contains_identity(tmp_path: Path):
    root = ensure_memory_layout(str(tmp_path))
    assert (root / "AGENTS.md").exists()
    assert (root / "SOUL.md").exists()
    assert (root / "USER.md").exists()
    assert (root / "IDENTITY.md").exists()
    assert (root / "MEMORY.md").exists()


def test_append_and_search_semantic(tmp_path: Path):
    root = ensure_memory_layout(str(tmp_path))
    append_daily_log("Usuário prefere respostas curtas", path=str(root))
    hits = semantic_search_memory("prefere respostas", path=str(root))
    assert hits
    assert "respostas" in hits[0].snippet.lower()


def test_compact_keeps_recent_files(tmp_path: Path):
    root = ensure_memory_layout(str(tmp_path))
    mem = root / "memory"
    for i in range(25):
        p = mem / f"2026-01-{i+1:02d}.md"
        p.write_text("# day\n- evento\n", encoding="utf-8")
    result = compact_daily_memory(max_daily_files=21, path=str(root))
    assert result["compacted"] == 4


def test_startup_context_loads_core_files(tmp_path: Path):
    root = ensure_memory_layout(str(tmp_path))
    ctx = startup_context(str(root))
    loaded = "\n".join(ctx["files_loaded"])
    assert "AGENTS.md" in loaded
    assert "MEMORY.md" in loaded


def test_auto_consolidate_session_generates_summary(tmp_path: Path, monkeypatch):
    root = ensure_memory_layout(str(tmp_path))

    monkeypatch.setattr(
        "clawlite.runtime.session_memory.read_recent_session_messages",
        lambda session_id, limit=20: [
            {"session_id": session_id, "role": "user", "text": "Me lembra de revisar o deploy."},
            {"session_id": session_id, "role": "assistant", "text": "Claro, vou monitorar isso."},
        ],
    )

    result = auto_consolidate_session("sessao-1", reason="stop-command", path=str(root))
    assert result["ok"] is True
    assert result["session_id"] == "sessao-1"
    assert "Sessão sessao-1 encerrada" in result["summary"]

    memory_text = (root / "MEMORY.md").read_text(encoding="utf-8")
    assert "sessao-1" in memory_text


def test_auto_consolidate_session_requires_id() -> None:
    result = auto_consolidate_session("")
    assert result["ok"] is False
