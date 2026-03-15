from __future__ import annotations
import io
import time
from pathlib import Path
from clawlite.tools.base import Tool, ToolContext, ToolHealthResult

class PdfReadTool(Tool):
    name = "pdf_read"
    description = "Extract text from a PDF file (local path or HTTPS URL). Supports page ranges like '1-5'."
    cacheable = True

    def __init__(self, *, max_chars: int = 20_000, timeout_s: float = 15.0) -> None:
        self.max_chars = max(256, int(max_chars or 20_000))
        self.timeout_s = max(5.0, float(timeout_s or 15.0))

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Local file path or HTTPS URL."},
                "pages": {"type": "string", "description": "Page range e.g. '1-5', '3'. Empty = all."},
                "max_chars": {"type": "integer", "default": 20_000},
            },
            "required": ["path"],
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            return "error: pypdf not installed. Run: pip install pypdf"
        src = str(arguments.get("path", "") or "").strip()
        if not src: return "error: path is required"
        max_chars = int(arguments.get("max_chars", self.max_chars) or self.max_chars)
        try:
            if src.startswith("https://"):
                import httpx
                async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                    r = await c.get(src)
                    if r.status_code != 200: return f"error: HTTP {r.status_code}"
                    reader = PdfReader(io.BytesIO(r.content))
            else:
                p = Path(src).expanduser().resolve()
                if not p.exists(): return f"error: file not found: {p}"
                reader = PdfReader(str(p))
        except Exception as exc:
            return f"error reading PDF: {exc}"
        total = len(reader.pages)
        indices = self._parse_pages(str(arguments.get("pages", "") or ""), total)
        parts = []
        for i in indices:
            try:
                t = (reader.pages[i].extract_text() or "").strip()
                if t: parts.append(f"[Page {i+1}]\n{t}")
            except Exception: pass
        if not parts: return f"pdf: {total} page(s) — no extractable text."
        result = "\n\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n\n[truncated — {len(result)} chars total]"
        return f"pdf: {total} page(s), showing {len(indices)}.\n\n{result}"

    async def health_check(self) -> ToolHealthResult:
        t0 = time.monotonic()
        try:
            from pypdf import PdfReader, PdfWriter
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            reader = PdfReader(buf)
            _ = len(reader.pages)
            return ToolHealthResult(ok=True, latency_ms=(time.monotonic() - t0) * 1000, detail="pypdf_ok")
        except Exception as exc:
            return ToolHealthResult(ok=False, latency_ms=(time.monotonic() - t0) * 1000, detail=str(exc))

    def _parse_pages(self, pages_arg: str, total: int) -> list:
        if not pages_arg: return list(range(total))
        idxs: set = set()
        for part in pages_arg.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    s, e = part.split("-", 1)
                    idxs.update(range(max(0, int(s)-1), min(total, int(e))))
                except ValueError: pass
            else:
                try:
                    n = int(part)
                    if 1 <= n <= total: idxs.add(n-1)
                except ValueError: pass
        return sorted(idxs) if idxs else list(range(total))
