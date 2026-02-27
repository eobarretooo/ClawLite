# Community Automation Playbook

Este guia consolida o fluxo de automações de comunidade do ClawLite:

1. **Reddit** (OAuth, post de milestone, monitor de menções)
2. **Template de milestone** (texto base reutilizável)
3. **Checklist de divulgação em Threads + GitHub**

---

## 1) Reddit (status atual)

Referência completa: `docs/REDDIT_INTEGRATION.md`

Comandos principais:

```bash
clawlite reddit status
clawlite reddit auth-url
clawlite reddit exchange-code "SEU_CODE"
clawlite reddit post-milestone --title "ClawLite vX.Y.Z" --text "..."
clawlite reddit monitor-once
```

### Validação rápida (ambiente sem OAuth)

- `reddit status` ✅
- `reddit auth-url` ✅
- `reddit monitor-once` retorna `401 Unauthorized` sem `refresh_token` (esperado)

---

## 2) Templates prontos

Arquivos:

- `templates/community/milestone_reddit.md`
- `templates/community/checklist_github_release.md`
- `templates/community/checklist_threads_post.md`

Use os templates diretamente ou gere uma cópia preenchida com o script:

```bash
python3 scripts/community_pack.py \
  --version v0.5.0 \
  --date 2026-02-27 \
  --highlights "Multiagent por thread" "Cron por conversa" "Reddit monitor"
```

Saída padrão: `tmp/community/v0.5.0/`

---

## 3) Fluxo recomendado por milestone

1. **Preparar release no GitHub**
   - Preencher `checklist_github_release.md`
2. **Preparar anúncio no Reddit**
   - Gerar texto base pelo template
   - Rodar `clawlite reddit post-milestone ...`
3. **Publicar no Threads**
   - Adaptar versão curta e CTA
   - Marcar checklist de Threads
4. **Monitorar feedback**
   - Rodar `clawlite reddit monitor-once` periodicamente
   - Aprovar respostas antes de publicar

---

## 4) Dicas operacionais

- Defina subreddits alvo no `~/.clawlite/config.json`.
- Evite spam: ajuste texto por comunidade quando necessário.
- Não responder automaticamente sem revisão humana em menções críticas.
- Reutilize o mesmo "changelog curto" em Reddit, Threads e GitHub para consistência.
