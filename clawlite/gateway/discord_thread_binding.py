from __future__ import annotations

from typing import Any

from clawlite.bus.events import InboundEvent


def _extract_action(event: InboundEvent) -> tuple[str, str]:
    if str(event.channel or "").strip().lower() != "discord":
        return ("", "")
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    command_name = str(metadata.get("command_name", "") or "").strip().lower()
    if command_name in {"focus", "unfocus", "discord-status", "discord-refresh", "discord-presence", "discord-presence-refresh"}:
        if command_name == "discord-status":
            return ("status", "")
        if command_name == "discord-refresh":
            return ("refresh", "")
        if command_name == "discord-presence":
            return ("presence", "")
        if command_name == "discord-presence-refresh":
            return ("presence_refresh", "")
        if command_name == "unfocus":
            return ("unfocus", "")
        options = metadata.get("command_options")
        if isinstance(options, list):
            for item in options:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "") or "").strip().lower()
                if name not in {"session", "session_id", "session_key", "target"}:
                    continue
                value = str(item.get("value", "") or "").strip()
                if value:
                    return ("focus", value)
        return ("focus", "")

    text = str(event.text or "").strip()
    lowered = text.lower()
    if lowered == "/discord-status":
        return ("status", "")
    if lowered == "/discord-refresh":
        return ("refresh", "")
    if lowered == "/discord-presence":
        return ("presence", "")
    if lowered == "/discord-presence-refresh":
        return ("presence_refresh", "")
    if lowered == "/unfocus":
        return ("unfocus", "")
    if lowered.startswith("/focus"):
        remainder = text[6:].strip()
        if "=" in remainder and " " not in remainder:
            key, _, value = remainder.partition("=")
            if key.strip().lower() in {"session", "session_id", "session_key", "target"}:
                remainder = value.strip()
        elif " " in remainder:
            first, _, value = remainder.partition(" ")
            if first.strip().lower() in {"session", "session_id", "session_key", "target"}:
                remainder = value.strip()
        return ("focus", remainder.strip())
    return ("", "")


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


