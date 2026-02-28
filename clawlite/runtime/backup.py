from __future__ import annotations

import tarfile
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawlite.config import settings as app_settings


class BackupError(RuntimeError):
    """Erro no fluxo de backup/restore."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _config_dir() -> Path:
    return Path(app_settings.CONFIG_DIR)


def _backup_dir() -> Path:
    return _config_dir() / "backups"


def _collect_sources(config_dir: Path) -> list[Path]:
    sources: list[Path] = []

    for filename in ("config.json", "mcp.json", "pairing.json", "dashboard_settings.json"):
        candidate = config_dir / filename
        if candidate.exists():
            sources.append(candidate)

    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        for db_file in sorted(config_dir.glob(pattern)):
            if db_file.is_file():
                sources.append(db_file)

    workspace = config_dir / "workspace"
    if workspace.exists() and workspace.is_dir():
        sources.append(workspace)

    dashboard = config_dir / "dashboard"
    if dashboard.exists() and dashboard.is_dir():
        sources.append(dashboard)

    return sources


def create_backup(*, label: str = "manual", keep_last: int = 7) -> dict[str, Any]:
    backup_dir = _backup_dir()
    config_dir = _config_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(ch for ch in str(label or "manual").strip().lower() if ch.isalnum() or ch in {"-", "_"})
    if not safe_label:
        safe_label = "manual"

    archive = backup_dir / f"clawlite_backup_{_timestamp()}_{safe_label}.tar.gz"
    sources = _collect_sources(config_dir)
    if not sources:
        raise BackupError(f"Nenhuma fonte crítica encontrada em {config_dir}")

    with tarfile.open(archive, mode="w:gz") as tar:
        for src in sources:
            tar.add(src, arcname=src.name)

    # retenção simples dos mais recentes
    if keep_last > 0:
        all_archives = sorted(backup_dir.glob("clawlite_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in all_archives[keep_last:]:
            old.unlink(missing_ok=True)

    return {
        "ok": True,
        "archive": str(archive),
        "entries": [src.name for src in sources],
        "size_bytes": archive.stat().st_size,
    }


def list_backups() -> list[dict[str, Any]]:
    backup_dir = _backup_dir()
    if not backup_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for archive in sorted(backup_dir.glob("clawlite_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = archive.stat()
        rows.append(
            {
                "path": str(archive),
                "name": archive.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return rows


def _safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    safe: list[tarfile.TarInfo] = []
    for member in tar.getmembers():
        name = member.name
        if not name or name.startswith("/") or ".." in Path(name).parts:
            continue
        safe.append(member)
    return safe


def restore_backup(archive_path: str) -> dict[str, Any]:
    archive = Path(archive_path).expanduser()
    if not archive.exists() or not archive.is_file():
        raise BackupError(f"Arquivo de backup não encontrado: {archive}")

    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:gz") as tar:
        members = _safe_members(tar)
        if not members:
            raise BackupError("Backup sem entradas válidas para restaurar.")
        extract_kwargs: dict[str, Any] = {}
        try:
            if "filter" in inspect.signature(tar.extractall).parameters:
                extract_kwargs["filter"] = "data"
        except (TypeError, ValueError):
            extract_kwargs = {}
        tar.extractall(path=config_dir, members=members, **extract_kwargs)

    return {
        "ok": True,
        "archive": str(archive),
        "restored_entries": [member.name for member in members],
        "target_dir": str(config_dir),
    }
