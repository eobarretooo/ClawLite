from __future__ import annotations

import asyncio
import json
import time

from clawlite.config.schema import ToolSafetyLayerConfig, ToolSafetyPolicyConfig
from clawlite.runtime.telemetry import set_test_tracer_factory
from clawlite.tools.base import Tool, ToolContext
from clawlite.tools.registry import ToolRegistry


class EchoTool(Tool):
    name = "echo"
    description = "echo"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return str(arguments.get("text", ""))


class ExecLikeTool(Tool):
    name = "exec"
    description = "exec"

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "workdir": {"type": "string"},
                "env": {"type": "object"},
            },
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return f"channel={ctx.channel};user={ctx.user_id}"


class RunSkillLikeTool(Tool):
    name = "run_skill"
    description = "run skill"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"name": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return f"skill={arguments.get('name', '')}"


class BrowserLikeTool(Tool):
    name = "browser"
    description = "browser"

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "script": {"type": "string"},
            },
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        del arguments, ctx
        return "ok"


class StrictSchemaTool(Tool):
    name = "strict"
    description = "strict schema validation"

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "count": {"type": "integer", "minimum": 1, "maximum": 3},
                "mode": {"type": "string", "enum": ["fast", "safe"]},
            },
            "required": ["path", "count"],
            "additionalProperties": False,
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        del ctx
        return f"{arguments['path']}:{arguments['count']}:{arguments.get('mode', '')}"


class NestedSchemaTool(Tool):
    name = "nested"
    description = "nested schema validation"

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "media": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "url": {"type": "string"},
                        },
                        "required": ["type"],
                        "additionalProperties": False,
                    },
                },
                "buttons": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    },
                },
            },
            "additionalProperties": False,
        }

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        del ctx
        return str(arguments)


class _FakeSpan:
    def __init__(self, name: str, sink: list[dict[str, object]]) -> None:
        self._row = {"name": name, "attributes": {}, "exceptions": []}
        self._sink = sink

    def __enter__(self) -> "_FakeSpan":
        self._sink.append(self._row)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def set_attribute(self, name: str, value: object) -> None:
        self._row["attributes"][name] = value

    def record_exception(self, exc: Exception) -> None:
        self._row["exceptions"].append(type(exc).__name__)


class _FakeTracer:
    def __init__(self, sink: list[dict[str, object]]) -> None:
        self._sink = sink

    def start_as_current_span(self, name: str) -> _FakeSpan:
        return _FakeSpan(name, self._sink)


def test_tool_registry_execute() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(EchoTool())
        out = await reg.execute("echo", {"text": "ok"}, session_id="s")
        assert out == "ok"

    asyncio.run(_scenario())


def test_tool_registry_execute_emits_tool_span() -> None:
    async def _scenario() -> None:
        spans: list[dict[str, object]] = []
        set_test_tracer_factory(lambda _name: _FakeTracer(spans))
        try:
            reg = ToolRegistry()
            reg.register(EchoTool())
            out = await reg.execute("echo", {"text": "ok"}, session_id="s", channel="telegram", user_id="u1")
        finally:
            set_test_tracer_factory(None)

        assert out == "ok"
        assert spans
        span = spans[-1]
        assert span["name"] == "tool.execute"
        assert span["attributes"]["tool.name"] == "echo"
        assert span["attributes"]["tool.channel"] == "telegram"
        assert int(span["attributes"]["tool.result.length"]) == 2

    asyncio.run(_scenario())


