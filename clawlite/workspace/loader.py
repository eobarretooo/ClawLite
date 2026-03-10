from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from loguru import logger

from clawlite.workspace.user_profile import WorkspaceUserProfile, load_user_profile_from_path

TEMPLATE_FILES = (
    "IDENTITY.md",
    "SOUL.md",
    "USER.md",
    "AGENTS.md",
    "TOOLS.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "memory/MEMORY.md",
)

RUNTIME_CRITICAL_FILES = ("IDENTITY.md", "SOUL.md", "USER.md")

DEFAULT_VARS = {
    "assistant_name": "ClawLite",
    "assistant_emoji": "🦊",
    "assistant_creature": "fox",
    "assistant_vibe": "direct, pragmatic, autonomous",
    "assistant_backstory": "An autonomous personal assistant focused on execution.",
    "user_name": "Owner",
    "user_timezone": "UTC",
    "user_context": "Personal operations and software projects",
    "user_preferences": "Clear answers, direct actions, concise updates",
}


class WorkspaceLoader:
    def __init__(self, workspace_path: str | Path | None = None, template_root: str | Path | None = None) -> None:
        self.workspace = Path(workspace_path) if workspace_path else (Path.home() / ".clawlite" / "workspace")
        self.templates = Path(template_root) if template_root else Path(__file__).resolve().parent / "templates"
        self._last_runtime_health: dict[str, Any] = {}

    @staticmethod
    def _render(template: str, variables: dict[str, str]) -> str:
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
        return rendered

    def sync_templates(
        self,
        *,
        variables: dict[str, str] | None = None,
        update_existing: bool = False,
    ) -> dict[str, list[Path]]:
        values = dict(DEFAULT_VARS)
        values.update({k: str(v) for k, v in (variables or {}).items()})

        created: list[Path] = []
        updated: list[Path] = []
        skipped: list[Path] = []

        self.workspace.mkdir(parents=True, exist_ok=True)

        bootstrap_status = self.bootstrap_status()
        bootstrap_completed = bool(bootstrap_status.get("completed_at")) or str(bootstrap_status.get("last_status", "")) == "completed"
        onboarding_status = self.onboarding_status(variables=values, persist=True)
        onboarding_completed = bool(onboarding_status.get("completed", False))

        for rel in TEMPLATE_FILES:
            src = self.templates / rel
            dst = self.workspace / rel
            if not src.exists():
                continue

            if rel == "BOOTSTRAP.md" and (bootstrap_completed or onboarding_completed):
                skipped.append(dst)
                continue

            rendered = self._render(src.read_text(encoding="utf-8"), values)
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(rendered, encoding="utf-8")
                created.append(dst)
                continue

            current = dst.read_text(encoding="utf-8", errors="ignore")
            if current == rendered:
                skipped.append(dst)
                continue

            if update_existing:
                dst.write_text(rendered, encoding="utf-8")
                updated.append(dst)
            else:
                skipped.append(dst)

        self._reconcile_onboarding_state(variables=values, persist=True)

        return {
            "created": sorted(created),
            "updated": sorted(updated),
            "skipped": sorted(skipped),
        }

    def bootstrap(self, *, variables: dict[str, str] | None = None, overwrite: bool = False) -> list[Path]:
        result = self.sync_templates(variables=variables, update_existing=overwrite)
        return [*result["created"], *result["updated"]]

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _render_template_file(self, filename: str, *, variables: dict[str, str] | None = None) -> str:
        values = dict(DEFAULT_VARS)
        values.update({k: str(v) for k, v in (variables or {}).items()})
        template_path = self.templates / filename
        if not template_path.exists():
            raise FileNotFoundError(f"workspace_template_missing:{filename}")
        return self._render(template_path.read_text(encoding="utf-8"), values)

    def _runtime_file_issue(self, path: Path) -> tuple[str, str]:
        if not path.exists():
            return "missing", ""
        try:
            raw = path.read_bytes()
        except Exception as exc:
            return "unreadable", str(exc)
        if not raw:
            return "empty", ""
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            return "corrupt", str(exc)
        if "\x00" in text:
            return "corrupt", "contains_nul_bytes"
        if not text.strip():
            return "empty", ""
        return "", ""

    def _backup_runtime_file(self, path: Path, *, suffix: str) -> str:
        if not path.exists():
            return ""
        backup_name = f"{path.name}.{suffix}.bak"
        backup_path = path.with_name(backup_name)
        counter = 1
        while backup_path.exists():
            backup_path = path.with_name(f"{path.name}.{suffix}.{counter}.bak")
            counter += 1
        try:
            backup_path.write_bytes(path.read_bytes())
            return str(backup_path)
        except Exception as exc:
            logger.warning("workspace backup failed path={} error={}", path, exc)
            return ""

    def ensure_runtime_files(self, *, variables: dict[str, str] | None = None) -> dict[str, Any]:
        values = dict(DEFAULT_VARS)
        values.update({k: str(v) for k, v in (variables or {}).items()})
        self.workspace.mkdir(parents=True, exist_ok=True)

        files_payload: dict[str, Any] = {}
        repaired_files: list[str] = []
        failed_files: list[str] = []
        issues_detected = 0

        for filename in RUNTIME_CRITICAL_FILES:
            path = self.workspace / filename
            issue, error = self._runtime_file_issue(path)
            repaired = False
            backup_path = ""
            status = "ok"
            if issue:
                issues_detected += 1
                try:
                    if issue in {"corrupt", "unreadable"} and path.exists():
                        backup_path = self._backup_runtime_file(path, suffix=f"repair-{issue}")
                    rendered = self._render_template_file(filename, variables=values)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(rendered, encoding="utf-8")
                    repaired = True
                    repaired_files.append(filename)
                    logger.warning("workspace runtime file repaired file={} issue={}", filename, issue)
                except Exception as exc:
                    status = "repair_failed"
                    failed_files.append(filename)
                    error = str(exc)
                    logger.warning("workspace runtime file repair failed file={} issue={} error={}", filename, issue, exc)

            exists = path.exists()
            byte_size = 0
            try:
                if exists:
                    byte_size = int(path.stat().st_size)
            except Exception:
                byte_size = 0

            files_payload[filename] = {
                "path": str(path),
                "status": status,
                "issue": issue,
                "error": error,
                "exists": exists,
                "bytes": byte_size,
                "repaired": repaired,
                "backup_path": backup_path,
            }

        report = {
            "checked_at": self._utcnow_iso(),
            "critical_files": files_payload,
            "repaired_files": repaired_files,
            "repaired_count": len(repaired_files),
            "failed_files": failed_files,
            "failed_count": len(failed_files),
            "issues_detected": issues_detected,
            "healthy_count": sum(1 for payload in files_payload.values() if str(payload.get("status", "")) == "ok"),
        }
        self._last_runtime_health = dict(report)
        return dict(report)

    def runtime_health(self) -> dict[str, Any]:
        if not self._last_runtime_health:
            return self.ensure_runtime_files()
        return dict(self._last_runtime_health)

    def read(self, filenames: Iterable[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for filename in filenames:
            path = self.workspace / filename
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            if text:
                out[filename] = text
        return out

    def user_profile(self) -> WorkspaceUserProfile:
        self.ensure_runtime_files()
        return load_user_profile_from_path(self.workspace / "USER.md")

    def user_profile_prompt(self) -> str:
        return self.user_profile().prompt_hint()

    def bootstrap_path(self) -> Path:
        return self.workspace / "BOOTSTRAP.md"

    def bootstrap_state_path(self) -> Path:
        return self.workspace / "memory" / "bootstrap-state.json"

    def onboarding_state_path(self) -> Path:
        return self.workspace / "memory" / "onboarding-state.json"

    @staticmethod
    def _bootstrap_state_defaults() -> dict[str, Any]:
        return {
            "last_run_iso": "",
            "completed_at": "",
            "last_status": "",
            "last_error": "",
            "run_count": 0,
            "last_session_id": "",
        }

    def _read_bootstrap_state(self) -> dict[str, Any]:
        defaults = self._bootstrap_state_defaults()
        path = self.bootstrap_state_path()
        if not path.exists():
            return dict(defaults)
        try:
            payload = json.loads(path.read_text(encoding="utf-8").strip() or "{}")
        except Exception:
            return dict(defaults)
        if not isinstance(payload, dict):
            return dict(defaults)

        state = dict(defaults)
        state["last_run_iso"] = str(payload.get("last_run_iso", "") or "")
        state["completed_at"] = str(payload.get("completed_at", "") or "")
        state["last_status"] = str(payload.get("last_status", "") or "")
        state["last_error"] = str(payload.get("last_error", "") or "")
        state["last_session_id"] = str(payload.get("last_session_id", "") or "")
        try:
            state["run_count"] = max(0, int(payload.get("run_count", 0) or 0))
        except Exception:
            state["run_count"] = 0
        return state

    def _write_bootstrap_state(self, payload: dict[str, Any]) -> bool:
        path = self.bootstrap_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
                prefix=".bootstrap-state-",
                suffix=".tmp",
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                temp_path = Path(handle.name)
            if temp_path is None:
                return False
            temp_path.replace(path)
            return True
        except Exception:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return False

    @staticmethod
    def _onboarding_state_defaults() -> dict[str, Any]:
        return {
            "version": 1,
            "bootstrap_seeded_at": "",
            "onboarding_completed_at": "",
        }

    def _read_onboarding_state(self) -> dict[str, Any]:
        defaults = self._onboarding_state_defaults()
        path = self.onboarding_state_path()
        if not path.exists():
            return dict(defaults)
        try:
            payload = json.loads(path.read_text(encoding="utf-8").strip() or "{}")
        except Exception:
            return dict(defaults)
        if not isinstance(payload, dict):
            return dict(defaults)

        state = dict(defaults)
        state["bootstrap_seeded_at"] = str(payload.get("bootstrap_seeded_at", payload.get("bootstrapSeededAt", "")) or "")
        state["onboarding_completed_at"] = str(payload.get("onboarding_completed_at", payload.get("onboardingCompletedAt", "")) or "")
        return state

    def _write_onboarding_state(self, payload: dict[str, Any]) -> bool:
        path = self.onboarding_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                delete=False,
                prefix=".onboarding-state-",
                suffix=".tmp",
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                temp_path = Path(handle.name)
            if temp_path is None:
                return False
            temp_path.replace(path)
            return True
        except Exception:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return False

    def _legacy_onboarding_completed(self, *, variables: dict[str, str] | None = None) -> bool:
        identity_path = self.workspace / "IDENTITY.md"
        user_path = self.workspace / "USER.md"
        if not identity_path.exists() or not user_path.exists():
            return False

        try:
            expected_identity = self._render_template_file("IDENTITY.md", variables=variables)
            expected_user = self._render_template_file("USER.md", variables=variables)
            identity_content = identity_path.read_text(encoding="utf-8", errors="ignore")
            user_content = user_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False

        indicators = [self.workspace / "memory", self.workspace / ".git"]
        has_user_content = any(path.exists() for path in indicators)
        return identity_content != expected_identity or user_content != expected_user or has_user_content

    def _reconcile_onboarding_state(self, *, variables: dict[str, str] | None = None, persist: bool = True) -> dict[str, Any]:
        state = self._read_onboarding_state()
        state_dirty = False
        bootstrap_exists = self.bootstrap_path().exists()
        now = self._utcnow_iso()

        def mark(key: str) -> None:
            nonlocal state_dirty
            if not str(state.get(key, "") or ""):
                state[key] = now
                state_dirty = True

        if bootstrap_exists:
            mark("bootstrap_seeded_at")
        elif str(state.get("bootstrap_seeded_at", "") or "") and not str(state.get("onboarding_completed_at", "") or ""):
            mark("onboarding_completed_at")
        elif not str(state.get("bootstrap_seeded_at", "") or "") and not str(state.get("onboarding_completed_at", "") or ""):
            if self._legacy_onboarding_completed(variables=variables):
                mark("onboarding_completed_at")

        if persist and state_dirty:
            payload = {
                "version": 1,
                "bootstrap_seeded_at": str(state.get("bootstrap_seeded_at", "") or ""),
                "onboarding_completed_at": str(state.get("onboarding_completed_at", "") or ""),
            }
            self._write_onboarding_state(payload)

        return {
            "state_path": str(self.onboarding_state_path()),
            "bootstrap_exists": bootstrap_exists,
            "bootstrap_seeded_at": str(state.get("bootstrap_seeded_at", "") or ""),
            "onboarding_completed_at": str(state.get("onboarding_completed_at", "") or ""),
            "completed": bool(str(state.get("onboarding_completed_at", "") or "")),
        }

    def onboarding_status(self, *, variables: dict[str, str] | None = None, persist: bool = False) -> dict[str, Any]:
        return self._reconcile_onboarding_state(variables=variables, persist=persist)

    def bootstrap_status(self) -> dict[str, Any]:
        state = self._read_bootstrap_state()
        bootstrap_path = self.bootstrap_path()
        exists = bootstrap_path.exists()
        has_content = False
        if exists:
            try:
                has_content = bool(bootstrap_path.read_text(encoding="utf-8", errors="ignore").strip())
            except Exception:
                has_content = False
        completed = bool(state.get("completed_at")) or str(state.get("last_status", "")) == "completed"
        pending = bool(exists and has_content and not completed)
        return {
            "pending": pending,
            "bootstrap_exists": exists,
            "bootstrap_path": str(bootstrap_path),
            "state_path": str(self.bootstrap_state_path()),
            "last_run_iso": str(state.get("last_run_iso", "") or ""),
            "completed_at": str(state.get("completed_at", "") or ""),
            "last_status": str(state.get("last_status", "") or ""),
            "last_error": str(state.get("last_error", "") or ""),
            "run_count": int(state.get("run_count", 0) or 0),
            "last_session_id": str(state.get("last_session_id", "") or ""),
        }

    def record_bootstrap_result(self, status: str, session_id: str = "", error: str = "") -> bool:
        state = self._read_bootstrap_state()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        normalized_status = str(status or "").strip().lower() or "unknown"

        state["last_run_iso"] = now
        state["last_status"] = normalized_status
        state["last_error"] = str(error or "")
        state["last_session_id"] = str(session_id or "")
        state["run_count"] = max(0, int(state.get("run_count", 0) or 0)) + 1
        if normalized_status == "completed":
            state["completed_at"] = now

        payload = {
            "last_run_iso": str(state.get("last_run_iso", "") or ""),
            "completed_at": str(state.get("completed_at", "") or ""),
            "last_status": str(state.get("last_status", "") or ""),
            "last_error": str(state.get("last_error", "") or ""),
            "run_count": int(state.get("run_count", 0) or 0),
            "last_session_id": str(state.get("last_session_id", "") or ""),
        }
        return self._write_bootstrap_state(payload)

    def should_run_bootstrap(self) -> bool:
        return bool(self.bootstrap_status().get("pending", False))

    def should_run(self) -> bool:
        return self.should_run_bootstrap()

    def bootstrap_prompt(self) -> str:
        if not self.should_run_bootstrap():
            return ""
        path = self.bootstrap_path()
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    def get_prompt(self) -> str:
        return self.bootstrap_prompt()

    def complete_bootstrap(self) -> bool:
        path = self.bootstrap_path()
        if not path.exists():
            return False
        path.unlink()
        self._reconcile_onboarding_state(persist=True)
        return True

    def complete(self) -> bool:
        return self.complete_bootstrap()

    def heartbeat_prompt(self) -> str:
        path = self.workspace / "HEARTBEAT.md"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="ignore").strip()

    def system_context(self, *, include_heartbeat: bool = True, include_bootstrap: bool = True) -> str:
        self.ensure_runtime_files()
        files = ["IDENTITY.md", "SOUL.md", "AGENTS.md", "TOOLS.md", "USER.md"]
        if include_heartbeat:
            files.append("HEARTBEAT.md")
        if include_bootstrap and self.should_run_bootstrap():
            files.append("BOOTSTRAP.md")

        docs = self.read(files)
        ordered_files = [name for name in files if name in docs]
        parts = [f"## {name}\n{docs[name]}" for name in ordered_files]
        return "\n\n".join(parts).strip()
