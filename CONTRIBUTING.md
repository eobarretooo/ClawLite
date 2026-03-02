# Contribuindo para o ClawLite

Obrigado por contribuir.

## Princípios do projeto

- Arquitetura simples e auditável
- Comportamento previsível no runtime
- Documentação alinhada com o código real
- Segurança por padrão para uso pessoal

## Fluxo recomendado

1. Abra issue (bug/proposta) antes de mudança grande.
2. Crie branch focada (`feat/...`, `fix/...`, `docs/...`).
3. Faça mudanças pequenas por módulo.
4. Atualize testes quando houver mudança de comportamento.
5. Rode validação local:
   - `pytest -q`
   - smoke dos comandos alterados (`clawlite --help`, `clawlite start`, `clawlite run`)
6. Abra PR com contexto, risco e evidência de teste.

## Padrões de qualidade

- Não quebrar comandos base: `start`, `run`, `onboard`, `cron`, `skills`.
- Não introduzir regressão de API em `/v1/chat` e `/v1/cron/*` sem migração documentada.
- Nunca versionar segredo/token/chave privada.
- Sempre atualizar docs se CLI/API/fluxo operacional mudar.

## Checklist de PR

- [ ] Escopo e objetivo claros
- [ ] Testes executados e informados
- [ ] Docs atualizadas
- [ ] Sem credenciais no diff
