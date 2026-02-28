# UX do `clawlite configure` e `clawlite onboarding` (PT-BR)

A experiência de configuração foi redesenhada para público não-técnico:

1. **Menu com ícones + descrições curtas** por opção
2. **Navegação por setas** e marcação com **espaço**
3. **Progresso visual** por etapas concluídas
4. **Validações amigáveis** (campos obrigatórios e porta)
5. **Prévia JSON + confirmação** antes de salvar
6. **Resumo final** objetivo após persistência

## Fluxo do onboarding (alinhado ao OpenClaw)

O `clawlite onboarding` opera em dois modos:

- **QuickStart**: setup rápido com defaults seguros.
- **Avançado**: fluxo completo com etapas explícitas e confirmação final.

No modo avançado, as etapas seguem:

1. Model/Auth
2. Workspace
3. Gateway
4. Canais
5. Daemon
6. Health check (preflight)
7. Skills
8. Review + Apply (prévia antes de salvar)

## Exemplo do menu

```text
╭──────────────────────────────────────────────╮
│ ⚙️ ClawLite Configure (PT-BR)               │
│ 🟪🟪🟪🟪🟪🟪🟪⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 2/6 etapas • 33% │
╰──────────────────────────────────────────────╯

? Use ↑↓ para navegar e Enter para abrir uma etapa:
❯ 🌐 Gateway
    └─ Host, porta e token de acesso
```

## Exemplo de validação amigável

```text
? 🔌 Porta do gateway: abc
⚠️ Porta precisa ser numérica (ex.: 8787).
```

## Exemplo de resumo final

```text
✅ Configuração concluída
🤖 Modelo: openai/gpt-4o-mini
📡 Telegram: ✅ ativo
💬 Discord: ❌ desativado
🧩 Skills ativas: 5
🌐 Gateway: 0.0.0.0:8787
🕸️ Web tools: ✅ ativado
```
