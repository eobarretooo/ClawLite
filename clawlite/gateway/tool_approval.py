from __future__ import annotations

from typing import Any

from clawlite.bus.events import InboundEvent
from clawlite.utils.logging import bind_event


def _extract_action_token(event: InboundEvent) -> str:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    candidates = [
        metadata.get("callback_data"),
        metadata.get("custom_id"),
        event.text,
    ]
    for raw in candidates:
        value = str(raw or "").strip()
        if not value:
            continue
        if value.startswith("[button:") and value.endswith("]"):
            value = value[8:-1].strip()
        if value.startswith("tool_approval:approve:") or value.startswith("tool_approval:reject:"):
            return value
    return ""


async def _reply_telegram(*, channels: Any, event: InboundEvent, text: str) -> bool:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    target = str(metadata.get("chat_id") or event.user_id or "").strip()
    if not target:
        return False
    reply_metadata: dict[str, Any] = {}
    thread_id = metadata.get("message_thread_id")
    if thread_id is not None:
        reply_metadata["message_thread_id"] = thread_id
    reply_to_message_id = metadata.get("message_id")
    if reply_to_message_id is not None:
        reply_metadata["reply_to_message_id"] = reply_to_message_id
    await channels.send(channel="telegram", target=target, text=text, metadata=reply_metadata)
    return True


async def _reply_discord(*, channels: Any, event: InboundEvent, text: str) -> bool:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    channel = channels.get_channel("discord")
    interaction_id = str(metadata.get("interaction_id", "") or "").strip()
    interaction_token = str(metadata.get("interaction_token", "") or "").strip()
    reply_fn = getattr(channel, "reply_interaction", None) if channel is not None else None
    if callable(reply_fn) and interaction_id and interaction_token:
        await reply_fn(
            interaction_id=interaction_id,
            interaction_token=interaction_token,
            text=text,
            ephemeral=True,
        )
        return True
    target = str(metadata.get("channel_id") or event.user_id or "").strip()
    if not target:
        return False
    await channels.send(channel="discord", target=target, text=text)
    return True


async def _reply_generic(*, channels: Any, event: InboundEvent, text: str) -> bool:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    target = str(
        metadata.get("chat_id")
        or metadata.get("channel_id")
        or event.user_id
        or ""
    ).strip()
    if not target:
        return False
    await channels.send(channel=event.channel, target=target, text=text)
    return True


async def _reply_to_event(*, channels: Any, event: InboundEvent, text: str) -> bool:
    channel_name = str(event.channel or "").strip().lower()
    if channel_name == "telegram":
        return await _reply_telegram(channels=channels, event=event, text=text)
    if channel_name == "discord":
        return await _reply_discord(channels=channels, event=event, text=text)
    return await _reply_generic(channels=channels, event=event, text=text)


def build_tool_approval_metadata(requests: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [item for item in requests if isinstance(item, dict)]
    if not rows:
        return {}

    telegram_keyboard: list[list[dict[str, str]]] = []
    discord_components: list[dict[str, Any]] = []
    request_ids: list[str] = []
    for payload in rows[:5]:
        request_id = str(payload.get("request_id", "") or "").strip()
        if not request_id:
            continue
        request_ids.append(request_id)
        tool_name = str(payload.get("tool", "") or "tool").strip() or "tool"
        label_tool = tool_name[:24]
        approve_id = f"tool_approval:approve:{request_id}"
        reject_id = f"tool_approval:reject:{request_id}"
        telegram_keyboard.append(
            [
                {"text": f"Approve {label_tool}", "callback_data": approve_id},
                {"text": f"Reject {label_tool}", "callback_data": reject_id},
            ]
        )
        discord_components.append(
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 1, "label": f"Approve {label_tool}"[:80], "custom_id": approve_id},
                    {"type": 2, "style": 4, "label": f"Reject {label_tool}"[:80], "custom_id": reject_id},
                ],
            }
        )

    return {
        "approval_required": True,
        "approval_kind": "tool",
        "approval_command": "Approve below, then retry the original request in the same session.",
        "approval_request_ids": request_ids,
        "_telegram_inline_keyboard": telegram_keyboard,
        "discord_components": discord_components,
    }


