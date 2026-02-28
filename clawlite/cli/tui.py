from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Input, Log, Static, Tree


class ClawLiteTUI(App):
    """Dashboard TUI do ClawLite com integracao real ao agente."""

    CSS = """
    Screen { layout: vertical; }
    #main-container { layout: horizontal; height: 1fr; }
    #left-panel { width: 30%; height: 1fr; border: solid green; background: $surface; }
    #chat-panel { width: 70%; height: 1fr; layout: vertical; border: solid blue; }
    #log-view { height: 1fr; padding: 1; overflow-y: scroll; }
    #chat-input { dock: bottom; height: 3; margin: 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Sair", show=True),
        Binding("c", "clear", "Limpar Log", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.log_widget = Log(id="log-view", highlight=True)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main-container"):
            with Vertical(id="left-panel"):
                yield Static(
                    "[bold green]ClawLite Engine[/]\n\n"
                    "Status: [bold cyan]Online[/]\n"
                    "Modo: TUI Local",
                    classes="box",
                )
                tree = Tree("Sessoes Ativas")
                tree.root.add("tui-session (Voce)")
                tree.root.expand()
                yield tree

            with Vertical(id="chat-panel"):
                yield self.log_widget
                yield Input(placeholder="Digite sua mensagem pro ClawLite...", id="chat-input")

        yield Footer()

    def on_mount(self) -> None:
        self.title = "ClawLite Terminal UI"
        self.log_widget.write_line("[!] Bem-vindo ao modo interativo do ClawLite.")
        self.log_widget.write_line("Digite sua mensagem abaixo. /clear limpa, /help mostra comandos.")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return

        event.input.value = ""
        self.log_widget.write_line(f"[bold magenta]Voce:[/] {msg}")

        if msg == "/clear":
            self.action_clear()
            return

        if msg == "/help":
            self.log_widget.write_line(
                "[dim]/clear[/] - Limpar log\n"
                "[dim]/status[/] - Status do sistema\n"
                "[dim]q[/] - Sair\n"
                "Qualquer outro texto e enviado ao agente."
            )
            return

        if msg == "/status":
            try:
                from clawlite.runtime.status import runtime_status

                status = runtime_status()
                self.log_widget.write_line(f"[bold cyan]Status:[/] {status}")
            except Exception as e:
                self.log_widget.write_line(f"[bold red]Erro ao obter status:[/] {e}")
            return

        self.log_widget.write_line("[dim]Processando...[/]")
        try:
            import asyncio
            from clawlite.core.agent import run_task_with_meta

            try:
                reply, meta = await asyncio.to_thread(run_task_with_meta, msg, "", "tui-session")
            except TypeError:
                reply, meta = await asyncio.to_thread(run_task_with_meta, msg)
            mode = str(meta.get("mode", "unknown"))
            model = str(meta.get("model", "unknown"))
            self.log_widget.write_line(f"[dim]meta: mode={mode} model={model}[/]")
            self.log_widget.write_line(f"[bold cyan]ClawLite:[/] {reply}")
        except Exception as e:
            self.log_widget.write_line(f"[bold red]Erro:[/] {e}")

    def action_clear(self) -> None:
        self.log_widget.clear()
        self.log_widget.write_line("[!] Logs limpos.")


if __name__ == "__main__":
    app = ClawLiteTUI()
    app.run()
