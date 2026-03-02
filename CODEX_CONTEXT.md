# CODEX_CONTEXT

## Estado atual (2026-03-02)

- Branch: `main`
- Foco desta sessão: limpeza de repositório e padronização da base de testes
- Testes: `48 passed` com `pytest -q tests`

## Mudanças aplicadas nesta limpeza

1. `tests_next/` renomeado para `tests/`.
2. `clawlite/core/__init__.py` criado.
3. Removido do versionamento:
   - `docs-site/`
   - `hub/marketplace/`
   - `scripts/community_pack.py`
   - `scripts/sync_community_downloads.py`
   - `scripts/sync_openclaw_skills.py`
   - `scripts/templates/community/`
4. `clawlite/tools/skill.py` documentado com docstring de módulo e classe.
5. `.gitignore` corrigido: removida entrada inválida `~/.clawlite/`.
6. Referências atualizadas para o novo diretório de testes:
   - `.github/workflows/ci.yml`
   - `docs/OPERATIONS.md`
   - `scripts/smoke_test.sh`

## Nota técnica: tools/skill.py

- Arquivo **necessário** para execução real de skills descobertas por `SKILL.md`.
- Ele conecta descoberta (`SkillsLoader`) com execução (`command:` / `script:`), evitando edição manual de `registry.py` para cada skill nova.

## Próximo passo sugerido

- Revisar README/documentação para remover referências a `docs-site` e `hub/marketplace` se ainda existirem.
