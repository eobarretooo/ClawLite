# SELF.md

Documento gerado a partir do código atual do ClawLite. Este arquivo existe para o próprio agente se orientar sem inventar comportamento que o runtime não implementa.

## 1. O que é o ClawLite

- ClawLite é um runtime de agente autônomo local-first, com gateway FastAPI, memória persistente, tools, skills, cron, heartbeat e canais reais de chat.
- O projeto roda em Linux e também tem caminho documentado para Android via Termux + `proot-distro` Ubuntu.
- A filosofia real do código é local-first: o runtime, o estado e o workspace ficam na sua máquina. O projeto pode usar APIs externas de LLM, mas também suporta runtimes locais como Ollama e vLLM.

## 2. Como o agente funciona

- O loop principal fica em `clawlite/core/engine.py` e roda enquanto ainda houver iterações disponíveis.
- O limite padrão por turno é `40`, vindo de `agents.defaults.max_tool_iterations`.
- Em cada iteração, o engine:
  1. lê histórico da sessão;
  2. consulta a policy de memória e planeja snippets relevantes;
  3. monta o prompt com workspace + perfil do usuário + skills + memória + resumo de histórico + contexto runtime;
  4. chama o provider atual;
  5. se vierem `tool_calls`, executa cada tool via `ToolRegistry`, grava o resultado e volta ao loop;
  6. se vier texto final suficiente, persiste turno/histórico/memória e encerra.
- As tools são validadas por schema JSON, passam por timeout/safety/approval/cache no `ToolRegistry`, e só então executam.
- Histórico de conversa fica no `SessionStore` em `~/.clawlite/state/sessions`.
- Memória persistente fica no `MemoryStore`, com histórico principal em `~/.clawlite/state/memory.jsonl` e artefatos em `~/.clawlite/memory`.
- O prompt final é montado pelo `PromptBuilder`. A ordem prática é: contexto do workspace -> guard rails de identidade/execução -> perfil estruturado do usuário -> memória -> skills -> resumo de histórico -> emoção/memory hints -> histórico recente -> mensagem atual com contexto runtime.

## 3. Arquivo de configuração

- Caminho padrão real no código: `~/.clawlite/config.json`.
- YAML também é aceito pelo loader, por exemplo `~/.clawlite/config.yaml`, mas não é o default.
- Profiles são overlays do mesmo arquivo base, por exemplo `config.prod.json` ou `config.prod.yaml`.
- Não existe hot reload geral de config sem reinício no parser atual. O que existe hoje é:
  - `clawlite validate config` para validar o arquivo;
  - `clawlite telegram refresh` e `clawlite discord refresh` para refresh de transporte específico;
  - `clawlite restart-gateway` para aplicar mudança estrutural de config no runtime em execução.
- Na inicialização, o runtime chama `load_config()`: lê o arquivo base, aplica overlay de profile, mescla env vars suportadas, e valida o resultado com `AppConfig.model_validate(...)`.
- A checagem estrita de chaves desconhecidas só roda com `strict=True` ou `CLAWLITE_CONFIG_STRICT=1`; o comando exato da CLI é `clawlite validate config`.

- Arquivo alvo desta sessão/profile: `~/.clawlite/config.json`.
- Workspace configurado agora: `~/.clawlite/workspace`.

