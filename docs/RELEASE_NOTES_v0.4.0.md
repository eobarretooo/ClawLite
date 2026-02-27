# ClawLite Release Notes

## v0.4.0 - 2026-02-27

### Principais entregas
- Multi-agente persistente para Telegram (MVP)
- Dashboard v2 com chat realtime + telemetria + logs
- Marketplace de skills seguro (install/update/publish)
- Runtime avançado: offline fallback Ollama, cron por conversa, notificações inteligentes, modo bateria
- UX PT-BR no configure/onboarding + docs i18n
- Hardening e suíte de testes ampliada

### Commits recentes

```
fd901c5 docs(dashboard): atualizar guia da v2 e endpoints de API
12734e3 feat(dashboard): melhorar UX de skills, telemetria e logs em tempo real
9814967 feat(gateway): integrar chat real e telemetria avançada no dashboard
bcab0f7 docs: adicionar troubleshooting para erros de skills e comandos
5c9c065 test(integration): adicionar 5 cenarios CLI+gateway+dashboard
7aaaaab refactor(cli): padronizar erros e mensagens pt-br em auth/skill/cron/battery/agents
9f3a81d fix(skills): corrigir indentation error em aws, ssh e supabase
24b9a7e docs: update configuration guide and add example config for new runtime modes
12f47db feat(runtime): add conversation cron jobs and configurable battery throttling
15a4009 feat(runtime): add offline fallback with Ollama and smart notifications
f0d020f docs/tests: document dashboard MVP and add gateway dashboard API tests
d194739 feat(gateway): add full dashboard API, chat/log websockets and local persistence
5787f8a docs(config): exemplos ASCII da nova experiência de configuração
b222231 feat(config): nova UX PT-BR no configure e onboarding
5c4b483 docs(memory): register reprioritization and ClawLite focus
c3eb5f8 feat(skills): add secure marketplace install/update/publish workflow
4c651bc docs: document telegram multi-agent MVP and CLI flow
4457546 feat(agents): add persistent sqlite workers and local label routing
4f385ed brand: update mascot with improved fox SVG provided by user
650060e docs(strategy): add competitive analysis and ClawLite differentiation report
1120306 feat(models): add fallback profile controls inspired by multi-provider assistants
561bfde feat(runtime): add workspace bootstrap, channel templates and enhanced doctor checks
01742f0 feat(branding): add ClawLite mascot ascii onboarding and SVG logo
473d370 docs: upgrade README with professional structure inspired by awesome skill hubs
480aeeb feat(skill-port): import rss from openclaw/skills archive
173ca2d feat(skill-port): import firebase from openclaw/skills archive
da3bd5e feat(skill-port): import docker from openclaw/skills archive
1ec5c4a feat(skill-port): import web-search from openclaw/skills archive
2f54b48 feat(skill-port): import browser from openclaw/skills archive
bc8eb75 feat(skill-port): import find-skills from openclaw/skills archive
```
