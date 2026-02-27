# Multi-agente Multi-canal (PT-BR)

## O que entrou

- Modelo unificado de agentes por canal (`agents` + `agent_bindings` em `~/.clawlite/multiagent.db`)
- CLI nova:
  - `clawlite agents create <nome> --channel <...> [--token] [--account] [--personality] [--orchestrator]`
  - `clawlite agents list`
  - `clawlite agents bind <agente> --channel <...> --account <...>`
- Configure/Onboarding agora aceitam múltiplas contas por canal (`accounts`)
- Roteamento por menção + fallback para orquestrador + delegação por tags/intenção
- API Gateway: `/api/agents`, `/api/agents/bind`
- Dashboard com seção **Agents (multi-canal)**

## Exemplo prático (Telegram)

```bash
clawlite agents create orchestrator --channel telegram --account community-main --orchestrator --personality "coordena handoff"
clawlite agents create dev --channel telegram --account dev-bot --personality "resolve bugs e código" --tag bug --tag code
clawlite agents create docs --channel telegram --account docs-bot --personality "escreve documentação" --tag docs --tag tutorial
clawlite agents create community --channel telegram --account community-bot --personality "modera e atende comunidade" --tag suporte --tag comunidade

clawlite agents list
```

### Fluxo esperado

- Mensagem com `@dev` -> roteia para `dev`
- Mensagem sem menção, com “bug”, “code” -> roteia para `dev` por tag
- Mensagem geral sem tag -> cai no `orchestrator`

## Bind multi-canal

Mesmo agente pode atuar em vários canais com contas distintas:

```bash
clawlite agents bind dev --channel slack --account workspace-dev
clawlite agents bind dev --channel discord --account guild-dev
clawlite agents bind docs --channel teams --account tenant-docs
```

## Configure > Channels

Em cada canal, use o campo de contas múltiplas no formato:

- Telegram: `account:token`
- Slack: `workspace:token`
- Discord: `guild:token`
- WhatsApp: `instance:token`
- Teams: `tenant:token`

Separar por vírgula quando houver múltiplas contas.
