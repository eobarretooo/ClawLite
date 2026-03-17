from __future__ import annotations

import asyncio
import json

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
        return {"type": "object", "properties": {"command": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return f"channel={ctx.channel};user={ctx.user_id}"


class RunSkillLikeTool(Tool):
    name = "run_skill"
    description = "run skill"

    def args_schema(self) -> dict:
        return {"type": "object", "properties": {"name": {"type": "string"}}}

    async def run(self, arguments: dict, ctx: ToolContext) -> str:
        return f"skill={arguments.get('name', '')}"


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
