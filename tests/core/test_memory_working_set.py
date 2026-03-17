from __future__ import annotations

from types import SimpleNamespace

from clawlite.core.memory_working_set import (
    collect_visible_working_set,
    episodic_session_boost,
    normalize_session_id,
    normalize_user_id,
    normalize_working_memory_entry,
    normalize_working_memory_promotion_state,
    normalize_working_memory_session,
    normalize_working_memory_share_scope,
    normalize_working_memory_state_payload,
    parent_session_id,
    synthesize_visible_episode_digest,
    working_episode_context,
    working_episode_visible_in_session,
    working_memory_episode_summary,
    working_memory_related_sessions,
    working_memory_share_group,
)


def _share_scope(value: object, session_id: str) -> str:
    return normalize_working_memory_share_scope(
        value,
        session_id=session_id,
        allowed_scopes=frozenset({"private", "parent", "family"}),
        default_scope_fn=lambda current: "parent" if parent_session_id(current, normalize_session_id_fn=normalize_session_id) else "family",
    )


def test_normalize_working_memory_state_payload_bounds_sessions_and_messages() -> None:
    def _entry(item: object, session_id: str, user_id: str):
        return normalize_working_memory_entry(
            item,
            session_id=session_id,
            fallback_user_id=user_id,
            normalize_session_id_fn=normalize_session_id,
            normalize_user_id_fn=normalize_user_id,
            parent_session_id_fn=lambda current: parent_session_id(current, normalize_session_id_fn=normalize_session_id),
            normalize_working_memory_share_scope_fn=_share_scope,
            normalize_memory_metadata_fn=lambda value: dict(value or {}),
            utcnow_iso=lambda: "2026-03-17T00:00:00+00:00",
        )

    def _session(session_id: str, payload: object):
        return normalize_working_memory_session(
            session_id,
            payload,
            normalize_session_id_fn=normalize_session_id,
            normalize_user_id_fn=normalize_user_id,
            parent_session_id_fn=lambda current: parent_session_id(current, normalize_session_id_fn=normalize_session_id),
            normalize_working_memory_share_scope_fn=_share_scope,
            normalize_working_memory_promotion_state_fn=normalize_working_memory_promotion_state,
            normalize_working_memory_entry_fn=_entry,
            max_messages_per_session=2,
        )

    payload = {
        "sessions": {
            "cli:a": {"updated_at": "2026-03-17T00:00:01+00:00", "messages": [{"role": "user", "content": "a1", "created_at": "2026-03-17T00:00:01+00:00"}]},
            "cli:b": {"updated_at": "2026-03-17T00:00:02+00:00", "messages": [{"role": "user", "content": "b1", "created_at": "2026-03-17T00:00:02+00:00"}]},
            "cli:c": {
                "updated_at": "2026-03-17T00:00:03+00:00",
                "messages": [
                    {"role": "user", "content": "c1", "created_at": "2026-03-17T00:00:01+00:00"},
                    {"role": "assistant", "content": "c2", "created_at": "2026-03-17T00:00:02+00:00"},
                    {"role": "user", "content": "c3", "created_at": "2026-03-17T00:00:03+00:00"},
                ],
            },
        }
    }

    normalized = normalize_working_memory_state_payload(
        payload,
        normalize_working_memory_session_fn=_session,
        max_sessions=2,
    )

    assert set(normalized["sessions"].keys()) == {"cli:b", "cli:c"}
    assert [row["content"] for row in normalized["sessions"]["cli:c"]["messages"]] == ["c2", "c3"]


