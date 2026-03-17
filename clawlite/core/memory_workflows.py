from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable


def ingest_file(
    *,
    path: str,
    source: str,
    resource_id: str | None,
    add_record: Callable[..., Any],
) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"ok": False, "modality": "", "record_id": "", "reason": "file not found"}

    suffix = target.suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            text = target.read_text(encoding="utf-8", errors="replace").strip()
        except Exception as exc:
            return {"ok": False, "modality": "text", "record_id": "", "reason": str(exc)}
        if not text:
            return {"ok": False, "modality": "text", "record_id": "", "reason": "empty file"}
        record = add_record(text, source=source, modality="text", resource_id=resource_id)
        return {"ok": True, "modality": "text", "record_id": str(getattr(record, "id", "")), "reason": ""}

    if suffix == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(str(target))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages).strip()
        except ImportError:
            return {
                "ok": False,
                "modality": "document",
                "record_id": "",
                "reason": 'pdf read error: pypdf not installed. Run: pip install "clawlite[media]"',
            }
        except Exception as exc:
            return {"ok": False, "modality": "document", "record_id": "", "reason": f"pdf read error: {exc}"}
        if not text:
            return {"ok": False, "modality": "document", "record_id": "", "reason": "pdf has no extractable text"}
        record = add_record(text, source=source, modality="document", resource_id=resource_id)
        return {"ok": True, "modality": "document", "record_id": str(getattr(record, "id", "")), "reason": ""}

    return {"ok": False, "modality": "", "record_id": "", "reason": f"unsupported file type: {suffix}"}


def consolidate_in_scope(
    *,
    scope: dict[str, Path],
    messages: Iterable[dict[str, str]],
    source: str,
    user_id: str,
    shared: bool,
    metadata: dict[str, Any] | None,
    reasoning_layer: str | None,
    confidence: float | None,
    memory_type: str | None,
    happened_at: str | None,
    decay_rate: float | None,
    ensure_scope_paths: Callable[[dict[str, Path]], None],
    consolidate_messages: Callable[..., Any],
    read_curated_facts_from: Callable[[Path], list[dict[str, object]]],
    write_curated_facts_to: Callable[[Path, list[dict[str, object]]], None],
    add_record: Callable[..., Any],
) -> Any | None:
    ensure_scope_paths(scope)
    return consolidate_messages(
        messages,
        source=source,
        metadata=metadata,
        reasoning_layer=reasoning_layer,
        confidence=confidence,
        memory_type=memory_type,
        happened_at=happened_at,
        decay_rate=decay_rate,
        checkpoints_path=scope["checkpoints"],
        add_record=lambda summary, resource_text: add_record(
            summary,
            source=source,
            raw_resource_text=resource_text,
            user_id=user_id,
            shared=shared,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
        ),
        read_curated_facts=lambda: read_curated_facts_from(scope["curated"]),
        write_curated_facts=lambda facts: write_curated_facts_to(scope["curated"], facts),
    )


def consolidate(
    *,
    messages: Iterable[dict[str, str]],
    source: str,
    user_id: str,
    shared: bool,
    metadata: dict[str, Any] | None,
    reasoning_layer: str | None,
    confidence: float | None,
    memory_type: str | None,
    happened_at: str | None,
    decay_rate: float | None,
    normalize_user_id: Callable[[str], str],
    scope_paths: Callable[..., dict[str, Path]],
    consolidate_in_scope_fn: Callable[..., Any | None],
    consolidate_messages: Callable[..., Any | None],
    checkpoints_path: Path,
    read_curated_facts: Callable[[], list[dict[str, object]]],
    write_curated_facts: Callable[[list[dict[str, object]]], None],
    add_record: Callable[..., Any],
    max_checkpoint_sources: int,
    max_checkpoint_signatures: int,
) -> Any | None:
    clean_user = normalize_user_id(user_id)
    if shared or clean_user != "default":
        scope = scope_paths(user_id=clean_user, shared=shared)
        return consolidate_in_scope_fn(
            scope=scope,
            messages=messages,
            source=source,
            user_id=clean_user,
            shared=shared,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
        )
    return consolidate_messages(
        messages,
        source=source,
        metadata=metadata,
        reasoning_layer=reasoning_layer,
        confidence=confidence,
        memory_type=memory_type,
        happened_at=happened_at,
        decay_rate=decay_rate,
        checkpoints_path=checkpoints_path,
        add_record=lambda summary, resource_text: add_record(
            summary,
            source=source,
            raw_resource_text=resource_text,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
        ),
        read_curated_facts=read_curated_facts,
        write_curated_facts=write_curated_facts,
        max_checkpoint_sources=max_checkpoint_sources,
        max_checkpoint_signatures=max_checkpoint_signatures,
    )


