from __future__ import annotations

from typing import Any


class SubagentSynthesizer:
    """Deterministic digest generator for completed subagent runs."""

    _MAX_RUNS = 8
    _MAX_SESSION_CHARS = 48
    _MAX_TASK_CHARS = 72
    _MAX_EXCERPT_CHARS = 120
    _MAX_TOTAL_CHARS = 1400

    @classmethod
    def _compact(cls, value: Any, max_chars: int) -> str:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        keep = max(1, max_chars - 3)
        return f"{text[:keep]}..."

    @staticmethod
    def _run_sort_key(run: Any) -> tuple[str, str]:
        finished = str(getattr(run, "finished_at", "") or "")
        run_id = str(getattr(run, "run_id", "") or "")
        return finished, run_id

    def _excerpt_from_run(self, run: Any) -> str:
        metadata = dict(getattr(run, "metadata", {}) or {})
        result = self._compact(getattr(run, "result", ""), self._MAX_EXCERPT_CHARS)
        error = self._compact(getattr(run, "error", ""), self._MAX_EXCERPT_CHARS)
        continuation = self._compact(metadata.get("continuation_digest_summary", ""), self._MAX_EXCERPT_CHARS)
        episodic = self._compact(metadata.get("episodic_digest_summary", ""), self._MAX_EXCERPT_CHARS)
        if error:
            return error
        if continuation and continuation != episodic and episodic and result:
            return self._compact(
                f"continued from {continuation} | current={episodic} | result={result}",
                self._MAX_EXCERPT_CHARS,
            )
        if continuation and continuation != episodic and episodic:
            return self._compact(
                f"continued from {continuation} | current={episodic}",
                self._MAX_EXCERPT_CHARS,
            )
        if continuation and continuation != episodic and result:
            return self._compact(f"continued from {continuation} | result={result}", self._MAX_EXCERPT_CHARS)
        if continuation and continuation != episodic:
            return self._compact(f"continued from {continuation}", self._MAX_EXCERPT_CHARS)
        if episodic and result:
            return self._compact(f"{episodic} | result={result}", self._MAX_EXCERPT_CHARS)
        if episodic:
            return episodic
        if result:
            return result
        return "(no output)"

    def summarize(self, runs: list[Any]) -> str:
        if not runs:
            return ""

        lines: list[str] = []
        total_chars = 0
        for run in sorted(runs, key=self._run_sort_key)[: self._MAX_RUNS]:
            run_id = str(getattr(run, "run_id", "") or "").strip()
            if not run_id:
                continue
            short_id = run_id[:8]
            status = self._compact(getattr(run, "status", "unknown"), 24) or "unknown"
            task = self._compact(getattr(run, "task", ""), self._MAX_TASK_CHARS)
            metadata = dict(getattr(run, "metadata", {}) or {})
            target_session_id = self._compact(metadata.get("target_session_id", ""), self._MAX_SESSION_CHARS)
            excerpt = self._excerpt_from_run(run)

            line = f"- {short_id} [{status}] task={task or '-'}"
            if target_session_id:
                line = f"{line} | session={target_session_id}"
            line = f"{line} | excerpt={excerpt}"
            if total_chars + len(line) > self._MAX_TOTAL_CHARS:
                break
            lines.append(line)
            total_chars += len(line) + 1

        return "\n".join(lines).strip()