#### `root`
| Campo | Padrão | O que faz |
|---|---|---|
| `workspace_path` | `~/.clawlite/workspace` | Caminho do workspace que o prompt builder e o loader usam. |
| `state_path` | `~/.clawlite/state` | Caminho base do estado persistente do runtime. |
#### `provider.model`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.model` | `gemini/gemini-2.5-flash` | Modelo principal resolvido pelo runtime. |
#### `provider.litellm_base_url`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.litellm_base_url` | `https://api.openai.com/v1` | Base URL global para providers compatíveis com LiteLLM/OpenAI. |
#### `provider.litellm_api_key`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.litellm_api_key` | `""` | API key global de fallback para providers compatíveis. |
#### `provider.retry_max_attempts`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.retry_max_attempts` | `3` | Campo `retry_max_attempts` de o bloco `provider.retry_max_attempts`. |
#### `provider.retry_initial_backoff_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.retry_initial_backoff_s` | `0.5` | Backoff usado por o bloco `provider.retry_initial_backoff_s`. |
#### `provider.retry_max_backoff_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.retry_max_backoff_s` | `8.0` | Backoff usado por o bloco `provider.retry_max_backoff_s`. |
#### `provider.retry_jitter_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.retry_jitter_s` | `0.2` | Campo `retry_jitter_s` de o bloco `provider.retry_jitter_s`. |
#### `provider.circuit_failure_threshold`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.circuit_failure_threshold` | `3` | Limiar de falhas seguidas antes de abrir circuito em o bloco `provider.circuit_failure_threshold`. |
#### `provider.circuit_cooldown_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.circuit_cooldown_s` | `30.0` | Cooldown em segundos usado por o bloco `provider.circuit_cooldown_s`. |
#### `provider.fallback_model`
| Campo | Padrão | O que faz |
|---|---|---|
| `provider.fallback_model` | `""` | Modelo fallback usado pelo failover quando configurado. |
#### `providers.openrouter`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.openrouter.api_key` | `""` | API key usada por o override do provider OpenRouter. |
| `providers.openrouter.api_base` | `""` | Base URL explícita usada por o override do provider OpenRouter. |
| `providers.openrouter.extra_headers` | `{}` | Headers extras enviados por o override do provider OpenRouter. |
#### `providers.gemini`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.gemini.api_key` | `""` | API key usada por o override do provider Gemini. |
| `providers.gemini.api_base` | `""` | Base URL explícita usada por o override do provider Gemini. |
| `providers.gemini.extra_headers` | `{}` | Headers extras enviados por o override do provider Gemini. |
#### `providers.openai`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.openai.api_key` | `""` | API key usada por o override do provider OpenAI. |
| `providers.openai.api_base` | `""` | Base URL explícita usada por o override do provider OpenAI. |
| `providers.openai.extra_headers` | `{}` | Headers extras enviados por o override do provider OpenAI. |
#### `providers.anthropic`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.anthropic.api_key` | `""` | API key usada por o override do provider Anthropic. |
| `providers.anthropic.api_base` | `""` | Base URL explícita usada por o override do provider Anthropic. |
| `providers.anthropic.extra_headers` | `{}` | Headers extras enviados por o override do provider Anthropic. |
#### `providers.deepseek`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.deepseek.api_key` | `""` | API key usada por o override do provider DeepSeek. |
| `providers.deepseek.api_base` | `""` | Base URL explícita usada por o override do provider DeepSeek. |
| `providers.deepseek.extra_headers` | `{}` | Headers extras enviados por o override do provider DeepSeek. |
#### `providers.groq`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.groq.api_key` | `""` | API key usada por o override do provider Groq. |
| `providers.groq.api_base` | `""` | Base URL explícita usada por o override do provider Groq. |
| `providers.groq.extra_headers` | `{}` | Headers extras enviados por o override do provider Groq. |
#### `providers.ollama`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.ollama.api_key` | `""` | API key usada por o override do runtime local Ollama. |
| `providers.ollama.api_base` | `""` | Base URL explícita usada por o override do runtime local Ollama. |
| `providers.ollama.extra_headers` | `{}` | Headers extras enviados por o override do runtime local Ollama. |
#### `providers.vllm`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.vllm.api_key` | `""` | API key usada por o override do runtime local vLLM. |
| `providers.vllm.api_base` | `""` | Base URL explícita usada por o override do runtime local vLLM. |
| `providers.vllm.extra_headers` | `{}` | Headers extras enviados por o override do runtime local vLLM. |
#### `providers.custom`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.custom.api_key` | `""` | API key usada por o provider custom. |
| `providers.custom.api_base` | `""` | Base URL explícita usada por o provider custom. |
| `providers.custom.extra_headers` | `{}` | Headers extras enviados por o provider custom. |
#### `providers.extra`
| Campo | Padrão | O que faz |
|---|---|---|
| `providers.extra` | `{}` | Overrides extras de providers fora da lista tipada. |
#### `auth.providers`
| Campo | Padrão | O que faz |
|---|---|---|
| `auth.providers.openai_codex.access_token` | `""` | Access token usado por a autenticação OAuth persistida. |
| `auth.providers.openai_codex.account_id` | `""` | Conta/organização usada por a autenticação OAuth persistida. |
| `auth.providers.openai_codex.source` | `""` | Origem persistida do segredo/token de a autenticação OAuth persistida. |
| `auth.providers.gemini_oauth.access_token` | `""` | Access token usado por a autenticação OAuth persistida. |
| `auth.providers.gemini_oauth.account_id` | `""` | Conta/organização usada por a autenticação OAuth persistida. |
| `auth.providers.gemini_oauth.source` | `""` | Origem persistida do segredo/token de a autenticação OAuth persistida. |
| `auth.providers.qwen_oauth.access_token` | `""` | Access token usado por a autenticação OAuth persistida. |
| `auth.providers.qwen_oauth.account_id` | `""` | Conta/organização usada por a autenticação OAuth persistida. |
| `auth.providers.qwen_oauth.source` | `""` | Origem persistida do segredo/token de a autenticação OAuth persistida. |
#### `agents.defaults.model`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.model` | `gemini/gemini-2.5-flash` | Modelo configurado em o bloco `agents.defaults.model`. |
#### `agents.defaults.provider`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.provider` | `auto` | Provider selecionado em o bloco `agents.defaults.provider`. |
#### `agents.defaults.max_tokens`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.max_tokens` | `8192` | Limite de tokens da resposta do modelo. |
#### `agents.defaults.temperature`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.temperature` | `0.1` | Temperatura enviada ao modelo. |
#### `agents.defaults.context_token_budget`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.context_token_budget` | `7000` | Orçamento de tokens reservado para o prompt. |
#### `agents.defaults.max_tool_iterations`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.max_tool_iterations` | `40` | Máximo de iterações do loop por turno. |
#### `agents.defaults.memory_window`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.memory_window` | `100` | Quantidade de mensagens recentes mantidas no contexto. |
#### `agents.defaults.session_retention_messages`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.session_retention_messages` | `2000` | Campo `session_retention_messages` de o bloco `agents.defaults.session_retention_messages`. |
#### `agents.defaults.session_retention_ttl_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.session_retention_ttl_s` | `null` | Campo `session_retention_ttl_s` de o bloco `agents.defaults.session_retention_ttl_s`. |
#### `agents.defaults.reasoning_effort`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.reasoning_effort` | `null` | Nível de raciocínio pedido ao provider, quando suportado. |
#### `agents.defaults.semantic_history_summary_enabled`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.semantic_history_summary_enabled` | `false` | Campo `semantic_history_summary_enabled` de o bloco `agents.defaults.semantic_history_summary_enabled`. |
#### `agents.defaults.tool_result_compaction_enabled`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.tool_result_compaction_enabled` | `false` | Campo `tool_result_compaction_enabled` de o bloco `agents.defaults.tool_result_compaction_enabled`. |
#### `agents.defaults.tool_result_compaction_threshold_chars`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.tool_result_compaction_threshold_chars` | `3200` | Campo `tool_result_compaction_threshold_chars` de o bloco `agents.defaults.tool_result_compaction_threshold_chars`. |
#### `agents.defaults.workspace_prompt_file_max_bytes`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.workspace_prompt_file_max_bytes` | `16384` | Campo `workspace_prompt_file_max_bytes` de o bloco `agents.defaults.workspace_prompt_file_max_bytes`. |
#### `agents.defaults.semantic_memory`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.semantic_memory` | `false` | Campo `semantic_memory` de o bloco `agents.defaults.semantic_memory`. |
#### `agents.defaults.memory_auto_categorize`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.memory_auto_categorize` | `false` | Campo `memory_auto_categorize` de o bloco `agents.defaults.memory_auto_categorize`. |
#### `agents.defaults.memory`
| Campo | Padrão | O que faz |
|---|---|---|
| `agents.defaults.memory.semantic_search` | `false` | Campo `semantic_search` de a memória do agente padrão. |
| `agents.defaults.memory.auto_categorize` | `false` | Campo `auto_categorize` de a memória do agente padrão. |
| `agents.defaults.memory.proactive` | `false` | Campo `proactive` de a memória do agente padrão. |
| `agents.defaults.memory.proactive_retry_backoff_s` | `300.0` | Backoff usado por a memória do agente padrão. |
| `agents.defaults.memory.proactive_max_retry_attempts` | `3` | Número de tentativas de retry de a memória do agente padrão. |
| `agents.defaults.memory.emotional_tracking` | `false` | Campo `emotional_tracking` de a memória do agente padrão. |
| `agents.defaults.memory.backend` | `sqlite` | Backend configurado para a memória do agente padrão. |
| `agents.defaults.memory.pgvector_url` | `""` | Campo `pgvector_url` de a memória do agente padrão. |
#### `gateway.host`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.host` | `127.0.0.1` | Host HTTP do gateway. |
#### `gateway.port`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.port` | `8787` | Porta HTTP do gateway. |
#### `gateway.startup_timeout_default_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.startup_timeout_default_s` | `15.0` | Campo `startup_timeout_default_s` de o bloco `gateway.startup_timeout_default_s`. |
#### `gateway.startup_timeout_channels_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.startup_timeout_channels_s` | `30.0` | Campo `startup_timeout_channels_s` de o bloco `gateway.startup_timeout_channels_s`. |
#### `gateway.startup_timeout_autonomy_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.startup_timeout_autonomy_s` | `10.0` | Campo `startup_timeout_autonomy_s` de o bloco `gateway.startup_timeout_autonomy_s`. |
#### `gateway.startup_timeout_supervisor_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.startup_timeout_supervisor_s` | `5.0` | Campo `startup_timeout_supervisor_s` de o bloco `gateway.startup_timeout_supervisor_s`. |
#### `gateway.heartbeat`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.heartbeat.enabled` | `true` | Ativa ou desativa o heartbeat do gateway. |
| `gateway.heartbeat.interval_s` | `1800` | Campo `interval_s` de o heartbeat do gateway. |
#### `gateway.auth`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.auth.mode` | `off` | Modo de autenticação HTTP do gateway. |
| `gateway.auth.token` | `""` | Token de autenticação de a autenticação HTTP do gateway. |
| `gateway.auth.allow_loopback_without_auth` | `true` | Campo `allow_loopback_without_auth` de a autenticação HTTP do gateway. |
| `gateway.auth.header_name` | `Authorization` | Campo `header_name` de a autenticação HTTP do gateway. |
| `gateway.auth.query_param` | `token` | Campo `query_param` de a autenticação HTTP do gateway. |
| `gateway.auth.protect_health` | `false` | Campo `protect_health` de a autenticação HTTP do gateway. |
#### `gateway.diagnostics`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.diagnostics.enabled` | `true` | Ativa ou desativa o bloco de diagnostics do gateway. |
| `gateway.diagnostics.require_auth` | `true` | Campo `require_auth` de o bloco de diagnostics do gateway. |
| `gateway.diagnostics.include_config` | `false` | Campo `include_config` de o bloco de diagnostics do gateway. |
| `gateway.diagnostics.include_provider_telemetry` | `true` | Campo `include_provider_telemetry` de o bloco de diagnostics do gateway. |
#### `gateway.supervisor`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.supervisor.enabled` | `true` | Ativa ou desativa o supervisor do runtime. |
| `gateway.supervisor.interval_s` | `20` | Campo `interval_s` de o supervisor do runtime. |
| `gateway.supervisor.cooldown_s` | `30` | Campo `cooldown_s` de o supervisor do runtime. |
#### `gateway.autonomy`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.autonomy.enabled` | `false` | Ativa ou desativa o loop de autonomia. |
| `gateway.autonomy.interval_s` | `900` | Campo `interval_s` de o loop de autonomia. |
| `gateway.autonomy.cooldown_s` | `300` | Campo `cooldown_s` de o loop de autonomia. |
| `gateway.autonomy.timeout_s` | `45.0` | Campo `timeout_s` de o loop de autonomia. |
| `gateway.autonomy.max_queue_backlog` | `200` | Campo `max_queue_backlog` de o loop de autonomia. |
| `gateway.autonomy.session_id` | `autonomy:system` | Campo `session_id` de o loop de autonomia. |
| `gateway.autonomy.max_actions_per_run` | `1` | Campo `max_actions_per_run` de o loop de autonomia. |
| `gateway.autonomy.action_cooldown_s` | `120.0` | Cooldown em segundos usado por o loop de autonomia. |
| `gateway.autonomy.action_rate_limit_per_hour` | `20` | Campo `action_rate_limit_per_hour` de o loop de autonomia. |
| `gateway.autonomy.max_replay_limit` | `50` | Campo `max_replay_limit` de o loop de autonomia. |
| `gateway.autonomy.action_policy` | `balanced` | Policy usada por o loop de autonomia. |
| `gateway.autonomy.environment_profile` | `dev` | Campo `environment_profile` de o loop de autonomia. |
| `gateway.autonomy.min_action_confidence` | `0.55` | Campo `min_action_confidence` de o loop de autonomia. |
| `gateway.autonomy.degraded_backlog_threshold` | `300` | Campo `degraded_backlog_threshold` de o loop de autonomia. |
| `gateway.autonomy.degraded_supervisor_error_threshold` | `3` | Campo `degraded_supervisor_error_threshold` de o loop de autonomia. |
| `gateway.autonomy.audit_export_path` | `""` | Caminho de arquivo usado por o loop de autonomia. |
| `gateway.autonomy.audit_max_entries` | `200` | Campo `audit_max_entries` de o loop de autonomia. |
| `gateway.autonomy.tuning_loop_enabled` | `false` | Campo `tuning_loop_enabled` de o loop de autonomia. |
| `gateway.autonomy.tuning_loop_interval_s` | `1800` | Intervalo em segundos usado por o loop de autonomia. |
| `gateway.autonomy.tuning_loop_timeout_s` | `45.0` | Timeout em segundos usado por o loop de autonomia. |
| `gateway.autonomy.tuning_loop_cooldown_s` | `300` | Cooldown em segundos usado por o loop de autonomia. |
| `gateway.autonomy.tuning_degrading_streak_threshold` | `2` | Campo `tuning_degrading_streak_threshold` de o loop de autonomia. |
| `gateway.autonomy.tuning_recent_actions_limit` | `20` | Campo `tuning_recent_actions_limit` de o loop de autonomia. |
| `gateway.autonomy.tuning_error_backoff_s` | `900` | Backoff usado por o loop de autonomia. |
| `gateway.autonomy.self_evolution_enabled` | `false` | Campo `self_evolution_enabled` de o loop de autonomia. |
| `gateway.autonomy.self_evolution_cooldown_s` | `3600` | Cooldown em segundos usado por o loop de autonomia. |
| `gateway.autonomy.self_evolution_branch_prefix` | `self-evolution` | Campo `self_evolution_branch_prefix` de o loop de autonomia. |
| `gateway.autonomy.self_evolution_require_approval` | `false` | Campo `self_evolution_require_approval` de o loop de autonomia. |
| `gateway.autonomy.self_evolution_enabled_for_sessions` | `[]` | Sessões autorizadas para self-evolution quando a feature estiver ligada. |
#### `gateway.websocket`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.websocket.coalesce_enabled` | `true` | Campo `coalesce_enabled` de o websocket do gateway. |
| `gateway.websocket.coalesce_min_chars` | `24` | Campo `coalesce_min_chars` de o websocket do gateway. |
| `gateway.websocket.coalesce_max_chars` | `120` | Campo `coalesce_max_chars` de o websocket do gateway. |
| `gateway.websocket.coalesce_profile` | `compact` | Campo `coalesce_profile` de o websocket do gateway. |
#### `gateway.rate_limit`
| Campo | Padrão | O que faz |
|---|---|---|
| `gateway.rate_limit.enabled` | `true` | Ativa ou desativa o rate limit do gateway. |
| `gateway.rate_limit.window_s` | `60.0` | Campo `window_s` de o rate limit do gateway. |
| `gateway.rate_limit.chat_requests_per_window` | `60` | Campo `chat_requests_per_window` de o rate limit do gateway. |
| `gateway.rate_limit.ws_chat_requests_per_window` | `60` | Campo `ws_chat_requests_per_window` de o rate limit do gateway. |
| `gateway.rate_limit.exempt_loopback` | `false` | Campo `exempt_loopback` de o rate limit do gateway. |
#### `scheduler.heartbeat_interval_seconds`
| Campo | Padrão | O que faz |
|---|---|---|
| `scheduler.heartbeat_interval_seconds` | `1800` | Intervalo em segundos usado por o bloco `scheduler.heartbeat_interval_seconds`. |
#### `scheduler.timezone`
| Campo | Padrão | O que faz |
|---|---|---|
| `scheduler.timezone` | `UTC` | Timezone usada por o bloco `scheduler.timezone`. |
#### `scheduler.cron_max_concurrent_jobs`
| Campo | Padrão | O que faz |
|---|---|---|
| `scheduler.cron_max_concurrent_jobs` | `2` | Campo `cron_max_concurrent_jobs` de o bloco `scheduler.cron_max_concurrent_jobs`. |
#### `scheduler.cron_completed_job_retention_seconds`
| Campo | Padrão | O que faz |
|---|---|---|
| `scheduler.cron_completed_job_retention_seconds` | `604800` | Campo `cron_completed_job_retention_seconds` de o bloco `scheduler.cron_completed_job_retention_seconds`. |
#### `channels.send_progress`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.send_progress` | `false` | Campo `send_progress` de o bloco `channels.send_progress`. |
#### `channels.send_tool_hints`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.send_tool_hints` | `false` | Campo `send_tool_hints` de o bloco `channels.send_tool_hints`. |
#### `channels.recovery_enabled`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.recovery_enabled` | `true` | Campo `recovery_enabled` de o bloco `channels.recovery_enabled`. |
#### `channels.recovery_interval_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.recovery_interval_s` | `15.0` | Intervalo em segundos usado por o bloco `channels.recovery_interval_s`. |
#### `channels.recovery_cooldown_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.recovery_cooldown_s` | `30.0` | Cooldown em segundos usado por o bloco `channels.recovery_cooldown_s`. |
#### `channels.replay_dead_letters_on_startup`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.replay_dead_letters_on_startup` | `true` | Campo `replay_dead_letters_on_startup` de o bloco `channels.replay_dead_letters_on_startup`. |
#### `channels.replay_dead_letters_limit`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.replay_dead_letters_limit` | `50` | Campo `replay_dead_letters_limit` de o bloco `channels.replay_dead_letters_limit`. |
#### `channels.replay_dead_letters_reasons`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.replay_dead_letters_reasons` | `["send_failed", "channel_unavailable"]` | Campo `replay_dead_letters_reasons` de o bloco `channels.replay_dead_letters_reasons`. |
#### `channels.delivery_persistence_path`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.delivery_persistence_path` | `""` | Caminho de arquivo usado por o bloco `channels.delivery_persistence_path`. |
#### `channels.telegram`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.telegram.enabled` | `false` | Ativa ou desativa o canal Telegram. |
| `channels.telegram.allow_from` | `[]` | Allowlist global de remetentes aceitos no Telegram. |
| `channels.telegram.token` | `""` | Token do bot Telegram. |
| `channels.telegram.mode` | `polling` | Modo de operação de o canal Telegram. |
| `channels.telegram.webhook_enabled` | `false` | Campo `webhook_enabled` de o canal Telegram. |
| `channels.telegram.webhook_secret` | `""` | Segredo de webhook usado por o canal Telegram. |
| `channels.telegram.webhook_path` | `/api/webhooks/telegram` | Caminho de arquivo usado por o canal Telegram. |
| `channels.telegram.webhook_url` | `""` | URL pública de webhook usada por o canal Telegram. |
| `channels.telegram.webhook_fail_fast_on_error` | `false` | Campo `webhook_fail_fast_on_error` de o canal Telegram. |
| `channels.telegram.update_dedupe_limit` | `4096` | Campo `update_dedupe_limit` de o canal Telegram. |
| `channels.telegram.dedupe_state_path` | `""` | Caminho de arquivo usado por o canal Telegram. |
| `channels.telegram.offset_state_path` | `""` | Caminho de arquivo usado por o canal Telegram. |
| `channels.telegram.media_download_dir` | `""` | Diretório usado por o canal Telegram. |
| `channels.telegram.transcribe_voice` | `true` | Campo `transcribe_voice` de o canal Telegram. |
| `channels.telegram.transcribe_audio` | `true` | Campo `transcribe_audio` de o canal Telegram. |
| `channels.telegram.transcription_api_key` | `""` | Campo `transcription_api_key` de o canal Telegram. |
| `channels.telegram.transcription_base_url` | `https://api.groq.com/openai/v1` | Campo `transcription_base_url` de o canal Telegram. |
| `channels.telegram.transcription_model` | `whisper-large-v3-turbo` | Campo `transcription_model` de o canal Telegram. |
| `channels.telegram.transcription_language` | `pt` | Campo `transcription_language` de o canal Telegram. |
| `channels.telegram.transcription_timeout_s` | `90.0` | Timeout em segundos usado por o canal Telegram. |
| `channels.telegram.poll_interval_s` | `1.0` | Intervalo em segundos usado por o canal Telegram. |
| `channels.telegram.poll_timeout_s` | `20` | Timeout em segundos usado por o canal Telegram. |
| `channels.telegram.reconnect_initial_s` | `2.0` | Campo `reconnect_initial_s` de o canal Telegram. |
| `channels.telegram.reconnect_max_s` | `30.0` | Campo `reconnect_max_s` de o canal Telegram. |
| `channels.telegram.send_timeout_s` | `15.0` | Timeout em segundos usado por o canal Telegram. |
| `channels.telegram.send_retry_attempts` | `1` | Número de tentativas de retry de o canal Telegram. |
| `channels.telegram.send_backoff_base_s` | `0.35` | Backoff usado por o canal Telegram. |
| `channels.telegram.send_backoff_max_s` | `8.0` | Backoff usado por o canal Telegram. |
| `channels.telegram.send_backoff_jitter` | `0.2` | Campo `send_backoff_jitter` de o canal Telegram. |
| `channels.telegram.send_circuit_failure_threshold` | `1` | Limiar de falhas seguidas antes de abrir circuito em o canal Telegram. |
| `channels.telegram.send_circuit_cooldown_s` | `60.0` | Cooldown em segundos usado por o canal Telegram. |
| `channels.telegram.typing_enabled` | `true` | Campo `typing_enabled` de o canal Telegram. |
| `channels.telegram.typing_interval_s` | `2.5` | Intervalo em segundos usado por o canal Telegram. |
| `channels.telegram.typing_max_ttl_s` | `120.0` | Campo `typing_max_ttl_s` de o canal Telegram. |
| `channels.telegram.typing_timeout_s` | `5.0` | Timeout em segundos usado por o canal Telegram. |
| `channels.telegram.typing_circuit_failure_threshold` | `1` | Limiar de falhas seguidas antes de abrir circuito em o canal Telegram. |
| `channels.telegram.typing_circuit_cooldown_s` | `60.0` | Cooldown em segundos usado por o canal Telegram. |
| `channels.telegram.reaction_notifications` | `own` | Campo `reaction_notifications` de o canal Telegram. |
| `channels.telegram.reaction_own_cache_limit` | `4096` | Campo `reaction_own_cache_limit` de o canal Telegram. |
| `channels.telegram.dm_policy` | `open` | Policy usada por o canal Telegram. |
| `channels.telegram.group_policy` | `open` | Policy usada por o canal Telegram. |
| `channels.telegram.topic_policy` | `open` | Policy usada por o canal Telegram. |
| `channels.telegram.dm_allow_from` | `[]` | Allowlist específica para DM no Telegram. |
| `channels.telegram.group_allow_from` | `[]` | Allowlist específica para grupos no Telegram. |
| `channels.telegram.topic_allow_from` | `[]` | Allowlist específica para tópicos no Telegram. |
| `channels.telegram.group_overrides` | `{}` | Overrides por grupo/tópico no Telegram. |
| `channels.telegram.pairing_state_path` | `""` | Caminho de arquivo usado por o canal Telegram. |
| `channels.telegram.pairing_notice_cooldown_s` | `30.0` | Cooldown em segundos usado por o canal Telegram. |
| `channels.telegram.callback_signing_enabled` | `false` | Campo `callback_signing_enabled` de o canal Telegram. |
| `channels.telegram.callback_signing_secret` | `""` | Campo `callback_signing_secret` de o canal Telegram. |
| `channels.telegram.callback_require_signed` | `false` | Campo `callback_require_signed` de o canal Telegram. |
#### `channels.discord`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.discord.enabled` | `false` | Ativa ou desativa o canal Discord. |
| `channels.discord.allow_from` | `[]` | Allowlist principal de remetentes de o canal Discord. |
| `channels.discord.token` | `""` | Token do bot Discord. |
| `channels.discord.api_base` | `https://discord.com/api/v10` | Base URL explícita usada por o canal Discord. |
| `channels.discord.timeout_s` | `10.0` | Campo `timeout_s` de o canal Discord. |
| `channels.discord.gateway_url` | `wss://gateway.discord.gg/?v=10&encoding=json` | Campo `gateway_url` de o canal Discord. |
| `channels.discord.gateway_intents` | `46593` | Campo `gateway_intents` de o canal Discord. |
| `channels.discord.gateway_backoff_base_s` | `2.0` | Backoff usado por o canal Discord. |
| `channels.discord.gateway_backoff_max_s` | `30.0` | Backoff usado por o canal Discord. |
| `channels.discord.typing_enabled` | `true` | Campo `typing_enabled` de o canal Discord. |
| `channels.discord.typing_interval_s` | `8.0` | Intervalo em segundos usado por o canal Discord. |
| `channels.discord.transcribe_voice` | `true` | Campo `transcribe_voice` de o canal Discord. |
| `channels.discord.transcribe_audio` | `true` | Campo `transcribe_audio` de o canal Discord. |
| `channels.discord.transcription_api_key` | `""` | Campo `transcription_api_key` de o canal Discord. |
| `channels.discord.transcription_base_url` | `https://api.groq.com/openai/v1` | Campo `transcription_base_url` de o canal Discord. |
| `channels.discord.transcription_model` | `whisper-large-v3-turbo` | Campo `transcription_model` de o canal Discord. |
| `channels.discord.transcription_language` | `pt` | Campo `transcription_language` de o canal Discord. |
| `channels.discord.transcription_timeout_s` | `90.0` | Timeout em segundos usado por o canal Discord. |
| `channels.discord.dm_policy` | `open` | Policy usada por o canal Discord. |
| `channels.discord.group_policy` | `open` | Policy usada por o canal Discord. |
| `channels.discord.allow_bots` | `disabled` | Campo `allow_bots` de o canal Discord. |
| `channels.discord.require_mention` | `false` | Campo `require_mention` de o canal Discord. |
| `channels.discord.ignore_other_mentions` | `false` | Campo `ignore_other_mentions` de o canal Discord. |
| `channels.discord.reply_to_mode` | `all` | Campo `reply_to_mode` de o canal Discord. |
| `channels.discord.slash_isolated_sessions` | `true` | Campo `slash_isolated_sessions` de o canal Discord. |
| `channels.discord.status` | `""` | Campo `status` de o canal Discord. |
| `channels.discord.activity` | `""` | Campo `activity` de o canal Discord. |
| `channels.discord.activity_type` | `4` | Campo `activity_type` de o canal Discord. |
| `channels.discord.activity_url` | `""` | Campo `activity_url` de o canal Discord. |
| `channels.discord.guilds` | `{}` | Campo `guilds` de o canal Discord. |
| `channels.discord.thread_bindings_enabled` | `true` | Campo `thread_bindings_enabled` de o canal Discord. |
| `channels.discord.thread_binding_state_path` | `""` | Caminho de arquivo usado por o canal Discord. |
| `channels.discord.thread_binding_idle_timeout_s` | `0.0` | Timeout em segundos usado por o canal Discord. |
| `channels.discord.thread_binding_max_age_s` | `0.0` | Campo `thread_binding_max_age_s` de o canal Discord. |
| `channels.discord.auto_presence` | `{}` | Campo `auto_presence` de o canal Discord. |
#### `channels.email`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.email.enabled` | `false` | Ativa ou desativa o canal Email. |
| `channels.email.allow_from` | `[]` | Allowlist principal de remetentes de o canal Email. |
| `channels.email.imap_host` | `""` | Campo `imap_host` de o canal Email. |
| `channels.email.imap_port` | `993` | Campo `imap_port` de o canal Email. |
| `channels.email.imap_user` | `""` | Campo `imap_user` de o canal Email. |
| `channels.email.imap_password` | `""` | Senha da conta IMAP. |
| `channels.email.imap_use_ssl` | `true` | Campo `imap_use_ssl` de o canal Email. |
| `channels.email.smtp_host` | `""` | Campo `smtp_host` de o canal Email. |
| `channels.email.smtp_port` | `465` | Campo `smtp_port` de o canal Email. |
| `channels.email.smtp_user` | `""` | Campo `smtp_user` de o canal Email. |
| `channels.email.smtp_password` | `""` | Senha da conta SMTP. |
| `channels.email.smtp_use_ssl` | `true` | Campo `smtp_use_ssl` de o canal Email. |
| `channels.email.smtp_use_starttls` | `true` | Campo `smtp_use_starttls` de o canal Email. |
| `channels.email.poll_interval_s` | `30.0` | Intervalo em segundos usado por o canal Email. |
| `channels.email.mailbox` | `INBOX` | Campo `mailbox` de o canal Email. |
| `channels.email.mark_seen` | `true` | Campo `mark_seen` de o canal Email. |
| `channels.email.dedupe_state_path` | `""` | Caminho de arquivo usado por o canal Email. |
| `channels.email.max_body_chars` | `12000` | Campo `max_body_chars` de o canal Email. |
| `channels.email.from_address` | `""` | Campo `from_address` de o canal Email. |
#### `channels.slack`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.slack.enabled` | `false` | Ativa ou desativa o canal Slack. |
| `channels.slack.allow_from` | `[]` | Allowlist principal de remetentes de o canal Slack. |
| `channels.slack.bot_token` | `""` | Token do bot Slack. |
| `channels.slack.app_token` | `""` | Token de app Slack para Socket Mode. |
| `channels.slack.api_base` | `https://slack.com/api` | Base URL explícita usada por o canal Slack. |
| `channels.slack.timeout_s` | `10.0` | Campo `timeout_s` de o canal Slack. |
| `channels.slack.send_retry_attempts` | `3` | Número de tentativas de retry de o canal Slack. |
| `channels.slack.send_retry_after_default_s` | `1.0` | Campo `send_retry_after_default_s` de o canal Slack. |
| `channels.slack.socket_mode_enabled` | `true` | Campo `socket_mode_enabled` de o canal Slack. |
| `channels.slack.socket_backoff_base_s` | `1.0` | Backoff usado por o canal Slack. |
| `channels.slack.socket_backoff_max_s` | `30.0` | Backoff usado por o canal Slack. |
| `channels.slack.typing_enabled` | `true` | Campo `typing_enabled` de o canal Slack. |
| `channels.slack.working_indicator_enabled` | `true` | Campo `working_indicator_enabled` de o canal Slack. |
| `channels.slack.working_indicator_emoji` | `hourglass_flowing_sand` | Campo `working_indicator_emoji` de o canal Slack. |
#### `channels.whatsapp`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.whatsapp.enabled` | `false` | Ativa ou desativa o canal WhatsApp. |
| `channels.whatsapp.allow_from` | `[]` | Allowlist principal de remetentes de o canal WhatsApp. |
| `channels.whatsapp.bridge_url` | `ws://localhost:3001` | Endpoint da bridge de WhatsApp. |
| `channels.whatsapp.bridge_token` | `""` | Token usado para autenticar com a bridge de WhatsApp. |
| `channels.whatsapp.timeout_s` | `10.0` | Campo `timeout_s` de o canal WhatsApp. |
| `channels.whatsapp.webhook_path` | `/api/webhooks/whatsapp` | Caminho de arquivo usado por o canal WhatsApp. |
| `channels.whatsapp.webhook_secret` | `""` | Segredo de webhook usado por o canal WhatsApp. |
| `channels.whatsapp.send_retry_attempts` | `3` | Número de tentativas de retry de o canal WhatsApp. |
| `channels.whatsapp.send_retry_after_default_s` | `1.0` | Campo `send_retry_after_default_s` de o canal WhatsApp. |
| `channels.whatsapp.typing_enabled` | `true` | Campo `typing_enabled` de o canal WhatsApp. |
| `channels.whatsapp.typing_interval_s` | `4.0` | Intervalo em segundos usado por o canal WhatsApp. |
#### `channels.irc`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.irc.enabled` | `false` | Ativa ou desativa o canal IRC. |
| `channels.irc.host` | `irc.libera.chat` | Host usado por o canal IRC. |
| `channels.irc.port` | `6697` | Porta usada por o canal IRC. |
| `channels.irc.nick` | `clawlite` | Campo `nick` de o canal IRC. |
| `channels.irc.username` | `clawlite` | Campo `username` de o canal IRC. |
| `channels.irc.realname` | `ClawLite` | Campo `realname` de o canal IRC. |
| `channels.irc.channels_to_join` | `[]` | Lista de canais IRC que o bot deve entrar. |
| `channels.irc.use_ssl` | `true` | Campo `use_ssl` de o canal IRC. |
| `channels.irc.connect_timeout_s` | `10.0` | Timeout em segundos usado por o canal IRC. |
#### `channels.extra`
| Campo | Padrão | O que faz |
|---|---|---|
| `channels.extra` | `{}` | Canais extras fora da lista tipada do schema. |
#### `tools.restrict_to_workspace`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.restrict_to_workspace` | `false` | Campo `restrict_to_workspace` de o bloco `tools.restrict_to_workspace`. |
#### `tools.default_timeout_s`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.default_timeout_s` | `20.0` | Timeout em segundos usado por o bloco `tools.default_timeout_s`. |
#### `tools.timeouts`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.timeouts` | `{}` | Overrides de timeout por nome de tool. |
#### `tools.web`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.web.proxy` | `""` | Campo `proxy` de as tools web. |
| `tools.web.timeout` | `15.0` | Timeout padrão usado por as tools web. |
| `tools.web.search_timeout` | `10.0` | Timeout em segundos usado por as tools web. |
| `tools.web.max_redirects` | `5` | Campo `max_redirects` de as tools web. |
| `tools.web.max_chars` | `12000` | Campo `max_chars` de as tools web. |
| `tools.web.block_private_addresses` | `true` | Campo `block_private_addresses` de as tools web. |
| `tools.web.brave_api_key` | `""` | Campo `brave_api_key` de as tools web. |
| `tools.web.brave_base_url` | `https://api.search.brave.com/res/v1/web/search` | Campo `brave_base_url` de as tools web. |
| `tools.web.searxng_base_url` | `""` | Campo `searxng_base_url` de as tools web. |
| `tools.web.allowlist` | `[]` | Allowlist usada por as tools web. |
| `tools.web.denylist` | `[]` | Denylist usada por as tools web. |
#### `tools.exec`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.exec.timeout` | `60` | Timeout padrão usado por a tool exec. |
| `tools.exec.path_append` | `""` | Campo `path_append` de a tool exec. |
| `tools.exec.deny_patterns` | `[]` | Campo `deny_patterns` de a tool exec. |
| `tools.exec.allow_patterns` | `[]` | Campo `allow_patterns` de a tool exec. |
| `tools.exec.deny_path_patterns` | `[]` | Campo `deny_path_patterns` de a tool exec. |
| `tools.exec.allow_path_patterns` | `[]` | Campo `allow_path_patterns` de a tool exec. |
#### `tools.mcp`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.mcp.default_timeout_s` | `20.0` | Timeout em segundos usado por a tool MCP. |
| `tools.mcp.policy.allowed_schemes` | `["http", "https"]` | Campo `allowed_schemes` de a tool MCP. |
| `tools.mcp.policy.allowed_hosts` | `[]` | Campo `allowed_hosts` de a tool MCP. |
| `tools.mcp.policy.denied_hosts` | `[]` | Campo `denied_hosts` de a tool MCP. |
| `tools.mcp.servers` | `{}` | Mapa de servidores MCP nomeados. |
#### `tools.loop_detection`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.loop_detection.enabled` | `false` | Ativa ou desativa a proteção contra loops de tools. |
| `tools.loop_detection.history_size` | `20` | Campo `history_size` de a proteção contra loops de tools. |
| `tools.loop_detection.repeat_threshold` | `3` | Campo `repeat_threshold` de a proteção contra loops de tools. |
| `tools.loop_detection.critical_threshold` | `6` | Campo `critical_threshold` de a proteção contra loops de tools. |
#### `tools.safety`
| Campo | Padrão | O que faz |
|---|---|---|
| `tools.safety.enabled` | `true` | Ativa ou desativa a safety policy de tools. |
| `tools.safety.risky_tools` | `["browser", "exec", "run_skill", "web_fetch", "web_search", "mcp"]` | Lista de tools consideradas arriscadas pela safety policy. |
| `tools.safety.risky_specifiers` | `[]` | Campo `risky_specifiers` de a safety policy de tools. |
| `tools.safety.approval_specifiers` | `["browser:evaluate", "exec", "mcp", "run_skill"]` | Specifiers que exigem aprovação explícita. |
| `tools.safety.approval_channels` | `["discord", "telegram"]` | Canais que participam do fluxo de aprovação. |
| `tools.safety.approval_grant_ttl_s` | `900.0` | Campo `approval_grant_ttl_s` de a safety policy de tools. |
| `tools.safety.blocked_channels` | `[]` | Campo `blocked_channels` de a safety policy de tools. |
| `tools.safety.allowed_channels` | `[]` | Campo `allowed_channels` de a safety policy de tools. |
| `tools.safety.profile` | `""` | Campo `profile` de a safety policy de tools. |
| `tools.safety.profiles` | `{}` | Campo `profiles` de a safety policy de tools. |
| `tools.safety.by_agent` | `{}` | Campo `by_agent` de a safety policy de tools. |
| `tools.safety.by_channel` | `{}` | Campo `by_channel` de a safety policy de tools. |
#### `bus.backend`
| Campo | Padrão | O que faz |
|---|---|---|
| `bus.backend` | `inprocess` | Backend configurado para o bloco `bus.backend`. |
#### `bus.redis_url`
| Campo | Padrão | O que faz |
|---|---|---|
| `bus.redis_url` | `""` | URL do Redis do bus. |
#### `bus.redis_prefix`
| Campo | Padrão | O que faz |
|---|---|---|
| `bus.redis_prefix` | `clawlite:bus` | Prefixo das chaves do Redis do bus. |
#### `bus.journal_enabled`
| Campo | Padrão | O que faz |
|---|---|---|
| `bus.journal_enabled` | `false` | Ativa journal persistente de o bloco `bus.journal_enabled`. |
#### `bus.journal_path`
| Campo | Padrão | O que faz |
|---|---|---|
| `bus.journal_path` | `""` | Caminho de arquivo usado por o bloco `bus.journal_path`. |
#### `observability.enabled`
| Campo | Padrão | O que faz |
|---|---|---|
| `observability.enabled` | `false` | Ativa ou desativa o bloco `observability.enabled`. |
#### `observability.otlp_endpoint`
| Campo | Padrão | O que faz |
|---|---|---|
| `observability.otlp_endpoint` | `""` | Endpoint OTLP de observabilidade. |
#### `observability.service_name`
| Campo | Padrão | O que faz |
|---|---|---|
| `observability.service_name` | `clawlite` | Nome do serviço enviado para observabilidade. |
#### `observability.service_namespace`
| Campo | Padrão | O que faz |
|---|---|---|
| `observability.service_namespace` | `""` | Namespace do serviço enviado para observabilidade. |
#### `jobs.persist_enabled`
| Campo | Padrão | O que faz |
|---|---|---|
| `jobs.persist_enabled` | `false` | Ativa persistência de jobs em disco. |
#### `jobs.persist_path`
| Campo | Padrão | O que faz |
|---|---|---|
| `jobs.persist_path` | `""` | Caminho de arquivo usado por o bloco `jobs.persist_path`. |
#### `jobs.worker_concurrency`
| Campo | Padrão | O que faz |
|---|---|---|
| `jobs.worker_concurrency` | `2` | Concorrência de workers da fila de jobs. |

