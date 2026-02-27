# ClawLite Release Notes

## v0.4.1 - 2026-02-27

### Resumo
Release incremental focada em **voz**, **memória persistente**, **learning/stats**, melhoria de **UX/configuração**, e revisão de docs/branding para o fluxo oficial do ClawLite.

### Principais entregas
- Pipeline de voz (STT/TTS) para Telegram e WhatsApp.
- Memória persistente com sumarização automática ao encerrar sessão.
- Aprendizado contínuo com Task Tracker, Preference Learning e métricas (`clawlite stats`).
- Melhorias de operação: `clawlite start` como alias, `status` + `doctor` expandidos e configure resiliente para non-TTY.
- Skills com auto-update seguro (trust policy, rollback, agendamento).
- Revisão completa de docs/branding e onboarding guiado.

### Changelog completo (v0.4.0..v0.4.1)

```text
f410dbf docs(quickstart): enforce full guided setup incl. voice in onboarding
7e83c46 feat(voice): add STT/TTS pipeline for Telegram and WhatsApp
686ecbf fix(locale): replace deprecated getdefaultlocale with getlocale
6cf79fc docs(readme): professional rewrite synced with real v0.4.x status
c0f5f1c docs(branding): use animated mascot on docs homepage
c984efe brand: add animated mascot asset and use it in README
4957fff docs: update README/docs with official logo and Vercel site link
f1c394f brand: set official ClawLite mascot logo from v0.dev site
91910d0 feat(skills): auto-update with trust policy, rollback and runtime scheduling
09d8bc7 feat(memory): auto-save CLI session summaries on exit
62ca376 feat(memory): add persistent session memory architecture with semantic search and compaction
c0e7754 fix(configure): handle non-tty smoke runs gracefully
9341dfa stabiliza skills alteradas e melhora mensagens PT-BR
649c3bf docs: atualizar README e docs para fluxo atual de operação
bf99c32 docs+scripts: consolidate community automation playbook and milestone templates
769fc0a fix(cli): add clawlite start command alias for gateway startup
851ff75 test: testes unitários para learning, preferences e stats
7814c6c feat: dashboard Learning + endpoint /api/learning/stats
2e6c8d2 feat: comando 'clawlite stats' com rich tables
c079de6 feat: integrar aprendizado contínuo no agent pipeline
30ff8eb feat: Task Tracker com SQLite e Preference Learning
32b2f3b docs(memory): save full session summary — v0.4.0 status and roadmap
828dcc2 test/docs: cobre configure-onboarding-status-doctor e atualiza README
c2c0cdf feat(runtime): adiciona clawlite status e doctor expandido
b040a2a feat(cli): novo configurador interativo OpenClaw-style
91a5ed4 feat(reddit): add oauth, milestone posting and hourly mention monitor with telegram approval
```

### Upgrade rápido
```bash
git fetch --tags
git checkout v0.4.1
pip install -e .
```

### Notas
- Tag anterior: `v0.4.0`
- Range desta release: `v0.4.0..v0.4.1`
