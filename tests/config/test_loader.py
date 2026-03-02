from __future__ import annotations

import json
from pathlib import Path

from clawlite.config.loader import load_config


def test_load_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.provider.model
    assert cfg.gateway.port == 8787


def test_load_config_file_and_env_override(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "provider": {"model": "openai/gpt-4.1-mini"},
                "gateway": {"port": 9999},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAWLITE_GATEWAY_PORT", "7777")
    cfg = load_config(path)
    assert cfg.provider.model == "openai/gpt-4.1-mini"
    assert cfg.gateway.port == 7777


def test_load_config_tools_flags(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "tools": {
                    "restrictToWorkspace": True,
                    "exec": {
                        "pathAppend": "/usr/sbin",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.tools.restrict_to_workspace is True
    assert cfg.tools.exec.path_append == "/usr/sbin"
