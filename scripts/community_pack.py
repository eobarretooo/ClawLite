#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "templates" / "community"


def _load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _render(base: str, mapping: dict[str, str]) -> str:
    out = base
    for k, v in mapping.items():
        out = out.replace(f"{{{{{k}}}}}", v)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Gera pacote de comunicação da milestone (Reddit + checklists).")
    p.add_argument("--version", required=True, help="Ex: v0.5.0")
    p.add_argument("--date", required=True, help="Ex: 2026-02-27")
    p.add_argument("--subreddit", default="selfhosted")
    p.add_argument("--repo-url", default="https://github.com/eobarretooo/ClawLite")
    p.add_argument("--release-url", default="https://github.com/eobarretooo/ClawLite/releases")
    p.add_argument("--docs-url", default="https://eobarretooo.github.io/ClawLite/")
    p.add_argument("--highlights", nargs="*", default=[])
    p.add_argument("--out-dir", default=None)
    args = p.parse_args()

    highlights = (args.highlights + ["(preencher)", "(preencher)", "(preencher)"])[:3]

    target = Path(args.out_dir) if args.out_dir else (ROOT / "tmp" / "community" / args.version)
    target.mkdir(parents=True, exist_ok=True)

    mapping = {
        "VERSION": args.version,
        "DATE": args.date,
        "SUBREDDIT": args.subreddit,
        "REPO_URL": args.repo_url,
        "RELEASE_URL": args.release_url,
        "DOCS_URL": args.docs_url,
        "HIGHLIGHT_1": highlights[0],
        "HIGHLIGHT_2": highlights[1],
        "HIGHLIGHT_3": highlights[2],
        "PRACTICAL_1": "(preencher)",
        "PRACTICAL_2": "(preencher)",
        "NEXT_1": "(preencher)",
        "NEXT_2": "(preencher)",
    }

    files = {
        "reddit_milestone.md": TEMPLATES_DIR / "milestone_reddit.md",
        "checklist_github_release.md": TEMPLATES_DIR / "checklist_github_release.md",
        "checklist_threads_post.md": TEMPLATES_DIR / "checklist_threads_post.md",
    }

    for output_name, template_path in files.items():
        rendered = _render(_load(template_path), mapping)
        (target / output_name).write_text(rendered, encoding="utf-8")

    print(f"✅ Pacote de comunidade gerado em: {target}")
    for name in files:
        print(f"- {target / name}")


if __name__ == "__main__":
    main()
