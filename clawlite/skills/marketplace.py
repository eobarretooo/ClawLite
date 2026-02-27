from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
from urllib.request import urlopen

DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/eobarretooo/ClawLite/main/hub/marketplace/manifest.local.json"
DEFAULT_DOWNLOAD_BASE_URL = "https://raw.githubusercontent.com/eobarretooo/ClawLite/main/hub/marketplace/packages"
DEFAULT_ALLOWED_HOSTS = frozenset({
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
})
LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1"})
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MARKETPLACE_DIR = Path.home() / ".clawlite" / "marketplace"
INSTALLED_MANIFEST_PATH = MARKETPLACE_DIR / "installed.json"
INSTALLED_SKILLS_DIR = MARKETPLACE_DIR / "skills"
SYSTEM_AUTO_UPDATE_CHANNEL = "system"
SYSTEM_AUTO_UPDATE_CHAT = "local"
SYSTEM_AUTO_UPDATE_LABEL = "skills"
SYSTEM_AUTO_UPDATE_NAME = "auto-update"


class SkillMarketplaceError(RuntimeError):
    """Raised when marketplace operations fail safely."""


def _normalize_slug(value: str) -> str:
    slug = value.strip().lower()
    if not slug or not SLUG_RE.fullmatch(slug):
        raise SkillMarketplaceError(f"Slug inválido: {value!r}")
    return slug


def _normalize_version(value: str) -> str:
    version = value.strip()
    if not version or not VERSION_RE.fullmatch(version):
        raise SkillMarketplaceError(f"Versão inválida: {value!r}")
    return version


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_allowed_hosts(extra_hosts: Iterable[str] | None = None) -> set[str]:
    hosts = {h.lower() for h in DEFAULT_ALLOWED_HOSTS}
    for host in extra_hosts or ():
        h = host.strip().lower()
        if h:
            hosts.add(h)
    return hosts


def _is_allowed_url(url: str, allowed_hosts: set[str], allow_file_urls: bool) -> None:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()

    if scheme == "file":
        if not allow_file_urls:
            raise SkillMarketplaceError("URLs file:// estão desabilitadas por segurança")
        return

    if scheme not in {"https", "http"}:
        raise SkillMarketplaceError(f"Esquema de URL não suportado: {scheme or 'vazio'}")

    if host not in allowed_hosts:
        raise SkillMarketplaceError(f"Host fora da allowlist: {host or 'vazio'}")

    if scheme == "http" and host not in LOCALHOST_HOSTS:
        raise SkillMarketplaceError("HTTP sem TLS só é permitido para localhost/127.0.0.1")


def _download_bytes(url: str, timeout_seconds: int = 20) -> bytes:
    with urlopen(url, timeout=timeout_seconds) as response:  # nosec: allowlisted URL validated before call
        return response.read()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _version_key(version: str) -> tuple[Any, ...]:
    parts = re.split(r"[.\-+_]", version)
    key: list[Any] = []
    for part in parts:
        if part.isdigit():
            key.append((1, int(part)))
        else:
            key.append((0, part))
    return tuple(key)


def _safe_extract_zip(archive_data: bytes, destination: Path) -> None:
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(archive_data)) as zf:
        for member in zf.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise SkillMarketplaceError(f"Arquivo inseguro no pacote: {member.filename}")

            out_path = (destination / member_path).resolve()
            try:
                out_path.relative_to(destination)
            except ValueError as exc:
                raise SkillMarketplaceError(f"Path traversal detectado: {member.filename}") from exc

            if member.is_dir():
                out_path.mkdir(parents=True, exist_ok=True)
                continue

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, out_path.open("wb") as target:
                shutil.copyfileobj(source, target)


def _default_installed_manifest() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "updated_at": _utcnow_iso(),
        "skills": {},
    }


def load_installed_manifest(manifest_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path) if manifest_path else INSTALLED_MANIFEST_PATH
    if not path.exists():
        return _default_installed_manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("skills"), dict):
        data["skills"] = {}
    return data


def save_installed_manifest(data: dict[str, Any], manifest_path: str | Path | None = None) -> Path:
    path = Path(manifest_path) if manifest_path else INSTALLED_MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utcnow_iso()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _default_hub_manifest() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at": _utcnow_iso(),
        "allow_hosts": sorted(DEFAULT_ALLOWED_HOSTS),
        "skills": [],
    }


def load_hub_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    if not path.exists():
        return _default_hub_manifest()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("skills"), list):
        raise SkillMarketplaceError("Manifesto do hub inválido: 'skills' deve ser lista")
    return data


