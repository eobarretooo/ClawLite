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
        if value.startswith("self_evolution:approve:") or value.startswith("self_evolution:reject:"):
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


async def handle_self_evolution_inbound_action(
    event: InboundEvent,
    *,
    self_evolution: Any,
    channels: Any,
) -> bool:
    action_token = _extract_action_token(event)
    if not action_token:
        return False

    parts = action_token.split(":", 2)
    if len(parts) != 3:
        return True
    _, action, run_id = parts
    normalized_action = str(action or "").strip().lower()
    normalized_run_id = str(run_id or "").strip()
    if normalized_action not in {"approve", "reject"} or not normalized_run_id:
        await _reply_to_event(
            channels=channels,
            event=event,
            text="Self-evolution review command is invalid.",
        )
        return True

    if self_evolution is None or not bool(getattr(self_evolution, "require_approval", False)):
        await _reply_to_event(
            channels=channels,
            event=event,
            text="Self-evolution approval flow is not enabled on this runtime.",
        )
        return True

    actor = f"{event.channel}:{event.user_id}"
    username = ""
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    if isinstance(metadata, dict):
        username = str(metadata.get("username", "") or "").strip()
    note = username if username else actor
    decision = "approved" if normalized_action == "approve" else "rejected"
    result = self_evolution.review_run(
        normalized_run_id,
        decision=decision,
        actor=actor,
        note=note,
    )

    if bool(result.get("ok", False)):
        status = str(result.get("status", decision) or decision)
        changed = bool(result.get("changed", False))
        branch_name = str(result.get("branch_name", "") or "").strip()
        commit_sha = str(result.get("commit_sha", "") or "").strip()
        summary = (
            f"Self-evolution run `{normalized_run_id}` {status}."
            if changed
            else f"Self-evolution run `{normalized_run_id}` was already {status}."
        )
        details: list[str] = [summary]
        if branch_name:
            details.append(f"Branch: {branch_name}")
        if commit_sha:
            details.append(f"Commit: {commit_sha}")
        await _reply_to_event(
            channels=channels,
            event=event,
            text="\n".join(details),
        )
        bind_event("self_evolution.review").info(
            "decision={} run_id={} actor={} changed={}",
            status,
            normalized_run_id,
            actor,
            changed,
        )
        return True

    error = str(result.get("error", "review_failed") or "review_failed")
    await _reply_to_event(
        channels=channels,
        event=event,
        text=f"Self-evolution review failed: {error}",
    )
    bind_event("self_evolution.review").warning(
        "decision_failed={} run_id={} actor={}",
        error,
        normalized_run_id,
        actor,
    )
    return True


__all__ = ["handle_self_evolution_inbound_action"]
