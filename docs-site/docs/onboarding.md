# 🚀 Onboarding

Wizard guiado para configurar tudo sem editar JSON manualmente.

## Comando

```bash
clawlite onboarding
```

## Modos disponíveis

- **QuickStart:** aplica defaults seguros para levantar rápido.
- **Avançado:** fluxo completo com revisão antes de salvar.

## Etapas do wizard (estado atual)

1. Model/Auth
2. Teste de API key
3. Workspace
4. Gateway
5. Canais
6. Daemon
7. Health check
8. Skills
9. Review + Apply

## Pós-onboarding recomendado

```bash
clawlite doctor
clawlite start --host 127.0.0.1 --port 8787
```

Se você habilitou daemon:

```bash
clawlite install-daemon --host 127.0.0.1 --port 8787
```

➡️ Próxima página: [Comandos CLI](/comandos-cli)