async def handle_discord_thread_binding_inbound_action(
    event: InboundEvent,
    *,
    channels: Any,
) -> bool:
    action, session_key = _extract_action(event)
    if not action:
        return False

    channel = channels.get_channel("discord")
    if channel is None:
        await _reply_discord(
            channels=channels,
            event=event,
            text="Discord thread binding is unavailable because the Discord channel is not running.",
        )
        return True

    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    channel_id = str(metadata.get("channel_id", "") or "").strip()
    guild_id = str(metadata.get("guild_id", "") or "").strip()
    if not channel_id:
        await _reply_discord(
            channels=channels,
            event=event,
            text="Discord focus commands need a channel context.",
        )
        return True

    if action == "status":
        status_fn = getattr(channel, "operator_status", None)
        if not callable(status_fn):
            await _reply_discord(
                channels=channels,
                event=event,
                text="Discord operator status is not available on this runtime.",
            )
            return True
        status = status_fn()
        gateway_session_task_state = str(status.get("gateway_session_task_state", "unknown") or "unknown").strip()
        gateway_session_waiting_for = str(status.get("gateway_session_waiting_for", "") or "").strip()
        gateway_reconnect_attempt = int(status.get("gateway_reconnect_attempt", 0) or 0)
        gateway_reconnect_retry_in_s = float(status.get("gateway_reconnect_retry_in_s", 0.0) or 0.0)
        gateway_reconnect_state = str(status.get("gateway_reconnect_state", "") or "").strip().lower()
        lines = [
            "Discord operator status",
            f"- connected: {bool(status.get('connected', False))}",
            f"- gateway: {status.get('gateway_task_state', 'unknown')}",
            f"- heartbeat: {status.get('heartbeat_task_state', 'unknown')}",
            f"- session_watchdog: {gateway_session_task_state}",
            f"- policies: allowed={status.get('policy_allowed_count', 0)} blocked={status.get('policy_blocked_count', 0)}",
            f"- focus bindings: {status.get('thread_binding_count', 0)}",
        ]
        if gateway_session_waiting_for:
            lines.append(f"- waiting_for: {gateway_session_waiting_for.upper()}")
        if gateway_reconnect_attempt > 0 or gateway_reconnect_retry_in_s > 0.0:
            reconnect_detail = (
                f"retry_in {gateway_reconnect_retry_in_s:.1f}s"
                if gateway_reconnect_retry_in_s > 0.0
                else ("retrying now" if gateway_reconnect_state == "retrying" else "retry active")
            )
            lines.append(f"- reconnect: attempt {gateway_reconnect_attempt} | {reconnect_detail}")
        last_error = str(status.get("last_error", "") or "").strip()
        if last_error:
            lines.append(f"- last_error: {last_error}")
        await _reply_discord(
            channels=channels,
            event=event,
            text="\n".join(lines),
        )
        return True

    if action == "refresh":
        refresh_fn = getattr(channel, "operator_refresh_transport", None)
        if not callable(refresh_fn):
            await _reply_discord(
                channels=channels,
                event=event,
                text="Discord transport refresh is not available on this runtime.",
            )
            return True
        result = await refresh_fn()
        status = result.get("status", {}) if isinstance(result, dict) else {}
        lines = [
            "Discord transport refresh completed",
            f"- ok: {bool(result.get('ok', False)) if isinstance(result, dict) else False}",
            f"- gateway_restarted: {bool(result.get('gateway_restarted', False)) if isinstance(result, dict) else False}",
            f"- connected: {bool(status.get('connected', False))}",
            f"- gateway: {status.get('gateway_task_state', 'unknown')}",
        ]
        last_error = ""
        if isinstance(result, dict):
            last_error = str(result.get("last_error", "") or "").strip()
        if not last_error:
            last_error = str(status.get("last_error", "") or "").strip()
        if last_error:
            lines.append(f"- last_error: {last_error}")
        await _reply_discord(
            channels=channels,
            event=event,
            text="\n".join(lines),
        )
        return True

    if action == "presence":
        status_fn = getattr(channel, "operator_status", None)
        if not callable(status_fn):
            await _reply_discord(
                channels=channels,
                event=event,
                text="Discord presence status is not available on this runtime.",
            )
            return True
        status = status_fn()
        lines = [
            "Discord presence status",
            f"- auto_presence_enabled: {bool(status.get('auto_presence_enabled', False))}",
            f"- presence_state: {status.get('presence_last_state', 'unknown')}",
            f"- static_status: {status.get('presence_status', '') or '-'}",
            f"- static_activity: {status.get('presence_activity', '') or '-'}",
            f"- auto_presence_task: {status.get('auto_presence_task_state', 'unknown')}",
        ]
        last_error = str(status.get("presence_last_error", "") or "").strip()
        if last_error:
            lines.append(f"- last_error: {last_error}")
        await _reply_discord(
            channels=channels,
            event=event,
            text="\n".join(lines),
        )
        return True

    if action == "presence_refresh":
        refresh_presence_fn = getattr(channel, "operator_refresh_presence", None)
        if not callable(refresh_presence_fn):
            await _reply_discord(
                channels=channels,
                event=event,
                text="Discord presence refresh is not available on this runtime.",
            )
            return True
        result = await refresh_presence_fn()
        status = result.get("status", {}) if isinstance(result, dict) else {}
        lines = [
            "Discord presence refresh completed",
            f"- ok: {bool(result.get('ok', False)) if isinstance(result, dict) else False}",
            f"- sent: {bool(result.get('sent', False)) if isinstance(result, dict) else False}",
            f"- reason: {str(result.get('reason', '') or '-') if isinstance(result, dict) else '-'}",
            f"- state: {status.get('presence_last_state', 'unknown')}",
        ]
        last_error = str(status.get("presence_last_error", "") or "").strip()
        if last_error:
            lines.append(f"- last_error: {last_error}")
        await _reply_discord(
            channels=channels,
            event=event,
            text="\n".join(lines),
        )
        return True

    if action == "focus":
        if not session_key:
            await _reply_discord(
                channels=channels,
                event=event,
                text="Usage: `/focus <session_id>`",
            )
            return True
        bind_fn = getattr(channel, "bind_thread", None)
        if not callable(bind_fn):
            await _reply_discord(
                channels=channels,
                event=event,
                text="Discord focus bindings are not supported by this runtime.",
            )
            return True
        actor = f"{event.channel}:{event.user_id}"
        result = await bind_fn(
            channel_id=channel_id,
            session_id=session_key,
            actor=actor,
            guild_id=guild_id,
            source_session_id=event.session_id,
        )
        if not bool(result.get("ok", False)):
            error = str(result.get("error", "discord_thread_binding_failed") or "discord_thread_binding_failed")
            await _reply_discord(
                channels=channels,
                event=event,
                text=f"Discord focus failed: {error}",
            )
            return True
        changed = bool(result.get("changed", False))
        summary = (
            f"Focused this Discord channel on `{session_key}`."
            if changed
            else f"This Discord channel is already focused on `{session_key}`."
        )
        await _reply_discord(
            channels=channels,
            event=event,
            text=summary,
        )
        return True

    unbind_fn = getattr(channel, "unbind_thread", None)
    if not callable(unbind_fn):
        await _reply_discord(
            channels=channels,
            event=event,
            text="Discord focus bindings are not supported by this runtime.",
        )
        return True
    result = await unbind_fn(channel_id=channel_id)
    if not bool(result.get("ok", False)):
        error = str(result.get("error", "discord_thread_binding_failed") or "discord_thread_binding_failed")
        await _reply_discord(
            channels=channels,
            event=event,
            text=f"Discord unfocus failed: {error}",
        )
        return True
    changed = bool(result.get("changed", False))
    summary = (
        "Removed the focus binding from this Discord channel."
        if changed
        else "This Discord channel was not focused on any other session."
    )
    await _reply_discord(
        channels=channels,
        event=event,
        text=summary,
    )
    return True


__all__ = ["handle_discord_thread_binding_inbound_action"]
