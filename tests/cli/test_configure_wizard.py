# tests/cli/test_configure_wizard.py
from __future__ import annotations
import json
from pathlib import Path
import pytest
from clawlite.config.schema import AppConfig
from clawlite.cli.onboarding import (
    _configure_memory,
    _configure_context_budget,
    _configure_jobs,
    _configure_bus,
)
from rich.console import Console


def _console() -> Console:
    return Console(quiet=True)


def test_configure_memory_updates_fields(monkeypatch) -> None:
    config = AppConfig.from_dict({})
    # _configure_memory calls: Prompt(backend), Confirm(proactive), Confirm(auto_cat),
    # Confirm(semantic), Prompt(backoff) [only when proactive=True]
    prompt_answers = iter(["pgvector", "300"])  # backend, backoff
    confirm_answers = iter([True, False, False])  # proactive=True, auto_cat=False, semantic=False
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", lambda *a, **kw: next(prompt_answers))
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", lambda *a, **kw: next(confirm_answers))
    _configure_memory(_console(), config)
    assert config.agents.defaults.memory.proactive is True
    assert config.agents.defaults.memory.backend == "pgvector"


def test_configure_memory_preserves_existing_values(monkeypatch) -> None:
    config = AppConfig.from_dict({"agents": {"defaults": {"memory": {"backend": "pgvector", "proactive": True}}}})
    # User hits Enter on every prompt (keeps current value)
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", lambda *a, **kw: kw.get("default", ""))
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", lambda *a, **kw: kw.get("default", False))
    _configure_memory(_console(), config)
    assert config.agents.defaults.memory.backend == "pgvector"
    assert config.agents.defaults.memory.proactive is True


def test_configure_context_budget_sets_values(monkeypatch) -> None:
    config = AppConfig.from_dict({})
    answers = iter(["16384", "0.1", "60", "200"])  # max_tokens, temperature, max_tool_iterations, memory_window
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", lambda *a, **kw: next(answers))
    _configure_context_budget(_console(), config)
    assert config.agents.defaults.max_tokens == 16384
    assert config.agents.defaults.max_tool_iterations == 60


def test_configure_context_budget_keeps_defaults_on_empty(monkeypatch) -> None:
    config = AppConfig.from_dict({})
    original_tokens = config.agents.defaults.max_tokens
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", lambda *a, **kw: kw.get("default", ""))
    _configure_context_budget(_console(), config)
    assert config.agents.defaults.max_tokens == original_tokens


def test_configure_jobs_sets_workers_and_persist(monkeypatch) -> None:
    config = AppConfig.from_dict({})
    prompt_answers = iter(["4", "/tmp/jobs.db"])
    confirm_answers = iter([True])
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", lambda *a, **kw: next(prompt_answers))
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", lambda *a, **kw: next(confirm_answers))
    _configure_jobs(_console(), config)
    assert config.jobs.worker_concurrency == 4
    assert config.jobs.persist_enabled is True


def test_configure_bus_enables_journal(monkeypatch) -> None:
    config = AppConfig.from_dict({})
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", lambda *a, **kw: "/tmp/bus.db")
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", lambda *a, **kw: True)
    _configure_bus(_console(), config)
    assert config.bus.journal_enabled is True
    assert config.bus.journal_path == "/tmp/bus.db"


def test_configure_bus_disable_journal(monkeypatch) -> None:
    config = AppConfig.from_dict({"bus": {"journal_enabled": True, "journal_path": "/old/path"}})
    monkeypatch.setattr("clawlite.cli.onboarding.Prompt.ask", lambda *a, **kw: kw.get("default", ""))
    monkeypatch.setattr("clawlite.cli.onboarding.Confirm.ask", lambda *a, **kw: False)
    _configure_bus(_console(), config)
    assert config.bus.journal_enabled is False


