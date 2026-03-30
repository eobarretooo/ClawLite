from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from clawlite.config.loader import save_raw_config_payload
from clawlite.config.schema import AppConfig
from clawlite.gateway.restart_sentinel import consume_restart_sentinel
from clawlite.tools.base import ToolContext
from clawlite.tools.gateway_admin import GatewayAdminTool


def test_gateway_admin_config_get_redacts_sensitive_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload(
        {
            "provider": {
                "litellm_api_key": "secret-key",
            },
            "channels": {
                "telegram": {
                    "token": "telegram-secret",
                }
            },
        },
        path=config_path,
    )

    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {"action": "config_get"},
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["effective_config"]["provider"]["litellm_api_key"] == "***"
        assert payload["effective_config"]["channels"]["telegram"]["token"] == "***"

    asyncio.run(_scenario())


def test_gateway_admin_config_schema_lookup_returns_safe_leaf_metadata(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload(
        {
            "tools": {
                "default_timeout_s": 44,
                "web": {
                    "timeout": 12,
                },
            }
        },
        path=config_path,
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {"action": "config_schema_lookup", "path": "tools.default_timeout_s"},
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["ok"] is True
        assert payload["action"] == "config_schema_lookup"
        assert payload["path"] == "tools.default_timeout_s"
        assert payload["type"] == "number"
        assert payload["status"] == "editable"
        assert payload["editable_via_gateway_admin"] is True
        assert payload["effective_value"] == 44
        assert payload["target_value"] == 44
        assert payload["default_value"] == 20.0
        assert payload["children"] == []

    asyncio.run(_scenario())


def test_gateway_admin_config_schema_lookup_marks_protected_container_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload(
        {
            "tools": {
                "web": {
                    "timeout": 12,
                    "proxy": "http://localhost:8080",
                },
            }
        },
        path=config_path,
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {"action": "config_schema_lookup", "path": "tools.web"},
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["status"] == "container"
        assert payload["reason"] == "mixed_descendants"
        assert payload["editable_via_gateway_admin"] is False
        children = {row["path"]: row for row in payload["children"]}
        assert children["tools.web.timeout"]["status"] == "editable"
        assert children["tools.web.proxy"]["status"] == "protected"

    asyncio.run(_scenario())


def test_gateway_admin_config_patch_and_restart_writes_config_and_sentinel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)

    scheduled: dict[str, object] = {}

    def _fake_schedule(*, delay_s: float = 0.0, reason: str = "", execv_fn=None):
        del execv_fn
        scheduled.update(
            {
                "ok": True,
                "scheduled": True,
                "coalesced": False,
                "delay_s": delay_s,
                "reason": reason,
            }
        )
        return dict(scheduled)

    monkeypatch.setattr("clawlite.tools.gateway_admin.schedule_gateway_restart", _fake_schedule)

    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_patch_and_restart",
                    "patch": {"tools": {"default_timeout_s": 44}},
                    "note": "Enabled the requested tool setting.",
                    "restart_delay_s": 2.0,
                },
                ToolContext(
                    session_id="telegram:chat42:topic:9",
                    channel="telegram",
                    user_id="chat42",
                ),
            )
        )
        assert payload["ok"] is True
        assert payload["changed"] is True
        assert payload["restart"]["reason"] == "config_patch_and_restart"
        assert payload["changed_paths"] == ["tools.default_timeout_s"]

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["default_timeout_s"] == 44
    sentinel = consume_restart_sentinel(tmp_path / "state")
    assert sentinel is not None
    assert sentinel["channel"] == "telegram"
    assert sentinel["target"] == "telegram:chat42:topic:9"
    assert sentinel["note"] == "Enabled the requested tool setting."
    assert sentinel["changed_paths"] == ["tools.default_timeout_s"]
    assert sentinel["metadata"]["message_thread_id"] == 9
    assert scheduled["delay_s"] == 2.0


def test_gateway_admin_config_patch_and_restart_allows_dynamic_tool_timeout_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)

    monkeypatch.setattr(
        "clawlite.tools.gateway_admin.schedule_gateway_restart",
        lambda **kwargs: {"ok": True, "scheduled": True, "coalesced": False, **kwargs},
    )

    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_patch_and_restart",
                    "patch": {"tools": {"timeouts": {"web_fetch": 33}}},
                    "note": "Raised the tool timeout.",
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["ok"] is True
        assert payload["changed"] is True
        assert payload["changed_paths"] == ["tools.timeouts.web_fetch"]

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["timeouts"]["web_fetch"] == 33
    sentinel = consume_restart_sentinel(tmp_path / "state")
    assert sentinel is not None
    assert sentinel["changed_paths"] == ["tools.timeouts.web_fetch"]


