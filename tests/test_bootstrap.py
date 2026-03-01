from __future__ import annotations

import tempfile
from pathlib import Path

from clawlite.core.bootstrap import BootstrapManager


def test_should_run_false_when_file_missing():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = BootstrapManager(tmp)
        assert mgr.should_run() is False


def test_should_run_false_when_file_empty():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "BOOTSTRAP.md").write_text("   \n\n", encoding="utf-8")
        mgr = BootstrapManager(tmp)
        assert mgr.should_run() is False


def test_should_run_true_when_file_has_content():
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "BOOTSTRAP.md").write_text("# Tarefa inicial\n- fazer X", encoding="utf-8")
        mgr = BootstrapManager(tmp)
        assert mgr.should_run() is True


def test_get_prompt_returns_content():
    with tempfile.TemporaryDirectory() as tmp:
        content = "# Bootstrap\nExecute o setup inicial."
        Path(tmp, "BOOTSTRAP.md").write_text(content, encoding="utf-8")
        mgr = BootstrapManager(tmp)
        assert mgr.get_prompt() == content


def test_complete_deletes_file():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp, "BOOTSTRAP.md")
        f.write_text("conteúdo", encoding="utf-8")
        mgr = BootstrapManager(tmp)
        assert mgr.should_run() is True
        mgr.complete()
        assert mgr.is_completed() is True
        assert not f.exists()
        # segunda chamada não levanta exceção
        mgr.complete()


def test_complete_noop_when_file_missing():
    with tempfile.TemporaryDirectory() as tmp:
        mgr = BootstrapManager(tmp)
        mgr.complete()  # não deve levantar exceção
        assert mgr.is_completed() is True


def test_should_not_run_when_completed_marker_exists():
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        workspace.joinpath("BOOTSTRAP.md").write_text("conteúdo", encoding="utf-8")
        workspace.joinpath(".bootstrap_completed").write_text("done", encoding="utf-8")
        mgr = BootstrapManager(workspace)
        assert mgr.should_run() is False


def test_full_cycle():
    """Simula o ciclo completo: should_run → get_prompt → complete."""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp, "BOOTSTRAP.md")
        f.write_text("Olá, sou o bootstrap.", encoding="utf-8")

        mgr = BootstrapManager(tmp)
        assert mgr.should_run() is True

        prompt = mgr.get_prompt()
        assert "bootstrap" in prompt.lower()

        # Simula agente respondendo — chama complete()
        mgr.complete()

        # Arquivo deve ter sido apagado
        assert not f.exists()
        # Nova sessão não deve mais ver o bootstrap
        mgr2 = BootstrapManager(tmp)
        assert mgr2.should_run() is False