## 4. Providers disponíveis

| Provider | Tipo | Como configurar | Onde fica a credencial | Base URL padrão / observação |
|---|---|---|---|---|
| `custom` | `openai_compatible` | `provider.model`, `providers.custom.api_base`, `providers.custom.api_key`, `providers.custom.extra_headers` | Config em `providers.custom.api_key`; env (nenhum específico); fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `Sem base URL padrão fixa.`. Custom provider; review the model, auth, and base URL manually before use. |
| `openrouter` | `openai_compatible` | `provider.model`, `providers.openrouter.api_key`, `providers.openrouter.api_base`, `providers.openrouter.extra_headers` | Config em `providers.openrouter.api_key`; env `OPENROUTER_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://openrouter.ai/api/v1`. Multi-model Gateway; 'auto' mode does not require an exact match in the remote list. |
| `aihubmix` | `openai_compatible` | `provider.model`, `providers.aihubmix.api_key`, `providers.aihubmix.api_base`, `providers.aihubmix.extra_headers` | Config em `providers.aihubmix.api_key`; env `AIHUBMIX_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://aihubmix.com/v1`. AiHubMix exposes an OpenAI-compatible multi-model gateway; confirm the upstream model name you want to route. |
| `siliconflow` | `openai_compatible` | `provider.model`, `providers.siliconflow.api_key`, `providers.siliconflow.api_base`, `providers.siliconflow.extra_headers` | Config em `providers.siliconflow.api_key`; env `SILICONFLOW_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.siliconflow.cn/v1`. SiliconFlow uses an OpenAI-compatible base URL; copy the full upstream model id from the SiliconFlow model catalog. |
| `kilocode` | `openai_compatible` | `provider.model`, `providers.kilocode.api_key`, `providers.kilocode.api_base`, `providers.kilocode.extra_headers` | Config em `providers.kilocode.api_key`; env `KILOCODE_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.kilo.ai/api/gateway/`. Multi-model Gateway; confirm the upstream provider embedded in the model name. |
| `gemini` | `openai_compatible` | `provider.model`, `providers.gemini.api_key`, `providers.gemini.api_base`, `providers.gemini.extra_headers` | Config em `providers.gemini.api_key`; env `GEMINI_API_KEY`, `GOOGLE_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://generativelanguage.googleapis.com/v1beta/openai`. Gemini uses an OpenAI-compatible endpoint via Google Generative Language. |
| `groq` | `openai_compatible` | `provider.model`, `providers.groq.api_key`, `providers.groq.api_base`, `providers.groq.extra_headers` | Config em `providers.groq.api_key`; env `GROQ_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.groq.com/openai/v1`. Groq responds via OpenAI-compatible endpoints; prefer low-latency models when possible. |
| `deepseek` | `openai_compatible` | `provider.model`, `providers.deepseek.api_key`, `providers.deepseek.api_base`, `providers.deepseek.extra_headers` | Config em `providers.deepseek.api_key`; env `DEEPSEEK_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.deepseek.com/v1`. DeepSeek responds via OpenAI-compatible endpoints; validate quota and billing before rollout. |
| `together` | `openai_compatible` | `provider.model`, `providers.together.api_key`, `providers.together.api_base`, `providers.together.extra_headers` | Config em `providers.together.api_key`; env `TOGETHER_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.together.xyz/v1`. Together behaves like an OpenAI-compatible gateway; confirm the full upstream model name. |
| `huggingface` | `openai_compatible` | `provider.model`, `providers.huggingface.api_key`, `providers.huggingface.api_base`, `providers.huggingface.extra_headers` | Config em `providers.huggingface.api_key`; env `HUGGINGFACE_HUB_TOKEN`, `HF_TOKEN`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://router.huggingface.co/v1`. The Hugging Face router exposes full upstream models; confirm the repo/model id. |
| `xai` | `openai_compatible` | `provider.model`, `providers.xai.api_key`, `providers.xai.api_base`, `providers.xai.extra_headers` | Config em `providers.xai.api_key`; env `XAI_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.x.ai/v1`. xAI responds via OpenAI-compatible endpoints; confirm access to the chosen Grok model. |
| `mistral` | `openai_compatible` | `provider.model`, `providers.mistral.api_key`, `providers.mistral.api_base`, `providers.mistral.extra_headers` | Config em `providers.mistral.api_key`; env `MISTRAL_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.mistral.ai/v1`. Mistral responds via OpenAI-compatible endpoints; prefer 'latest' aliases to avoid fixed-version drift. |
| `moonshot` | `openai_compatible` | `provider.model`, `providers.moonshot.api_key`, `providers.moonshot.api_base`, `providers.moonshot.extra_headers` | Config em `providers.moonshot.api_key`; env `MOONSHOT_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.moonshot.ai/v1`. Moonshot/Kimi responds via OpenAI-compatible endpoints; confirm regional endpoint availability. |
| `qianfan` | `openai_compatible` | `provider.model`, `providers.qianfan.api_key`, `providers.qianfan.api_base`, `providers.qianfan.extra_headers` | Config em `providers.qianfan.api_key`; env `QIANFAN_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://qianfan.baidubce.com/v2`. Qianfan uses its own OpenAI-compatible endpoint; verify credentials and the Baidu Cloud region. |
| `zai` | `openai_compatible` | `provider.model`, `providers.zai.api_key`, `providers.zai.api_base`, `providers.zai.extra_headers` | Config em `providers.zai.api_key`; env `ZAI_API_KEY`, `Z_AI_API_KEY`, `ZHIPUAI_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.z.ai/api/paas/v4`. Z.AI/GLM responds via a compatible endpoint; confirm that your account is enabled for the GLM model. |
| `nvidia` | `openai_compatible` | `provider.model`, `providers.nvidia.api_key`, `providers.nvidia.api_base`, `providers.nvidia.extra_headers` | Config em `providers.nvidia.api_key`; env `NVIDIA_API_KEY`, `NGC_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://integrate.api.nvidia.com/v1`. NVIDIA NIM responds via OpenAI-compatible endpoints; the catalog may vary by tenant or project. |
| `byteplus` | `openai_compatible` | `provider.model`, `providers.byteplus.api_key`, `providers.byteplus.api_base`, `providers.byteplus.extra_headers` | Config em `providers.byteplus.api_key`; env `BYTEPLUS_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://ark.ap-southeast.bytepluses.com/api/v3`. BytePlus Ark responds via OpenAI-compatible endpoints; confirm the project and regional endpoint. |
| `doubao` | `openai_compatible` | `provider.model`, `providers.doubao.api_key`, `providers.doubao.api_base`, `providers.doubao.extra_headers` | Config em `providers.doubao.api_key`; env `VOLCANO_ENGINE_API_KEY`, `VOLCENGINE_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://ark.cn-beijing.volces.com/api/v3`. Doubao Ark responds via OpenAI-compatible endpoints; confirm that the tenant has access to the chosen model. |
| `volcengine` | `openai_compatible` | `provider.model`, `providers.volcengine.api_key`, `providers.volcengine.api_base`, `providers.volcengine.extra_headers` | Config em `providers.volcengine.api_key`; env `VOLCANO_ENGINE_API_KEY`, `VOLCENGINE_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://ark.cn-beijing.volces.com/api/v3`. Volcengine Ark responds via OpenAI-compatible endpoints; validate region and project before use. |
| `minimax` | `openai_compatible` | `provider.model`, `providers.minimax.api_key`, `providers.minimax.api_base`, `providers.minimax.extra_headers` | Config em `providers.minimax.api_key`; env `MINIMAX_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.minimax.io/anthropic`. MiniMax uses Anthropic-compatible transport; the base URL usually ends with /anthropic. |
| `xiaomi` | `openai_compatible` | `provider.model`, `providers.xiaomi.api_key`, `providers.xiaomi.api_base`, `providers.xiaomi.extra_headers` | Config em `providers.xiaomi.api_key`; env `XIAOMI_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.xiaomimimo.com/anthropic`. Xiaomi Mimo uses Anthropic-compatible transport; confirm a base URL ending with /anthropic. |
| `kimi_coding` | `openai_compatible` | `provider.model`, `providers.kimi_coding.api_key`, `providers.kimi_coding.api_base`, `providers.kimi_coding.extra_headers` | Config em `providers.kimi_coding.api_key`; env `KIMI_API_KEY`, `KIMICODE_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.kimi.com/coding/`. Kimi Coding uses Anthropic-compatible transport and a dedicated /coding/ base URL. |
| `anthropic` | `openai_compatible` | `provider.model`, `providers.anthropic.api_key`, `providers.anthropic.api_base`, `providers.anthropic.extra_headers` | Config em `providers.anthropic.api_key`; env `ANTHROPIC_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.anthropic.com/v1`. Anthropic uses the native /v1/messages transport; confirm the ANTHROPIC_API_KEY value. |
| `openai` | `openai_compatible` | `provider.model`, `providers.openai.api_key`, `providers.openai.api_base`, `providers.openai.extra_headers` | Config em `providers.openai.api_key`; env `OPENAI_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.openai.com/v1`. OpenAI responds via the standard OpenAI-compatible endpoint; validate billing and the active project. |
| `azure_openai` | `openai_compatible` | `provider.model`, `providers.azure_openai.api_key`, `providers.azure_openai.api_base`, `providers.azure_openai.extra_headers` | Config em `providers.azure_openai.api_key`; env `AZURE_OPENAI_API_KEY`, `AZURE_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `Sem default; precisa de endpoint `https://<resource>.../openai/v1`.`. Azure OpenAI now accepts resource-scoped OpenAI v1 base URLs; use your own `https://<resource>.openai.azure.com/openai/v1` or `https://<resource>.services.ai.azure.com/openai/v1` endpoint. |
| `cerebras` | `openai_compatible` | `provider.model`, `providers.cerebras.api_key`, `providers.cerebras.api_base`, `providers.cerebras.extra_headers` | Config em `providers.cerebras.api_key`; env `CEREBRAS_API_KEY`; fallback global `CLAWLITE_LITELLM_API_KEY`, `CLAWLITE_API_KEY`. | `https://api.cerebras.ai/v1`. Cerebras exposes an OpenAI-compatible API; confirm that your account has access to the selected model family. |
| `openai_codex` | `oauth` | `provider.model`, `auth.providers.openai_codex.access_token`, `auth.providers.openai_codex.account_id` | Config em `auth.providers.openai_codex.*`; env `CLAWLITE_CODEX_ACCESS_TOKEN`, `OPENAI_CODEX_ACCESS_TOKEN`, `OPENAI_ACCESS_TOKEN`; arquivo local `~/.codex/auth.json` ou `CLAWLITE_CODEX_AUTH_PATH`. | `https://chatgpt.com/backend-api`. OpenAI Codex uses local OAuth; sign in before validating the provider. |
| `gemini_oauth` | `oauth` | `provider.model`, `auth.providers.gemini_oauth.access_token`, `auth.providers.gemini_oauth.account_id` | Config em `auth.providers.gemini_oauth.*`; env `CLAWLITE_GEMINI_ACCESS_TOKEN`, `GEMINI_ACCESS_TOKEN`, `CLAWLITE_GEMINI_AUTH_PATH`; arquivo local `~/.gemini/oauth_creds.json` ou `CLAWLITE_GEMINI_AUTH_PATH`. | `https://generativelanguage.googleapis.com/v1beta/openai`. Gemini OAuth uses a local OAuth token against the Google OpenAI-compatible endpoint. |
| `qwen_oauth` | `oauth` | `provider.model`, `auth.providers.qwen_oauth.access_token`, `auth.providers.qwen_oauth.account_id` | Config em `auth.providers.qwen_oauth.*`; env `CLAWLITE_QWEN_ACCESS_TOKEN`, `QWEN_ACCESS_TOKEN`, `CLAWLITE_QWEN_AUTH_PATH`; arquivo local `~/.qwen/oauth_creds.json`, `~/.qwen/auth.json` ou `CLAWLITE_QWEN_AUTH_PATH`. | `https://api.qwen.ai/v1`. Qwen OAuth uses a local OAuth token against the Qwen-compatible endpoint. |
| `ollama` | `local` | `provider.model`, `providers.ollama.api_key`, `providers.ollama.api_base`, `providers.ollama.extra_headers` | Sem API key obrigatória; o essencial é a base URL do runtime local. | `http://127.0.0.1:11434/v1`. Ollama requires a running local runtime and a model downloaded ahead of time with 'ollama pull'. |
| `vllm` | `local` | `provider.model`, `providers.vllm.api_key`, `providers.vllm.api_base`, `providers.vllm.extra_headers` | Sem API key obrigatória; o essencial é a base URL do runtime local. | `http://127.0.0.1:8000/v1`. vLLM requires a running server and a model loaded when the process starts. |

