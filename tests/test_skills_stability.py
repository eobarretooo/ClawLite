from __future__ import annotations

from clawlite.skills import cron, github, ollama, registry, whisper


def test_cron_remove_invalid_id_is_graceful() -> None:
    msg = cron.run("remove abc")
    assert "ID inválido" in msg


def test_cron_run_invalid_id_is_graceful() -> None:
    msg = cron.run("run xyz")
    assert "ID inválido" in msg


def test_ollama_empty_prompt_returns_ptbr_error() -> None:
    result = ollama.ollama_generate("")
    assert result["error"] == "Prompt não pode ser vazio."


def test_whisper_empty_audio_path_returns_ptbr_error() -> None:
    result = whisper.whisper_transcribe("")
    assert result["error"] == "Caminho do áudio não pode ser vazio."


def test_github_run_without_gh_cli(monkeypatch) -> None:
    monkeypatch.setattr(github, "_gh_available", lambda: False)
    msg = github.run("")
    assert "gh CLI" in msg


def test_registry_descriptions_updated_for_changed_skills() -> None:
    assert "upload" in registry.SKILL_DESCRIPTIONS["google-drive"]
    assert "status" in registry.SKILL_DESCRIPTIONS["ollama"]
    assert "status" in registry.SKILL_DESCRIPTIONS["cron"]