def test_tool_registry_blocks_risky_tools_for_blocked_channels() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(ExecLikeTool())
        try:
            await reg.execute("exec", {"command": "id"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:exec:telegram"

    asyncio.run(_scenario())


def test_tool_registry_blocks_risky_tools_with_derived_channel_from_session() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(ExecLikeTool())
        try:
            await reg.execute("exec", {"command": "id"}, session_id="telegram:1", user_id="1")
            raise AssertionError("expected safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:exec:telegram"

    asyncio.run(_scenario())


def test_tool_registry_blocks_risky_tools_for_unknown_channel_when_restricted() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(ExecLikeTool())
        try:
            await reg.execute("exec", {"command": "id"}, session_id="", channel="", user_id="1")
            raise AssertionError("expected safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:exec:unknown"

    asyncio.run(_scenario())


def test_tool_registry_allows_risky_tools_for_cli_channel() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(ExecLikeTool())
        out = await reg.execute("exec", {"command": "id"}, session_id="cli:1", channel="cli", user_id="1")
        assert out == "channel=cli;user=1"

    asyncio.run(_scenario())


def test_tool_registry_allows_non_risky_tools_for_empty_channel_and_session() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(EchoTool())
        out = await reg.execute("echo", {"text": "ok"}, session_id="", channel="", user_id="")
        assert out == "ok"

    asyncio.run(_scenario())


def test_tool_registry_default_safety_allows_run_skill_for_telegram() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(RunSkillLikeTool())
        out = await reg.execute("run_skill", {"name": "echo"}, session_id="telegram:1", channel="telegram", user_id="1")
        assert out == "skill=echo"

    asyncio.run(_scenario())


def test_tool_registry_default_safety_marks_browser_as_risky() -> None:
    policy = ToolSafetyPolicyConfig()
    assert "browser" in policy.risky_tools


def test_tool_registry_blocks_operation_specific_browser_specifier() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                risky_specifiers=["browser:evaluate"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(BrowserLikeTool())
        out = await reg.execute("browser", {"action": "navigate"}, session_id="telegram:1", channel="telegram", user_id="1")
        assert out == "ok"
        try:
            await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected operation-specific safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:browser:telegram"

    asyncio.run(_scenario())


def test_tool_registry_blocks_wildcard_browser_specifier() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                risky_specifiers=["browser:*"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute("browser", {"action": "click"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected wildcard safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:browser:telegram"

    asyncio.run(_scenario())


def test_tool_registry_blocks_browser_when_configured_for_channel() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["browser"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute("browser", {"action": "navigate"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:browser:telegram"

    asyncio.run(_scenario())


def test_tool_registry_blocks_run_skill_for_telegram_when_explicitly_configured() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["run_skill"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(RunSkillLikeTool())
        try:
            await reg.execute("run_skill", {"name": "echo"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:run_skill:telegram"

    asyncio.run(_scenario())


def test_tool_registry_blocks_run_skill_name_specifier_for_telegram() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                risky_specifiers=["run_skill:github"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(RunSkillLikeTool())
        out = await reg.execute("run_skill", {"name": "echo"}, session_id="telegram:1", channel="telegram", user_id="1")
        assert out == "skill=echo"
        try:
            await reg.execute("run_skill", {"name": "github"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected skill-specific safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:run_skill:telegram"

    asyncio.run(_scenario())


def test_tool_registry_blocks_exec_binary_specifier_for_telegram() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                risky_specifiers=["exec:git"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(ExecLikeTool())
        out = await reg.execute("exec", {"command": "python script.py"}, session_id="telegram:1", channel="telegram", user_id="1")
        assert out == "channel=telegram;user=1"
        try:
            await reg.execute("exec", {"command": "git status"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected command-specific safety policy block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:exec:telegram"

    asyncio.run(_scenario())


def test_tool_registry_derives_exec_shell_env_and_cwd_specifiers() -> None:
    reg = ToolRegistry(
        safety=ToolSafetyPolicyConfig(
            enabled=True,
            risky_tools=[],
            risky_specifiers=["exec:shell", "exec:env-key:git-ssh-command", "exec:cwd"],
            blocked_channels=["telegram"],
            allowed_channels=[],
        )
    )

    payload = reg.safety_decision(
        "exec",
        {
            "command": 'git status && echo ok',
            "env": {"GIT_SSH_COMMAND": "ssh -i /tmp/key"},
            "cwd": "./repo",
        },
        session_id="telegram:1",
        channel="telegram",
    )

    assert payload["derived_specifiers"] == [
        "exec",
        "exec:git",
        "exec:cmd",
        "exec:cmd:git",
        "exec:shell",
        "exec:shell-meta",
        "exec:env",
        "exec:env-key:git-ssh-command",
        "exec:cwd",
    ]
    assert payload["matched_specifiers"] == [
        "exec:shell",
        "exec:env-key:git-ssh-command",
        "exec:cwd",
    ]
    assert payload["blocked"] is True


def test_tool_registry_exec_can_require_approval_for_specific_env_key() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                approval_specifiers=["exec:env-key:git-ssh-command"],
                approval_channels=["telegram"],
                approval_grant_ttl_s=300,
            )
        )
        reg.register(ExecLikeTool())

        try:
            await reg.execute(
                "exec",
                {"command": "git status", "env": {"GIT_SSH_COMMAND": "ssh -i /tmp/key"}},
                session_id="telegram:1",
                channel="telegram",
                user_id="7",
            )
            raise AssertionError("expected approval requirement")
        except RuntimeError as exc:
            assert str(exc) == "tool_requires_approval:exec:telegram"

        pending = reg.consume_pending_approval_requests(session_id="telegram:1", channel="telegram")
        assert len(pending) == 1
        assert pending[0]["matched_approval_specifiers"] == ["exec:env-key:git-ssh-command"]

    asyncio.run(_scenario())


def test_tool_registry_layered_profile_override_changes_effective_risky_tools() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
                profile="ops",
                profiles={
                    "ops": ToolSafetyLayerConfig(
                        risky_tools=["run_skill"],
                    )
                },
            )
        )
        reg.register(ExecLikeTool())
        out = await reg.execute("exec", {"command": "id"}, session_id="telegram:1", channel="telegram", user_id="1")
        assert out == "channel=telegram;user=1"

    asyncio.run(_scenario())


def test_tool_registry_layered_channel_override_can_clear_risky_specifiers() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                risky_specifiers=["browser:evaluate"],
                blocked_channels=["telegram"],
                allowed_channels=[],
                by_channel={
                    "telegram": ToolSafetyLayerConfig(
                        risky_specifiers=[],
                    )
                },
            )
        )
        reg.register(BrowserLikeTool())
        out = await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="1")
        assert out == "ok"

    asyncio.run(_scenario())


def test_tool_registry_safety_decision_reports_matched_specifiers() -> None:
    reg = ToolRegistry(
        safety=ToolSafetyPolicyConfig(
            enabled=True,
            risky_tools=[],
            risky_specifiers=["browser:evaluate"],
            blocked_channels=["telegram"],
            allowed_channels=[],
        )
    )

    payload = reg.safety_decision(
        "browser",
        {"action": "evaluate"},
        session_id="telegram:1",
        channel="telegram",
    )

    assert payload["risky"] is True
    assert payload["blocked"] is True
    assert payload["resolved_channel"] == "telegram"
    assert payload["derived_specifiers"] == ["browser", "browser:evaluate"]
    assert payload["matched_specifiers"] == ["browser:evaluate"]
    assert payload["block_reason"] == "channel:telegram"


def test_tool_registry_derives_host_specifiers_for_web_fetch() -> None:
    reg = ToolRegistry(
        safety=ToolSafetyPolicyConfig(
            enabled=True,
            risky_tools=[],
            risky_specifiers=["web_fetch:host:example-com"],
            blocked_channels=["telegram"],
            allowed_channels=[],
        )
    )

    payload = reg.safety_decision(
        "web_fetch",
        {"url": "https://example.com/docs"},
        session_id="telegram:1",
        channel="telegram",
    )

    assert payload["derived_specifiers"] == [
        "web_fetch",
        "web_fetch:host",
        "web_fetch:host:example-com",
    ]
    assert payload["matched_specifiers"] == ["web_fetch:host:example-com"]
    assert payload["blocked"] is True


def test_tool_registry_derives_host_specifiers_for_browser_navigate() -> None:
    reg = ToolRegistry(
        safety=ToolSafetyPolicyConfig(
            enabled=True,
            risky_tools=[],
            approval_specifiers=["browser:navigate:host:example-com"],
            approval_channels=["telegram"],
            blocked_channels=[],
            allowed_channels=[],
        )
    )

    payload = reg.safety_decision(
        "browser",
        {"action": "navigate", "url": "https://example.com/account"},
        session_id="telegram:1",
        channel="telegram",
    )

    assert payload["derived_specifiers"] == [
        "browser",
        "browser:navigate",
        "browser:host",
        "browser:host:example-com",
        "browser:navigate:host",
        "browser:navigate:host:example-com",
    ]
    assert payload["matched_approval_specifiers"] == ["browser:navigate:host:example-com"]
    assert payload["approval_required"] is True


def test_tool_registry_safety_decision_reports_approval_requirement() -> None:
    reg = ToolRegistry(
        safety=ToolSafetyPolicyConfig(
            enabled=True,
            risky_tools=[],
            risky_specifiers=[],
            approval_specifiers=["browser:evaluate"],
            approval_channels=["telegram"],
            blocked_channels=[],
            allowed_channels=[],
        )
    )

    payload = reg.safety_decision(
        "browser",
        {"action": "evaluate"},
        session_id="telegram:1",
        channel="telegram",
    )

    assert payload["risky"] is False
    assert payload["approval_required"] is True
    assert payload["blocked"] is False
    assert payload["decision"] == "approval"
    assert payload["matched_approval_specifiers"] == ["browser:evaluate"]
    assert payload["approval_reason"] == "channel:telegram"
    assert len(str(payload["approval_request_id"])) == 16


def test_tool_registry_execute_requires_approval_when_configured() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                approval_specifiers=["browser:evaluate"],
                approval_channels=["telegram"],
                blocked_channels=[],
                allowed_channels=[],
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected approval requirement")
        except RuntimeError as exc:
            assert str(exc) == "tool_requires_approval:browser:telegram"

    asyncio.run(_scenario())


def test_tool_registry_block_precedes_approval_when_both_match() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["browser"],
                approval_specifiers=["browser:evaluate"],
                approval_channels=["telegram"],
                blocked_channels=["telegram"],
                allowed_channels=[],
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="1")
            raise AssertionError("expected hard block")
        except RuntimeError as exc:
            assert str(exc) == "tool_blocked_by_safety_policy:browser:telegram"

    asyncio.run(_scenario())


def test_tool_registry_approval_request_grant_allows_retry() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                approval_specifiers=["browser:evaluate"],
                approval_channels=["telegram"],
                blocked_channels=[],
                allowed_channels=[],
                approval_grant_ttl_s=300,
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="7")
            raise AssertionError("expected approval requirement")
        except RuntimeError as exc:
            assert str(exc) == "tool_requires_approval:browser:telegram"

        pending = reg.consume_pending_approval_requests(session_id="telegram:1", channel="telegram")
        assert len(pending) == 1
        assert pending[0]["tool"] == "browser"
        assert pending[0]["matched_approval_specifiers"] == ["browser:evaluate"]

        review = reg.review_approval_request(
            pending[0]["request_id"],
            decision="approved",
            actor="telegram:7",
        )
        assert review["ok"] is True
        assert review["status"] == "approved"

        out = await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="7")
        assert out == "ok"

    asyncio.run(_scenario())


def test_tool_registry_approval_grant_is_bound_to_same_request_payload() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                approval_specifiers=["browser:evaluate"],
                approval_channels=["telegram"],
                blocked_channels=[],
                allowed_channels=[],
                approval_grant_ttl_s=300,
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute(
                "browser",
                {"action": "evaluate", "script": "1 + 1"},
                session_id="telegram:1",
                channel="telegram",
                user_id="7",
            )
            raise AssertionError("expected approval requirement")
        except RuntimeError as exc:
            assert str(exc) == "tool_requires_approval:browser:telegram"

        pending = reg.consume_pending_approval_requests(session_id="telegram:1", channel="telegram")
        assert len(pending) == 1
        approved_request_id = str(pending[0]["request_id"])

        review = reg.review_approval_request(
            approved_request_id,
            decision="approved",
            actor="telegram:7",
        )
        assert review["ok"] is True

        same_request = await reg.execute(
            "browser",
            {"action": "evaluate", "script": "1 + 1"},
            session_id="telegram:1",
            channel="telegram",
            user_id="7",
        )
        assert same_request == "ok"

        try:
            await reg.execute(
                "browser",
                {"action": "evaluate", "script": "2 + 2"},
                session_id="telegram:1",
                channel="telegram",
                user_id="7",
            )
            raise AssertionError("expected approval requirement for different payload")
        except RuntimeError as exc:
            assert str(exc) == "tool_requires_approval:browser:telegram"

        later_pending = reg.consume_pending_approval_requests(session_id="telegram:1", channel="telegram")
        assert len(later_pending) == 1
        assert str(later_pending[0]["request_id"]) != approved_request_id

    asyncio.run(_scenario())


def test_tool_registry_consume_pending_approval_requests_is_one_shot() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=[],
                approval_specifiers=["browser:evaluate"],
                approval_channels=["telegram"],
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="7")
            raise AssertionError("expected approval requirement")
        except RuntimeError:
            pass

        first = reg.consume_pending_approval_requests(session_id="telegram:1", channel="telegram")
        second = reg.consume_pending_approval_requests(session_id="telegram:1", channel="telegram")
        assert len(first) == 1
        assert second == []

    asyncio.run(_scenario())


def test_tool_registry_approval_snapshots_include_requests_and_grants() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                approval_specifiers=["browser:evaluate"],
                approval_channels=["telegram"],
                approval_grant_ttl_s=300,
            )
        )
        reg.register(BrowserLikeTool())
        try:
            await reg.execute("browser", {"action": "evaluate"}, session_id="telegram:1", channel="telegram", user_id="7")
            raise AssertionError("expected approval requirement")
        except RuntimeError:
            pass

        pending = reg.approval_requests_snapshot(status="pending", session_id="telegram:1", channel="telegram")
        assert len(pending) == 1
        assert pending[0]["tool"] == "browser"
        assert pending[0]["request_age_s"] >= 0.0
        assert pending[0]["expires_in_s"] > 0.0

        review = reg.review_approval_request(pending[0]["request_id"], decision="approved", actor="cli")
        assert review["ok"] is True

        approved = reg.approval_requests_snapshot(status="approved", session_id="telegram:1", channel="telegram")
        assert len(approved) == 1
        assert approved[0]["status"] == "approved"
        assert approved[0]["grant_expires_in_s"] > 0.0

        grants = reg.approval_grants_snapshot(session_id="telegram:1", channel="telegram")
        assert len(grants) == 1
        assert grants[0]["rule"] == "browser:evaluate"
        assert grants[0]["scope"] == "exact"
        assert grants[0]["request_id"] == pending[0]["request_id"]
        assert grants[0]["expires_in_s"] > 0.0

    asyncio.run(_scenario())


def test_tool_registry_revoke_approval_grants_filters_by_session_channel_and_rule() -> None:
    reg = ToolRegistry(safety=ToolSafetyPolicyConfig(enabled=True))
    reg._approval_grants["telegram:1::telegram::browser:evaluate"] = time.monotonic() + 120.0
    reg._approval_grants["telegram:2::telegram::browser:evaluate"] = time.monotonic() + 120.0

    summary = reg.revoke_approval_grants(session_id="telegram:1", channel="telegram", rule="browser:evaluate")

    assert summary["ok"] is True
    assert summary["removed_count"] == 1
    assert summary["removed"][0]["session_id"] == "telegram:1"
    remaining = reg.approval_grants_snapshot()
    assert len(remaining) == 1
    assert remaining[0]["session_id"] == "telegram:2"


def test_tool_registry_legacy_approval_grants_remain_visible_and_usable() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                approval_specifiers=["browser:evaluate"],
                approval_channels=["telegram"],
                approval_grant_ttl_s=300,
            )
        )
        reg.register(BrowserLikeTool())
        reg._approval_grants["telegram:1::telegram::browser:evaluate"] = time.monotonic() + 120.0

        payload = reg.safety_decision(
            "browser",
            {"action": "evaluate", "script": "legacy"},
            session_id="telegram:1",
            channel="telegram",
        )
        assert payload["approval_granted"] is True
        assert payload["approval_request_id"]

        out = await reg.execute(
            "browser",
            {"action": "evaluate", "script": "legacy"},
            session_id="telegram:1",
            channel="telegram",
            user_id="7",
        )
        assert out == "ok"

        grants = reg.approval_grants_snapshot(session_id="telegram:1", channel="telegram")
        assert len(grants) == 1
        assert grants[0]["scope"] == "legacy"
        assert grants[0]["request_id"] == ""

    asyncio.run(_scenario())


def test_tool_registry_layered_agent_override_supersedes_profile_and_global() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
                profile="ops",
                profiles={
                    "ops": ToolSafetyLayerConfig(
                        risky_tools=["exec"],
                        blocked_channels=["telegram"],
                    )
                },
                by_agent={
                    "alpha": ToolSafetyLayerConfig(
                        risky_tools=["exec"],
                        blocked_channels=["slack"],
                    )
                },
            )
        )
        reg.register(ExecLikeTool())
        out = await reg.execute("exec", {"command": "id"}, session_id="agent:alpha:42", channel="telegram", user_id="1")
        assert out == "channel=telegram;user=1"

    asyncio.run(_scenario())


def test_tool_registry_layered_channel_override_supersedes_agent_and_global() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry(
            safety=ToolSafetyPolicyConfig(
                enabled=True,
                risky_tools=["exec"],
                blocked_channels=["telegram"],
                allowed_channels=[],
                by_agent={
                    "alpha": ToolSafetyLayerConfig(
                        blocked_channels=["telegram"],
                    )
                },
                by_channel={
                    "telegram": ToolSafetyLayerConfig(
                        blocked_channels=[],
                    )
                },
            )
        )
        reg.register(ExecLikeTool())
        out = await reg.execute("exec", {"command": "id"}, session_id="agent:alpha:42", channel="telegram", user_id="1")
        assert out == "channel=telegram;user=1"

    asyncio.run(_scenario())


def test_tool_registry_blocks_non_object_arguments_fail_closed() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(StrictSchemaTool())
        try:
            await reg.execute("strict", ["bad"], session_id="cli:1")  # type: ignore[arg-type]
            raise AssertionError("expected argument validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:strict:expected_object"

    asyncio.run(_scenario())


def test_tool_registry_blocks_missing_required_arguments_fail_closed() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(StrictSchemaTool())
        try:
            await reg.execute("strict", {"path": "demo.txt"}, session_id="cli:1")
            raise AssertionError("expected missing required validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:strict:missing_required:count"

    asyncio.run(_scenario())


def test_tool_registry_blocks_type_and_range_mismatches_fail_closed() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(StrictSchemaTool())
        try:
            await reg.execute("strict", {"path": "demo.txt", "count": 0}, session_id="cli:1")
            raise AssertionError("expected range validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:strict:count:minimum_1"

        try:
            await reg.execute("strict", {"path": "demo.txt", "count": "2"}, session_id="cli:1")  # type: ignore[dict-item]
            raise AssertionError("expected type validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:strict:count:expected_integer"

    asyncio.run(_scenario())


def test_tool_registry_blocks_unexpected_arguments_when_schema_forbids_them() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(StrictSchemaTool())
        try:
            await reg.execute(
                "strict",
                {"path": "demo.txt", "count": 2, "extra": True},
                session_id="cli:1",
            )
            raise AssertionError("expected unexpected-argument validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:strict:unexpected_arguments:extra"

    asyncio.run(_scenario())


def test_tool_registry_allows_valid_arguments_after_schema_validation() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(StrictSchemaTool())
        out = await reg.execute(
            "strict",
            {"path": "demo.txt", "count": 2, "mode": "safe"},
            session_id="cli:1",
        )
        assert out == "demo.txt:2:safe"

    asyncio.run(_scenario())


def test_tool_registry_blocks_nested_missing_required_arguments_fail_closed() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(NestedSchemaTool())
        try:
            await reg.execute("nested", {"media": [{}]}, session_id="cli:1")
            raise AssertionError("expected nested missing-required validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:nested:media[0]:missing_required:type"

    asyncio.run(_scenario())


def test_tool_registry_blocks_nested_unexpected_arguments_fail_closed() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(NestedSchemaTool())
        try:
            await reg.execute("nested", {"media": [{"type": "photo", "extra": True}]}, session_id="cli:1")
            raise AssertionError("expected nested unexpected-argument validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:nested:media[0]:unexpected_arguments:extra"

    asyncio.run(_scenario())


def test_tool_registry_blocks_nested_item_type_and_min_items_fail_closed() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(NestedSchemaTool())
        try:
            await reg.execute("nested", {"media": []}, session_id="cli:1")
            raise AssertionError("expected nested min-items validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:nested:media:min_items_1"

        try:
            await reg.execute(
                "nested",
                {"buttons": [[{"text": 123}]]},
                session_id="cli:1",
            )
            raise AssertionError("expected nested item type validation block")
        except RuntimeError as exc:
            assert str(exc) == "tool_invalid_arguments:nested:buttons[0][0].text:expected_string"

    asyncio.run(_scenario())


def test_tool_registry_aggregates_multiple_validation_errors() -> None:
    async def _scenario() -> None:
        reg = ToolRegistry()
        reg.register(StrictSchemaTool())
        try:
            await reg.execute(
                "strict",
                {
                    "path": 123,
                    "count": 0,
                    "mode": "turbo",
                    "extra": True,
                },
                session_id="cli:1",
            )
            raise AssertionError("expected aggregated validation block")
        except RuntimeError as exc:
            message = str(exc)
            assert message.startswith("tool_invalid_arguments:strict:multiple:")
            payload = json.loads(message.split(":multiple:", 1)[1])
            assert payload == [
                "unexpected_arguments:extra",
                "path:expected_string",
                "count:minimum_1",
                "mode:value_not_allowed",
            ]

    asyncio.run(_scenario())