Troca de provider no código atual é build-time. Não existe hot-swap genérico sem reinício do gateway. O caminho prático é atualizar config com `clawlite provider use` / `clawlite provider set-auth`, validar, e reiniciar o gateway.

### Troca de provider sem parar o agente

- Não existe hot-swap genérico de provider sem reinício do gateway.
- Para trocar o provider de forma suportada hoje:
  1. `clawlite provider use <provider> --model <provider/model>`
  2. se o provider usar API key, rode `clawlite provider set-auth <provider> --api-key ...`
  3. se usar OAuth, rode `clawlite provider login <provider>`
  4. valide com `clawlite validate config` e `clawlite validate provider`
  5. aplique no processo atual com `clawlite restart-gateway`.

## 5. Canais

| Canal | Status real | Observação |
|---|---|---|
| `telegram` | `funcional` | Polling + webhook, streaming, reactions, topics, callbacks, pairing e refresh dedicado. |
| `discord` | `funcional` | HTTP outbound, gateway inbound, slash commands, threads, webhooks, voz, presence e refresh dedicado. |
| `slack` | `funcional` | Web API outbound e Socket Mode opcional para inbound. |
| `whatsapp` | `funcional` | Bridge HTTP/websocket + webhook inbound + retry outbound. |
| `email` | `funcional` | Polling IMAP inbound e SMTP outbound. |
| `irc` | `funcional` | Loop asyncio com PING/PONG e envio básico. |
| `signal` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |
| `googlechat` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |
| `matrix` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |
| `imessage` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |
| `dingtalk` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |
| `feishu` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |
| `mochat` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |
| `qq` | `stub` | Canal passivo; `send()` levanta `<name>_not_implemented`. |