def test_gateway_admin_config_intent_and_restart_sets_default_tool_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)
    monkeypatch.setattr(
        "clawlite.tools.gateway_admin.schedule_gateway_restart",
        lambda **kwargs: {"ok": True, "scheduled": True, "coalesced": False, **kwargs},
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_and_restart",
                    "intent": "set_default_tool_timeout",
                    "timeout_s": 31,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_intent_and_restart"
        assert payload["intent"] == "set_default_tool_timeout"
        assert payload["resolved_patch"] == {"tools": {"default_timeout_s": 31.0}}

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["default_timeout_s"] == 31


def test_gateway_admin_config_intent_and_restart_sets_named_tool_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)
    monkeypatch.setattr(
        "clawlite.tools.gateway_admin.schedule_gateway_restart",
        lambda **kwargs: {"ok": True, "scheduled": True, "coalesced": False, **kwargs},
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_and_restart",
                    "intent": "set_tool_timeout",
                    "tool_name": "web-fetch",
                    "timeout_s": 33,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["intent"] == "set_tool_timeout"
        assert payload["changed_paths"] == ["tools.timeouts.web_fetch"]

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["timeouts"]["web_fetch"] == 33


def test_gateway_admin_config_intent_and_restart_updates_loop_detection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)
    monkeypatch.setattr(
        "clawlite.tools.gateway_admin.schedule_gateway_restart",
        lambda **kwargs: {"ok": True, "scheduled": True, "coalesced": False, **kwargs},
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_and_restart",
                    "intent": "set_loop_detection",
                    "enabled": True,
                    "repeat_threshold": 4,
                    "critical_threshold": 7,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["intent"] == "set_loop_detection"
        assert payload["changed_paths"] == [
            "tools.loop_detection.critical_threshold",
            "tools.loop_detection.enabled",
            "tools.loop_detection.repeat_threshold",
        ]

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["loop_detection"]["enabled"] is True
    assert saved["tools"]["loop_detection"]["repeat_threshold"] == 4
    assert saved["tools"]["loop_detection"]["critical_threshold"] == 7


def test_gateway_admin_config_intent_and_restart_rejects_unsupported_intent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload({}, path=config_path)
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        with pytest.raises(RuntimeError, match="gateway_admin_intent_unsupported:enable_exec"):
            await tool.run(
                {
                    "action": "config_intent_and_restart",
                    "intent": "enable_exec",
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )

    asyncio.run(_scenario())


def test_gateway_admin_rejects_background_sessions(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload({}, path=config_path)
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        for session_id in ("autonomy:system", "heartbeat:system", "bootstrap:system", "cli:owner:sub:1"):
            with pytest.raises(RuntimeError, match="gateway_admin_not_allowed_in_background_or_subagent_sessions"):
                await tool.run(
                    {"action": "restart_gateway"},
                    ToolContext(session_id=session_id, channel="telegram", user_id="chat42"),
                )

    asyncio.run(_scenario())


def test_gateway_admin_rejects_when_restart_already_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )
    monkeypatch.setattr("clawlite.tools.gateway_admin.gateway_restart_pending", lambda: True)

    async def _scenario() -> None:
        with pytest.raises(RuntimeError, match="gateway_restart_already_pending"):
            await tool.run(
                {
                    "action": "config_patch_and_restart",
                    "patch": {"tools": {"default_timeout_s": 44}},
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )

    asyncio.run(_scenario())


def test_gateway_admin_rolls_back_config_when_sentinel_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )
    monkeypatch.setattr(
        "clawlite.tools.gateway_admin.write_restart_sentinel",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("sentinel_write_failed")),
    )

    async def _scenario() -> None:
        with pytest.raises(RuntimeError, match="sentinel_write_failed"):
            await tool.run(
                {
                    "action": "config_patch_and_restart",
                    "patch": {"tools": {"default_timeout_s": 44}},
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["default_timeout_s"] == 20.0
    assert consume_restart_sentinel(tmp_path / "state") is None


def test_gateway_admin_config_patch_and_restart_rejects_protected_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    initial = AppConfig(
        workspace_path=str(tmp_path / "workspace"),
        state_path=str(tmp_path / "state"),
        channels={},
    )
    save_raw_config_payload(initial.to_dict(), path=config_path)
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        with pytest.raises(RuntimeError, match="gateway_admin_patch_path_protected:tools\\.web\\.proxy"):
            await tool.run(
                {
                    "action": "config_patch_and_restart",
                    "patch": {"tools": {"web": {"proxy": "http://localhost:8080"}}},
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["web"]["proxy"] == ""
    assert consume_restart_sentinel(tmp_path / "state") is None
