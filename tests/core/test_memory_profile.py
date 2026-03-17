from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from clawlite.core.memory_profile import (
    profile_prompt_hint,
    update_profile_from_record,
    update_profile_from_text,
)


def _default_profile() -> dict[str, object]:
    return {
        "communication_style": "balanced",
        "response_length_preference": "normal",
        "timezone": "UTC",
        "language": "pt-BR",
        "emotional_baseline": "neutral",
        "interests": [],
        "recurring_patterns": {},
        "upcoming_events": [],
        "learned_at": "2026-03-17T00:00:00+00:00",
        "updated_at": "2026-03-17T00:00:00+00:00",
    }


def _load_json_dict(path: Path, fallback: dict[str, object]) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(fallback)
    return payload if isinstance(payload, dict) else dict(fallback)


def _write_json_dict(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_iso_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def test_profile_prompt_hint_summarizes_non_default_profile(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                **_default_profile(),
                "response_length_preference": "curto",
                "timezone": "America/Sao_Paulo",
                "language": "en-US",
                "emotional_baseline": "excited",
                "interests": ["viagens", "python"],
                "upcoming_events": [
                    {"title": "Product launch deadline", "happened_at": "2099-05-10T09:30:00+00:00"},
                    {"title": "Old sync", "happened_at": "2000-01-01T10:00:00+00:00"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    hint = profile_prompt_hint(
        load_json_dict=_load_json_dict,
        profile_path=profile_path,
        default_profile=_default_profile,
        parse_iso_timestamp=_parse_iso_timestamp,
    )

    assert "[User Profile]" in hint
    assert "Preferred response length: curto" in hint
    assert "Timezone: America/Sao_Paulo" in hint
    assert "Preferred language: en-US" in hint
    assert "Emotional baseline: excited" in hint
    assert "Recurring interests: viagens, python" in hint
    assert "2099-05-10 Product launch deadline" in hint
    assert "Old sync" not in hint


def test_update_profile_from_text_updates_timezone_topics_and_baseline(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    _write_json_dict(profile_path, _default_profile())

    fixed_now = "2026-03-17T12:00:00+00:00"
    for text in (
        "prefiro respostas curtas, moro em Sao Paulo e gosto de viagens",
        "estou animado com viagens internacionais",
    ):
        update_profile_from_text(
            text,
            load_json_dict=_load_json_dict,
            write_json_dict=_write_json_dict,
            profile_path=profile_path,
            default_profile=_default_profile,
            extract_timezone_fn=lambda raw: "America/Sao_Paulo" if "Sao Paulo" in raw else None,
            extract_topics_fn=lambda raw: ["viagens"] if "viagens" in raw else [],
            detect_emotional_tone=lambda raw: "excited" if "animado" in raw else "neutral",
            utcnow_iso=lambda: fixed_now,
        )

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["response_length_preference"] == "curto"
    assert profile["timezone"] == "America/Sao_Paulo"
    assert profile["interests"] == ["viagens"]
    assert profile["recurring_patterns"]["viagens"]["count"] == 2
    assert profile["emotional_baseline"] == "excited"
    assert profile["updated_at"] == fixed_now


def test_update_profile_from_record_skips_text_sync_when_requested() -> None:
    called: list[str] = []
    record = SimpleNamespace(
        text="prefiro respostas curtas",
        metadata={"skip_profile_sync": True},
    )

    update_profile_from_record(
        record,
        normalize_memory_metadata=lambda value: dict(value),
        update_profile_from_text_fn=lambda text: called.append(f"text:{text}"),
        update_profile_upcoming_events_fn=lambda current: called.append(f"event:{current.text}"),
    )

    assert called == ["event:prefiro respostas curtas"]
