"""
Phase 7 – Self-Evolution Engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Runs autonomously to:
  1. Scan own source for gaps (TODOs, FIXMEs, stubs, unchecked ROADMAP items).
  2. Generate a targeted fix proposal via the configured LLM provider.
  3. Apply the fix, validate with ruff + pytest.
  4. Auto-commit when green, notify operator via the configured notification path.
  5. Skip and log when validation fails (never force-commit broken code).

Safety limits
-------------
- Never edits self_evolution.py itself.
- MAX_FILES_PER_RUN files and MAX_LINES_DELTA added/removed per cycle.
- Full test suite must exit 0 before any commit.
- Cooldown enforced between runs.
- All applied patches are persisted in evolution-log.json for audit.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from clawlite.utils.logging import bind_event

# ── tunables ──────────────────────────────────────────────────────────────────
MAX_FILES_PER_RUN = 3
MAX_LINES_DELTA = 200          # total added+removed across changed files
_SELF_FILE = Path(__file__).resolve()
_DENYLIST_NAMES = frozenset({"self_evolution.py", "autonomy.py", "gateway", "config"})
_GAP_PATTERN = re.compile(
    r"#\s*(TODO|FIXME|HACK|XXX|STUB|NOT IMPLEMENTED|raise NotImplementedError)",
    re.IGNORECASE,
)
_RAISE_NOT_IMPL = re.compile(r"^\s*raise\s+NotImplementedError", re.IGNORECASE)
_STUB_BODY = re.compile(r"^\s*(pass|\.\.\.)\s*$")
_DEF_LINE = re.compile(r"^\s*(async\s+)?def\s+\w+")
_ROADMAP_UNCHECKED = re.compile(r"^\s*-\s*\[\s*\]\s+(.+)$")

NotifyCallback = Callable[[str, dict[str, Any]], Awaitable[Any]]
_BRANCH_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9._/-]+")


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class Gap:
    file: str
    line: int
    kind: str      # "todo" | "stub" | "roadmap"
    text: str


@dataclass
class FixProposal:
    gap: Gap
    description: str
    patch_unified: str    # unified diff text
    files_touched: list[str] = field(default_factory=list)


@dataclass
class EvolutionRecord:
    run_id: str
    started_at: str
    finished_at: str = ""
    outcome: str = "pending"   # "committed" | "dry_run" | "validation_failed" | "no_gaps" | "error"
    gaps_found: int = 0
    fix_description: str = ""
    files_changed: list[str] = field(default_factory=list)
    commit_sha: str = ""
    error: str = ""
    ruff_ok: bool = False
    pytest_ok: bool = False
    branch_name: str = ""
    patch_preview: str = ""
    review_status: str = ""
    reviewed_at: str = ""
    reviewed_by: str = ""
    review_note: str = ""


@dataclass
class _GitSandbox:
    branch_name: str
    project_root: Path
    source_root: Path


@dataclass
class PatchPreview:
    path: Path
    lines: list[str]
    patch_lines: list[str]
    block_start: int
    block_end: int
    changed_lines: int
    original_header: str
    replacement_header: str


# ── gap scanner ───────────────────────────────────────────────────────────────

class SourceScanner:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _is_safe_file(self, path: Path) -> bool:
        if path.resolve() == _SELF_FILE:
            return False
        for part in path.parts:
            if part in _DENYLIST_NAMES:
                return False
        return path.suffix == ".py"

    def scan(self, *, max_gaps: int = 20) -> list[Gap]:
        gaps: list[Gap] = []
        for py_file in sorted(self.root.rglob("*.py")):
            if not self._is_safe_file(py_file):
                continue
            try:
                lines = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            rel = str(py_file.relative_to(self.root))
            gaps.extend(self._scan_file_lines(rel, lines, remaining=max_gaps - len(gaps)))
            if len(gaps) >= max_gaps:
                return gaps[:max_gaps]
        return gaps

    def _scan_file_lines(self, rel: str, lines: list[str], *, remaining: int) -> list[Gap]:
        found: list[Gap] = []
        last_def_idx: int | None = None

        for idx, line in enumerate(lines, 1):
            if remaining <= 0:
                break

            # Explicit gap markers
            m = _GAP_PATTERN.search(line)
            if m:
                kind = m.group(1).lower().replace(" ", "_")
                found.append(Gap(file=rel, line=idx, kind=kind, text=line.strip()))
                remaining -= 1
                continue

            # Track last def/async def header
            if _DEF_LINE.match(line):
                last_def_idx = idx
                continue

            # raise NotImplementedError as the meaningful body line
            if _RAISE_NOT_IMPL.match(line) and last_def_idx is not None:
                found.append(Gap(
                    file=rel, line=idx,
                    kind="not_implemented",
                    text=f"raise NotImplementedError (def at line {last_def_idx})",
                ))
                remaining -= 1
                last_def_idx = None
                continue

            # pass / ... as the only body (stub detection)
            if _STUB_BODY.match(line) and last_def_idx is not None:
                # Only flag if this is the first non-comment, non-docstring body line
                # after the def header.
                body_between = lines[last_def_idx:idx - 1]
                meaningful = [
                    bl for bl in body_between
                    if bl.strip() and not bl.strip().startswith("#")
                    and not (bl.strip().startswith('"""') or bl.strip().startswith("'''"))
                    and not bl.strip() == '"""' and not bl.strip() == "'''"
                ]
                if not meaningful:
                    found.append(Gap(
                        file=rel, line=idx,
                        kind="stub_pass",
                        text=f"stub body (pass/...) for def at line {last_def_idx}",
                    ))
                    remaining -= 1
                last_def_idx = None
                continue

            # Reset def tracker on non-trivial lines
            if line.strip() and not line.strip().startswith("#"):
                last_def_idx = None

        return found

    def scan_roadmap(self, roadmap_path: Path, *, max_items: int = 10) -> list[Gap]:
        gaps: list[Gap] = []
        if not roadmap_path.exists():
            return gaps
        try:
            lines = roadmap_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return gaps
        for idx, line in enumerate(lines, 1):
            m = _ROADMAP_UNCHECKED.match(line)
            if m:
                gaps.append(Gap(file=str(roadmap_path.name), line=idx, kind="roadmap", text=m.group(1).strip()))
                if len(gaps) >= max_items:
                    break
        return gaps

    def scan_reference_gaps(self, catalog_path: Path, *, max_items: int = 10) -> list[Gap]:
        """Load gaps from a JSON reference catalog (OpenClaw/nanobot feature parity).

        Expected format:
        [{"feature": "...", "status": "missing|partial", "notes": "..."}]
        """
        if not catalog_path.exists():
            return []
        try:
            raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        gaps: list[Gap] = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "") or "").strip().lower()
            if status not in {"missing", "partial"}:
                continue
            feature = str(item.get("feature", "") or "").strip()
            notes = str(item.get("notes", "") or "").strip()
            if not feature:
                continue
            text = feature if not notes else f"{feature} — {notes}"
            gaps.append(Gap(file=str(catalog_path.name), line=idx + 1, kind="reference_gap", text=text))
            if len(gaps) >= max_items:
                break
        return gaps

    def read_context(self, gap: Gap, *, context_lines: int = 30) -> str:
        """Return source context around a gap for the LLM prompt."""
        path = self.root / gap.file
        if not path.exists():
            return ""
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return ""
        start = max(0, gap.line - 1 - context_lines)
        end = min(len(lines), gap.line + context_lines)
        numbered = [f"{i + 1:4d}| {l}" for i, l in enumerate(lines[start:end], start)]
        return "\n".join(numbered)


