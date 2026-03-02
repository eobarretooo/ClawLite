from __future__ import annotations

import json
from pathlib import Path

from clawlite.cli.commands import main


def test_cli_onboard_generates_workspace_files(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "workspace_path": str(tmp_path / "workspace"),
                "state_path": str(tmp_path / "state"),
                "provider": {"model": "openai/gpt-4o-mini"},
            }
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--config",
            str(config_path),
            "onboard",
            "--assistant-name",
            "Atlas",
            "--user-name",
            "Eder",
        ]
    )
    assert rc == 0
    assert (tmp_path / "workspace" / "IDENTITY.md").exists()
    content = (tmp_path / "workspace" / "IDENTITY.md").read_text(encoding="utf-8")
    assert "Atlas" in content
