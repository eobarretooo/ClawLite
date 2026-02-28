# Contribuindo para o ClawLite

Obrigado por contribuir com o ClawLite.

## Objetivo do projeto

O ClawLite é um assistente pessoal local-first. Mudanças devem preservar:

- operação estável em Linux e Termux;
- segurança padrão para uso pessoal;
- onboarding/configure simples para quem não é especialista.

## Fluxo recomendado

1. Abra uma issue com problema ou proposta.
2. Crie branch focada (`feat/...`, `fix/...`, `docs/...`).
3. Faça mudanças pequenas e com escopo claro.
4. Adicione ou ajuste testes quando alterar comportamento.
5. Rode a suíte local (`pytest -q`).
6. Abra PR com contexto técnico e validação executada.

## Padrões de qualidade

- Não quebre comandos centrais: `doctor`, `onboarding`, `configure`, `start`.
- Mantenha compatibilidade com configurações existentes.
- Não adicione segredos no repositório.
- Atualize documentação quando mudar UX/CLI/configuração.

## PR checklist

- [ ] Escopo claro e justificativa técnica.
- [ ] Testes relevantes executados.
- [ ] Docs e exemplos atualizados.
- [ ] Sem credenciais ou dados sensíveis no diff.
