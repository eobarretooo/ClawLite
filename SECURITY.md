# Security Policy

Este documento define como reportar vulnerabilidades no ClawLite e o baseline mínimo de operação segura.

## Reporte de vulnerabilidade

Não publique detalhes exploráveis em issue pública.

Use:
- https://github.com/eobarretooo/ClawLite/security/advisories/new

Inclua:
- descrição técnica
- impacto prático
- passos de reprodução
- commit/versão afetada
- evidências (logs, payloads, stacktrace)

## Escopo coberto

- CLI (`start`, `run`, `onboard`, `cron`, `skills`)
- Gateway (`/health`, `/v1/chat`, `/v1/cron/*`, `/v1/ws`)
- Providers e integração com APIs externas
- Tools locais (exec/files/web/cron/message/spawn/mcp)
- Canais e componentes de scheduler

## Modelo de ameaça

- Entrada de usuário/canal é não confiável.
- Tools com execução local são privilegiadas.
- Chaves de provider são segredos críticos.

## Hardening recomendado

1. Definir token no gateway e proteger acesso de rede.
2. Rodar com usuário sem privilégios administrativos.
3. Restringir permissões de arquivo em `~/.clawlite/` (`700` ou `600` quando aplicável).
4. Revisar skills com `command/script` antes de habilitar em produção.
5. Aplicar rotação de chaves de provider periodicamente.

## Disclosure responsável

Depois da correção, publique patch + orientação clara de atualização.
