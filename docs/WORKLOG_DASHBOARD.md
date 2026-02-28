# WORKLOG Dashboard (Sprint 1 / P0)

Data: 2026-02-27

## Entregas

### 1) Cron panel (endpoints + UI)
- Endpoint `/api/cron` (GET/POST) e `/api/cron/{id}` (DELETE) já existentes foram conectados de forma completa no novo painel `⏱️ Cron` do `dashboard.html`.
- UI adicionada para:
  - listar jobs;
  - criar job (name/text/interval/channel/chat_id);
  - remover job;
  - feedback visual de sucesso/erro.

### 2) Channels panel status/config
- Mantido status em `/api/channels/status`.
- Novo endpoint `PUT /api/channels/config` para salvar configuração de canais com saneamento básico:
  - enabled/token/account/stt_enabled/tts_enabled.
- UI `📡 Channels` adicionada para visualizar/editar/salvar canais.

### 3) Config apply/restart seguro
- Novo endpoint `POST /api/dashboard/config/apply`:
  - valida model/channels;
  - suporta `dry_run`;
  - aplica `save_config` quando não é dry-run.
- Novo endpoint `POST /api/dashboard/config/restart`:
  - fluxo seguro/noop (não derruba runtime nos testes),
  - retorna status claro (`performed: false`, mensagem explícita).
- UI `⚙️ Config` com ações:
  - salvar settings;
  - apply;
  - dry-run apply;
  - restart seguro.

### 4) Debug/update panel básico
- Novo endpoint `GET /api/dashboard/debug` com versão/runtime/paths/uptime.
- Novo endpoint `POST /api/dashboard/update` com `dry_run`/`apply` (via `update_skills`) e tratamento de erro 400.
- UI `🧪 Debug` e `⬆️ Update` adicionadas com visualização de payload/resultados.

### 5) Testes
- Atualizado `tests/test_cron_channels_metrics.py` com cobertura adicional:
  - config apply + restart + debug;
  - channels config save;
  - update endpoint (com monkeypatch para evitar rede).

## Observações
- Mantido comportamento compatível com ambiente de teste.
- Restart de config é intencionalmente seguro/noop neste estágio P0 para evitar side effects em runtime embutido.

---

Data: 2026-02-28

## Ciclo curto (validação APIs/WS + UX)

### Validação executada
- Testes de integração do dashboard/API/WS executados com sucesso:
  - `tests/test_gateway_dashboard.py`
  - `tests/test_cron_channels_metrics.py`
  - `tests/test_cli_gateway_dashboard_integration.py`
- Resultado: **17 testes passando** (incluindo cobertura de endpoints e WebSocket `/ws/chat` e `/ws/logs`).

### Melhoria pequena de UX/integração aplicada
- Arquivo: `clawlite/gateway/dashboard.html`
- Ajustes no chat WebSocket:
  - botão **Enviar** começa desabilitado até a conexão WS ficar pronta;
  - construção de URL WS ficou explícita por protocolo (`ws://`/`wss://`) usando `location.protocol` + `location.host`;
  - feedback visual no bloco de auth para estados: conectando, conectado, desconectado e erro;
  - reconexão automática curta (2s) quando a conexão cai.

### Impacto
- Evita clique “silencioso” em Enviar antes do socket abrir.
- Melhora resiliência do painel em quedas transitórias de WS sem exigir refresh manual.
