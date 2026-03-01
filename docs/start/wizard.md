# Onboarding Wizard (CLI)

O wizard CLI é o caminho recomendado para configurar o ClawLite.

```bash
clawlite onboarding
```

## QuickStart vs Avançado

QuickStart (recomendado):

- gateway local (`127.0.0.1:8787`)
- token obrigatório por padrão
- workspace inicializado
- validações essenciais

Avançado (controle total):

- fluxo completo por etapas
- revisão antes de aplicar
- opção de planejar instalação de daemon no Apply

## Canais suportados no wizard/configure

- `telegram`
- `whatsapp`
- `discord`
- `slack`
- `googlechat`
- `irc`
- `signal`
- `imessage`
- `teams`

## Etapas do fluxo avançado

1. Model/Auth
2. Teste de API key
3. Workspace
4. Gateway
5. Canais
6. Daemon
7. Health check (preflight)
8. Skills
9. Review + Apply

## O que o wizard grava

- `~/.clawlite/config.json`
- `~/.clawlite/workspace/` com arquivos base de memória e identidade
- `~/.clawlite/workspace/ONBOARDING_REPORT.md`

## Notas de canal

- `slack`: requer `token` (xoxb) e `app_token` (xapp).
- `googlechat`: requer `serviceAccountFile` (ou secret equivalente) e webhook em `/api/webhooks/googlechat`.
- `irc`: usa modo bridge/webhook em `/api/webhooks/irc`; `relay_url` é opcional para outbound.
- `signal`: funciona por `signal-cli` (`cliPath`) ou `httpUrl` de daemon externo.
- `imessage`: integração legada via `imsg` (`cliPath`).

## Reexecutar onboarding

O wizard pode ser executado novamente sempre que necessário:

```bash
clawlite onboarding
```

Para ajustes rápidos por seção:

```bash
clawlite configure
```
