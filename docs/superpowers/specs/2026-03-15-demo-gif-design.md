# Demo GIF — Design Spec

**Date:** 2026-03-15
**Goal:** Substituir o placeholder `docs/demo.gif` por uma demo animada real do ClawLite.

---

## O que será mostrado

Cena única: `clawlite run "o que você pode fazer?"` com resposta em streaming (bullet points concisos), em janela macOS-style.

**Sequência de estados:**

1. Prompt aparece: `❯ clawlite run "o que você pode fazer?"`
2. Cursor piscando (pausa breve)
3. `⠸ pensando...` aparece em cinza
4. Linha a linha da resposta surge (efeito streaming):
   - `Posso ajudar com muita coisa! Aqui o resumo:`
   - `🧠 Memória — lembro do que conversamos entre sessões`
   - `🔍 Busca — pesquiso na web em tempo real`
   - `💻 Código — escrevo, reviso e executo scripts`
   - `📂 Arquivos — leio, crio e edito arquivos locais`
   - `📡 Canais — respondo no Telegram e Discord`
   - `Use clawlite skills list para ver tudo.`
5. Pausa final de 3s antes de reiniciar o loop

---

## Abordagem técnica: Playwright + Pillow

Sem dependências novas. Playwright já está em `pyproject.toml`; Pillow já instalado.

**Fluxo do script `scripts/make_demo_gif.py`:**

1. Verifica/instala chromium via `playwright install chromium`
2. Renderiza HTML da janela terminal via Playwright (chromium headless)
3. Para cada estado, injeta via JS e captura screenshot PNG (720×400px)
4. Pillow monta os PNGs em GIF animado com delays por frame
5. Salva em `docs/demo.gif` e limpa frames temporários

---

## Especificação visual

| Parâmetro | Valor |
|-----------|-------|
| Dimensões | 720 × 400 px |
| Tema | Catppuccin Mocha |
| Fundo janela | `#1e1e2e` |
| Barra de título | `#2a2a3e` |
| Texto principal | `#cdd6f4` |
| Prompt verde | `#a6e3a1` |
| Comando azul | `#89b4fa` |
| Argumento ciano | `#89dceb` |
| Spinner/rodapé | `#6c7086` |
| Fonte | monospace do sistema (fallback: Courier New) |
| Loop | infinito |
| Duração total | ~15 segundos |

---

## Delays por frame

| Estado | Delay |
|--------|-------|
| Prompt digitando (por char) | 80ms |
| Cursor piscando | 400ms × 2 |
| Spinner | 800ms |
| Primeira linha resposta | 600ms |
| Cada linha subsequente | 500ms |
| Última linha + rodapé | 800ms |
| Pausa final | 3000ms |

---

## Arquivo gerado

`docs/demo.gif` — substitui o placeholder atual (847KB, janela vazia).

---

## Fora de escopo

- Gateway/dashboard web
- Multi-cena (memory list, skills list)
- Configuração de provider real (demo é scripted)