def build_tool_approval_notice(
    requests: list[dict[str, Any]],
    *,
    base_text: str = "",
) -> str:
    rows = [item for item in requests if isinstance(item, dict)]
    if not rows:
        return str(base_text or "").strip()

    lines: list[str] = []
    if str(base_text or "").strip():
        lines.append(str(base_text or "").strip())
        lines.append("")
    lines.append("Tool approval is required before ClawLite can continue.")
    for payload in rows[:5]:
        tool_name = str(payload.get("tool", "") or "tool").strip() or "tool"
        matched = payload.get("matched_approval_specifiers") or []
        channel_name = str(payload.get("channel", "") or "unknown").strip() or "unknown"
        rule = ""
        if isinstance(matched, list) and matched:
            rule = str(matched[0] or "").strip()
        rule_suffix = f" ({rule})" if rule else ""
        lines.append(f"- {tool_name} on {channel_name}{rule_suffix}")
    lines.append("Approve or reject below. If approved, retry the original request in this session.")
    return "\n".join(lines).strip()


async def handle_tool_approval_inbound_action(
    event: InboundEvent,
    *,
    tools: Any,
    channels: Any,
) -> bool:
    action_token = _extract_action_token(event)
    if not action_token:
        return False

    parts = action_token.split(":", 2)
    if len(parts) != 3:
        return True
    _, action, request_id = parts
    normalized_action = str(action or "").strip().lower()
    normalized_request_id = str(request_id or "").strip()
    if normalized_action not in {"approve", "reject"} or not normalized_request_id:
        await _reply_to_event(
            channels=channels,
            event=event,
            text="Tool approval command is invalid.",
        )
        return True

    review_fn = getattr(tools, "review_approval_request", None)
    if not callable(review_fn):
        await _reply_to_event(
            channels=channels,
            event=event,
            text="Tool approval flow is not enabled on this runtime.",
        )
        return True

    actor = f"{event.channel}:{event.user_id}"
    username = ""
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    if isinstance(metadata, dict):
        username = str(metadata.get("username", "") or "").strip()
    note = username if username else actor
    decision = "approved" if normalized_action == "approve" else "rejected"
    result = review_fn(
        normalized_request_id,
        decision=decision,
        actor=actor,
        note=note,
        trusted_actor=True,
    )

    if bool(result.get("ok", False)):
        status = str(result.get("status", decision) or decision)
        changed = bool(result.get("changed", False))
        tool_name = str(result.get("tool", "tool") or "tool").strip() or "tool"
        channel_name = str(result.get("channel", "") or "unknown").strip() or "unknown"
        summary = (
            f"Tool approval for `{tool_name}` on `{channel_name}` {status}."
            if changed
            else f"Tool approval for `{tool_name}` on `{channel_name}` was already {status}."
        )
        lines: list[str] = [summary]
        if status == "approved":
            ttl_s = float(result.get("grant_ttl_s", 0.0) or 0.0)
            if ttl_s > 0:
                lines.append(f"Grant TTL: {int(ttl_s)}s")
            lines.append("Retry the original request in the same session to use the approved tool.")
        await _reply_to_event(
            channels=channels,
            event=event,
            text="\n".join(lines),
        )
        bind_event("tool.approval.review").info(
            "decision={} request_id={} actor={} changed={}",
            status,
            normalized_request_id,
            actor,
            changed,
        )
        return True

    error = str(result.get("error", "review_failed") or "review_failed")
    if error == "approval_actor_required":
        error = "approval_actor_required:reviewer identity is required for this approval"
    if error == "approval_channel_bound":
        error = "approval_channel_bound:this approval must be reviewed from the original channel interaction"
    if error == "approval_actor_mismatch":
        error = "approval_actor_mismatch:only the original requester can review this approval"
    await _reply_to_event(
        channels=channels,
        event=event,
        text=f"Tool approval failed: {error}",
    )
    bind_event("tool.approval.review").warning(
        "decision_failed={} request_id={} actor={}",
        error,
        normalized_request_id,
        actor,
    )
    return True


__all__ = [
    "build_tool_approval_metadata",
    "build_tool_approval_notice",
    "handle_tool_approval_inbound_action",
]
