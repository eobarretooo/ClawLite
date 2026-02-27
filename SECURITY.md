# Security Policy

Obrigado por ajudar a manter o ClawLite seguro.

## Reportar vulnerabilidades

Se você encontrou uma falha de segurança:

1. **Não abra issue pública** com detalhes exploráveis.
2. Envie um relatório privado para o mantenedor via GitHub Security Advisories (aba **Security** do repositório) ou contato privado definido pelo mantenedor.
3. Inclua:
   - descrição da falha
   - impacto esperado
   - passos para reproduzir
   - versão/commit afetado
   - possível mitigação (se houver)

## Escopo

Esta política cobre:
- CLI do ClawLite
- Gateway e dashboard
- Runtime (multiagente, cron, memória, learning)
- Skills oficiais do repositório

## Boas práticas adotadas

- Segredos e arquivos sensíveis ignorados por `.gitignore`
- Tokens e credenciais fora do repositório
- Revisão contínua para evitar exposição acidental de dados

## Disclosure responsável

Após correção e validação, a divulgação pública deve ocorrer com patch disponível e orientação de atualização.
