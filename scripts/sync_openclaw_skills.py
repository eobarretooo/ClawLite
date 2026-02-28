#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def adapt_text(text: str) -> str:
    # Metadata provider key
    text = re.sub(r'"openclaw"\s*:', '"clawdbot":', text)

    # Paths and env
    text = text.replace("~/.openclaw", "~/.clawlite")
    text = text.replace("OPENCLAW_", "CLAWLITE_")

    # Brand and command names
    text = re.sub(r"\bOpenClaw\b", "ClawLite", text)
    text = re.sub(r"\bopenclaw\b", "clawlite", text)

    # Docs domain where command name appears in URLs can remain; no forced rewrites.

    note = (
        "\n\n## ClawLite Adaptation\n"
        "Conteúdo sincronizado da skill equivalente do OpenClaw e adaptado para nomenclatura/fluxo do ClawLite.\n"
        "Quando algum comando depender de backend não disponível no ambiente atual, use `clawlite skill search` para alternativas.\n"
    )
    if "## ClawLite Adaptation" not in text:
        text = text.rstrip() + note + "\n"
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Sincroniza SKILL.md do OpenClaw para ClawLite com adaptação de nomenclatura.")
    parser.add_argument("--openclaw-skills", default="/root/projetos/openclaw/skills")
    parser.add_argument("--clawlite-skills", default="/root/projetos/ClawLite/skills")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    oc_root = Path(args.openclaw_skills)
    cl_root = Path(args.clawlite_skills)

    if not oc_root.exists():
        raise SystemExit(f"OpenClaw skills dir não encontrado: {oc_root}")

    updated = 0
    created = 0

    for src in sorted(oc_root.glob("*/SKILL.md")):
        slug = src.parent.name
        dst = cl_root / slug / "SKILL.md"
        dst.parent.mkdir(parents=True, exist_ok=True)

        raw = src.read_text(encoding="utf-8")
        adapted = adapt_text(raw)

        old = dst.read_text(encoding="utf-8") if dst.exists() else ""
        if old == adapted:
            continue

        if not args.dry_run:
            dst.write_text(adapted, encoding="utf-8")

        if old:
            updated += 1
        else:
            created += 1

    print(f"created={created} updated={updated} total_changed={created+updated}")


if __name__ == "__main__":
    main()
