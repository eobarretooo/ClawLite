from __future__ import annotations

import ast
import hashlib
import json
import re
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = ROOT / "docs" / "generated_architecture"
PER_FILE_ROOT = OUTPUT_ROOT / "per_file"
CODE_EXTENSIONS = {".py", ".js", ".html", ".css", ".sh"}
TEXT_EXTENSIONS = CODE_EXTENSIONS | {".md", ".toml", ".yml", ".yaml", ".json"}
EXCLUDED_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
}
EXCLUDED_PATH_PARTS = {"docs/generated_architecture"}


@dataclass(slots=True)
class FileInfo:
    path: Path
    rel_path: str
    ext: str
    area: str
    line_count: int
    size_bytes: int
    sha1: str
    summary: str
    doc_path: str
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    async_functions: list[str] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    tests_for: list[str] = field(default_factory=list)
    references_tests: list[str] = field(default_factory=list)
    string_markers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class PythonAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes: list[str] = []
        self.functions: list[str] = []
        self.async_functions: list[str] = []
        self.constants: list[str] = []
        self.imports: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.async_functions.append(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                self.constants.append(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        target = node.target
        if isinstance(target, ast.Name) and target.id.isupper():
            self.constants.append(target.id)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        prefix = "." * node.level
        self.imports.append(f"{prefix}{module}")


def _is_excluded(path: Path) -> bool:
    path_str = path.as_posix()
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    return any(excluded in path_str for excluded in EXCLUDED_PATH_PARTS)


def discover_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or _is_excluded(path):
            continue
        if path.suffix.lower() in CODE_EXTENSIONS:
            files.append(path)
    return sorted(files)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_module(rel_path: str) -> str:
    if not rel_path.endswith(".py"):
        return rel_path
    if rel_path.endswith("/__init__.py"):
        return rel_path[:-12].replace("/", ".")
    return rel_path[:-3].replace("/", ".")


def classify_area(rel_path: str) -> str:
    parts = rel_path.split("/")
    if len(parts) == 1:
        return "root"
    if rel_path.startswith("tests/"):
        return "tests"
    if rel_path.startswith("scripts/"):
        return "scripts"
    if rel_path.startswith("docs/"):
        return "docs"
    if rel_path.startswith("clawlite/"):
        if len(parts) == 2:
            return "clawlite"
        return parts[1] if len(parts) > 1 else "clawlite"
    return parts[0]


def summarize_text_file(rel_path: str, text: str, area: str) -> str:
    stripped = [line.strip() for line in text.splitlines() if line.strip()]
    if not stripped:
        return f"{rel_path} is an empty {area} file."
    first = stripped[0]
    if first.startswith('"""') or first.startswith("'''"):
        cleaned = first.strip("\"'")
        return f"{rel_path} opens with a module docstring: {cleaned[:140]}."
    if first.startswith("#!"):
        return f"{rel_path} is an executable script in the {area} area."
    if first.startswith("#"):
        return f"{rel_path} starts with a heading or comment that frames the file purpose."
    return f"{rel_path} is a {area} file whose first meaningful line is `{first[:120]}`."


def summarize_python(
    rel_path: str,
    classes: list[str],
    functions: list[str],
    async_functions: list[str],
    imports: list[str],
) -> str:
    role = classify_area(rel_path)
    module = normalize_module(rel_path)
    parts = [f"`{module}` is a Python module in the `{role}` area."]
    if classes:
        parts.append(f"It defines {len(classes)} class(es), led by {', '.join(f'`{name}`' for name in classes[:4])}.")
    if functions or async_functions:
        leading = functions[:3] + async_functions[:3]
        parts.append(
            f"It exposes {len(functions) + len(async_functions)} function(s), including {', '.join(f'`{name}`' for name in leading[:6])}."
        )
    if imports:
        parts.append(f"It depends on {len(imports)} import statement target(s).")
    return " ".join(parts)


def extract_string_markers(text: str) -> list[str]:
    patterns = [
        r"@(?:app|router)\.(?:get|post|put|delete|patch|websocket)\(([^)]*)\)",
        r"add_api_route\(([^)]*)\)",
        r"clawlite\s+[A-Za-z0-9:_-]+",
        r"test_[A-Za-z0-9_]+",
    ]
    markers: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            marker = match if isinstance(match, str) else str(match)
            cleaned = " ".join(marker.strip().split())
            if cleaned:
                markers.append(cleaned[:120])
    return sorted(dict.fromkeys(markers))[:12]


def build_file_info(path: Path) -> FileInfo:
    rel_path = path.relative_to(ROOT).as_posix()
    text = read_text(path)
    sha1 = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()
    area = classify_area(rel_path)
    file_info = FileInfo(
        path=path,
        rel_path=rel_path,
        ext=path.suffix.lower(),
        area=area,
        line_count=len(text.splitlines()),
        size_bytes=path.stat().st_size,
        sha1=sha1,
        summary="",
        doc_path=str(PER_FILE_ROOT / path.parent.relative_to(ROOT) / f"READ_{path.stem}.md"),
    )
    if path.suffix.lower() == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            file_info.summary = f"{rel_path} could not be parsed with `ast` due to `{exc.msg}`."
            file_info.notes.append("AST parse failed; symbol and import extraction is incomplete.")
            return file_info
        analyzer = PythonAnalyzer()
        analyzer.visit(tree)
        file_info.classes = sorted(dict.fromkeys(analyzer.classes))
        file_info.functions = sorted(dict.fromkeys(analyzer.functions))
        file_info.async_functions = sorted(dict.fromkeys(analyzer.async_functions))
        file_info.constants = sorted(dict.fromkeys(analyzer.constants))
        file_info.imports = sorted(dict.fromkeys(analyzer.imports))
        file_info.summary = summarize_python(
            rel_path,
            file_info.classes,
            file_info.functions,
            file_info.async_functions,
            file_info.imports,
        )
    else:
        file_info.summary = summarize_text_file(rel_path, text, area)
    file_info.string_markers = extract_string_markers(text)
    return file_info


def resolve_relative_import(module: str, imported: str) -> str:
    if not imported.startswith("."):
        return imported
    level = len(imported) - len(imported.lstrip("."))
    tail = imported[level:]
    parts = module.split(".")
    if module.endswith(".__init__"):
        base_parts = parts[:-1]
    else:
        base_parts = parts[:-1]
    if level > len(base_parts):
        resolved_parts: list[str] = []
    else:
        resolved_parts = base_parts[: len(base_parts) - level + 1]
    if tail:
        resolved_parts.extend([part for part in tail.split(".") if part])
    return ".".join(part for part in resolved_parts if part)


def build_relationships(file_map: dict[str, FileInfo]) -> None:
    py_modules = {
        normalize_module(info.rel_path): info.rel_path
        for info in file_map.values()
        if info.ext == ".py"
    }
    for info in file_map.values():
        if info.ext != ".py":
            continue
        current_module = normalize_module(info.rel_path)
        imported_paths: set[str] = set()
        for imported in info.imports:
            resolved = resolve_relative_import(current_module, imported)
            target = py_modules.get(resolved)
            if target:
                imported_paths.add(target)
                file_map[target].imported_by.append(info.rel_path)
        info.imports = sorted(imported_paths)

    tests = [info for info in file_map.values() if info.rel_path.startswith("tests/")]
    for test_info in tests:
        test_name = Path(test_info.rel_path).stem
        suffix = test_name.replace("test_", "", 1)
        candidates: list[str] = []
        if suffix:
            for rel_path, info in file_map.items():
                stem = Path(rel_path).stem
                if rel_path.startswith("tests/"):
                    continue
                if stem == suffix or suffix in rel_path or stem in suffix:
                    candidates.append(rel_path)
        for candidate in sorted(dict.fromkeys(candidates))[:20]:
            test_info.references_tests.append(candidate)
            file_map[candidate].tests_for.append(test_info.rel_path)

    for info in file_map.values():
        info.imported_by = sorted(dict.fromkeys(info.imported_by))
        info.tests_for = sorted(dict.fromkeys(info.tests_for))
        info.references_tests = sorted(dict.fromkeys(info.references_tests))


def make_slug(rel_path: str) -> str:
    return rel_path.replace("/", "__").replace(".", "_")


def mermaid_edges(nodes: list[tuple[str, str]], edges: list[tuple[str, str, str]]) -> str:
    lines = ["```mermaid", "flowchart TD"]
    for node_id, label in nodes:
        lines.append(f'    {node_id}["{label}"]')
    for left, right, label in edges:
        if label:
            lines.append(f"    {left} -->|{label}| {right}")
        else:
            lines.append(f"    {left} --> {right}")
    lines.append("```")
    return "\n".join(lines)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_index(file_infos: list[FileInfo], counts: Counter[str]) -> None:
    top_files = sorted(file_infos, key=lambda item: item.line_count, reverse=True)[:25]
    content = [
        "# Generated Architecture Index",
        "",
        "This directory is a generated architecture and repository-intelligence snapshot for ClawLite_VikingEdition.",
        "",
        "## Outputs",
        "",
        "- `ARCHITECTURE_WALKTHROUGH.md`: long-form architecture narrative.",
        "- `ARCHITECTURE_FLOWCHARTS.md`: Mermaid flowcharts for the major subsystems.",
        "- `PROJECT_STRUCTURE_DATA.md`: repository structure, counts, hotspots, and data tables.",
        "- `per_file/**/READ_*.md`: descriptive notes for each code file.",
        "- `per_file/**/CONNECTIONS_*.md`: dependency and relationship notes for each code file.",
        "",
        "## Repository Counts",
        "",
    ]
    for key in sorted(counts):
        content.append(f"- `{key}`: {counts[key]} code file(s)")
    content.extend(
        [
            "",
            "## Largest Code Files",
            "",
        ]
    )
    for info in top_files:
        content.append(f"- `{info.rel_path}`: {info.line_count} line(s), {info.size_bytes} byte(s)")
    content.extend(
        [
            "",
            "## Per-File Documentation Inventory",
            "",
        ]
    )
    for info in file_infos:
        per_dir = Path(info.rel_path).parent.as_posix()
        content.append(
            f"- `{info.rel_path}` -> `per_file/{per_dir}/READ_{Path(info.rel_path).stem}.md` and `per_file/{per_dir}/CONNECTIONS_{Path(info.rel_path).stem}.md`"
        )
    write_text(OUTPUT_ROOT / "INDEX.md", "\n".join(content))


def subsystem_summary(file_infos: list[FileInfo]) -> dict[str, list[FileInfo]]:
    grouped: dict[str, list[FileInfo]] = defaultdict(list)
    for info in file_infos:
        grouped[info.area].append(info)
    return dict(sorted(grouped.items()))


def write_project_structure(file_infos: list[FileInfo]) -> None:
    grouped = subsystem_summary(file_infos)
    total_lines = sum(info.line_count for info in file_infos)
    longest = sorted(file_infos, key=lambda item: item.line_count, reverse=True)[:40]
    most_imported = sorted(
        [info for info in file_infos if info.ext == ".py"],
        key=lambda item: len(item.imported_by),
        reverse=True,
    )[:40]
    content = [
        "# Project Structure Data",
        "",
        "## Snapshot Summary",
        "",
        f"- Total code files: {len(file_infos)}",
        f"- Total code lines: {total_lines}",
        "",
        "## Subsystem Inventory",
        "",
    ]
    for area, infos in grouped.items():
        py_count = sum(1 for info in infos if info.ext == ".py")
        content.append(f"### {area}")
        content.append("")
        content.append(f"- Files: {len(infos)}")
        content.append(f"- Python modules: {py_count}")
        content.append(f"- Total lines: {sum(info.line_count for info in infos)}")
        content.append("- Representative files:")
        for info in sorted(infos, key=lambda item: item.line_count, reverse=True)[:8]:
            content.append(f"  - `{info.rel_path}` ({info.line_count} lines)")
        content.append("")
    content.extend(["## Largest Files", ""])
    for info in longest:
        content.append(
            f"- `{info.rel_path}`: {info.line_count} lines, {len(info.functions) + len(info.async_functions)} functions, {len(info.classes)} classes"
        )
    content.extend(["", "## Most Imported Python Modules", ""])
    for info in most_imported:
        content.append(
            f"- `{info.rel_path}`: imported by {len(info.imported_by)} file(s), owns {len(info.functions) + len(info.async_functions)} functions"
        )
    content.extend(["", "## Source/Test Pairings", ""])
    for info in sorted(file_infos, key=lambda item: item.rel_path):
        if info.tests_for:
            content.append(f"- `{info.rel_path}` is covered by {len(info.tests_for)} matching test file(s)")
            for test_path in info.tests_for[:10]:
                content.append(f"  - `{test_path}`")
    content.extend(["", "## Raw Manifest", "", "```json", json.dumps(
        [
            {
                "path": info.rel_path,
                "area": info.area,
                "ext": info.ext,
                "lines": info.line_count,
                "size_bytes": info.size_bytes,
                "imports": info.imports,
                "imported_by_count": len(info.imported_by),
                "tests_for": info.tests_for,
            }
            for info in file_infos
        ],
        indent=2,
    ), "```"])
    write_text(OUTPUT_ROOT / "PROJECT_STRUCTURE_DATA.md", "\n".join(content))


def write_architecture_walkthrough(file_infos: list[FileInfo]) -> None:
    grouped = subsystem_summary(file_infos)
    sections = [
        "# Massive Architecture Walkthrough",
        "",
        "## Executive View",
        "",
        "ClawLite_VikingEdition is a local-first Python autonomous-agent system with a layered design: configuration feeds the CLI and gateway surfaces; the gateway composes runtime state and control handlers; the core engine manages prompt construction, memory, tools, and subagents; runtime services add autonomy, supervision, and self-evolution; providers abstract LLM backends; channels carry inbound and outbound communication; tools expose guarded system capabilities; tests mirror almost every subsystem.",
        "",
        "The codebase is broad rather than minimal. It favors separate modules for operational responsibilities, especially in Telegram/channel handling, gateway runtime orchestration, memory internals, and provider integration. The package is therefore best understood as a control plane around a central engine rather than as a single monolithic chatbot process.",
        "",
        "## Top-Level Layers",
        "",
        "1. `clawlite/config`: schema, loading, health checks, and file watching.",
        "2. `clawlite/cli`: user-facing commands, onboarding, and operational helpers.",
        "3. `clawlite/gateway`: HTTP/WebSocket control plane, runtime assembly, dashboard state, diagnostics, and approval flows.",
        "4. `clawlite/core`: prompt building, memory, skills, subagents, and the main engine.",
        "5. `clawlite/runtime`: autonomy loop, supervisor, self-evolution, and telemetry helpers.",
        "6. `clawlite/providers`: model registry, auth adapters, failover, reliability, and probes.",
        "7. `clawlite/channels`: message transport adapters and the channel manager.",
        "8. `clawlite/tools`: built-in tool implementations plus registry and policy surfaces.",
        "9. `clawlite/scheduler`, `clawlite/jobs`, `clawlite/bus`, and `clawlite/session`: supporting runtime infrastructure.",
        "10. `clawlite/workspace` and `clawlite/skills`: workspace prompt files and skill packaging.",
        "",
        "## Subsystem Deep Dive",
        "",
    ]
    area_order = [
        "cli",
        "config",
        "gateway",
        "core",
        "runtime",
        "providers",
        "channels",
        "tools",
        "scheduler",
        "jobs",
        "bus",
        "session",
        "workspace",
        "skills",
        "dashboard",
        "scripts",
        "tests",
    ]
    for area in area_order:
        infos = grouped.get(area)
        if not infos:
            continue
        sections.append(f"### {area}")
        sections.append("")
        sections.append(
            f"This area contains {len(infos)} code file(s) and {sum(info.line_count for info in infos)} line(s)."
        )
        sections.append("")
        for info in sorted(infos, key=lambda item: item.line_count, reverse=True)[:12]:
            sections.append(f"- `{info.rel_path}`: {info.summary}")
        sections.append("")
        sections.append("Operational read:")
        sections.append(
            f"The `{area}` area has {sum(len(info.imports) for info in infos if info.ext == '.py')} internal Python dependency edge(s), "
            f"{sum(len(info.tests_for) for info in infos)} matched test relationship(s), and "
            f"{sum(len(info.functions) + len(info.async_functions) for info in infos)} discovered function definitions."
        )
        sections.append("")
    sections.extend(
        [
            "## Cross-Cutting Themes",
            "",
            "- The gateway is the main orchestration layer. It wires request handlers, runtime state, background services, diagnostics, dashboard payloads, tool approvals, and supervisor recovery.",
            "- Memory is a dedicated internal subsystem, not a helper. The `core/memory*.py` cluster is large enough to act as a mini-package for ingestion, retrieval, pruning, versioning, workflows, quality, policy, and reporting.",
            "- Telegram and Discord support are not thin integrations. The channel area contains protocol-specific logic for offsets, delivery, pairing, interactions, dedupe, runtime state, and transport behavior.",
            "- Runtime autonomy is separated from the gateway but tightly integrated with it. The runtime area owns long-lived loops and safety guards; the gateway area owns lifecycle startup and exposure.",
            "- Test coverage mirrors the package structure heavily, which makes the codebase navigable through adjacent tests.",
            "",
            "## Evidence-Backed Hotspots",
            "",
        ]
    )
    hotspots = sorted(file_infos, key=lambda item: (item.line_count, len(item.imported_by)), reverse=True)[:30]
    for info in hotspots:
        sections.append(
            f"- `{info.rel_path}`: {info.line_count} lines, {len(info.imported_by)} inbound dependency edge(s), {len(info.tests_for)} matching test file(s)"
        )
    sections.extend(
        [
            "",
            "## Generated Per-File Corpus",
            "",
            "A separate generated Markdown pair exists for every discovered code file:",
            "",
            "- `READ_<filename>.md` explains what the file contains and how to read it.",
            "- `CONNECTIONS_<filename>.md` records dependencies, dependents, and matched test relationships.",
            "",
            "These files are stored under `docs/generated_architecture/per_file/` in mirrored directory paths.",
        ]
    )
    write_text(OUTPUT_ROOT / "ARCHITECTURE_WALKTHROUGH.md", "\n".join(sections))


def write_flowcharts(file_infos: list[FileInfo]) -> None:
    area_nodes = []
    grouped = subsystem_summary(file_infos)
    for index, area in enumerate(grouped):
        area_nodes.append((f"A{index}", area))
    node_lookup = {label: node_id for node_id, label in area_nodes}

    area_edges_counter: Counter[tuple[str, str]] = Counter()
    for info in file_infos:
        for imported in info.imports:
            from_area = info.area
            to_area = grouped[file_map[imported].area][0].area if imported in file_map else classify_area(imported)
            if from_area != to_area:
                area_edges_counter[(from_area, to_area)] += 1

    area_edges = []
    for (left_area, right_area), count in sorted(area_edges_counter.items()):
        if left_area in node_lookup and right_area in node_lookup:
            area_edges.append((node_lookup[left_area], node_lookup[right_area], str(count)))

    gateway_nodes = [
        ("G1", "CLI"),
        ("G2", "Config"),
        ("G3", "Gateway"),
        ("G4", "Request Handlers"),
        ("G5", "Core Engine"),
        ("G6", "Tools"),
        ("G7", "Providers"),
        ("G8", "Memory"),
        ("G9", "Channels"),
        ("G10", "Runtime Loops"),
        ("G11", "Dashboard/API"),
    ]
    gateway_edges = [
        ("G1", "G2", "load"),
        ("G1", "G3", "start"),
        ("G2", "G3", "configure"),
        ("G3", "G4", "route"),
        ("G4", "G5", "invoke"),
        ("G5", "G6", "tool calls"),
        ("G5", "G7", "model access"),
        ("G5", "G8", "retrieve/store"),
        ("G3", "G9", "channel runtime"),
        ("G3", "G10", "spawn"),
        ("G3", "G11", "publish state"),
        ("G10", "G5", "background actions"),
    ]

    content = [
        "# Architecture Flowcharts",
        "",
        "## Subsystem Import Flow",
        "",
        mermaid_edges(area_nodes, area_edges),
        "",
        "## Runtime Control Plane",
        "",
        mermaid_edges(gateway_nodes, gateway_edges),
        "",
        "## Core Memory Cluster",
        "",
        mermaid_edges(
            [
                ("M1", "engine.py"),
                ("M2", "prompt.py"),
                ("M3", "memory.py"),
                ("M4", "memory_ingest.py"),
                ("M5", "memory_retrieval.py"),
                ("M6", "memory_search.py"),
                ("M7", "memory_workflows.py"),
                ("M8", "memory_quality.py"),
                ("M9", "memory_prune.py"),
                ("M10", "memory_versions.py"),
            ],
            [
                ("M1", "M2", "context"),
                ("M1", "M3", "memory facade"),
                ("M3", "M4", "ingest"),
                ("M3", "M5", "retrieve"),
                ("M5", "M6", "search"),
                ("M3", "M7", "maintenance"),
                ("M7", "M8", "quality"),
                ("M7", "M9", "prune"),
                ("M7", "M10", "version"),
            ],
        ),
        "",
        "## Channel and Runtime Flow",
        "",
        mermaid_edges(
            [
                ("C1", "Inbound Channel"),
                ("C2", "Channel Manager"),
                ("C3", "Gateway"),
                ("C4", "Core Engine"),
                ("C5", "Tool/Memory/Provider"),
                ("C6", "Outbound Adapter"),
                ("C7", "Supervisor"),
            ],
            [
                ("C1", "C2", "receive"),
                ("C2", "C3", "dispatch"),
                ("C3", "C4", "session request"),
                ("C4", "C5", "execute"),
                ("C4", "C6", "response"),
                ("C7", "C2", "restart/recover"),
                ("C7", "C3", "diagnostics"),
            ],
        ),
    ]
    write_text(OUTPUT_ROOT / "ARCHITECTURE_FLOWCHARTS.md", "\n".join(content))


def limited_list(items: list[str], limit: int = 20) -> list[str]:
    return items[:limit]


def write_per_file_docs(file_infos: list[FileInfo]) -> None:
    for info in file_infos:
        relative_parent = Path(info.rel_path).parent
        read_path = PER_FILE_ROOT / relative_parent / f"READ_{Path(info.rel_path).stem}.md"
        connections_path = PER_FILE_ROOT / relative_parent / f"CONNECTIONS_{Path(info.rel_path).stem}.md"
        header = [
            f"# READ {info.rel_path}",
            "",
            "## Identity",
            "",
            f"- Path: `{info.rel_path}`",
            f"- Area: `{info.area}`",
            f"- Extension: `{info.ext}`",
            f"- Lines: {info.line_count}",
            f"- Size bytes: {info.size_bytes}",
            f"- SHA1: `{info.sha1}`",
            "",
            "## Summary",
            "",
            info.summary,
            "",
            "## Structural Data",
            "",
            f"- Classes: {len(info.classes)}",
            f"- Functions: {len(info.functions)}",
            f"- Async functions: {len(info.async_functions)}",
            f"- Constants: {len(info.constants)}",
            f"- Internal imports: {len(info.imports)}",
            f"- Imported by: {len(info.imported_by)}",
            f"- Matching tests: {len(info.tests_for)}",
            "",
        ]
        if info.classes:
            header.append("## Classes")
            header.append("")
            header.extend(f"- `{item}`" for item in limited_list(info.classes, 100))
            header.append("")
        if info.functions or info.async_functions:
            header.append("## Functions")
            header.append("")
            header.extend(f"- `{item}`" for item in limited_list(info.functions, 200))
            header.extend(f"- `{item}` (async)" for item in limited_list(info.async_functions, 200))
            header.append("")
        if info.constants:
            header.append("## Constants")
            header.append("")
            header.extend(f"- `{item}`" for item in limited_list(info.constants, 100))
            header.append("")
        if info.string_markers:
            header.append("## Notable String Markers")
            header.append("")
            header.extend(f"- `{item}`" for item in info.string_markers)
            header.append("")
        if info.notes:
            header.append("## Notes")
            header.append("")
            header.extend(f"- {item}" for item in info.notes)
            header.append("")
        header.extend(
            [
                "## Reading Guidance",
                "",
                f"- Start with the file summary, then scan the symbols list for `{info.rel_path}`.",
                f"- Cross-reference `CONNECTIONS_{Path(info.rel_path).stem}.md` to see how this file fits into the wider system.",
                "",
            ]
        )
        write_text(read_path, "\n".join(header))

        edges = []
        nodes = [("N0", Path(info.rel_path).name)]
        seen_nodes = {info.rel_path: "N0"}
        for idx, dep in enumerate(limited_list(info.imports, 10), start=1):
            node_id = f"D{idx}"
            seen_nodes[dep] = node_id
            nodes.append((node_id, dep))
            edges.append(("N0", node_id, "imports"))
        base = len(nodes)
        for idx, dep in enumerate(limited_list(info.imported_by, 10), start=1):
            node_id = f"R{idx}"
            seen_nodes[dep] = node_id
            nodes.append((node_id, dep))
            edges.append((node_id, "N0", "uses"))
        for idx, dep in enumerate(limited_list(info.tests_for, 10), start=1):
            node_id = f"T{idx}"
            nodes.append((node_id, dep))
            edges.append((node_id, "N0", "tests"))
        mermaid = mermaid_edges(nodes, edges)
        connection_lines = [
            f"# CONNECTIONS {info.rel_path}",
            "",
            "## Relationship Summary",
            "",
            f"- Imports {len(info.imports)} internal file(s).",
            f"- Imported by {len(info.imported_by)} internal file(s).",
            f"- Matched test files: {len(info.tests_for)}.",
            "",
        ]
        if info.imports:
            connection_lines.append("## Internal Imports")
            connection_lines.append("")
            connection_lines.extend(f"- `{item}`" for item in limited_list(info.imports, 100))
            connection_lines.append("")
        if info.imported_by:
            connection_lines.append("## Reverse Dependencies")
            connection_lines.append("")
            connection_lines.extend(f"- `{item}`" for item in limited_list(info.imported_by, 100))
            connection_lines.append("")
        if info.tests_for:
            connection_lines.append("## Matching Tests")
            connection_lines.append("")
            connection_lines.extend(f"- `{item}`" for item in limited_list(info.tests_for, 100))
            connection_lines.append("")
        if info.references_tests:
            connection_lines.append("## Candidate Sources Exercised By This Test File")
            connection_lines.append("")
            connection_lines.extend(f"- `{item}`" for item in limited_list(info.references_tests, 100))
            connection_lines.append("")
        connection_lines.extend(["## Mermaid", "", mermaid])
        write_text(connections_path, "\n".join(connection_lines))


def main() -> None:
    global file_map
    files = discover_files()
    file_infos = [build_file_info(path) for path in files]
    file_map = {info.rel_path: info for info in file_infos}
    build_relationships(file_map)

    if OUTPUT_ROOT.exists():
        for existing in sorted(OUTPUT_ROOT.rglob("*"), reverse=True):
            if existing.is_file():
                existing.unlink()
            elif existing.is_dir():
                existing.rmdir()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    counts = Counter(info.area for info in file_infos)
    write_index(file_infos, counts)
    write_project_structure(file_infos)
    write_architecture_walkthrough(file_infos)
    write_flowcharts(file_infos)
    write_per_file_docs(file_infos)


if __name__ == "__main__":
    main()
