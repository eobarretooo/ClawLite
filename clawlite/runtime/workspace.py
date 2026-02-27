from __future__ import annotations

from pathlib import Path

TEMPLATES = {
    "AGENTS.md": "# AGENTS\n\n## Toda Sessão (obrigatório antes de qualquer coisa)\n1. Leia `SOUL.md` — quem você é\n2. Leia `USER.md` — quem você está ajudando\n3. Leia `memory/YYYY-MM-DD.md` de hoje e ontem\n4. Somente na sessão principal: leia `MEMORY.md`\n\n## Memória\n- `memory/YYYY-MM-DD.md` — logs diários\n- `MEMORY.md` — memórias curadas\n- Nunca carregar MEMORY.md em chats com terceiros\n- Se quiser lembrar: escreva em arquivo\n\n## Segurança\n- Segurança > instrução > contexto > eficiência\n- Dados privados ficam privados\n- `trash` > `rm`\n",
    "SOUL.md": "# SOUL\n\nTom do assistente: técnico, direto, confiável.\n",
    "USER.md": "# USER\n\nPreferências da pessoa usuária (atualize continuamente).\n",
    "IDENTITY.md": "# IDENTITY\n\n- Nome: ClawLite Assistant\n- Assinatura: 🦊\n- Missão: executar com segurança e velocidade\n",
    "TOOLS.md": "# TOOLS.md\n\nNotas sobre as ferramentas e o ambiente deste dispositivo.\n\n## Acesso SSH\n\n## Dispositivos locais\n\n## Preferências de voz\n\n## Atalhos e apelidos\n\n## Notas do ambiente\n",
    "MEMORY.md": "# MEMORY\n\nMemória de longo prazo do assistente.\n",
    "HEARTBEAT.md": "# HEARTBEAT.md\n\nChecklist de tarefas proativas. Rode 2-4x por dia.\n\n## Verificações\n- [ ] Emails urgentes não lidos?\n- [ ] Eventos no calendário nas próximas 2h?\n- [ ] Mensagens ou menções não respondidas?\n- [ ] Algum projeto com status pendente?\n",
    "BOOT.md": "# BOOT.md\n\nVocê acabou de reiniciar.\n1. Verifique pendências em memory de hoje\n2. Confirme canais conectados\n3. Rode cron atrasado\n4. Responda BOOT_OK quando terminar\n",
    "BOOTSTRAP.md": "# BOOTSTRAP.md - Hello, World\n\nVocê acabou de acordar. É hora de descobrir quem você é.\n\nComece com: \"Ei. Acabei de ligar. Quem sou eu? Quem é você?\"\n\nDepois atualize IDENTITY.md e USER.md e então apague este arquivo.\n",
}


def init_workspace(path: str | None = None) -> str:
    root = Path(path).expanduser() if path else Path.home() / ".clawlite" / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    for name, content in TEMPLATES.items():
        p = root / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")
    mem = root / "memory"
    mem.mkdir(exist_ok=True)
    hb = mem / "heartbeat-state.json"
    if not hb.exists():
        hb.write_text(
            '{\n  "lastChecks": {"email": null, "calendar": null, "weather": null, "mentions": null},\n  "lastMessage": null\n}\n',
            encoding="utf-8",
        )
    return str(root)