Telegram usa principalmente `channels.telegram.*`. Os campos críticos do bot são `channels.telegram.enabled`, `channels.telegram.token`, `channels.telegram.mode`, `channels.telegram.webhook_*`, `channels.telegram.allow_from`, `channels.telegram.dm_policy`, `channels.telegram.group_policy`, `channels.telegram.topic_policy`, `channels.telegram.dm_allow_from`, `channels.telegram.group_allow_from`, `channels.telegram.topic_allow_from`, e `channels.telegram.group_overrides`.

Para adicionar um usuário autorizado no Telegram, hoje existem três caminhos reais no código:
1. Colocar o identificador em `channels.telegram.allow_from` para uma allowlist global.
2. Colocar em `channels.telegram.dm_allow_from`, `group_allow_from` ou `topic_allow_from` se você usa policy por escopo.
3. Se a policy estiver em `pairing`, aprovar o código com `clawlite pairing approve telegram <codigo>`.

Para canais que têm `allow_from` tipado no schema, o campo exato fica no bloco do próprio canal, por exemplo `channels.discord.allow_from`, `channels.slack.allow_from`, `channels.whatsapp.allow_from` e `channels.email.allow_from`.

Se um canal não conectar:
- Primeiro rode `clawlite validate channels`.
- Depois consulte `clawlite telegram status` ou `clawlite discord status` quando o canal tiver status dedicado.
- Se for problema de transporte sem mudança de config, use `clawlite telegram refresh` ou `clawlite discord refresh`.
- Se a config mudou em disco, faça restart do gateway; refresh não relê o config inteiro.

