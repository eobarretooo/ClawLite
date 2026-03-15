from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from clawlite.config.health import config_health
from clawlite.config.schema import AppConfig


def _cfg_from_dict(data: dict) -> AppConfig:
    return AppConfig.model_validate(data)


def test_health_ok_with_key_and_writable_path(tmp_path):
    cfg = _cfg_from_dict({
        "provider": {"litellm_api_key": "sk-test", "model": "gpt-4o"},
        "workspace_path": str(tmp_path),
        "gateway": {"port": 0},
    })
    result = config_health(cfg)
    assert result["ok"] is True
    assert result["issues"] == []


def test_health_missing_api_key_not_local():
    cfg = _cfg_from_dict({
        "provider": {"litellm_api_key": "", "model": "gpt-4o"},
        "workspace_path": "/tmp",
        "gateway": {"port": 0},
    })
    result = config_health(cfg)
    assert result["ok"] is False
    assert any("litellm_api_key" in issue for issue in result["issues"])


def test_health_local_model_no_key_needed():
    cfg = _cfg_from_dict({
        "provider": {"litellm_api_key": "", "model": "ollama/llama3"},
        "workspace_path": "/tmp",
        "gateway": {"port": 0},
    })
    result = config_health(cfg)
    api_key_issues = [i for i in result["issues"] if "litellm_api_key" in i]
    assert api_key_issues == []


@pytest.mark.skipif(os.getuid() == 0, reason="root bypasses filesystem permission checks")
def test_health_unwritable_workspace(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o444)
    try:
        cfg = _cfg_from_dict({
            "provider": {"litellm_api_key": "sk-test", "model": "gpt-4o"},
            "workspace_path": str(locked),
            "gateway": {"port": 0},
        })
        result = config_health(cfg)
        assert result["ok"] is False
        assert any("not writable" in issue for issue in result["issues"])
    finally:
        locked.chmod(0o755)


def test_health_empty_workspace_bypasses_schema():
    """Use model_construct to bypass Pydantic's default-fill validator."""
    base = AppConfig.model_validate({
        "provider": {"litellm_api_key": "sk-test", "model": "gpt-4o"},
        "gateway": {"port": 0},
    })
    # Bypass schema validator that would fill in default workspace_path
    cfg = base.model_copy(update={"workspace_path": ""})
    result = config_health(cfg)
    assert any("workspace_path" in issue for issue in result["issues"])


def test_health_port_in_use(tmp_path):
    # Bind a port WITHOUT SO_REUSEADDR — matches health.py's _port_available
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    occupied_port = s.getsockname()[1]
    try:
        cfg = _cfg_from_dict({
            "provider": {"litellm_api_key": "sk-test", "model": "gpt-4o"},
            "workspace_path": str(tmp_path),
            "gateway": {"port": occupied_port},
        })
        result = config_health(cfg)
        assert any(str(occupied_port) in issue for issue in result["issues"])
    finally:
        s.close()