def test_working_memory_related_sessions_respects_family_and_parent_scope() -> None:
    primary = {
        "session_id": "cli:owner:subagent-a",
        "share_group": "cli:owner",
        "share_scope": "family",
        "parent_session_id": "cli:owner",
    }
    sessions = {
        "cli:owner": {
            "session_id": "cli:owner",
            "share_group": "cli:owner",
            "share_scope": "family",
            "parent_session_id": "",
        },
        "cli:owner:subagent-b": {
            "session_id": "cli:owner:subagent-b",
            "share_group": "cli:owner",
            "share_scope": "family",
            "parent_session_id": "cli:owner",
        },
        "cli:owner:subagent-c": {
            "session_id": "cli:owner:subagent-c",
            "share_group": "cli:owner",
            "share_scope": "private",
            "parent_session_id": "cli:owner",
        },
    }

    related = working_memory_related_sessions(
        sessions,
        primary,
        include_shared_subagents=True,
        normalize_working_memory_session_fn=lambda session_id, payload: dict(payload),
        normalize_working_memory_share_scope_fn=_share_scope,
    )

    assert [row["session_id"] for row in related] == [
        "cli:owner:subagent-a",
        "cli:owner",
        "cli:owner:subagent-b",
    ]


def test_working_episode_visibility_and_boost_follow_share_rules() -> None:
    row = SimpleNamespace(
        source="working-session:cli:owner:subagent-b",
        metadata={
            "working_memory_promoted": True,
            "working_memory_session_id": "cli:owner:subagent-b",
            "working_memory_parent_session_id": "cli:owner",
            "working_memory_share_group": "cli:owner",
            "working_memory_share_scope": "family",
        },
    )

    context = lambda current: working_episode_context(
        current,
        normalize_memory_metadata_fn=lambda value: dict(value or {}),
        normalize_session_id_fn=normalize_session_id,
        parent_session_id_fn=lambda session_id: parent_session_id(session_id, normalize_session_id_fn=normalize_session_id),
        working_memory_share_group_fn=lambda session_id: working_memory_share_group(
            session_id,
            normalize_session_id_fn=normalize_session_id,
            parent_session_id_fn=lambda current_id: parent_session_id(current_id, normalize_session_id_fn=normalize_session_id),
        ),
        normalize_working_memory_share_scope_fn=_share_scope,
    )

    visible = working_episode_visible_in_session(
        row,
        session_id="cli:owner:subagent-a",
        normalize_session_id_fn=normalize_session_id,
        is_working_episode_record_fn=lambda current: True,
        working_episode_context_fn=context,
        parent_session_id_fn=lambda session_id: parent_session_id(session_id, normalize_session_id_fn=normalize_session_id),
        working_memory_share_group_fn=lambda session_id: working_memory_share_group(
            session_id,
            normalize_session_id_fn=normalize_session_id,
            parent_session_id_fn=lambda current_id: parent_session_id(current_id, normalize_session_id_fn=normalize_session_id),
        ),
    )
    boost = episodic_session_boost(
        row,
        session_id="cli:owner:subagent-a",
        normalize_session_id_fn=normalize_session_id,
        is_working_episode_record_fn=lambda current: True,
        working_episode_context_fn=context,
        working_episode_visible_in_session_fn=lambda current, session_id: working_episode_visible_in_session(
            current,
            session_id=session_id,
            normalize_session_id_fn=normalize_session_id,
            is_working_episode_record_fn=lambda value: True,
            working_episode_context_fn=context,
            parent_session_id_fn=lambda current_id: parent_session_id(current_id, normalize_session_id_fn=normalize_session_id),
            working_memory_share_group_fn=lambda current_id: working_memory_share_group(
                current_id,
                normalize_session_id_fn=normalize_session_id,
                parent_session_id_fn=lambda nested_id: parent_session_id(nested_id, normalize_session_id_fn=normalize_session_id),
            ),
        ),
        parent_session_id_fn=lambda session_id: parent_session_id(session_id, normalize_session_id_fn=normalize_session_id),
    )

    assert visible is True
    assert boost == 0.28


