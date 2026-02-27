# Prompt Architecture Notes (inspirado em padrões de mercado)

Referência analisada: prompts públicos reunidos em `system_prompts_leaks/Anthropic`.

## Padrões estruturais observados

1. **Contexto inicial explícito**
   - papel do assistente
   - ambiente de execução
   - data/tempo e limitações do canal

2. **Hierarquia de regras**
   - segurança e políticas primeiro
   - instrução do usuário em seguida
   - comportamento e estilo por último

3. **Blocos temáticos curtos**
   - role/mission
   - tool rules
   - output style
   - edge-cases (falhas, refusals, segurança)

4. **Mecanismos anti-deriva**
   - lembretes de não inventar fatos
   - transparência sobre incerteza
   - validação antes de ação externa

5. **Tom consistente**
   - profissional, direto, operacional
   - redução de verborragia

## Aplicação no ClawLite

- Sistema de prompt base por sessão em `clawlite/runtime/system_prompt.py`
- Contexto persistente via:
  - `AGENTS.md`
  - `SOUL.md`
  - `USER.md`
  - `IDENTITY.md`
- Injeção no pipeline em `clawlite/core/agent.py`

Objetivo: respostas mais consistentes entre sessões, com melhor alinhamento entre segurança, execução e estilo.
