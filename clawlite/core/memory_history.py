from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable


def stored_history_payload(
    *,
    record: Any,
    encrypt_text_for_category: Callable[[str, str], str],
) -> dict[str, Any]:
    payload = asdict(record)
    payload["text"] = encrypt_text_for_category(str(getattr(record, "text", "") or ""), getattr(record, "category", "context"))
    return payload


def read_history_records_from(
    *,
    history_path: Path,
    locked_file: Callable[..., Any],
    record_from_payload: Callable[[dict[str, Any]], Any | None],
    decrypt_text_for_category: Callable[[str, str], str],
) -> list[Any]:
    out: list[Any] = []
    with locked_file(history_path, "r", exclusive=False) as fh:
        lines = fh.read().splitlines()
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        row = record_from_payload(payload)
        if row is None:
            continue
        row.text = decrypt_text_for_category(str(getattr(row, "text", "") or ""), getattr(row, "category", "context"))
        out.append(row)
    return out


def repair_history_file(
    *,
    history_path: Path,
    valid_lines: list[str],
    atomic_write_text_locked: Callable[[Path, str], None],
    diagnostics: dict[str, Any],
) -> None:
    try:
        rewritten = "\n".join(valid_lines)
        if rewritten:
            rewritten = f"{rewritten}\n"
        atomic_write_text_locked(history_path, rewritten)
        diagnostics["history_repaired_files"] = int(diagnostics.get("history_repaired_files", 0) or 0) + 1
        diagnostics["last_error"] = ""
    except Exception as exc:
        diagnostics["last_error"] = str(exc)


def read_history_records(
    *,
    history_path: Path,
    locked_file: Callable[..., Any],
    record_from_payload: Callable[[dict[str, Any]], Any | None],
    decrypt_text_for_category: Callable[[str, str], str],
    repair_history_file_fn: Callable[[list[str]], None],
    diagnostics: dict[str, Any],
) -> list[Any]:
    out: list[Any] = []
    valid_lines: list[str] = []
    corrupt_lines = 0
    with locked_file(history_path, "r", exclusive=False) as fh:
        lines = fh.read().splitlines()
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            corrupt_lines += 1
            continue
        if not isinstance(payload, dict):
            corrupt_lines += 1
            continue
        valid_lines.append(raw)
        row = record_from_payload(payload)
        if row is None:
            continue
        row.text = decrypt_text_for_category(str(getattr(row, "text", "") or ""), getattr(row, "category", "context"))
        out.append(row)

    if corrupt_lines:
        diagnostics["history_read_corrupt_lines"] = int(diagnostics.get("history_read_corrupt_lines", 0) or 0) + corrupt_lines
        repair_history_file_fn(valid_lines)

    return out


def append_or_reinforce_history_record(
    *,
    history_path: Path,
    record: Any,
    content_hash: str,
    scope_key: str,
    source: str,
    reinforced_at: str,
    ensure_file: Callable[[Path], None],
    locked_file: Callable[..., Any],
    flush_and_fsync: Callable[[Any], None],
    record_from_payload: Callable[[dict[str, Any]], Any | None],
    decrypt_text_for_category: Callable[[str, str], str],
    record_content_hash: Callable[[Any], str],
    record_scope_key: Callable[[Any], str],
    reinforce_record: Callable[..., Any],
    stored_history_payload_fn: Callable[[Any], dict[str, Any]],
) -> tuple[Any, bool]:
    ensure_file(history_path)
    with locked_file(history_path, "r+", exclusive=True) as fh:
        lines = fh.read().splitlines()
        rewritten_lines: list[str] = []
        reinforced_row: Any | None = None

        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                rewritten_lines.append(raw)
                continue
            if not isinstance(payload, dict):
                rewritten_lines.append(raw)
                continue
            candidate = record_from_payload(payload)
            if candidate is None:
                rewritten_lines.append(raw)
                continue
            candidate.text = decrypt_text_for_category(str(getattr(candidate, "text", "") or ""), getattr(candidate, "category", "context"))
            candidate_hash = record_content_hash(candidate)
            if reinforced_row is None and candidate_hash == content_hash and record_scope_key(candidate) == scope_key:
                reinforced_row = reinforce_record(
                    candidate,
                    record,
                    source=source,
                    scope_key=scope_key,
                    reinforced_at=reinforced_at,
                )
                rewritten_lines.append(json.dumps(stored_history_payload_fn(reinforced_row), ensure_ascii=False))
                continue
            rewritten_lines.append(raw)

        if reinforced_row is None:
            fh.seek(0, 2)
            fh.write(json.dumps(stored_history_payload_fn(record), ensure_ascii=False) + "\n")
            flush_and_fsync(fh)
            return record, True

        fh.seek(0)
        fh.truncate()
        if rewritten_lines:
            fh.write("\n".join(rewritten_lines) + "\n")
        flush_and_fsync(fh)
        return reinforced_row, False


def upsert_history_record_by_id(
    *,
    history_path: Path,
    record: Any,
    append_if_missing: bool,
    ensure_file: Callable[[Path], None],
    locked_file: Callable[..., Any],
    flush_and_fsync: Callable[[Any], None],
    stored_history_payload_fn: Callable[[Any], dict[str, Any]],
) -> bool:
    ensure_file(history_path)
    stored_payload = stored_history_payload_fn(record)
    with locked_file(history_path, "r+", exclusive=True) as fh:
        lines = fh.read().splitlines()
        rewritten_lines: list[str] = []
        found = False

        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                rewritten_lines.append(raw)
                continue
            if not isinstance(payload, dict):
                rewritten_lines.append(raw)
                continue
            if str(payload.get("id", "")).strip() == getattr(record, "id", ""):
                rewritten_lines.append(json.dumps(stored_payload, ensure_ascii=False))
                found = True
                continue
            rewritten_lines.append(raw)

        if not found and append_if_missing:
            fh.seek(0, 2)
            fh.write(json.dumps(stored_payload, ensure_ascii=False) + "\n")
            flush_and_fsync(fh)
            return True

        if not found:
            return False

        fh.seek(0)
        fh.truncate()
        if rewritten_lines:
            fh.write("\n".join(rewritten_lines) + "\n")
        flush_and_fsync(fh)
        return True


__all__ = [
    "append_or_reinforce_history_record",
    "read_history_records",
    "read_history_records_from",
    "repair_history_file",
    "stored_history_payload",
    "upsert_history_record_by_id",
]
