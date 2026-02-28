from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Log, Static, Tree, Input
from textual.binding import Binding

import os
import sys

class ClawLiteTUI(App):
    """
    O Dashboard TUI do ClawLite. 
    Permite rodar o Agente Local com uma interface interativa rica via CMD.
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    
    #main-container {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 30%;
        height: 1fr;
        border: solid green;
        background: $surface;
    }

    #chat-panel {
        width: 70%;
        height: 1fr;
        layout: vertical;
        border: solid blue;
    }
    
    #log-view {
        height: 1fr;
        padding: 1;
        overflow-y: scroll;
    }

    #chat-input {
        dock: bottom;
        height: 3;
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Sair", show=True),
        Binding("c", "clear", "Limpar Log", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.log_widget = Log(id="log-view", highlight=True)

    def compose(self) -> ComposeResult:
        """Cria o layout principal."""
        yield Header(show_clock=True)
        with Container(id="main-container"):
            # Painel esquerdo (Status/Agent Infos)
            with Vertical(id="left-panel"):
                yield Static("🦊 [bold green]ClawLite Engine[/]\n\nStatus: [bold cyan]Online[/]\nModo: TUI Local", classes="box")
                
                # Futura integração com o status de Sessions
                tree = Tree("Sessões Ativas")
                tree.root.add("cli-master (Você)")
                tree.root.expand()
                yield tree

            # Painel Direito (Chat/Logs interativos)
            with Vertical(id="chat-panel"):
                yield self.log_widget
                yield Input(placeholder="Digite sua mensagem pro ClawLite...", id="chat-input")
                
        yield Footer()

    def on_mount(self) -> None:
        """Executado quando a TUI carrega."""
        self.title = "ClawLite Terminal UI"
        self.log_widget.write_line("[!] Bem Vindo ao modo interativo do ClawLite.")
        self.log_widget.write_line("Digite /help no painel abaixo para ver os comandos locais.")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Lida com a entrada de texto do usuário."""
        msg = event.value.strip()
        if not msg:
            return
            
        # Limpa o input
        event.input.value = ""
        
        # Joga na tela o echo humano
        self.log_widget.write_line(f"[bold magenta]Você:[/] {msg}")
        
        # Em uma integração real aqui chamamos o agente e usamos SSE/generator
        # Para fins de mockup/esboço, simularemos um delay.
        if msg == "/clear":
            self.action_clear()
        else:
            self.log_widget.write_line(f"[bold cyan]ClawLite:[/] Processando...")

    def action_clear(self) -> None:
        self.log_widget.clear()
        self.log_widget.write_line("[!] Logs limpos.")

if __name__ == "__main__":
    app = ClawLiteTUI()
    app.run()