# ── LLM-based fix proposer ────────────────────────────────────────────────────

class FixProposer:
    """Generates a fix proposal by calling the runtime LLM provider."""

    def __init__(self, run_llm: Callable[[str], Awaitable[str]]) -> None:
        self._run_llm = run_llm

    async def propose(self, gap: Gap, context: str) -> FixProposal | None:
        prompt = self._build_prompt(gap, context)
        try:
            raw = await asyncio.wait_for(self._run_llm(prompt), timeout=60.0)
        except Exception as exc:
            bind_event("self_evolution.propose").warning("llm call failed gap={} error={}", gap.text[:60], exc)
            return None
        return self._parse_response(gap, raw)

    @staticmethod
    def _build_prompt(gap: Gap, context: str) -> str:
        return (
            f"You are ClawLite's self-evolution engine. Fix the following gap in the codebase.\n\n"
            f"File: {gap.file}  Line: {gap.line}  Kind: {gap.kind}\n"
            f"Gap: {gap.text}\n\n"
            f"Source context:\n```python\n{context}\n```\n\n"
            "Produce a minimal, correct Python fix. Output ONLY:\n"
            "DESCRIPTION: <one-line summary of what you changed>\n"
            "```python\n<complete replacement for the function or block containing the gap>\n```\n\n"
            "Rules:\n"
            "- Keep the same indentation and surrounding code structure.\n"
            "- Do NOT change imports, class definitions, or unrelated code.\n"
            "- The fix must be compatible with Python 3.10+ and pydantic v2.\n"
            "- Do NOT add docstrings or comments beyond what is necessary.\n"
            "- Output only DESCRIPTION + code block, nothing else."
        )

    @staticmethod
    def _parse_response(gap: Gap, raw: str) -> FixProposal | None:
        description = ""
        desc_match = re.search(r"DESCRIPTION:\s*(.+)", raw)
        if desc_match:
            description = desc_match.group(1).strip()

        code_match = re.search(r"```python\n([\s\S]+?)```", raw)
        if not code_match:
            return None
        patch = code_match.group(1).rstrip()
        if not patch.strip():
            return None

        return FixProposal(
            gap=gap,
            description=description or gap.text[:80],
            patch_unified=patch,
            files_touched=[gap.file],
        )