## 6. Tools disponíveis

Hoje não existe `tools.<nome>.enabled` no schema. As tools são registradas no runtime e o bloqueio real acontece por policy, falta de config, dependência opcional ou indisponibilidade do backend da tool.

| Tool | O que faz | Config / limite real | Quando falha ou fica indisponível |
|---|---|---|---|
| `agents_list` | List the primary agent runtime and delegated subagent inventory. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `apply_patch` | Apply patch envelope with add/update/delete operations. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `browser` | Control a headless browser. Actions: navigate (go to URL, returns page text), click (CSS selector), fill (CSS selector + value), screenshot (base64 PNG), evaluate (run JavaScript), close. | Não há bloco dedicado no schema; depende de Playwright/Chromium instalados. | Se Playwright/Chromium não existirem, retorna erro da própria tool. |
| `cron` | Manage scheduled jobs with add/remove/enable/disable/run/list. | Não tem enable flag no config; usa o scheduler ativo do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `discord_admin` | Inspect and administer Discord guilds with the configured bot: list guilds/channels/roles, create roles/channels, or apply a server layout. | Fica registrado sempre, mas só funciona de verdade se `channels.discord.token` estiver configurado. | Sem token de Discord, retorna `discord_not_configured`. |
| `edit` | Replace text in a file. | Alias de `edit_file`; respeita `tools.restrict_to_workspace`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `edit_file` | Replace text in a file. | Respeita `tools.restrict_to_workspace`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `exec` | Run shell command safely (no shell=True). | Usa `tools.restrict_to_workspace`, `tools.exec.*`, `tools.default_timeout_s` e `tools.timeouts.exec`. | Se a policy bloquear, a tool falha ou pede aprovação em Telegram/Discord. |
| `gateway_admin` | Inspect the active config, apply a partial config patch, and restart the ClawLite gateway. Use only when the user explicitly asks to change config or restart the runtime. Prefer config_intent_catalog to discover supported safe presets, then use config_intent_preview or config_intent_and_restart, and use config_schema_lookup or config_patch_preview before raw patching. For config_patch_and_restart, always pass a short human-readable note describing what was enabled or changed; ClawLite will send that note back after the gateway restarts. When applying after a preview, carry the preview_token from config_intent_preview or config_patch_preview into the real apply call. | Usa allowlist interna e hoje só libera mudanças seguras ligadas a tools, heartbeat do gateway e gateway restart. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `jobs` | Manage background jobs. Actions: submit, status, cancel, list. Use 'submit' to queue async work, 'status' to check progress. | Depende da fila de jobs do runtime; persistência vem de `jobs.persist_*`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `list_dir` | List files from directory. | Respeita `tools.restrict_to_workspace`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `mcp` | Call configured MCP server tools via registry. | Usa `tools.mcp.default_timeout_s`, `tools.mcp.policy.*` e `tools.mcp.servers`. | Sem servidores configurados em `tools.mcp.servers`, a chamada não encontra destino válido. |
| `memory_analyze` | Analyze memory footprint and optional query matches. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `memory_forget` | Forget memory entries by ref/query/source with deterministic guardrails. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `memory_get` | Read workspace memory files with OpenClaw-compatible slicing args. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `memory_learn` | Store a durable memory note with a source marker. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `memory_recall` | Recall semantically related memory snippets with provenance refs. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `memory_search` | Recall semantically related memory snippets with provenance refs. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `message` | Send proactive message to a channel target. | Não tem enable flag própria; depende dos canais ativos. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `pdf_read` | Extract text from a PDF file (local path or HTTPS URL). Supports page ranges like '1-5'. | Não há bloco dedicado no schema; depende de `pypdf`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `process` | Manage background process sessions (start/list/poll/log/write/kill/remove/clear). | Reusa as mesmas guardas de `exec`; não tem flag própria de enable. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `read` | Read text file content. | Alias de `read_file`; respeita `tools.restrict_to_workspace`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `read_file` | Read text file content. | Respeita `tools.restrict_to_workspace`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `run_skill` | Execute a discovered SKILL.md binding with deterministic contracts. | Depende do loader de skills e da policy de memória; não há `tools.run_skill.enabled`. | Skill desabilitada ou indisponível retorna erro explícito (`skill_disabled` ou `skill_unavailable`). |
| `session_status` | Return status card data for a session. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `sessions_history` | Read history for a specific session. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `sessions_list` | List persisted sessions with last-message preview. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `sessions_send` | Run a message against a target session. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `sessions_spawn` | Spawn delegated execution routed to target session. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `spawn` | Spawn a subagent task in background. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `subagents` | List or cancel subagent runs. | Sem bloco dedicado no schema; usa o registro padrão e/ou dependências do runtime. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `tts` | Convert text to speech using edge-tts. Returns path to MP3 file. Specify voice (e.g. 'en-US-AriaNeural', 'pt-BR-FranciscaNeural'). | Não há bloco dedicado no schema; depende de `edge-tts`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `web_fetch` | Fetch text content from URL. | Usa `tools.web.proxy`, `timeout`, `max_redirects`, `max_chars`, `allowlist`, `denylist` e `block_private_addresses`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `web_search` | Search the web and return snippets. | Usa `tools.web.proxy`, `search_timeout`, `brave_api_key`, `brave_base_url` e `searxng_base_url`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `write` | Write text file content. | Alias de `write_file`; respeita `tools.restrict_to_workspace`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |
| `write_file` | Write text file content. | Respeita `tools.restrict_to_workspace`. | Se a validação de argumentos, policy, backend ou dependência falhar, a tool retorna erro estruturado. |

Aliases publicados no catálogo do gateway: `bash -> exec`, `apply-patch -> apply_patch`, `read_file -> read`, `write_file -> write`, `edit_file -> edit`, `memory_recall -> memory_search`.

### Habilitar, desabilitar e sugerir ativação

- Não há `tools.<nome>.enabled` para a maioria das tools.
- O estado prático de uma tool hoje depende de um destes fatores:
  - safety policy (`tools.safety.*`);
  - timeout/restrição (`tools.default_timeout_s`, `tools.timeouts`, `tools.restrict_to_workspace`);
  - bloco de config específico (`tools.web.*`, `tools.exec.*`, `tools.mcp.*`, `tools.loop_detection.*`);
  - credencial/canal externo (`channels.discord.token` para `discord_admin`);
  - dependência opcional (`browser`, `pdf_read`, `tts`).
