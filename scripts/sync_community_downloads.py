#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from clawlite.skills.registry import SKILLS


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    stats_path = repo_root / "hub" / "marketplace" / "community_downloads.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, int] = {}
    if stats_path.exists():
        raw = json.loads(stats_path.read_text(encoding="utf-8"))
        skills = raw.get("skills", {})
        if isinstance(skills, dict):
            for slug, value in skills.items():
                try:
                    existing[str(slug)] = max(0, int(value))
                except (TypeError, ValueError):
                    continue

    merged = {slug: existing.get(slug, 0) for slug in sorted(SKILLS.keys())}
    total = sum(merged.values())
    payload = {
        "schema_version": "1.0",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_downloads": total,
        "skills": merged,
    }
    stats_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"synced {len(merged)} skills -> {stats_path}")


if __name__ == "__main__":
    main()