async def memorize(
    *,
    text: str | None,
    messages: Iterable[dict[str, str]] | None,
    source: str,
    user_id: str,
    shared: bool,
    include_shared: bool,
    file_path: str | None,
    url: str | None,
    modality: str,
    metadata: dict[str, Any] | None,
    reasoning_layer: str | None,
    confidence: float | None,
    memory_type: str | None,
    happened_at: str | None,
    decay_rate: float | None,
    cleanup_expired_ephemeral_records: Callable[[], int],
    diagnostics: dict[str, Any],
    privacy_block_reason: Callable[[str], str | None],
    append_privacy_audit_event: Callable[..., None],
    consolidate_fn: Callable[..., Any | None],
    add_fn: Callable[..., Any],
    memory_text_from_file: Callable[..., str],
    memory_text_from_url: Callable[..., str],
) -> dict[str, Any]:
    del include_shared
    try:
        await asyncio.to_thread(cleanup_expired_ephemeral_records)
    except Exception as exc:
        diagnostics["last_error"] = str(exc)

    if messages is not None:
        joined_text = "\n".join(str(item.get("content", "") or "") for item in messages if isinstance(item, dict))
        blocked_reason = privacy_block_reason(joined_text) if joined_text else None
        if blocked_reason is not None:
            append_privacy_audit_event(
                action="memorize_skipped",
                reason=blocked_reason,
                source=source,
                metadata={"mode": "consolidate"},
            )
            return {"status": "skipped", "mode": "consolidate", "record": None}
        record = await asyncio.to_thread(
            consolidate_fn,
            messages,
            source=source,
            user_id=user_id,
            shared=shared,
            metadata=metadata,
            reasoning_layer=reasoning_layer,
            confidence=confidence,
            memory_type=memory_type,
            happened_at=happened_at,
            decay_rate=decay_rate,
        )
        if record is None:
            return {"status": "skipped", "mode": "consolidate", "record": None}
        return {"status": "ok", "mode": "consolidate", "record": asdict(record)}

    resolved_modality = str(modality or "text").strip().lower() or "text"
    clean = str(text or "").strip()
    if not clean and file_path:
        clean = await asyncio.to_thread(
            memory_text_from_file,
            file_path,
            modality=resolved_modality,
            metadata=metadata,
        )
    if not clean and url:
        clean = await asyncio.to_thread(
            memory_text_from_url,
            url,
            modality=resolved_modality,
            metadata=metadata,
        )
    if not clean:
        raise ValueError("text or messages is required")
    blocked_reason = privacy_block_reason(clean)
    if blocked_reason is not None:
        append_privacy_audit_event(
            action="memorize_skipped",
            reason=blocked_reason,
            source=source,
            metadata={"mode": "add"},
        )
        return {"status": "skipped", "mode": "add", "record": None}
    record = await asyncio.to_thread(
        add_fn,
        clean,
        source=source,
        user_id=user_id,
        shared=shared,
        modality=resolved_modality,
        metadata=metadata,
        reasoning_layer=reasoning_layer,
        confidence=confidence,
        memory_type=memory_type,
        happened_at=happened_at,
        decay_rate=decay_rate,
    )
    return {"status": "ok", "mode": "add", "record": asdict(record)}


__all__ = [
    "consolidate",
    "consolidate_in_scope",
    "ingest_file",
    "memorize",
]