- Quando uma tool está indisponível, o comportamento não é um `enabled: false` genérico; o erro real vem do motivo concreto do bloqueio.
- O caminho correto do agente é sugerir o campo exato que destrava a tool, ou dizer claramente que não existe enable flag específica para ela.

## 7. Cron e Heartbeat

- Criar job via CLI: `clawlite cron add --session-id cli:cron --expression "every 300" --prompt "ping"`.
- Listar: `clawlite cron list --session-id cli:cron`.
- Rodar na hora: `clawlite cron run job-1`.
- Sintaxe aceita no código:
  - `every 120` -> a cada 120 segundos
  - `at 2026-03-02T20:00:00` -> execução única em ISO datetime
  - `0 9 * * *` -> expressão cron normal, mas só funciona se `croniter` estiver instalado
- Não existe lista de jobs cron dentro do `config` tipado. O schema só define defaults do scheduler (`scheduler.*`). Os jobs em si ficam no store persistido do `CronService`.
- Heartbeat usa `gateway.heartbeat.interval_s` como valor real. `scheduler.heartbeat_interval_seconds` ainda existe por compatibilidade legada e é migrado para o bloco do gateway.
- Estado do heartbeat: `~/.clawlite/state/heartbeat-state.json`.
- Estado do cron: `~/.clawlite/state/cron_jobs.json`.

## 8. Comandos CLI

| Comando | O que faz | Exemplo válido |
|---|---|---|
| `clawlite start` | usage: clawlite start [-h] [--host HOST] [--port PORT] | `clawlite start` |
| `clawlite gateway` | usage: clawlite gateway [-h] [--host HOST] [--port PORT] | `clawlite gateway` |
| `clawlite run` | usage: clawlite run [-h] [--session-id SESSION_ID] [--timeout TIMEOUT] prompt | `clawlite run "olá"` |
| `clawlite hatch` | usage: clawlite hatch [-h] [--message MESSAGE] [--timeout TIMEOUT] | `clawlite hatch` |
| `clawlite status` | usage: clawlite status [-h] | `clawlite status` |
| `clawlite dashboard` | usage: clawlite dashboard [-h] [--no-open] | `clawlite dashboard --no-open` |
| `clawlite generate-self` | usage: clawlite generate-self [-h] [--out OUT] | `clawlite generate-self` |
| `clawlite restart-gateway` | usage: clawlite restart-gateway [-h] [--gateway-url GATEWAY_URL] | `clawlite restart-gateway --gateway-url http://127.0.0.1:8787` |
| `clawlite configure` | usage: clawlite configure [-h] [--flow {quickstart,advanced}] | `clawlite configure` |
| `clawlite onboard` | usage: clawlite onboard [-h] [--assistant-name ASSISTANT_NAME] | `clawlite onboard --assistant-name ClawLite --user-name Owner` |
| `clawlite validate provider` | usage: clawlite validate provider [-h] | `clawlite validate provider` |
| `clawlite validate channels` | usage: clawlite validate channels [-h] | `clawlite validate channels` |
| `clawlite validate onboarding` | usage: clawlite validate onboarding [-h] [--fix] | `clawlite validate onboarding --fix` |
| `clawlite validate config` | usage: clawlite validate config [-h] | `clawlite validate config` |
| `clawlite validate preflight` | usage: clawlite validate preflight [-h] [--gateway-url GATEWAY_URL] | `clawlite validate preflight --gateway-url http://127.0.0.1:8787` |
| `clawlite tools safety` | usage: clawlite tools safety [-h] [--session-id SESSION_ID] | `clawlite tools safety exec` |
| `clawlite tools catalog` | usage: clawlite tools catalog [-h] [--gateway-url GATEWAY_URL] [--token TOKEN] | `clawlite tools catalog --gateway-url http://127.0.0.1:8787` |
| `clawlite tools show` | usage: clawlite tools show [-h] [--gateway-url GATEWAY_URL] [--token TOKEN] | `clawlite tools show github` |
| `clawlite tools approvals` | usage: clawlite tools approvals [-h] [--gateway-url GATEWAY_URL] | `clawlite tools approvals --gateway-url http://127.0.0.1:8787` |
| `clawlite tools approval-audit` | usage: clawlite tools approval-audit [-h] [--gateway-url GATEWAY_URL] | `clawlite tools approval-audit --gateway-url http://127.0.0.1:8787` |
| `clawlite tools approve` | usage: clawlite tools approve [-h] [--actor ACTOR] [--note NOTE] | `clawlite tools approve req-1 --gateway-url http://127.0.0.1:8787` |
| `clawlite tools reject` | usage: clawlite tools reject [-h] [--actor ACTOR] [--note NOTE] | `clawlite tools reject req-1 --gateway-url http://127.0.0.1:8787` |
| `clawlite tools revoke-grant` | usage: clawlite tools revoke-grant [-h] [--session-id SESSION_ID] | `clawlite tools revoke-grant --session-id telegram:123 --gateway-url http://127.0.0.1:8787` |
| `clawlite provider login` | usage: clawlite provider login [-h] [--access-token ACCESS_TOKEN] | `clawlite provider login openai-codex` |
| `clawlite provider status` | usage: clawlite provider status [-h] [provider] | `clawlite provider status openai-codex` |
| `clawlite provider logout` | usage: clawlite provider logout [-h] [{openai-codex,gemini-oauth,qwen-oauth}] | `clawlite provider logout openai-codex` |
| `clawlite provider use` | usage: clawlite provider use [-h] --model MODEL | `clawlite provider use openai --model openai/gpt-4o-mini` |
| `clawlite provider set-auth` | usage: clawlite provider set-auth [-h] --api-key API_KEY [--api-base API_BASE] | `clawlite provider set-auth openai --api-key sk-demo` |
| `clawlite provider clear-auth` | usage: clawlite provider clear-auth [-h] [--clear-api-base] provider | `clawlite provider clear-auth openai` |
| `clawlite provider recover` | usage: clawlite provider recover [-h] [--role ROLE] [--model MODEL] | `clawlite provider recover --gateway-url http://127.0.0.1:8787` |
| `clawlite autonomy wake` | usage: clawlite autonomy wake [-h] [--kind {proactive,heartbeat}] | `clawlite autonomy wake --gateway-url http://127.0.0.1:8787` |
| `clawlite supervisor recover` | usage: clawlite supervisor recover [-h] [--component COMPONENT] [--no-force] | `clawlite supervisor recover --gateway-url http://127.0.0.1:8787` |
| `clawlite heartbeat trigger` | usage: clawlite heartbeat trigger [-h] [--gateway-url GATEWAY_URL] | `clawlite heartbeat trigger --gateway-url http://127.0.0.1:8787` |
| `clawlite self-evolution status` | usage: clawlite self-evolution status [-h] [--gateway-url GATEWAY_URL] | `clawlite self-evolution status --gateway-url http://127.0.0.1:8787` |
| `clawlite self-evolution trigger` | usage: clawlite self-evolution trigger [-h] [--gateway-url GATEWAY_URL] | `clawlite self-evolution trigger --gateway-url http://127.0.0.1:8787 --dry-run` |
| `clawlite pairing list` | usage: clawlite pairing list [-h] channel | `clawlite pairing list telegram` |
| `clawlite pairing approve` | usage: clawlite pairing approve [-h] channel code | `clawlite pairing approve telegram ABCD12` |
| `clawlite pairing reject` | usage: clawlite pairing reject [-h] channel code | `clawlite pairing reject telegram ABCD12` |
| `clawlite pairing revoke` | usage: clawlite pairing revoke [-h] channel entry | `clawlite pairing revoke telegram telegram:user:123` |
| `clawlite discord status` | usage: clawlite discord status [-h] [--gateway-url GATEWAY_URL] | `clawlite discord status --gateway-url http://127.0.0.1:8787` |
| `clawlite discord refresh` | usage: clawlite discord refresh [-h] [--gateway-url GATEWAY_URL] | `clawlite discord refresh --gateway-url http://127.0.0.1:8787` |
| `clawlite telegram status` | usage: clawlite telegram status [-h] [--gateway-url GATEWAY_URL] | `clawlite telegram status --gateway-url http://127.0.0.1:8787` |
| `clawlite telegram refresh` | usage: clawlite telegram refresh [-h] [--gateway-url GATEWAY_URL] | `clawlite telegram refresh --gateway-url http://127.0.0.1:8787` |
| `clawlite telegram offset-commit` | usage: clawlite telegram offset-commit [-h] [--gateway-url GATEWAY_URL] | `clawlite telegram offset-commit 12345` |
| `clawlite telegram offset-sync` | usage: clawlite telegram offset-sync [-h] [--allow-reset] | `clawlite telegram offset-sync 12346` |
| `clawlite telegram offset-reset` | usage: clawlite telegram offset-reset [-h] [--yes] [--gateway-url GATEWAY_URL] | `clawlite telegram offset-reset` |
| `clawlite diagnostics` | usage: clawlite diagnostics [-h] [--gateway-url GATEWAY_URL] [--token TOKEN] | `clawlite diagnostics --gateway-url http://127.0.0.1:8787` |
| `clawlite memory` | usage: clawlite memory [-h] | `clawlite memory` |
| `clawlite memory doctor` | usage: clawlite memory doctor [-h] [--json] [--repair] | `clawlite memory doctor` |
| `clawlite memory eval` | usage: clawlite memory eval [-h] [--limit LIMIT] | `clawlite memory eval` |
| `clawlite memory quality` | usage: clawlite memory quality [-h] [--json] [--limit LIMIT] | `clawlite memory quality` |
| `clawlite memory profile` | usage: clawlite memory profile [-h] | `clawlite memory profile` |
| `clawlite memory suggest` | usage: clawlite memory suggest [-h] [--no-refresh] | `clawlite memory suggest` |
| `clawlite memory snapshot` | usage: clawlite memory snapshot [-h] [--tag TAG] | `clawlite memory snapshot --tag manual` |
| `clawlite memory version` | usage: clawlite memory version [-h] | `clawlite memory version` |
| `clawlite memory rollback` | usage: clawlite memory rollback [-h] id | `clawlite memory rollback snapshot-1` |
| `clawlite memory privacy` | usage: clawlite memory privacy [-h] | `clawlite memory privacy` |
| `clawlite memory export` | usage: clawlite memory export [-h] [--out OUT] | `clawlite memory export` |
| `clawlite memory import` | usage: clawlite memory import [-h] file | `clawlite memory import backup.json` |
| `clawlite memory branches` | usage: clawlite memory branches [-h] | `clawlite memory branches` |
| `clawlite memory branch` | usage: clawlite memory branch [-h] [--from-version FROM_VERSION] [--checkout] | `clawlite memory branch github` |
| `clawlite memory checkout` | usage: clawlite memory checkout [-h] name | `clawlite memory checkout github` |
| `clawlite memory merge` | usage: clawlite memory merge [-h] --source SOURCE --target TARGET [--tag TAG] | `clawlite memory merge --source workspace --target demo` |
| `clawlite memory share-optin` | usage: clawlite memory share-optin [-h] --user USER --enabled ENABLED | `clawlite memory share-optin --user alice --enabled true` |
| `clawlite cron add` | usage: clawlite cron add [-h] --session-id SESSION_ID --expression EXPRESSION | `clawlite cron add --session-id cli:cron --expression "every 300" --prompt "ping"` |
| `clawlite cron list` | usage: clawlite cron list [-h] --session-id SESSION_ID | `clawlite cron list --session-id cli:cron` |
| `clawlite cron remove` | usage: clawlite cron remove [-h] --job-id JOB_ID | `clawlite cron remove --job-id job-1` |
| `clawlite cron enable` | usage: clawlite cron enable [-h] job_id | `clawlite cron enable job-1` |
| `clawlite cron disable` | usage: clawlite cron disable [-h] job_id | `clawlite cron disable job-1` |
| `clawlite cron run` | usage: clawlite cron run [-h] job_id | `clawlite cron run job-1` |
| `clawlite jobs list` | usage: clawlite jobs list [-h] | `clawlite jobs list` |
| `clawlite jobs status` | usage: clawlite jobs status [-h] job_id | `clawlite jobs status job-1` |
| `clawlite jobs cancel` | usage: clawlite jobs cancel [-h] job_id | `clawlite jobs cancel job-1` |
| `clawlite skills list` | usage: clawlite skills list [-h] [--all] | `clawlite skills list` |
| `clawlite skills show` | usage: clawlite skills show [-h] name | `clawlite skills show github` |
| `clawlite skills config` | usage: clawlite skills config [-h] [--api-key API_KEY] [--clear-api-key] | `clawlite skills config github` |
| `clawlite skills check` | usage: clawlite skills check [-h] | `clawlite skills check` |
| `clawlite skills refresh` | usage: clawlite skills refresh [-h] [--no-force] [--gateway-url GATEWAY_URL] | `clawlite skills refresh` |
| `clawlite skills doctor` | usage: clawlite skills doctor [-h] [--all] | `clawlite skills doctor` |
| `clawlite skills validate` | usage: clawlite skills validate [-h] [--no-force] [--all] | `clawlite skills validate --gateway-url http://127.0.0.1:8787` |
| `clawlite skills enable` | usage: clawlite skills enable [-h] name | `clawlite skills enable github` |
| `clawlite skills disable` | usage: clawlite skills disable [-h] name | `clawlite skills disable github` |
| `clawlite skills pin` | usage: clawlite skills pin [-h] name | `clawlite skills pin github` |
| `clawlite skills unpin` | usage: clawlite skills unpin [-h] name | `clawlite skills unpin github` |
| `clawlite skills pin-version` | usage: clawlite skills pin-version [-h] name version | `clawlite skills pin-version github 1.0.0` |
| `clawlite skills clear-version` | usage: clawlite skills clear-version [-h] name | `clawlite skills clear-version github` |
| `clawlite skills install` | usage: clawlite skills install [-h] slug | `clawlite skills install github` |
| `clawlite skills update` | usage: clawlite skills update [-h] name | `clawlite skills update github` |
| `clawlite skills search` | usage: clawlite skills search [-h] [--limit LIMIT] query | `clawlite skills search "discord moderation"` |
| `clawlite skills managed` | usage: clawlite skills managed [-h] | `clawlite skills managed --status missing_requirements --query jira` |
| `clawlite skills sync` | usage: clawlite skills sync [-h] | `clawlite skills sync` |
| `clawlite skills remove` | usage: clawlite skills remove [-h] name | `clawlite skills remove github` |

