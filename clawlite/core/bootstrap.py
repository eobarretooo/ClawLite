from __future__ import annotations

from pathlib import Path


class BootstrapManager:
    """Gerencia o ciclo de vida do BOOTSTRAP.md no workspace.

    Fluxo de uso:
        mgr = BootstrapManager(workspace_path)
        if mgr.should_run():
            prompt = mgr.get_prompt()
            # injeta prompt no contexto do agente
            ...
            # após o agente responder pela primeira vez:
            mgr.complete()
    """

    def __init__(self, workspace_path: str | Path | None = None) -> None:
        if workspace_path is None:
            workspace_path = Path.home() / ".clawlite" / "workspace"
        self.file = Path(workspace_path) / "BOOTSTRAP.md"

    def should_run(self) -> bool:
        """Retorna True se BOOTSTRAP.md existe e tem conteúdo acionável."""
        return self.file.exists() and bool(self.file.read_text(encoding="utf-8").strip())

    def get_prompt(self) -> str:
        """Retorna o conteúdo de BOOTSTRAP.md."""
        return self.file.read_text(encoding="utf-8")

    def complete(self) -> None:
        """Apaga BOOTSTRAP.md após o agente processar (self-delete)."""
        self.file.unlink(missing_ok=True)