# ── patch applicator ──────────────────────────────────────────────────────────

class PatchApplicator:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def preview(self, proposal: FixProposal) -> tuple[PatchPreview | None, str]:
        if not proposal.files_touched:
            return None, "no_files_in_proposal"
        if len(proposal.files_touched) > MAX_FILES_PER_RUN:
            return None, f"proposal_files_limit_exceeded:{len(proposal.files_touched)}>{MAX_FILES_PER_RUN}"

        expected_file = Path(str(proposal.gap.file or "").strip()).as_posix()
        touched = [Path(str(item or "").strip()) for item in proposal.files_touched]
        if len({path.as_posix() for path in touched}) != 1:
            return None, "proposal_multiple_targets_not_allowed"

        target_rel = touched[0]
        if not target_rel.parts or target_rel.is_absolute() or ".." in target_rel.parts:
            return None, f"proposal_path_invalid:{target_rel}"
        if target_rel.suffix != ".py":
            return None, f"proposal_path_invalid:{target_rel}"
        if target_rel.as_posix() != expected_file:
            return None, f"proposal_file_mismatch:{target_rel.as_posix()}!={expected_file}"

        gap = proposal.gap
        path = self.root / target_rel
        try:
            resolved = path.resolve()
        except Exception:
            return None, f"proposal_path_invalid:{target_rel}"
        if self.root != resolved and self.root not in resolved.parents:
            return None, f"proposal_path_invalid:{target_rel}"
        if not path.exists():
            return None, f"file_not_found:{gap.file}"

        try:
            original = path.read_text(encoding="utf-8")
        except OSError as exc:
            return None, f"read_error:{exc}"

        lines = original.splitlines(keepends=True)
        patch_lines = self._normalized_patch_lines(proposal.patch_unified)
        if not patch_lines or not "".join(patch_lines).strip():
            return None, "proposal_patch_empty"
        if any("```" in line for line in patch_lines):
            return None, "proposal_patch_contains_fence"

        # Find the function/block at the gap line and replace it
        # Strategy: find the nearest `def ` or class header above the gap line,
        # then replace lines from that header until the next same-level def/class.
        gap_idx = max(0, gap.line - 1)
        block_start = self._find_block_start(lines, gap_idx)
        block_end = self._find_block_end(lines, block_start)
        original_header = self._header_signature(lines[block_start] if block_start < len(lines) else "")
        replacement_header = self._header_signature(self._first_meaningful_line(patch_lines))
        if original_header == "":
            return None, "proposal_target_missing_header"
        if replacement_header == "":
            return None, "proposal_patch_missing_header"
        if original_header != replacement_header:
            return None, f"proposal_header_mismatch:{original_header}->{replacement_header}"

        changed_lines = self._changed_line_count(lines[block_start:block_end], patch_lines)
        if changed_lines > MAX_LINES_DELTA:
            return None, f"proposal_diff_too_large:{changed_lines}>{MAX_LINES_DELTA}"

        return PatchPreview(
            path=path,
            lines=lines,
            patch_lines=patch_lines,
            block_start=block_start,
            block_end=block_end,
            changed_lines=changed_lines,
            original_header=original_header,
            replacement_header=replacement_header,
        ), ""

    def apply(self, proposal: FixProposal, *, preview: PatchPreview | None = None) -> tuple[bool, str]:
        """
        Apply a FixProposal by finding the original function/block and replacing it.
        Returns (ok, error_message).
        """
        resolved_preview = preview
        if resolved_preview is None:
            resolved_preview, error = self.preview(proposal)
            if resolved_preview is None:
                return False, error

        new_lines = (
            resolved_preview.lines[:resolved_preview.block_start]
            + resolved_preview.patch_lines
            + resolved_preview.lines[resolved_preview.block_end:]
        )
        new_text = "".join(new_lines)

        try:
            resolved_preview.path.write_text(new_text, encoding="utf-8")
        except OSError as exc:
            return False, f"write error: {exc}"

        return True, ""

    @staticmethod
    def _find_block_start(lines: list[str], gap_idx: int) -> int:
        """Walk backwards to find the nearest def/class header."""
        for i in range(gap_idx, -1, -1):
            stripped = lines[i].lstrip()
            if stripped.startswith(("def ", "async def ", "class ")):
                return i
        return gap_idx

    @staticmethod
    def _find_block_end(lines: list[str], start: int) -> int:
        """Walk forward to find where this block ends (next same-level def/class or EOF)."""
        if start >= len(lines):
            return start
        base_indent = len(lines[start]) - len(lines[start].lstrip())
        next_block_decorator_start: int | None = None
        for i in range(start + 1, len(lines)):
            line = lines[i]
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent <= base_indent and stripped.startswith("@"):
                if next_block_decorator_start is None:
                    next_block_decorator_start = i
                continue
            if indent <= base_indent and stripped.startswith(("def ", "async def ", "class ")):
                return next_block_decorator_start if next_block_decorator_start is not None else i
            if indent <= base_indent:
                next_block_decorator_start = None
        return len(lines)

    @staticmethod
    def _first_meaningful_line(lines: list[str]) -> str:
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            return line
        return ""

    @staticmethod
    def _header_signature(line: str) -> str:
        stripped = str(line or "").lstrip()
        match = re.match(r"(async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\b", stripped)
        if match is None:
            return ""
        return f"{match.group(1)}:{match.group(2)}"

    @staticmethod
    def _changed_line_count(original: list[str], replacement: list[str]) -> int:
        changed = 0
        for row in difflib.ndiff(
            [line.rstrip("\n") for line in original],
            [line.rstrip("\n") for line in replacement],
        ):
            if row.startswith("- ") or row.startswith("+ "):
                changed += 1
        return changed

    @staticmethod
    def _normalized_patch_lines(patch_unified: str) -> list[str]:
        patch_lines = str(patch_unified or "").splitlines(keepends=True)
        if patch_lines and not patch_lines[-1].endswith("\n"):
            patch_lines[-1] = f"{patch_lines[-1]}\n"
        return patch_lines