Comandos de referência rápida:
- Validar config: `clawlite validate config`
- Ver status: `clawlite status`
- Reiniciar gateway: `clawlite restart-gateway`

## 9. Estrutura de arquivos do projeto

```text
clawlite/
  config/        schema, loader, watcher e health
  core/          engine, prompt, memory, subagents, skills
  providers/     registry, auth, failover, probe, telemetry
  channels/      adapters reais e stubs
  tools/         tools do agente e registry
  scheduler/     cron e heartbeat
  gateway/       servidor FastAPI, dashboard, control-plane, websocket
  cli/           parser e handlers da CLI
  workspace/     templates e loader do contexto do prompt
tests/           regressões
docs/            documentação do repositório
workspace/       cópia de SELF.md pedida para este checkout
```

| Arquivo | O que faz / quando mexer |
|---|---|
| `clawlite/config/schema.py` | Schema tipado de todo o config; altere aqui quando criar ou remover campo. |
| `clawlite/config/loader.py` | Carrega, mescla env, valida, salva JSON/YAML e resolve profiles. |
| `clawlite/core/engine.py` | Loop principal do agente, execução de tools, memória e persistência de turno. |
| `clawlite/core/prompt.py` | Monta o prompt final antes da chamada ao provider. |
| `clawlite/core/memory.py` | Memória persistente, busca, consolidação, versões e privacidade. |
| `clawlite/providers/registry.py` | Resolve provider/base URL/auth e constrói o provider ativo. |
| `clawlite/providers/litellm.py` | Provider OpenAI-compatible e Anthropic-compatible com retry/telemetria. |
| `clawlite/providers/failover.py` | Encadeia provider principal + fallbacks. |
| `clawlite/channels/manager.py` | Instancia canais, roteia outbound/inbound e faz recovery. |
| `clawlite/channels/telegram.py` | Adapter Telegram completo. |
| `clawlite/channels/discord.py` | Adapter Discord completo. |
| `clawlite/tools/registry.py` | Registro, cache, timeouts, safety, approvals e auditoria de tools. |
| `clawlite/tools/gateway_admin.py` | Mudanças seguras de config via chat + preview + restart. |
| `clawlite/scheduler/cron.py` | Scheduler de cron/jobs persistidos. |
| `clawlite/scheduler/heartbeat.py` | Loop de heartbeat e estado persistido. |
| `clawlite/gateway/server.py` | Gateway FastAPI, dashboard, rotas HTTP/WS e bootstrap do runtime. |
| `clawlite/gateway/runtime_builder.py` | Monta engine, memory, tools, channels, cron, heartbeat e jobs. |
| `clawlite/cli/__init__.py` | Entrypoint real do console script `clawlite`. |
| `clawlite/cli/commands.py` | Parser argparse e handlers da CLI. |
| `clawlite/workspace/loader.py` | Workspace runtime, templates e contexto do prompt. |

- Entrypoint real da CLI: `clawlite.cli:main` em `pyproject.toml`; o arquivo `clawlite/cli.py` não existe neste repositório.
- O pacote `clawlite/gateway.py` também não existe; o servidor real está em `clawlite/gateway/server.py`.
- Logs: por padrão vão para `stderr`. Arquivo de log só existe se `CLAWLITE_LOG_FILE` estiver configurado.
- Workspace do agente: `~/.clawlite/workspace` por padrão, ou o valor de `workspace_path`.
- Estado persistente geral: `~/.clawlite/state` por padrão, ou o valor de `state_path`.
- Memória persistente principal: `~/.clawlite/state/memory.jsonl` e `~/.clawlite/memory`.
- Sessões persistidas: `~/.clawlite/state/sessions`.
- Cron persistido: `~/.clawlite/state/cron_jobs.json`.
- Cache de probes de provider: `~/.clawlite/state/provider-probes.json`.

## 10. Como o agente deve agir quando o usuário pedir mudanças

### Trocar token do Telegram
1. Eu localizo o campo exato `channels.telegram.token` no config ativo.
2. Eu altero o valor nesse arquivo.
3. Eu valido com `clawlite validate config`.
4. Como o runtime não faz hot reload geral de config, eu reinicio com `clawlite restart-gateway`.
5. Depois eu confirmo com `clawlite validate channels` e, se o gateway já estiver de pé, `clawlite telegram status`.

### Ativar uma tool que o usuário pediu
1. Eu identifico primeiro se existe mesmo um campo de enable no código.
2. Hoje, na maioria das tools, esse campo não existe. Então eu informo o motivo real do bloqueio: policy, credencial, dependência, servidor MCP, ou canal/provedor não configurado.
3. Eu peço confirmação uma única vez antes de mudar config ou policy.
4. Se houver campo seguro suportado pelo `gateway_admin`, eu faço preview e depois apply com restart, carregando o `preview_token` do preview quando eu quiser handoff estrito.
5. Se não houver enable flag tipada, eu explico o desbloqueio real com o campo exato e só então executo a tarefa original.

### Trocar de provider
1. Eu listo os providers suportados pelo runtime.
2. Eu peço a credencial certa do novo provider: API key ou login OAuth, dependendo do caso.
3. Eu atualizo `provider.model` e, se necessário, `providers.<provider>.api_key` / `api_base` ou `auth.providers.<provider>.*`.
4. Eu valido com `clawlite validate config` e `clawlite validate provider`.
5. Eu aplico no processo atual com `clawlite restart-gateway`.

### Quando a tarefa precisa de uma tool indisponível
1. Eu identifico a tool realmente necessária.
2. Eu digo ao usuário por que ela não está disponível: bloqueio de safety, config faltando, credencial faltando, dependência faltando, ou feature não implementada.
3. Eu informo o campo exato quando existir, ou digo claramente que não existe `enabled` genérico para aquela tool.
4. Eu aguardo confirmação uma única vez antes de mudar config.
5. Depois de destravar o bloqueio real, eu executo a tarefa original.

## 11. Limites e o que não fazer

- Nunca altero sem confirmação explícita: `gateway.auth.*`, `auth.*`, `provider.*`, `providers.*`, `channels.*`, e caminhos protegidos do `gateway_admin`.
- Em mudanças por chat, prefiro `config_schema_lookup`, `config_intent_catalog`, `config_intent_preview` ou `config_patch_preview` antes do apply real.
- Quando faço preview por `gateway_admin`, levo o `preview_token` para o apply real sempre que eu quiser garantir que o patch e a base da config não mudaram entre o preview e o restart.
- Não tento inventar `enabled: true` para tools que não têm esse campo no schema.
- Não tento hot reload genérico que o runtime não suporta; quando a mudança é estrutural, faço restart do gateway.
- Para evitar loop de restart, só disparo um restart por vez e não repito mudanças enquanto já existe restart pendente.
- Para evitar loop de execução de tools, respeito `tools.loop_detection.*` e não forço reexecuções cegas do mesmo plano.

## 12. Status atual do projeto

- Funcional no código hoje:
  - gateway FastAPI + dashboard + websocket
  - engine com tools + memória persistente + histórico
  - cron + heartbeat
  - failover de providers
  - Telegram funcional
  - Discord funcional/operável
  - Slack, WhatsApp, Email e IRC funcionais
  - fluxo via chat para preview/apply de config segura + restart + aviso pós-boot
- Em desenvolvimento parcial, mas usável:
  - Discord ainda é mais complexo e tem mais superfícies operacionais do que os outros canais
  - skills gerenciadas, automation e dashboard têm bastante cobertura, mas seguem evoluindo
- Stub/não implementado como adapter real:
  - `signal`, `googlechat`, `matrix`, `imessage`, `dingtalk`, `feishu`, `mochat`, `qq`.