def test_working_memory_episode_summary_mentions_topics_and_latest_turns() -> None:
    summary = working_memory_episode_summary(
        "cli:owner",
        [
            {"role": "user", "content": "Need deployment checklist for release"},
            {"role": "assistant", "content": "Deployment checklist is ready"},
        ],
        promotion_window=6,
        normalize_session_id_fn=normalize_session_id,
        extract_topics_fn=lambda text: ["deployment", "release"] if "deployment" in text.lower() else [],
        compact_whitespace_fn=lambda text: " ".join(str(text or "").split()),
    )

    assert "Session episode for cli:owner captured 2 recent messages." in summary
    assert "Topics: deployment, release." in summary
    assert "Latest user intent: Need deployment checklist for release." in summary
    assert "Latest assistant outcome: Deployment checklist is ready." in summary


def test_collect_visible_working_set_deduplicates_and_orders_messages() -> None:
    rows = collect_visible_working_set(
        "cli:owner",
        limit=4,
        include_shared_subagents=True,
        load_working_memory_state_fn=lambda: {
            "sessions": {
                "cli:owner": {
                    "session_id": "cli:owner",
                    "user_id": "42",
                    "messages": [
                        {"role": "assistant", "content": "owner note", "created_at": "2026-03-17T00:00:01+00:00"},
                    ],
                },
                "cli:owner:subagent": {
                    "session_id": "cli:owner:subagent",
                    "user_id": "42",
                    "messages": [
                        {"role": "assistant", "content": "subagent note", "created_at": "2026-03-17T00:00:02+00:00"},
                        {"role": "assistant", "content": "subagent note", "created_at": "2026-03-17T00:00:02+00:00"},
                    ],
                },
            }
        },
        normalize_session_id_fn=normalize_session_id,
        normalize_working_memory_session_fn=lambda session_id, payload: dict(payload) if payload else None,
        working_memory_related_sessions_fn=lambda sessions, primary, include_shared_subagents=True: [primary, sessions["cli:owner:subagent"]],
        normalize_working_memory_entry_fn=lambda payload, session_id, fallback_user_id: {
            "session_id": session_id,
            "role": payload["role"],
            "content": payload["content"],
            "created_at": payload["created_at"],
            "user_id": fallback_user_id,
        },
    )

    assert [row["content"] for row in rows] == ["subagent note", "owner note"]


def test_synthesize_visible_episode_digest_groups_ranked_sessions() -> None:
    rows = [
        SimpleNamespace(
            id="mem-1",
            text="parent deploy summary",
            source="working-session:cli:owner",
            created_at="2026-03-17T00:00:01+00:00",
            metadata={"working_memory_promoted": True, "working_memory_session_id": "cli:owner", "share_scope": "family"},
        ),
        SimpleNamespace(
            id="mem-2",
            text="child checklist details",
            source="working-session:cli:owner:subagent",
            created_at="2026-03-17T00:00:02+00:00",
            metadata={"working_memory_promoted": True, "working_memory_session_id": "cli:owner:subagent", "share_scope": "family"},
        ),
    ]

    digest = synthesize_visible_episode_digest(
        query="deploy checklist",
        session_id="cli:owner",
        records=rows,
        curated_importance={},
        curated_mentions={},
        semantic_enabled=False,
        limit=4,
        normalize_session_id_fn=normalize_session_id,
        is_working_episode_record_fn=lambda row: True,
        rank_records_fn=lambda query, records, **kwargs: list(records)[::-1],
        working_episode_context_fn=lambda row: {
            "session_id": row.metadata["working_memory_session_id"],
            "share_scope": row.metadata["share_scope"],
        },
        episodic_digest_label_fn=lambda active_session_id, target_session_id: "current" if active_session_id == target_session_id else "child",
        compact_whitespace_fn=lambda text: " ".join(str(text or "").split()),
    )

    assert digest is not None
    assert digest["count"] == 2
    assert digest["sessions"][0]["session_id"] == "cli:owner:subagent"
    assert "child:cli:owner:subagent" in digest["summary"]
