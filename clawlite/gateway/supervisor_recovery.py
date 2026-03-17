from __future__ import annotations

from typing import Any, Awaitable, Callable


async def handle_supervisor_incident(
    *,
    incident: Any,
    notice_until: dict[str, float],
    cooldown_s: float,
    now_monotonic: Callable[[], float],
    record_autonomy_event: Callable[..., None],
    send_autonomy_notice: Callable[..., Awaitable[Any]],
) -> None:
    if bool(getattr(incident, "recoverable", False)):
        return
    key = f"{getattr(incident, 'component', '')}:{getattr(incident, 'reason', '')}"
    now = now_monotonic()
    if now < float(notice_until.get(key, 0.0) or 0.0):
        return
    notice_until[key] = now + cooldown_s
    component = str(getattr(incident, "component", "") or "")
    reason = str(getattr(incident, "reason", "") or "")
    recoverable = bool(getattr(incident, "recoverable", False))
    record_autonomy_event(
        "supervisor",
        "component_incident",
        "observed",
        summary=f"{component} incident -> {reason}",
        metadata={
            "component": component,
            "incident_reason": reason,
            "recoverable": recoverable,
        },
    )
    text = f"Autonomy notice: supervisor detected component={component} issue."
    if reason:
        text += f" reason={reason}."
    await send_autonomy_notice(
        "supervisor",
        "component_incident",
        "observed",
        text=text,
        metadata={
            "source": "supervisor",
            "component": component,
            "incident_reason": reason,
            "recoverable": recoverable,
        },
    )


async def recover_supervised_component(
    *,
    component: str,
    reason: str,
    recoverers: dict[str, Callable[[], Awaitable[bool]]],
    record_autonomy_event: Callable[..., None],
    send_autonomy_notice: Callable[..., Awaitable[Any]],
) -> bool:
    recovered = False
    recoverer = recoverers.get(component)
    if recoverer is not None:
        recovered = bool(await recoverer())
    record_autonomy_event(
        "supervisor",
        "component_recovery",
        "recovered" if recovered else "failed",
        summary=f"{component} recovery -> {'recovered' if recovered else 'failed'}",
        metadata={"component": component, "reason": reason},
    )
    text = f"Autonomy notice: supervisor {'recovered' if recovered else 'failed'} component={component}."
    if reason:
        text += f" reason={reason}."
    await send_autonomy_notice(
        "supervisor",
        "component_recovery",
        "recovered" if recovered else "failed",
        text=text,
        metadata={
            "source": "supervisor",
            "component": component,
            "recovery_reason": reason,
        },
    )
    return recovered


__all__ = [
    "handle_supervisor_incident",
    "recover_supervised_component",
]
