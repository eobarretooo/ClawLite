from __future__ import annotations


_TUNING_DEFAULT_ACTION_BY_SEVERITY: dict[str, str] = {
    "low": "notify_operator",
    "medium": "semantic_backfill",
    "high": "memory_snapshot",
}

_TUNING_REASONING_LAYER_ALIASES: dict[str, str] = {
    "factual": "fact",
    "procedural": "decision",
    "episodic": "outcome",
}

_TUNING_LAYER_ACTION_PLAYBOOKS: dict[str, dict[str, str]] = {
    "fact": {
        "low": "semantic_backfill",
        "medium": "semantic_backfill",
        "high": "memory_snapshot",
    },
    "hypothesis": {
        "low": "notify_operator",
        "medium": "semantic_backfill",
        "high": "memory_snapshot",
    },
    "decision": {
        "low": "notify_operator",
        "medium": "memory_snapshot",
        "high": "memory_snapshot",
    },
    "outcome": {
        "low": "notify_operator",
        "medium": "semantic_backfill",
        "high": "memory_snapshot",
    },
}

_TUNING_SEVERITY_LEVELS: tuple[str, ...] = ("low", "medium", "high")

_TUNING_LAYER_BACKFILL_LIMITS: dict[str, dict[str, dict[str, int]]] = {
    "fact": {
        "low": {"floor": 8, "ceiling": 24, "default": 14},
        "medium": {"floor": 16, "ceiling": 42, "default": 24},
        "high": {"floor": 24, "ceiling": 64, "default": 40},
    },
    "hypothesis": {
        "low": {"floor": 6, "ceiling": 20, "default": 12},
        "medium": {"floor": 12, "ceiling": 34, "default": 20},
        "high": {"floor": 18, "ceiling": 50, "default": 30},
    },
    "decision": {
        "low": {"floor": 5, "ceiling": 16, "default": 10},
        "medium": {"floor": 8, "ceiling": 26, "default": 16},
        "high": {"floor": 12, "ceiling": 36, "default": 24},
    },
    "outcome": {
        "low": {"floor": 7, "ceiling": 22, "default": 12},
        "medium": {"floor": 14, "ceiling": 38, "default": 22},
        "high": {"floor": 20, "ceiling": 56, "default": 32},
    },
}

_TUNING_LAYER_SNAPSHOT_TAGS: dict[str, dict[str, str]] = {
    "fact": {
        "low": "quality-drift-fact-low",
        "medium": "quality-drift-fact-medium",
        "high": "quality-drift-fact-high",
    },
    "hypothesis": {
        "low": "quality-drift-hypothesis-low",
        "medium": "quality-drift-hypothesis-medium",
        "high": "quality-drift-hypothesis-high",
    },
    "decision": {
        "low": "quality-drift-decision-low",
        "medium": "quality-drift-decision-medium",
        "high": "quality-drift-decision-high",
    },
    "outcome": {
        "low": "quality-drift-outcome-low",
        "medium": "quality-drift-outcome-medium",
        "high": "quality-drift-outcome-high",
    },
}

_TUNING_NOTIFY_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "fact": {
        "low": {"template_id": "notify.fact.low.v1", "marker": "fact-low"},
        "medium": {"template_id": "notify.fact.medium.v1", "marker": "fact-medium"},
        "high": {"template_id": "notify.fact.high.v1", "marker": "fact-high"},
    },
    "hypothesis": {
        "low": {"template_id": "notify.hypothesis.low.v1", "marker": "hypothesis-low"},
        "medium": {"template_id": "notify.hypothesis.medium.v1", "marker": "hypothesis-medium"},
        "high": {"template_id": "notify.hypothesis.high.v1", "marker": "hypothesis-high"},
    },
    "decision": {
        "low": {"template_id": "notify.decision.low.v1", "marker": "decision-low"},
        "medium": {"template_id": "notify.decision.medium.v1", "marker": "decision-medium"},
        "high": {"template_id": "notify.decision.high.v1", "marker": "decision-high"},
    },
    "outcome": {
        "low": {"template_id": "notify.outcome.low.v1", "marker": "outcome-low"},
        "medium": {"template_id": "notify.outcome.medium.v1", "marker": "outcome-medium"},
        "high": {"template_id": "notify.outcome.high.v1", "marker": "outcome-high"},
    },
}


