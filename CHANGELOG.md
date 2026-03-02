# Changelog

Mudanças relevantes do ClawLite.

## [Unreleased]

### Changed
- Limpeza de documentação Markdown para refletir apenas o runtime atual.
- Atualização de README, CONTRIBUTING, SECURITY e ROADMAP para comandos/fluxos vigentes.
- Atualização da documentação do site (`docs-site/docs`) removendo páginas legadas.

### Removed
- Arquivos internos legados de análise/contexto que não fazem parte da documentação pública.

### Fixed
- `.gitignore` ajustado para ignorar apenas artefatos de sessão na raiz do repositório, permitindo versionar templates de workspace.
- Busca de memória ajustada para priorizar sobreposição léxica e evitar ranking instável com BM25 em corpus pequeno.

## [0.5.0-beta.2] - 2026-03-02

### Changed
- Refatoração consolidada do runtime modular (`core/tools/bus/channels/gateway/scheduler/providers/session/config/workspace/skills/cli`).
- Limpeza ampla de documentação para refletir apenas CLI/API e fluxos atuais.
- README redesenhado com posicionamento de produto e roadmap explícito.

### Added
- Execução real de skills `SKILL.md` via `command/script` no runtime (`run_skill`).
- Versionamento dos templates de workspace (`IDENTITY`, `SOUL`, `USER`, `memory/MEMORY`).

### Fixed
- Correção de recuperação de memória para consultas com score BM25 negativo.
