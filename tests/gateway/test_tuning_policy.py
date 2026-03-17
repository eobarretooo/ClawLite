from __future__ import annotations

from clawlite.gateway.tuning_policy import (
    normalize_reasoning_layer,
    normalize_tuning_severity,
    resolve_tuning_backfill_limit,
    resolve_tuning_layer,
    resolve_tuning_notify_variant,
    resolve_tuning_snapshot_tag,
    select_tuning_action_playbook,
)


def test_normalize_reasoning_layer_maps_legacy_aliases() -> None:
    assert normalize_reasoning_layer("factual") == "fact"
    assert normalize_reasoning_layer("procedural") == "decision"
    assert normalize_reasoning_layer("episodic") == "outcome"


def test_select_tuning_action_playbook_prefers_layer_specific_actions() -> None:
    assert select_tuning_action_playbook(severity="medium", weakest_layer="fact") == (
        "semantic_backfill",
        "layer_fact_medium_v1",
    )
    assert select_tuning_action_playbook(severity="high", weakest_layer="decision") == (
        "memory_snapshot",
        "layer_decision_high_v1",
    )
    assert select_tuning_action_playbook(severity="high", weakest_layer="outcome") == (
        "memory_compact",
        "layer_outcome_high_v1",
    )


def test_tuning_layer_resolution_and_backfill_limit_are_bounded() -> None:
    assert normalize_tuning_severity("weird") == "low"
    assert resolve_tuning_layer("procedural") == "decision"
    assert resolve_tuning_backfill_limit(layer="fact", severity="medium", missing_records=99) == 42
    assert resolve_tuning_backfill_limit(layer="unknown", severity="low", missing_records=0) == 12


def test_tuning_snapshot_and_notify_variants_follow_layer_and_severity() -> None:
    assert resolve_tuning_snapshot_tag(layer="decision", severity="low") == "quality-drift-decision-low"
    assert resolve_tuning_notify_variant(layer="decision", severity="medium") == (
        "notify.decision.medium.v1",
        "decision-medium",
    )
