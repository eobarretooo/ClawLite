from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from clawlite.config.settings import load_config, save_config
from clawlite.gateway.state import LOG_RING
from clawlite.gateway.utils import _check_bearer, _filter_logs, _hub_manifest_path, _log, _safe_slug, _skills_dir
from clawlite.skills.marketplace import (
    DEFAULT_DOWNLOAD_BASE_URL,
    SkillMarketplaceError,
    load_hub_manifest,
    publish_skill,
    update_skills as _marketplace_update_skills,
)

router = APIRouter()


def _resolve_update_skills():
    # Backward-compatible indirection so tests (and integrations) can monkeypatch server.update_skills.
    try:
        from clawlite.gateway import server as gateway_server

        fn = getattr(gateway_server, "update_skills", None)
        if callable(fn):
            return fn
    except Exception:
        pass
    return _marketplace_update_skills


@router.get("/api/dashboard/skills")
def api_dashboard_skills(authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    cfg = load_config()
    enabled = set(cfg.get("skills", []))
    local = []
    skills_dir = _skills_dir()
    if skills_dir.exists():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir():
                local.append(d.name)
    return JSONResponse({
        "ok": True,
        "skills": [{"slug": slug, "enabled": slug in enabled} for slug in sorted(set(local) | enabled)],
    })


@router.post("/api/dashboard/skills/install")
def api_dashboard_skills_install(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    skills_dir = _skills_dir()
    skill_dir = skills_dir / slug
    created = not skill_dir.exists()
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        skill_file.write_text(f"# {slug}\n\nSkill local instalada via dashboard.\n", encoding="utf-8")

    cfg = load_config()
    active = set(cfg.get("skills", []))
    active.add(slug)
    cfg["skills"] = sorted(active)
    save_config(cfg)
    _log("skills.installed", data={"slug": slug, "created": created})
    return JSONResponse({"ok": True, "slug": slug, "created": created})


@router.post("/api/dashboard/skills/enable")
def api_dashboard_skills_enable(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    if not (_skills_dir() / slug).exists():
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' não encontrada no diretório local")
    cfg = load_config()
    active = set(cfg.get("skills", []))
    active.add(slug)
    cfg["skills"] = sorted(active)
    save_config(cfg)
    _log("skills.enabled", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug, "enabled": True})


@router.post("/api/dashboard/skills/disable")
def api_dashboard_skills_disable(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    cfg = load_config()
    if slug not in cfg.get("skills", []):
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' já está desativada ou não existe")
    cfg["skills"] = [s for s in cfg.get("skills", []) if s != slug]
    save_config(cfg)
    _log("skills.disabled", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug, "enabled": False})


@router.post("/api/dashboard/skills/remove")
def api_dashboard_skills_remove(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slug = _safe_slug(str(payload.get("slug", "")))
    skill_dir = _skills_dir() / slug
    cfg = load_config()
    was_enabled = slug in cfg.get("skills", [])
    if not skill_dir.exists() and not was_enabled:
        raise HTTPException(status_code=404, detail=f"Skill '{slug}' não encontrada")

    cfg["skills"] = [s for s in cfg.get("skills", []) if s != slug]
    save_config(cfg)

    if skill_dir.exists() and skill_dir.is_dir():
        for p in sorted(skill_dir.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink(missing_ok=True)
            elif p.is_dir():
                try:
                    p.rmdir()
                except OSError:
                    pass
        try:
            skill_dir.rmdir()
        except OSError:
            pass

    _log("skills.removed", data={"slug": slug})
    return JSONResponse({"ok": True, "slug": slug, "removed": True})


@router.get("/api/dashboard/logs")
def api_dashboard_logs(
    authorization: str | None = Header(default=None),
    limit: int = 100,
    level: str = Query(default=""),
    event: str = Query(default=""),
    q: str = Query(default=""),
) -> JSONResponse:
    _check_bearer(authorization)
    n = max(1, min(limit, 500))
    rows = _filter_logs(list(LOG_RING), level=level, event=event, query=q)
    return JSONResponse({"ok": True, "logs": rows[-n:]})


@router.get("/api/hub/manifest")
def api_hub_manifest() -> JSONResponse:
    manifest = load_hub_manifest(_hub_manifest_path())
    return JSONResponse({"ok": True, "manifest": manifest})


@router.get("/api/hub/skills/{slug}")
def api_hub_skill(slug: str) -> JSONResponse:
    manifest = load_hub_manifest(_hub_manifest_path())
    for item in manifest.get("skills", []):
        if str(item.get("slug", "")).strip() == slug:
            return JSONResponse({"ok": True, "skill": item})
    raise HTTPException(status_code=404, detail="Skill not found")


@router.post("/api/hub/publish")
def api_hub_publish(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    try:
        result = publish_skill(
            payload.get("source_dir", ""),
            version=str(payload.get("version", "")).strip(),
            slug=payload.get("slug"),
            description=str(payload.get("description", "")),
            hub_dir=payload.get("hub_dir"),
            manifest_path=payload.get("manifest_path") or _hub_manifest_path(),
            download_base_url=str(payload.get("download_base_url", "")) or DEFAULT_DOWNLOAD_BASE_URL,
        )
    except SkillMarketplaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "result": result})


@router.post("/api/dashboard/update")
def api_dashboard_update(payload: dict[str, Any], authorization: str | None = Header(default=None)) -> JSONResponse:
    _check_bearer(authorization)
    slugs = payload.get("slugs") or []
    if not isinstance(slugs, list):
        raise HTTPException(status_code=400, detail="Campo 'slugs' deve ser lista")
    dry_run = bool(payload.get("dry_run", True))
    update_fn = _resolve_update_skills()
    try:
        result = update_fn(slugs=[str(s) for s in slugs], dry_run=dry_run)
    except SkillMarketplaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log("skills.update", data={"dry_run": dry_run, "count": len(result.get("updated", []))})
    return JSONResponse({"ok": True, "dry_run": dry_run, "result": result})