# ── validator ─────────────────────────────────────────────────────────────────

class Validator:
    def __init__(
        self,
        root: Path,
        *,
        timeout_s: float = 120.0,
        python_executable: str | Path | None = None,
    ) -> None:
        self.root = root
        self.timeout_s = timeout_s
        self.python_executable = str(python_executable or self._detect_python_executable())

    def _detect_python_executable(self) -> str:
        candidates = [
            self.root / ".venv" / "bin" / "python",
            self.root / ".venv" / "Scripts" / "python.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return sys.executable or "python"

    def run_ruff(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.python_executable, "-m", "ruff", "check", "--select=E,F,W", str(self.root)],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                cwd=str(self.root),
            )
            ok = result.returncode == 0
            output = (result.stdout + result.stderr).strip()
            return ok, output
        except FileNotFoundError:
            return False, f"python executable not found: {self.python_executable}"
        except subprocess.TimeoutExpired:
            return False, "ruff timed out"
        except Exception as exc:
            return False, str(exc)

    def run_pytest(self) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [self.python_executable, "-m", "pytest", "-q", "--tb=short", "--no-header"],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                cwd=str(self.root),
            )
            ok = result.returncode == 0
            output = (result.stdout + result.stderr).strip()[-3000:]
            return ok, output
        except FileNotFoundError:
            return False, f"python executable not found: {self.python_executable}"
        except subprocess.TimeoutExpired:
            return False, "pytest timed out"
        except Exception as exc:
            return False, str(exc)


# ── git helpers ───────────────────────────────────────────────────────────────

def _git(args: list[str], *, cwd: str) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, cwd=cwd, timeout=30
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as exc:
        return 1, str(exc)


def _commit(root: Path, files: list[str], message: str) -> tuple[bool, str]:
    cwd = str(root)
    rel_files = [str(Path(f)) for f in files]

    rc, _ = _git(["add", "--", *rel_files], cwd=cwd)
    if rc != 0:
        rc, out = _git(["add", "--", *rel_files], cwd=cwd)
        if rc != 0:
            return False, f"git add failed: {out}"

    rc, out = _git(["commit", "-m", message], cwd=cwd)
    if rc != 0:
        return False, f"git commit failed: {out}"

    rc, sha = _git(["rev-parse", "--short", "HEAD"], cwd=cwd)
    return True, sha if rc == 0 else ""


def _git_is_dirty(root: Path) -> tuple[bool, str]:
    rc, out = _git(["status", "--porcelain"], cwd=str(root))
    if rc != 0:
        return True, f"git_status_failed:{out}"
    return bool(str(out or "").strip()), str(out or "").strip()


# ── evolution log ─────────────────────────────────────────────────────────────

class EvolutionLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def append(self, record: EvolutionRecord) -> None:
        rows = self._load()
        rows.append(asdict(record))
        rows = rows[-200:]  # keep last 200 entries
        try:
            self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def recent(self, n: int = 10) -> list[dict[str, Any]]:
        return self._load()[-n:]

    def update(self, run_id: str, **changes: Any) -> dict[str, Any] | None:
        rows = self._load()
        target_id = str(run_id or "").strip()
        if not target_id:
            return None
        updated: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("run_id", "") or "").strip() != target_id:
                continue
            row.update(changes)
            updated = dict(row)
            break
        if updated is None:
            return None
        try:
            self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            return None
        return updated

    def get(self, run_id: str) -> dict[str, Any] | None:
        target_id = str(run_id or "").strip()
        if not target_id:
            return None
        for row in self._load():
            if str(row.get("run_id", "") or "").strip() == target_id:
                return dict(row)
        return None


