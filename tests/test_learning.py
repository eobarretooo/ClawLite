"""Testes unitários para learning, preferences e stats."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Isola DB e arquivos de preferências em diretório temporário."""
    import clawlite.runtime.learning as lr
    import clawlite.runtime.preferences as pr

    monkeypatch.setattr(lr, "DB_DIR", tmp_path)
    monkeypatch.setattr(lr, "DB_PATH", tmp_path / "learning.db")
    monkeypatch.setattr(lr, "TEMPLATES_PATH", tmp_path / "prompt_templates.json")
    monkeypatch.setattr(pr, "PREFS_PATH", tmp_path / "preferences.json")
    lr._conn = None  # Reset connection
    yield


class TestLearning:
    def test_record_and_stats(self):
        from clawlite.runtime.learning import get_stats, record_task

        record_task("teste prompt 1", "success", duration_s=1.5, model="gpt-4", tokens=100)
        record_task("teste prompt 2", "fail", duration_s=2.0, model="gpt-4", tokens=50)

        stats = get_stats()
        assert stats["total_tasks"] == 2
        assert stats["successes"] == 1
        assert stats["success_rate"] == 50.0
        assert stats["streak"] == 0  # last was fail

    def test_streak(self):
        from clawlite.runtime.learning import get_stats, record_task

        for i in range(5):
            record_task(f"task {i}", "success")
        assert get_stats()["streak"] == 5

    def test_find_similar(self):
        from clawlite.runtime.learning import find_similar_tasks, record_task

        record_task("criar arquivo python", "success", skill="coding")
        results = find_similar_tasks("editar arquivo python")
        assert len(results) >= 1

    def test_retry_strategy(self):
        from clawlite.runtime.learning import get_retry_strategy

        s0 = get_retry_strategy("teste", 0)
        assert s0 is not None and "Reformule" in s0
        s1 = get_retry_strategy("teste", 1)
        assert s1 is not None and "Decomponha" in s1
        s2 = get_retry_strategy("teste", 2)
        assert s2 is not None and "Simplifique" in s2
        assert get_retry_strategy("teste", 3) is None

    def test_templates_learned_on_success(self):
        from clawlite.runtime.learning import get_templates, record_task

        record_task("listar arquivos no diretório", "success", skill="filesystem")
        templates = get_templates("filesystem")
        assert len(templates.get("filesystem", [])) == 1


class TestPreferences:
    def test_learn_and_get(self):
        from clawlite.runtime.preferences import get_preferences, learn_preference

        result = learn_preference("contexto teste", "seja mais curto")
        assert result is not None
        assert result["category"] == "resposta_curta"

        prefs = get_preferences()
        assert len(prefs) == 1

    def test_no_duplicate(self):
        from clawlite.runtime.preferences import get_preferences, learn_preference

        learn_preference("ctx", "use PT-BR")
        learn_preference("ctx", "use PT-BR")
        assert len(get_preferences()) == 1

    def test_build_prefix(self):
        from clawlite.runtime.preferences import build_preference_prefix, learn_preference

        learn_preference("ctx", "seja mais conciso")
        prefix = build_preference_prefix()
        assert "curta" in prefix.lower() or "concis" in prefix.lower()

    def test_remove(self):
        from clawlite.runtime.preferences import get_preferences, learn_preference, remove_preference

        learn_preference("ctx", "formato em json")
        assert len(get_preferences()) == 1
        assert remove_preference(0)
        assert len(get_preferences()) == 0


class TestStats:
    def test_period_filter(self):
        from clawlite.runtime.learning import get_stats, record_task

        record_task("task hoje", "success")
        stats = get_stats(period="today")
        assert stats["total_tasks"] >= 1

    def test_skill_filter(self):
        from clawlite.runtime.learning import get_stats, record_task

        record_task("code task", "success", skill="coding")
        record_task("web task", "success", skill="web")
        stats = get_stats(skill="coding")
        assert stats["total_tasks"] == 1