def normalize_reasoning_layer(layer: str) -> str:
    normalized_layer = str(layer or "").strip().lower()
    if not normalized_layer:
        return ""
    return _TUNING_REASONING_LAYER_ALIASES.get(normalized_layer, normalized_layer)


def select_tuning_action_playbook(*, severity: str, weakest_layer: str) -> tuple[str, str]:
    normalized_severity = str(severity or "").strip().lower()
    if normalized_severity not in _TUNING_DEFAULT_ACTION_BY_SEVERITY:
        normalized_severity = "low"

    default_action = _TUNING_DEFAULT_ACTION_BY_SEVERITY[normalized_severity]
    normalized_layer = normalize_reasoning_layer(weakest_layer)
    if not normalized_layer:
        return default_action, f"severity_default_{normalized_severity}_v1"

    layer_playbook = _TUNING_LAYER_ACTION_PLAYBOOKS.get(normalized_layer)
    if not isinstance(layer_playbook, dict):
        return default_action, f"severity_default_{normalized_severity}_v1"

    action = str(layer_playbook.get(normalized_severity, "") or "").strip()
    if not action:
        action = default_action
    return action, f"layer_{normalized_layer}_{normalized_severity}_v1"


def normalize_tuning_severity(value: str) -> str:
    severity = str(value or "").strip().lower()
    if severity in _TUNING_SEVERITY_LEVELS:
        return severity
    return "low"


def resolve_tuning_layer(value: str) -> str:
    layer = normalize_reasoning_layer(value)
    if layer in _TUNING_LAYER_ACTION_PLAYBOOKS:
        return layer
    return "unknown"


def resolve_tuning_backfill_limit(*, layer: str, severity: str, missing_records: int) -> int:
    normalized_layer = resolve_tuning_layer(layer)
    normalized_severity = normalize_tuning_severity(severity)
    layer_cfg = _TUNING_LAYER_BACKFILL_LIMITS.get(normalized_layer) or _TUNING_LAYER_BACKFILL_LIMITS.get("hypothesis", {})
    bounds = layer_cfg.get(normalized_severity, {"floor": 8, "ceiling": 24, "default": 16})
    floor = max(1, int(bounds.get("floor", 8) or 8))
    ceiling = max(floor, int(bounds.get("ceiling", 24) or 24))
    default = int(bounds.get("default", floor) or floor)
    if default < floor:
        default = floor
    if default > ceiling:
        default = ceiling
    if missing_records <= 0:
        return default
    return max(floor, min(ceiling, int(missing_records)))


def resolve_tuning_snapshot_tag(*, layer: str, severity: str) -> str:
    normalized_layer = resolve_tuning_layer(layer)
    normalized_severity = normalize_tuning_severity(severity)
    layer_tags = _TUNING_LAYER_SNAPSHOT_TAGS.get(normalized_layer) or _TUNING_LAYER_SNAPSHOT_TAGS.get("hypothesis", {})
    return str(layer_tags.get(normalized_severity, "quality-drift-auto") or "quality-drift-auto")


def resolve_tuning_notify_variant(*, layer: str, severity: str) -> tuple[str, str]:
    normalized_layer = resolve_tuning_layer(layer)
    normalized_severity = normalize_tuning_severity(severity)
    layer_templates = _TUNING_NOTIFY_TEMPLATES.get(normalized_layer) or _TUNING_NOTIFY_TEMPLATES.get("hypothesis", {})
    template = layer_templates.get(normalized_severity, {"template_id": "notify.generic.low.v1", "marker": "generic-low"})
    template_id = str(template.get("template_id", "notify.generic.low.v1") or "notify.generic.low.v1")
    marker = str(template.get("marker", "generic-low") or "generic-low")
    return template_id, marker


__all__ = [
    "normalize_reasoning_layer",
    "normalize_tuning_severity",
    "resolve_tuning_backfill_limit",
    "resolve_tuning_layer",
    "resolve_tuning_notify_variant",
    "resolve_tuning_snapshot_tag",
    "select_tuning_action_playbook",
]