def _save_hub_manifest(data: dict[str, Any], manifest_path: str | Path) -> Path:
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["generated_at"] = _utcnow_iso()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _remote_entry(slug: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": slug,
        "version": str(item.get("version", "")).strip(),
        "checksum_sha256": str(item.get("checksum_sha256", "")).strip().lower(),
        "download_url": str(item.get("download_url", "")).strip(),
        "description": str(item.get("description", "")).strip(),
    }


def _load_remote_index(
    index_url: str,
    allowed_hosts: set[str],
    allow_file_urls: bool,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    _is_allowed_url(index_url, allowed_hosts, allow_file_urls)
    payload = _download_bytes(index_url)
    index_raw = json.loads(payload.decode("utf-8"))
    skills = index_raw.get("skills", [])
    if not isinstance(skills, list):
        raise SkillMarketplaceError("Índice remoto inválido: 'skills' deve ser lista")

    entries: dict[str, dict[str, Any]] = {}
    invalid_reasons: dict[str, str] = {}
    for item in skills:
        if not isinstance(item, dict):
            continue
        try:
            slug = _normalize_slug(str(item.get("slug", "")))
            version = _normalize_version(str(item.get("version", "")))
        except SkillMarketplaceError:
            continue

        entry = _remote_entry(slug, item)
        entry["version"] = version
        checksum = entry["checksum_sha256"]
        download_url = entry["download_url"]

        if not download_url:
            invalid_reasons[slug] = "missing-download-url"
        elif not checksum:
            invalid_reasons[slug] = "missing-checksum"
        elif not SHA256_RE.fullmatch(checksum):
            invalid_reasons[slug] = "invalid-checksum-format"

        entries[slug] = entry
    return index_raw, entries, invalid_reasons


def _install_entry(
    entry: dict[str, Any],
    *,
    source_index_url: str,
    allowed_hosts: set[str],
    install_dir: Path,
    manifest_path: Path,
    force: bool,
    allow_file_urls: bool,
) -> dict[str, Any]:
    slug = _normalize_slug(str(entry["slug"]))
    version = _normalize_version(str(entry["version"]))
    checksum_expected = str(entry["checksum_sha256"]).strip().lower()
    download_url = str(entry["download_url"]).strip()

    if not SHA256_RE.fullmatch(checksum_expected):
        raise SkillMarketplaceError(f"Checksum inválido no índice para {slug}")

    _is_allowed_url(download_url, allowed_hosts, allow_file_urls)
    archive_data = _download_bytes(download_url)
    checksum_got = _sha256_bytes(archive_data)
    if checksum_got != checksum_expected:
        raise SkillMarketplaceError(
            f"Checksum inválido para {slug}: esperado {checksum_expected}, recebido {checksum_got}"
        )

    install_dir.mkdir(parents=True, exist_ok=True)
    skill_dir = install_dir / slug
    backup_dir: Path | None = None

    if skill_dir.exists():
        if not force:
            raise SkillMarketplaceError(f"Skill '{slug}' já instalada. Use --force para sobrescrever")
        backup_dir = install_dir / f".{slug}.backup-{int(datetime.now(timezone.utc).timestamp())}"
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.move(str(skill_dir), str(backup_dir))

    try:
        _safe_extract_zip(archive_data, skill_dir)
        skill_doc = skill_dir / "SKILL.md"
        if not skill_doc.exists():
            raise SkillMarketplaceError("Pacote inválido: SKILL.md não encontrado na raiz")
    except Exception as exc:
        shutil.rmtree(skill_dir, ignore_errors=True)
        if backup_dir and backup_dir.exists():
            shutil.move(str(backup_dir), str(skill_dir))
        raise SkillMarketplaceError(f"Falha na instalação de {slug}: {exc}") from exc
    finally:
        if backup_dir and backup_dir.exists() and skill_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

    installed_manifest = load_installed_manifest(manifest_path)
    installed_manifest.setdefault("skills", {})[slug] = {
        "slug": slug,
        "version": version,
        "description": entry.get("description", ""),
        "checksum_sha256": checksum_expected,
        "index_url": source_index_url,
        "download_url": download_url,
        "install_path": str(skill_dir),
        "installed_at": _utcnow_iso(),
    }
    save_installed_manifest(installed_manifest, manifest_path)

    return {
        "slug": slug,
        "version": version,
        "install_path": str(skill_dir),
        "checksum_sha256": checksum_expected,
    }


def install_skill(
    slug: str,
    *,
    index_url: str = DEFAULT_INDEX_URL,
    allow_hosts: Iterable[str] | None = None,
    install_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    force: bool = False,
    allow_file_urls: bool = False,
) -> dict[str, Any]:
    slug = _normalize_slug(slug)
    allowed_hosts = _normalize_allowed_hosts(allow_hosts)
    target_install_dir = Path(install_dir) if install_dir else INSTALLED_SKILLS_DIR
    target_manifest = Path(manifest_path) if manifest_path else INSTALLED_MANIFEST_PATH

    _, entries, invalid_reasons = _load_remote_index(index_url, allowed_hosts, allow_file_urls)
    if slug not in entries:
        raise SkillMarketplaceError(f"Skill '{slug}' não encontrada no índice remoto")
    if slug in invalid_reasons:
        raise SkillMarketplaceError(f"Skill '{slug}' bloqueada: {invalid_reasons[slug]}")

    return _install_entry(
        entries[slug],
        source_index_url=index_url,
        allowed_hosts=allowed_hosts,
        install_dir=target_install_dir,
        manifest_path=target_manifest,
        force=force,
        allow_file_urls=allow_file_urls,
    )


def update_skills(
    *,
    index_url: str = DEFAULT_INDEX_URL,
    allow_hosts: Iterable[str] | None = None,
    install_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    slugs: Iterable[str] | None = None,
    force: bool = False,
    dry_run: bool = False,
    allow_file_urls: bool = False,
    strict: bool = False,
) -> dict[str, Any]:
    allowed_hosts = _normalize_allowed_hosts(allow_hosts)
    target_install_dir = Path(install_dir) if install_dir else INSTALLED_SKILLS_DIR
    target_manifest = Path(manifest_path) if manifest_path else INSTALLED_MANIFEST_PATH

    installed = load_installed_manifest(target_manifest).get("skills", {})
    wanted: set[str] = set()
    if slugs:
        for slug in slugs:
            wanted.add(_normalize_slug(str(slug)))
    else:
        for slug in installed.keys():
            try:
                wanted.add(_normalize_slug(str(slug)))
            except SkillMarketplaceError:
                continue

    if not wanted:
        return {"updated": [], "skipped": [], "blocked": [], "missing": []}

    _, entries, invalid_reasons = _load_remote_index(index_url, allowed_hosts, allow_file_urls)

    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    missing: list[str] = []

    for slug in sorted(wanted):
        current = installed.get(slug)
        remote = entries.get(slug)

        if current is None:
            missing.append(slug)
            continue

        if remote is None:
            skipped.append({"slug": slug, "reason": "not-in-index"})
            continue

        if slug in invalid_reasons:
            reason = invalid_reasons[slug]
            if strict:
                blocked.append({"slug": slug, "reason": reason})
            else:
                skipped.append({"slug": slug, "reason": reason})
            continue

        try:
            _is_allowed_url(remote["download_url"], allowed_hosts, allow_file_urls)
        except SkillMarketplaceError as exc:
            blocked.append({"slug": slug, "reason": f"trust-policy:{exc}"})
            continue

        current_version = str(current.get("version", "0"))
        current_checksum = str(current.get("checksum_sha256", "")).lower()
        needs_update = (
            force
            or _version_key(remote["version"]) > _version_key(current_version)
            or remote["checksum_sha256"] != current_checksum
        )

        if not needs_update:
            skipped.append({"slug": slug, "reason": "up-to-date"})
            continue

        if dry_run:
            updated.append({
                "slug": slug,
                "from_version": current_version,
                "to_version": remote["version"],
                "dry_run": True,
            })
            continue

        try:
            result = _install_entry(
                remote,
                source_index_url=index_url,
                allowed_hosts=allowed_hosts,
                install_dir=target_install_dir,
                manifest_path=target_manifest,
                force=True,
                allow_file_urls=allow_file_urls,
            )
            result["from_version"] = current_version
            updated.append(result)
        except SkillMarketplaceError as exc:
            blocked.append({"slug": slug, "reason": f"install-failed:{exc}"})

    return {
        "updated": updated,
        "skipped": skipped,
        "blocked": blocked,
        "missing": missing,
    }


def build_auto_update_runtime_payload(
    *,
    index_url: str,
    strict: bool,
    allow_hosts: Iterable[str] | None,
    manifest_path: str | None,
    install_dir: str | None,
    allow_file_urls: bool,
) -> str:
    payload = {
        "action": "skill-auto-update",
        "index_url": index_url,
        "strict": strict,
        "allow_hosts": sorted(set(allow_hosts or [])),
        "manifest_path": manifest_path,
        "install_dir": install_dir,
        "allow_file_urls": allow_file_urls,
    }
    return json.dumps(payload, ensure_ascii=False)


def schedule_auto_update(
    *,
    every_seconds: int,
    index_url: str = DEFAULT_INDEX_URL,
    strict: bool = False,
    allow_hosts: Iterable[str] | None = None,
    manifest_path: str | None = None,
    install_dir: str | None = None,
    allow_file_urls: bool = False,
    enabled: bool = True,
) -> int:
    from clawlite.runtime.conversation_cron import add_cron_job

    return add_cron_job(
        channel=SYSTEM_AUTO_UPDATE_CHANNEL,
        chat_id=SYSTEM_AUTO_UPDATE_CHAT,
        thread_id="",
        label=SYSTEM_AUTO_UPDATE_LABEL,
        name=SYSTEM_AUTO_UPDATE_NAME,
        text=build_auto_update_runtime_payload(
            index_url=index_url,
            strict=strict,
            allow_hosts=allow_hosts,
            manifest_path=manifest_path,
            install_dir=install_dir,
            allow_file_urls=allow_file_urls,
        ),
        interval_seconds=every_seconds,
        enabled=enabled,
    )


def run_runtime_auto_update(payload_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise SkillMarketplaceError(f"Payload inválido de auto-update: {exc}") from exc

    if payload.get("action") != "skill-auto-update":
        raise SkillMarketplaceError("Ação de runtime desconhecida para auto-update")

    return update_skills(
        index_url=str(payload.get("index_url") or DEFAULT_INDEX_URL),
        allow_hosts=payload.get("allow_hosts") or [],
        install_dir=payload.get("install_dir") or None,
        manifest_path=payload.get("manifest_path") or None,
        strict=bool(payload.get("strict", False)),
        dry_run=False,
        allow_file_urls=bool(payload.get("allow_file_urls", False)),
    )


def publish_skill(
    source_dir: str | Path,
    *,
    version: str,
    slug: str | None = None,
    description: str = "",
    hub_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    download_base_url: str = DEFAULT_DOWNLOAD_BASE_URL,
) -> dict[str, Any]:
    source_path = Path(source_dir).expanduser().resolve()
    if not source_path.exists() or not source_path.is_dir():
        raise SkillMarketplaceError(f"Diretório de skill inválido: {source_path}")
    if not (source_path / "SKILL.md").exists():
        raise SkillMarketplaceError("Publicação exige arquivo SKILL.md na raiz da skill")

    resolved_slug = _normalize_slug(slug or source_path.name)
    resolved_version = _normalize_version(version)

    hub_root = Path(hub_dir).expanduser().resolve() if hub_dir else (Path.cwd() / "hub" / "marketplace").resolve()
    packages_dir = hub_root / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    package_name = f"{resolved_slug}-{resolved_version}.zip"
    package_path = packages_dir / package_name
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(source_path.rglob("*")):
            if file_path.is_dir():
                continue
            arc_name = file_path.relative_to(source_path).as_posix()
            archive.write(file_path, arcname=arc_name)

    package_bytes = package_path.read_bytes()
    checksum = _sha256_bytes(package_bytes)

    target_manifest = (
        Path(manifest_path).expanduser().resolve() if manifest_path else hub_root / "manifest.local.json"
    )
    hub_manifest = load_hub_manifest(target_manifest)
    skills = [item for item in hub_manifest.get("skills", []) if isinstance(item, dict)]

    download_url = f"{download_base_url.rstrip('/')}/{package_name}"
    entry = {
        "slug": resolved_slug,
        "version": resolved_version,
        "description": description,
        "download_url": download_url,
        "checksum_sha256": checksum,
        "package_file": (
            str(package_path.relative_to(target_manifest.parent))
            if package_path.is_relative_to(target_manifest.parent)
            else str(package_path)
        ),
    }

    replaced = False
    for idx, item in enumerate(skills):
        if str(item.get("slug", "")).strip() == resolved_slug:
            skills[idx] = entry
            replaced = True
            break
    if not replaced:
        skills.append(entry)

    hub_manifest["skills"] = sorted(skills, key=lambda i: str(i.get("slug", "")))
    hub_manifest.setdefault("allow_hosts", sorted(DEFAULT_ALLOWED_HOSTS))
    _save_hub_manifest(hub_manifest, target_manifest)

    return {
        "slug": resolved_slug,
        "version": resolved_version,
        "package_path": str(package_path),
        "manifest_path": str(target_manifest),
        "checksum_sha256": checksum,
        "download_url": download_url,
    }