# ── main engine ───────────────────────────────────────────────────────────────

class SelfEvolutionEngine:
    """
    Phase 7 autonomous self-improvement loop.

    Call `run_once()` from the autonomy scheduler or heartbeat.
    It is safe to call concurrently — an internal lock prevents overlapping runs.
    """

    def __init__(
        self,
        *,
        project_root: str | Path,
        source_root: str | Path | None = None,
        run_llm: Callable[[str], Awaitable[str]] | None = None,
        notify: NotifyCallback | None = None,
        cooldown_s: float = 3600.0,
        enabled: bool = False,
        branch_prefix: str = "self-evolution",
        require_approval: bool = False,
        log_path: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.source_root = Path(source_root).resolve() if source_root else self.project_root / "clawlite"
        try:
            self._source_relpath = self.source_root.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("source_root must be inside project_root for isolated self-evolution runs") from exc
        self._run_llm = run_llm
        self._notify = notify
        self.cooldown_s = max(60.0, float(cooldown_s))
        self.enabled = bool(enabled)
        self.branch_prefix = self._normalize_branch_prefix(branch_prefix)
        self.require_approval = bool(require_approval)

        log_file = Path(log_path) if log_path else self.project_root / "memory" / "evolution-log.json"
        self.log = EvolutionLog(log_file)

        self._scanner = SourceScanner(self.source_root)
        self._validator = Validator(self.project_root)
        self._applicator = PatchApplicator(self.source_root)

        self._lock = asyncio.Lock()
        self._last_run_at: float | None = None
        self._run_count = 0
        self._committed_count = 0
        self._dry_run_count = 0
        self._last_outcome = ""
        self._last_error = ""
        self._last_branch = ""
        self._last_review_status = ""

    @classmethod
    def _normalize_branch_prefix(cls, value: str) -> str:
        normalized = _BRANCH_SEGMENT_RE.sub("-", str(value or "self-evolution").strip())
        normalized = normalized.strip("/.-")
        normalized = re.sub(r"/{2,}", "/", normalized)
        return normalized or "self-evolution"

    @staticmethod
    def _utc_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _now_monotonic() -> float:
        return time.monotonic()

    def _create_git_sandbox(self, run_id: str) -> tuple[_GitSandbox | None, str]:
        dirty, detail = _git_is_dirty(self.project_root)
        if dirty:
            if detail.startswith("git_status_failed:"):
                return None, detail
            return None, "git_worktree_dirty"

        branch_name = f"{self.branch_prefix}/{run_id}"
        worktree_dir = Path(tempfile.mkdtemp(prefix=f"clawlite-{run_id}-", dir=str(self.project_root.parent)))
        rc, out = _git(
            ["worktree", "add", "--quiet", "-b", branch_name, str(worktree_dir), "HEAD"],
            cwd=str(self.project_root),
        )
        if rc != 0:
            shutil.rmtree(worktree_dir, ignore_errors=True)
            return None, f"git_worktree_add_failed:{out}"

        source_root = worktree_dir / self._source_relpath
        return _GitSandbox(branch_name=branch_name, project_root=worktree_dir, source_root=source_root), ""

    def _cleanup_git_sandbox(self, sandbox: _GitSandbox, *, keep_branch: bool) -> None:
        _git(["worktree", "remove", "--force", str(sandbox.project_root)], cwd=str(self.project_root))
        if not keep_branch:
            _git(["branch", "-D", sandbox.branch_name], cwd=str(self.project_root))
        shutil.rmtree(sandbox.project_root, ignore_errors=True)

    async def _notify_operator(
        self,
        text: str,
        *,
        status: str = "info",
        summary: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._notify is None:
            bind_event("self_evolution").info("operator notice: {}", text)
            return
        try:
            await self._notify(
                "self_evolution",
                {
                    "text": text,
                    "status": str(status or "info").strip() or "info",
                    "summary": str(summary or "").strip(),
                    "metadata": dict(metadata or {}),
                },
            )
        except Exception as exc:
            bind_event("self_evolution").warning("notify failed: {}", exc)

    def _approval_metadata(self, *, run_id: str, branch_name: str, commit_sha: str) -> dict[str, Any]:
        if not self.require_approval:
            return {}
        callback_prefix = f"self_evolution:approve:{run_id}"
        reject_prefix = f"self_evolution:reject:{run_id}"
        return {
            "approval_required": True,
            "approval_command": f"clawlite self-evolution status",
            "_telegram_inline_keyboard": [
                [
                    {"text": "Approve", "callback_data": callback_prefix},
                    {"text": "Reject", "callback_data": reject_prefix},
                ]
            ],
            "discord_components": [
                {
                    "type": 1,
                    "components": [
                        {"type": 2, "style": 1, "label": "Approve", "custom_id": callback_prefix},
                        {"type": 2, "style": 4, "label": "Reject", "custom_id": reject_prefix},
                    ],
                }
            ],
            "branch_name": branch_name,
            "commit_sha": commit_sha,
        }

    def review_run(
        self,
        run_id: str,
        *,
        decision: str,
        actor: str = "",
        note: str = "",
    ) -> dict[str, Any]:
        normalized_run_id = str(run_id or "").strip()
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            return {"ok": False, "error": "invalid_review_decision"}
        row = self.log.get(normalized_run_id)
        if row is None:
            return {"ok": False, "error": "review_run_not_found", "run_id": normalized_run_id}
        outcome = str(row.get("outcome", "") or "").strip()
        if outcome not in {"committed", "dry_run"}:
            return {
                "ok": False,
                "error": f"review_run_not_reviewable:{outcome or 'unknown'}",
                "run_id": normalized_run_id,
            }
        existing_status = str(row.get("review_status", "") or "").strip().lower()
        if existing_status:
            if existing_status == normalized_decision:
                self._last_review_status = existing_status
                return {
                    "ok": True,
                    "status": existing_status,
                    "changed": False,
                    "run_id": normalized_run_id,
                    "branch_name": str(row.get("branch_name", "") or ""),
                    "commit_sha": str(row.get("commit_sha", "") or ""),
                }
            return {
                "ok": False,
                "error": f"review_run_already_decided:{existing_status}",
                "run_id": normalized_run_id,
            }

        reviewed_at = self._utc_iso()
        updated = self.log.update(
            normalized_run_id,
            review_status=normalized_decision,
            reviewed_at=reviewed_at,
            reviewed_by=str(actor or "").strip(),
            review_note=str(note or "").strip(),
        )
        if updated is None:
            return {"ok": False, "error": "review_update_failed", "run_id": normalized_run_id}
        self._last_review_status = normalized_decision
        return {
            "ok": True,
            "status": normalized_decision,
            "changed": True,
            "run_id": normalized_run_id,
            "reviewed_at": reviewed_at,
            "reviewed_by": str(actor or "").strip(),
            "branch_name": str(updated.get("branch_name", "") or ""),
            "commit_sha": str(updated.get("commit_sha", "") or ""),
        }

    async def run_once(self, *, force: bool = False, dry_run: bool = False) -> dict[str, Any]:
        if not self.enabled and not force:
            return self.status()

        now = self._now_monotonic()
        if (
            not force
            and self._last_run_at is not None
            and (now - self._last_run_at) < self.cooldown_s
        ):
            return self.status()

        if self._lock.locked():
            return self.status()

        async with self._lock:
            return await self._do_run(dry_run=dry_run)

    async def _do_run(self, *, dry_run: bool = False) -> dict[str, Any]:
        run_id = f"evo-{int(time.time() * 1000)}"
        record = EvolutionRecord(run_id=run_id, started_at=self._utc_iso())
        self._last_run_at = self._now_monotonic()
        self._run_count += 1
        backups: dict[str, str] = {}
        sandbox: _GitSandbox | None = None
        keep_branch = False

        try:
            sandbox, sandbox_error = await asyncio.to_thread(self._create_git_sandbox, run_id)
            if sandbox is None:
                record.outcome = "error"
                record.error = sandbox_error or "git_worktree_setup_failed"
                record.finished_at = self._utc_iso()
                self._last_outcome = "error"
                self._last_error = record.error
                self.log.append(record)
                return self.status()

            record.branch_name = sandbox.branch_name
            scanner = SourceScanner(sandbox.source_root)
            validator = Validator(sandbox.project_root, python_executable=self._validator.python_executable)
            applicator = PatchApplicator(sandbox.source_root)

            # 1. Scan for gaps
            code_gaps = scanner.scan(max_gaps=20)
            roadmap_path = sandbox.project_root / "ROADMAP.md"
            roadmap_gaps = scanner.scan_roadmap(roadmap_path, max_items=5)
            catalog_path = sandbox.project_root / "memory" / "gap-catalog.json"
            ref_gaps = scanner.scan_reference_gaps(catalog_path, max_items=5)
            all_gaps = code_gaps + roadmap_gaps + ref_gaps
            record.gaps_found = len(all_gaps)

            bind_event("self_evolution").info(
                "run={} gaps_found={} code={} roadmap={} ref={}",
                run_id, len(all_gaps), len(code_gaps), len(roadmap_gaps), len(ref_gaps),
            )

            if not all_gaps:
                record.outcome = "no_gaps"
                record.finished_at = self._utc_iso()
                self._last_outcome = "no_gaps"
                self._last_error = ""
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            if self._run_llm is None:
                record.outcome = "error"
                record.error = "llm_callback_missing"
                record.finished_at = self._utc_iso()
                self._last_outcome = "error"
                self._last_error = record.error
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            # 2. Pick the first actionable code gap (roadmap and reference gaps are informational only)
            target_gap = code_gaps[0] if code_gaps else all_gaps[0]
            if target_gap.kind in ("roadmap", "reference_gap"):
                # Log non-patchable gap as notice, nothing to patch
                bind_event("self_evolution").info(
                    "run={} informational_gap kind={} text={}",
                    run_id, target_gap.kind, target_gap.text[:120],
                )
                record.outcome = "no_gaps"
                record.finished_at = self._utc_iso()
                self._last_outcome = "no_gaps"
                self._last_error = ""
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            context = scanner.read_context(target_gap, context_lines=40)

            # 3. Propose fix
            proposer = FixProposer(self._run_llm)
            proposal = await proposer.propose(target_gap, context)
            if proposal is None:
                record.outcome = "error"
                record.error = "fix_proposal_failed"
                record.finished_at = self._utc_iso()
                self._last_outcome = "error"
                self._last_error = record.error
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            record.fix_description = proposal.description
            record.files_changed = list(proposal.files_touched)

            preview, preview_error = await asyncio.to_thread(applicator.preview, proposal)
            if preview is None:
                record.outcome = "error"
                record.error = f"proposal_policy_failed:{preview_error}"
                record.finished_at = self._utc_iso()
                self._last_outcome = "error"
                self._last_error = record.error
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            record.patch_preview = "\n".join(preview.patch_lines).strip()[:2000]

            if dry_run:
                record.outcome = "dry_run"
                record.finished_at = self._utc_iso()
                self._last_outcome = "dry_run"
                self._last_error = ""
                self._last_branch = ""
                self._dry_run_count += 1
                self.log.append(record)
                preview_snippet = proposal.patch_unified.strip() or record.patch_preview
                preview_snippet = preview_snippet[:500]
                await self._notify_operator(
                    f"[self-evolution dry-run] Proposed isolated fix `{target_gap.file}:{target_gap.line}` "
                    f"({target_gap.kind})\n"
                    f"Description: {proposal.description}\n"
                    f"Files: {', '.join(record.files_changed) or target_gap.file}\n"
                    f"Preview:\n```diff\n{preview_snippet}\n```",
                    status="dry_run",
                    summary=f"self-evolution dry-run for {target_gap.file}:{target_gap.line}",
                    metadata={
                        "dry_run": True,
                        "gap_file": target_gap.file,
                        "gap_line": int(target_gap.line),
                        "gap_kind": target_gap.kind,
                        "run_id": run_id,
                        "files_changed": list(record.files_changed),
                    },
                )
                return self.status()

            # 4. Backup original files
            for rel in proposal.files_touched:
                p = sandbox.source_root / rel
                if p.exists():
                    backups[rel] = p.read_text(encoding="utf-8", errors="replace")

            # 5. Apply patch
            ok, err = await asyncio.to_thread(applicator.apply, proposal, preview=preview)
            if not ok:
                record.outcome = "error"
                record.error = f"apply_failed: {err}"
                record.finished_at = self._utc_iso()
                self._last_outcome = "error"
                self._last_error = record.error
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            # 6. Validate
            ruff_ok, ruff_out = await asyncio.to_thread(validator.run_ruff)
            record.ruff_ok = ruff_ok

            if not ruff_ok:
                bind_event("self_evolution").warning("ruff failed run={} output={}", run_id, ruff_out[:400])
                await self._restore_backups(backups, project_root=sandbox.project_root, source_root=sandbox.source_root)
                record.outcome = "validation_failed"
                record.error = f"ruff: {ruff_out[:300]}"
                record.finished_at = self._utc_iso()
                self._last_outcome = "validation_failed"
                self._last_error = record.error
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            pytest_ok, pytest_out = await asyncio.to_thread(validator.run_pytest)
            record.pytest_ok = pytest_ok

            if not pytest_ok:
                bind_event("self_evolution").warning("pytest failed run={} output={}", run_id, pytest_out[-400:])
                await self._restore_backups(backups, project_root=sandbox.project_root, source_root=sandbox.source_root)
                record.outcome = "validation_failed"
                record.error = f"pytest: {pytest_out[-300:]}"
                record.finished_at = self._utc_iso()
                self._last_outcome = "validation_failed"
                self._last_error = record.error
                self._last_branch = ""
                self.log.append(record)
                await self._notify_operator(
                    f"[self-evolution] Proposed fix for `{target_gap.file}:{target_gap.line}` "
                    f"({target_gap.kind}) — tests FAILED, rolled back.\n"
                    f"Description: {proposal.description}",
                    status="validation_failed",
                    summary=f"self-evolution rollback for {target_gap.file}:{target_gap.line}",
                    metadata={
                        "gap_file": target_gap.file,
                        "gap_line": int(target_gap.line),
                        "gap_kind": target_gap.kind,
                        "run_id": run_id,
                    },
                )
                return self.status()

            # 7. Commit
            commit_msg = (
                f"auto: self-evolution — {proposal.description}\n\n"
                f"Gap: {target_gap.kind} in {target_gap.file}:{target_gap.line}\n"
                f"Run: {run_id}\n\n"
                f"Co-Authored-By: SelfEvolutionEngine <noreply@clawlite>"
            )
            repo_files_touched = [str(self._source_relpath / Path(rel)) for rel in proposal.files_touched]
            committed, sha = await asyncio.to_thread(
                _commit, sandbox.project_root, repo_files_touched, commit_msg
            )

            if not committed:
                await self._restore_backups(backups, project_root=sandbox.project_root, source_root=sandbox.source_root)
                record.outcome = "error"
                record.error = f"commit_failed: {sha}"
                record.finished_at = self._utc_iso()
                self._last_outcome = "error"
                self._last_error = record.error
                self._last_branch = ""
                self.log.append(record)
                return self.status()

            record.commit_sha = sha
            record.outcome = "committed"
            record.finished_at = self._utc_iso()
            self._last_outcome = "committed"
            self._last_error = ""
            self._last_branch = sandbox.branch_name
            self._committed_count += 1
            keep_branch = True
            self.log.append(record)

            bind_event("self_evolution").info(
                "committed run={} sha={} file={} description={}",
                run_id, sha, target_gap.file, proposal.description,
            )

            # 8. Notify operator (no approval required)
            await self._notify_operator(
                (
                    f"[self-evolution] Prepared isolated fix `{target_gap.file}:{target_gap.line}` "
                    f"({target_gap.kind})\n"
                    f"Description: {proposal.description}\n"
                    f"Branch: {sandbox.branch_name}\n"
                    f"Commit: {sha}  •  ruff ✓  pytest ✓"
                    + ("\nAwaiting operator approval before merge." if self.require_approval else "")
                ),
                status=("awaiting_approval" if self.require_approval else "committed"),
                summary=(
                    f"self-evolution awaiting approval for {target_gap.file}:{target_gap.line}"
                    if self.require_approval
                    else f"self-evolution committed fix for {target_gap.file}:{target_gap.line}"
                ),
                metadata={
                    "gap_file": target_gap.file,
                    "gap_line": int(target_gap.line),
                    "gap_kind": target_gap.kind,
                    "run_id": run_id,
                    "branch_name": sandbox.branch_name,
                    "commit_sha": sha,
                    **self._approval_metadata(
                        run_id=run_id,
                        branch_name=sandbox.branch_name,
                        commit_sha=sha,
                    ),
                },
            )

        except Exception as exc:
            if backups and sandbox is not None:
                await self._restore_backups(backups, project_root=sandbox.project_root, source_root=sandbox.source_root)
            record.outcome = "error"
            record.error = str(exc)
            record.finished_at = self._utc_iso()
            self._last_outcome = "error"
            self._last_error = str(exc)
            self._last_branch = ""
            self.log.append(record)
            bind_event("self_evolution").error("run failed run={} error={}", run_id, exc)
        finally:
            if sandbox is not None:
                await asyncio.to_thread(self._cleanup_git_sandbox, sandbox, keep_branch=keep_branch)

        return self.status()

    async def _restore_backups(
        self,
        backups: dict[str, str],
        *,
        project_root: Path,
        source_root: Path,
    ) -> None:
        restored: list[str] = []
        for rel, content in backups.items():
            path = source_root / rel
            try:
                await asyncio.to_thread(path.write_text, content, "utf-8")
                restored.append(str(path))
            except Exception as exc:
                bind_event("self_evolution").error("restore backup failed file={} error={}", rel, exc)

        # Also revert the git index so the restored files are not staged
        if restored:
            try:
                import subprocess
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "checkout", "HEAD", "--"] + restored,
                    cwd=str(project_root),
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    # git checkout failed (e.g. files were never committed) — files already restored via write_text above
                    bind_event("self_evolution").debug(
                        "git checkout rollback skipped (untracked files): {}", result.stderr.strip()
                    )
            except Exception as exc:
                bind_event("self_evolution").warning("git rollback index failed: {}", exc)

    def status(self) -> dict[str, Any]:
        if self._last_run_at is None:
            cooldown_remaining = 0.0
        else:
            cooldown_remaining = max(
                0.0, self.cooldown_s - (self._now_monotonic() - self._last_run_at)
            )
        return {
            "enabled": self.enabled,
            "run_count": self._run_count,
            "committed_count": self._committed_count,
            "dry_run_count": self._dry_run_count,
            "last_outcome": self._last_outcome,
            "last_error": self._last_error,
            "last_branch": self._last_branch,
            "last_review_status": self._last_review_status,
            "branch_prefix": self.branch_prefix,
            "require_approval": self.require_approval,
            "cooldown_remaining_s": round(cooldown_remaining, 1),
            "locked": self._lock.locked(),
        }
