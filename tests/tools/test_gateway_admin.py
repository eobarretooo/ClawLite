from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from clawlite.config.loader import load_config, save_raw_config_payload
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


def test_gateway_admin_config_intent_catalog_lists_safe_intents(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload({}, path=config_path)
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {"action": "config_intent_catalog"},
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_intent_catalog"
        assert payload["count"] >= 9
        rows = {row["name"]: row for row in payload["intents"]}
        assert rows["set_gateway_heartbeat"]["paths"] == ["gateway.heartbeat.enabled", "gateway.heartbeat.interval_s"]
        assert rows["set_gateway_heartbeat"]["required_args"] == []
        assert rows["set_gateway_heartbeat"]["requires_any_of"] == ["enabled", "interval_s"]
        assert rows["set_web_private_address_blocking"]["paths"] == ["tools.web.block_private_addresses"]
        assert rows["set_web_private_address_blocking"]["required_args"] == ["enabled"]
        assert rows["set_web_private_address_blocking"]["requires_any_of"] == []
        assert rows["set_web_private_address_blocking"]["preview_action"] == "config_intent_preview"
        assert rows["set_web_private_address_blocking"]["apply_action"] == "config_intent_and_restart"
        assert rows["set_loop_detection"]["required_args"] == []
        assert rows["set_loop_detection"]["requires_any_of"] == [
            "enabled",
            "history_size",
            "repeat_threshold",
            "critical_threshold",
        ]
        assert rows["set_web_timeouts"]["requires_any_of"] == ["timeout_s", "search_timeout_s"]

    asyncio.run(_scenario())


def test_gateway_admin_config_intent_catalog_can_filter_one_intent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload({}, path=config_path)
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {"action": "config_intent_catalog", "intent": "set_web_content_budget"},
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_intent_catalog"
        assert payload["intent"] == "set_web_content_budget"
        assert payload["count"] == 1
        assert payload["intents"][0]["name"] == "set_web_content_budget"
        assert payload["intents"][0]["paths"] == ["tools.web.max_chars"]

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


def test_gateway_admin_config_intent_preview_reports_web_fetch_patch_without_writing(
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
        lambda **kwargs: (_ for _ in ()).throw(AssertionError(f"restart should not be scheduled: {kwargs}")),
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    before = json.loads(config_path.read_text(encoding="utf-8"))

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_preview",
                    "intent": "set_web_fetch_limits",
                    "timeout_s": 18,
                    "search_timeout_s": 11,
                    "max_redirects": 7,
                    "max_chars": 16000,
                    "block_private_addresses": False,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_intent_preview"
        assert payload["intent"] == "set_web_fetch_limits"
        assert payload["preview_only"] is True
        assert payload["preview_scope"] == "config_intent:set_web_fetch_limits"
        assert len(payload["preview_basis_hash"]) == 64
        assert len(payload["preview_token"]) == 64
        assert payload["restart_required"] is True
        assert payload["would_change"] is True
        assert payload["changed_paths"] == [
            "tools.web.block_private_addresses",
            "tools.web.max_chars",
            "tools.web.max_redirects",
            "tools.web.search_timeout",
            "tools.web.timeout",
        ]
        assert payload["resolved_patch"] == {
            "tools": {
                "web": {
                    "timeout": 18.0,
                    "search_timeout": 11.0,
                    "max_redirects": 7,
                    "max_chars": 16000,
                    "block_private_addresses": False,
                }
            }
        }
        changes = {row["path"]: row for row in payload["changes"]}
        assert changes["tools.web.timeout"]["effective_value"] == 15.0
        assert changes["tools.web.timeout"]["effective_next_value"] == 18.0
        assert changes["tools.web.block_private_addresses"]["effective_value"] is True
        assert changes["tools.web.block_private_addresses"]["effective_next_value"] is False

    asyncio.run(_scenario())

    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert after == before
    assert consume_restart_sentinel(tmp_path / "state") is None


def test_gateway_admin_config_intent_preview_reports_gateway_heartbeat_without_writing(
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
        lambda **kwargs: (_ for _ in ()).throw(AssertionError(f"restart should not be scheduled: {kwargs}")),
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    before = json.loads(config_path.read_text(encoding="utf-8"))

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_preview",
                    "intent": "set_gateway_heartbeat",
                    "enabled": False,
                    "interval_s": 2400,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_intent_preview"
        assert payload["intent"] == "set_gateway_heartbeat"
        assert payload["preview_scope"] == "config_intent:set_gateway_heartbeat"
        assert payload["changed_paths"] == [
            "gateway.heartbeat.enabled",
            "gateway.heartbeat.interval_s",
            "scheduler.heartbeat_interval_seconds",
        ]
        changes = {row["path"]: row for row in payload["changes"]}
        assert changes["gateway.heartbeat.enabled"]["effective_value"] is True
        assert changes["gateway.heartbeat.enabled"]["effective_next_value"] is False
        assert changes["gateway.heartbeat.interval_s"]["effective_value"] == 1800
        assert changes["gateway.heartbeat.interval_s"]["effective_next_value"] == 2400
        assert changes["scheduler.heartbeat_interval_seconds"]["effective_value"] == 1800
        assert changes["scheduler.heartbeat_interval_seconds"]["effective_next_value"] == 2400

    asyncio.run(_scenario())

    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert after == before
    assert consume_restart_sentinel(tmp_path / "state") is None


def test_gateway_admin_config_patch_preview_reports_dynamic_timeout_without_writing(
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
        lambda **kwargs: (_ for _ in ()).throw(AssertionError(f"restart should not be scheduled: {kwargs}")),
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    before = json.loads(config_path.read_text(encoding="utf-8"))

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_patch_preview",
                    "patch": {"tools": {"timeouts": {"web_fetch": 33}}},
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_patch_preview"
        assert payload["preview_only"] is True
        assert payload["preview_scope"] == "config_patch"
        assert len(payload["preview_basis_hash"]) == 64
        assert len(payload["preview_token"]) == 64
        assert payload["restart_required"] is True
        assert payload["would_change"] is True
        assert payload["changed_paths"] == ["tools.timeouts.web_fetch"]
        assert payload["resolved_patch"] == {"tools": {"timeouts": {"web_fetch": 33}}}
        assert payload["note"] == "Applied the requested config change for `tools.timeouts.web_fetch`."
        changes = {row["path"]: row for row in payload["changes"]}
        assert changes["tools.timeouts.web_fetch"]["effective_value_present"] is False
        assert changes["tools.timeouts.web_fetch"]["effective_next_value"] == 33

    asyncio.run(_scenario())

    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert after == before
    assert consume_restart_sentinel(tmp_path / "state") is None


def test_gateway_admin_config_intent_preview_reports_web_timeouts_without_writing(
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
        lambda **kwargs: (_ for _ in ()).throw(AssertionError(f"restart should not be scheduled: {kwargs}")),
    )
    tool = GatewayAdminTool(
        config_path=config_path,
        config_profile=None,
        state_path=tmp_path / "state",
    )

    before = json.loads(config_path.read_text(encoding="utf-8"))

    async def _scenario() -> None:
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_preview",
                    "intent": "set_web_timeouts",
                    "timeout_s": 18,
                    "search_timeout_s": 11,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["intent"] == "set_web_timeouts"
        assert payload["preview_scope"] == "config_intent:set_web_timeouts"
        assert len(payload["preview_token"]) == 64
        assert payload["changed_paths"] == ["tools.web.search_timeout", "tools.web.timeout"]
        changes = {row["path"]: row for row in payload["changes"]}
        assert changes["tools.web.timeout"]["effective_next_value"] == 18.0
        assert changes["tools.web.search_timeout"]["effective_next_value"] == 11.0

    asyncio.run(_scenario())

    after = json.loads(config_path.read_text(encoding="utf-8"))
    assert after == before
    assert consume_restart_sentinel(tmp_path / "state") is None


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


def test_gateway_admin_config_intent_and_restart_updates_gateway_heartbeat(
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
                    "intent": "set_gateway_heartbeat",
                    "enabled": False,
                    "interval_s": 2400,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_intent_and_restart"
        assert payload["intent"] == "set_gateway_heartbeat"
        assert payload["changed_paths"] == [
            "gateway.heartbeat.enabled",
            "gateway.heartbeat.interval_s",
            "scheduler.heartbeat_interval_seconds",
        ]
        assert payload["note"] == "Updated the gateway heartbeat settings."
        assert payload["resolved_patch"] == {
            "gateway": {"heartbeat": {"enabled": False, "interval_s": 2400}},
            "scheduler": {"heartbeat_interval_seconds": 2400},
        }

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["gateway"]["heartbeat"]["enabled"] is False
    assert saved["gateway"]["heartbeat"]["interval_s"] == 2400
    assert saved["scheduler"]["heartbeat_interval_seconds"] == 2400
    sentinel = consume_restart_sentinel(tmp_path / "state")
    assert sentinel is not None
    assert sentinel["changed_paths"] == [
        "gateway.heartbeat.enabled",
        "gateway.heartbeat.interval_s",
        "scheduler.heartbeat_interval_seconds",
    ]


def test_gateway_admin_config_intent_and_restart_syncs_legacy_scheduler_heartbeat_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    save_raw_config_payload(
        {
            "workspace_path": str(tmp_path / "workspace"),
            "state_path": str(tmp_path / "state"),
            "scheduler": {"heartbeat_interval_seconds": 9999},
            "channels": {},
        },
        path=config_path,
    )
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
        preview = json.loads(
            await tool.run(
                {
                    "action": "config_intent_preview",
                    "intent": "set_gateway_heartbeat",
                    "interval_s": 1800,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert preview["changed_paths"] == [
            "gateway.heartbeat.interval_s",
            "scheduler.heartbeat_interval_seconds",
        ]
        changes = {row["path"]: row for row in preview["changes"]}
        assert changes["gateway.heartbeat.interval_s"]["effective_value"] == 9999
        assert changes["gateway.heartbeat.interval_s"]["effective_next_value"] == 1800
        assert changes["scheduler.heartbeat_interval_seconds"]["effective_value"] == 9999
        assert changes["scheduler.heartbeat_interval_seconds"]["effective_next_value"] == 1800

        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_and_restart",
                    "intent": "set_gateway_heartbeat",
                    "interval_s": 1800,
                    "preview_token": preview["preview_token"],
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["changed"] is True
        assert payload["resolved_patch"] == {
            "gateway": {"heartbeat": {"interval_s": 1800}},
            "scheduler": {"heartbeat_interval_seconds": 1800},
        }

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["gateway"]["heartbeat"]["interval_s"] == 1800
    assert saved["scheduler"]["heartbeat_interval_seconds"] == 1800
    runtime_cfg = load_config(config_path)
    assert runtime_cfg.gateway.heartbeat.interval_s == 1800


def test_gateway_admin_config_patch_and_restart_syncs_scheduler_only_heartbeat_interval(
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
        preview = json.loads(
            await tool.run(
                {
                    "action": "config_patch_preview",
                    "patch": {"scheduler": {"heartbeat_interval_seconds": 9999}},
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert preview["changed_paths"] == [
            "gateway.heartbeat.interval_s",
            "scheduler.heartbeat_interval_seconds",
        ]
        assert preview["resolved_patch"] == {
            "gateway": {"heartbeat": {"interval_s": 9999}},
            "scheduler": {"heartbeat_interval_seconds": 9999},
        }

        payload = json.loads(
            await tool.run(
                {
                    "action": "config_patch_and_restart",
                    "patch": {"scheduler": {"heartbeat_interval_seconds": 9999}},
                    "preview_token": preview["preview_token"],
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["changed"] is True
        assert payload["changed_paths"] == [
            "gateway.heartbeat.interval_s",
            "scheduler.heartbeat_interval_seconds",
        ]
        assert payload["resolved_patch"] == {
            "gateway": {"heartbeat": {"interval_s": 9999}},
            "scheduler": {"heartbeat_interval_seconds": 9999},
        }

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["gateway"]["heartbeat"]["interval_s"] == 9999
    assert saved["scheduler"]["heartbeat_interval_seconds"] == 9999
    runtime_cfg = load_config(config_path)
    assert runtime_cfg.gateway.heartbeat.interval_s == 9999


def test_gateway_admin_config_intent_and_restart_accepts_matching_preview_token(
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
        preview = json.loads(
            await tool.run(
                {
                    "action": "config_intent_preview",
                    "intent": "set_default_tool_timeout",
                    "timeout_s": 31,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        payload = json.loads(
            await tool.run(
                {
                    "action": "config_intent_and_restart",
                    "intent": "set_default_tool_timeout",
                    "timeout_s": 31,
                    "preview_token": preview["preview_token"],
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["action"] == "config_intent_and_restart"
        assert payload["changed"] is True
        assert payload["intent"] == "set_default_tool_timeout"
        assert payload["changed_paths"] == ["tools.default_timeout_s"]

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["default_timeout_s"] == 31
    sentinel = consume_restart_sentinel(tmp_path / "state")
    assert sentinel is not None
    assert sentinel["changed_paths"] == ["tools.default_timeout_s"]


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


def test_gateway_admin_config_intent_and_restart_updates_web_fetch_limits(
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
                    "intent": "set_web_fetch_limits",
                    "timeout_s": 18,
                    "search_timeout_s": 11,
                    "max_redirects": 7,
                    "max_chars": 16000,
                    "block_private_addresses": False,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["intent"] == "set_web_fetch_limits"
        assert payload["changed_paths"] == [
            "tools.web.block_private_addresses",
            "tools.web.max_chars",
            "tools.web.max_redirects",
            "tools.web.search_timeout",
            "tools.web.timeout",
        ]

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["web"]["timeout"] == 18
    assert saved["tools"]["web"]["search_timeout"] == 11
    assert saved["tools"]["web"]["max_redirects"] == 7
    assert saved["tools"]["web"]["max_chars"] == 16000
    assert saved["tools"]["web"]["block_private_addresses"] is False


def test_gateway_admin_config_intent_and_restart_updates_web_content_budget(
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
                    "intent": "set_web_content_budget",
                    "max_chars": 4096,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["intent"] == "set_web_content_budget"
        assert payload["changed_paths"] == ["tools.web.max_chars"]

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["web"]["max_chars"] == 4096


def test_gateway_admin_config_intent_and_restart_updates_web_private_address_blocking(
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
                    "intent": "set_web_private_address_blocking",
                    "enabled": False,
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        assert payload["intent"] == "set_web_private_address_blocking"
        assert payload["changed_paths"] == ["tools.web.block_private_addresses"]
        assert payload["note"] == "Disabled web private-address blocking."

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["web"]["block_private_addresses"] is False


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


def test_gateway_admin_config_patch_and_restart_rejects_stale_preview_token(
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
        preview = json.loads(
            await tool.run(
                {
                    "action": "config_patch_preview",
                    "patch": {"tools": {"default_timeout_s": 44}},
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )
        )
        save_raw_config_payload(
            {
                **initial.to_dict(),
                "tools": {
                    **initial.to_dict()["tools"],
                    "default_timeout_s": 25,
                },
            },
            path=config_path,
        )
        with pytest.raises(RuntimeError, match="gateway_admin_preview_token_mismatch"):
            await tool.run(
                {
                    "action": "config_patch_and_restart",
                    "patch": {"tools": {"default_timeout_s": 44}},
                    "preview_token": preview["preview_token"],
                },
                ToolContext(session_id="telegram:chat42", channel="telegram", user_id="chat42"),
            )

    asyncio.run(_scenario())

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["tools"]["default_timeout_s"] == 25
    assert consume_restart_sentinel(tmp_path / "state") is None


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
