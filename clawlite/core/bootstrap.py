from __future__ import annotations

from datetime import datetime, timezone
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

    BOOTSTRAP_FILENAME = "BOOTSTRAP.md"
    COMPLETED_MARKER_FILENAME = ".bootstrap_completed"

    def __init__(self, workspace_path: str | Path | None = None) -> None:
        if workspace_path is None:
            workspace_path = Path.home() / ".clawlite" / "workspace"
        self.workspace = Path(workspace_path)
        self.file = self.workspace / self.BOOTSTRAP_FILENAME
        self.completed_marker = self.workspace / self.COMPLETED_MARKER_FILENAME

    def is_completed(self) -> bool:
        return self.completed_marker.exists()

    def should_run(self) -> bool:
        """Retorna True se BOOTSTRAP.md existe e tem conteúdo acionável."""
        if self.is_completed():
            return False
        return self.file.exists() and bool(self.file.read_text(encoding="utf-8").strip())

    def get_prompt(self) -> str:
        """Retorna o conteúdo de BOOTSTRAP.md."""
        return self.file.read_text(encoding="utf-8")

    def complete(self) -> None:
        """Marca bootstrap como concluído e remove BOOTSTRAP.md."""
        self.completed_marker.parent.mkdir(parents=True, exist_ok=True)
        self.completed_marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        self.file.unlink(missing_ok=True)
