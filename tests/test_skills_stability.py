from __future__ import annotations

import subprocess

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


def test_github_unknown_command_uses_safe_argument_parsing(monkeypatch) -> None:
    monkeypatch.setattr(github, "_gh_available", lambda: True)

    def _fake_run(*args, timeout=30):
        assert args == ("repo", "list")
        return {"data": "ok"}

    monkeypatch.setattr(github, "_run_gh", _fake_run)
    assert github.run('gh "repo" list') == "ok"


def test_github_run_gh_timeout_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(github, "_gh_available", lambda: True)

    def _fake_subprocess_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="gh repo list", timeout=30)

    monkeypatch.setattr(github.subprocess, "run", _fake_subprocess_run)
    result = github._run_gh("repo", "list")
    assert "Timeout" in result["error"]


def test_cron_parse_interval_accepts_uppercase_presets() -> None:
    assert cron._parse_interval("1H") == 3600


def test_ollama_run_generate_parses_model_flag_with_quotes(monkeypatch) -> None:
    monkeypatch.setattr(ollama, "ollama_generate", lambda prompt, model="llama3", **kwargs: {"response": f"{model}:{prompt}"})
    result = ollama.run('generate "olá mundo" --model "qwen2.5"')
    assert result == "qwen2.5:olá mundo"


def test_whisper_invalid_model_returns_ptbr_error() -> None:
    result = whisper.whisper_transcribe("/tmp/audio.wav", model="invalid")
    assert "Modelo inválido" in result["error"]


def test_registry_descriptions_updated_for_changed_skills() -> None:
    assert "upload" in registry.SKILL_DESCRIPTIONS["google-drive"]
    assert "status" in registry.SKILL_DESCRIPTIONS["ollama"]
    assert "status" in registry.SKILL_DESCRIPTIONS["cron"]
