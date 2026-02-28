# Security Policy

Este documento define como reportar vulnerabilidades e o baseline de segurança do ClawLite.

## Como reportar vulnerabilidades

Não abra issue pública com detalhes exploráveis.

Use GitHub Security Advisories do repositório:

- https://github.com/eobarretooo/ClawLite/security/advisories/new

Inclua no reporte:

- descrição da falha;
- impacto esperado;
- passos para reproduzir;
- versão/commit afetado;
- evidências (logs, payloads, traces);
- proposta de mitigação (se houver).

## Escopo

Coberto por esta política:

- CLI e onboarding/configure;
- Gateway (HTTP/WS) e dashboard;
- runtime (multiagente, memória, cron, backup/restore, pairing);
- skills oficiais deste repositório.

## Modelo de confiança

O ClawLite assume uso como assistente pessoal (um operador confiável).

Entradas vindas de canais são consideradas não confiáveis.

Para reduzir risco:

- mantenha token obrigatório no gateway;
- aprove novos remetentes via pairing;
- exponha o gateway publicamente apenas com controles adicionais;
- revise permissões de tools e canais periodicamente.

## Hardening mínimo

1. `security.require_gateway_token=true`
2. `security.redact_tokens_in_logs=true`
3. Pairing habilitado para canais de DM
4. Backups frequentes de `~/.clawlite/`
5. `clawlite doctor` após mudanças de infra/config

## Disclosure responsável

Após correção e validação, a divulgação pública deve ocorrer com patch disponível e orientação objetiva de atualização.
