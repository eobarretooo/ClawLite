# ClawLite Competitive Analysis (nanobot, picoclaw, openclaw)

Data sources:
- https://github.com/HKUDS/nanobot
- https://github.com/sipeed/picoclaw
- https://github.com/openclaw/openclaw

## 1) O que cada concorrente faz bem

### nanobot
- Código extremamente compacto e foco em velocidade de iteração.
- Grande foco em canais de mensagem e setup prático.
- Ritmo alto de releases e melhorias em confiabilidade.
- Forte narrativa de simplicidade + produtividade.

### picoclaw
- Eficiência extrema de runtime (Go, baixo consumo de RAM, boot rápido).
- Portabilidade em hardware barato e arquiteturas diversas.
- Boa narrativa de custo/benefício e deploy em edge.
- Documentação com demonstrações visuais fortes.

### openclaw
- Plataforma mais completa de controle (gateway, UI, apps, nodes, automação).
- Segurança e operações maduras (doctor, políticas, pairing, sandbox).
- Multi-canal robusto e ecossistema amplo de ferramentas/skills.
- Forte arquitetura e documentação profunda.

## 2) Gaps identificados no ClawLite (antes desta rodada)

- Workspace bootstrap formal (arquivos de contexto e memória).
- Templates rápidos de canais para configuração inicial.
- Doctor com checagens de configuração e alertas operacionais.
- Controle explícito de fallback de modelos no CLI.
- Relatório estruturado de posicionamento competitivo.

## 3) O que foi adicionado no ClawLite nesta rodada

### A) Runtime bootstrap + diagnósticos
- `clawlite workspace init`
- `clawlite channels template <telegram|discord|whatsapp>`
- `clawlite doctor` com checagens de token, workspace, providers e warnings.

### B) Controle de modelos e fallback
- `clawlite model status`
- `clawlite model set-fallback <m1> <m2> ...`
- Persistência em `~/.clawlite/config.json`.

## 4) O que o ClawLite já supera

- Foco direto em Linux/Termux com experiência enxuta.
- Curva de customização de skills muito simples.
- Evolução rápida do CLI com onboarding + configure + auth + gateway.
- Documentação bilíngue (PT-BR/EN) já integrada no fluxo.

## 5) Diferencial final do ClawLite (posição atual)

- **Termux-first + produção incremental**: não tenta copiar monólitos; prioriza execução real e leve.
- **Arquitetura modular pragmática**: skills e runtime evoluem por blocos independentes.
- **Operação orientada a autonomia**: onboarding, configure, doctor, fallback e gateway no mesmo produto.

## 6) Próximos passos recomendados

1. P0: Multi-agente persistente no Telegram (core differentiator).
2. Auto-update seguro de skills (assinatura/hash + rollback).
3. Offline mode com Ollama (detecção automática + fallback).
4. Camada de políticas de segurança por canal (pairing/allowlists avançados).
