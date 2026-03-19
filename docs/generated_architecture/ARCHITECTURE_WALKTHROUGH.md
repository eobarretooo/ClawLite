# Massive Architecture Walkthrough

## Executive View

ClawLite_VikingEdition is a local-first Python autonomous-agent system with a layered design: configuration feeds the CLI and gateway surfaces; the gateway composes runtime state and control handlers; the core engine manages prompt construction, memory, tools, and subagents; runtime services add autonomy, supervision, and self-evolution; providers abstract LLM backends; channels carry inbound and outbound communication; tools expose guarded system capabilities; tests mirror almost every subsystem.

The codebase is broad rather than minimal. It favors separate modules for operational responsibilities, especially in Telegram/channel handling, gateway runtime orchestration, memory internals, and provider integration. The package is therefore best understood as a control plane around a central engine rather than as a single monolithic chatbot process.

## Top-Level Layers

1. `clawlite/config`: schema, loading, health checks, and file watching.
2. `clawlite/cli`: user-facing commands, onboarding, and operational helpers.
3. `clawlite/gateway`: HTTP/WebSocket control plane, runtime assembly, dashboard state, diagnostics, and approval flows.
4. `clawlite/core`: prompt building, memory, skills, subagents, and the main engine.
5. `clawlite/runtime`: autonomy loop, supervisor, self-evolution, and telemetry helpers.
6. `clawlite/providers`: model registry, auth adapters, failover, reliability, and probes.
7. `clawlite/channels`: message transport adapters and the channel manager.
8. `clawlite/tools`: built-in tool implementations plus registry and policy surfaces.
9. `clawlite/scheduler`, `clawlite/jobs`, `clawlite/bus`, and `clawlite/session`: supporting runtime infrastructure.
10. `clawlite/workspace` and `clawlite/skills`: workspace prompt files and skill packaging.

## Subsystem Deep Dive

### cli

This area contains 5 code file(s) and 7796 line(s).

- `clawlite/cli/ops.py`: `clawlite.cli.ops` is a Python module in the `cli` area. It exposes 76 function(s), including `_build_memory_store`, `_file_stat`, `_gateway_control_request`. It depends on 26 import statement target(s).
- `clawlite/cli/commands.py`: `clawlite.cli.commands` is a Python module in the `cli` area. It exposes 111 function(s), including `_ensure_config_materialized`, `_format_cli_error`, `_gateway_preflight_from_diagnostics`, `_scenario`. It depends on 24 import statement target(s).
- `clawlite/cli/onboarding.py`: `clawlite.cli.onboarding` is a Python module in the `cli` area. It exposes 43 function(s), including `_base_url_matches_provider`, `_configure_autonomy`, `_configure_bus`. It depends on 23 import statement target(s).
- `clawlite/cli/__main__.py`: `clawlite.cli.__main__` is a Python module in the `cli` area. It depends on 2 import statement target(s).
- `clawlite/cli/__init__.py`: `clawlite.cli` is a Python module in the `cli` area. It depends on 2 import statement target(s).

Operational read:
The `cli` area has 39 internal Python dependency edge(s), 4 matched test relationship(s), and 230 discovered function definitions.

### config

This area contains 6 code file(s) and 2409 line(s).

- `clawlite/config/schema.py`: `clawlite.config.schema` is a Python module in the `config` area. It defines 38 class(es), led by `AgentDefaultsConfig`, `AgentMemoryConfig`, `AgentsConfig`, `AppConfig`. It exposes 125 function(s), including `_activity_type_range`, `_apply_profile_defaults`, `_base_url_default`. It depends on 5 import statement target(s).
- `clawlite/config/loader.py`: `clawlite.config.loader` is a Python module in the `config` area. It exposes 16 function(s), including `_deep_merge`, `_env_overrides`, `_migrate_config`. It depends on 8 import statement target(s).
- `clawlite/config/watcher.py`: `clawlite.config.watcher` is a Python module in the `config` area. It defines 1 class(es), led by `ConfigWatcher`. It exposes 5 function(s), including `__init__`, `_get_bus`, `_watch_loop`, `start`, `stop`. It depends on 10 import statement target(s).
- `clawlite/config/health.py`: `clawlite.config.health` is a Python module in the `config` area. It exposes 4 function(s), including `_is_local_model`, `_is_writable`, `_port_available`. It depends on 5 import statement target(s).
- `clawlite/config/audit.py`: `clawlite.config.audit` is a Python module in the `config` area. It defines 1 class(es), led by `ConfigAudit`. It exposes 5 function(s), including `__init__`, `diff`, `history`. It depends on 5 import statement target(s).
- `clawlite/config/__init__.py`: `clawlite.config` is a Python module in the `config` area. It depends on 3 import statement target(s).

Operational read:
The `config` area has 9 internal Python dependency edge(s), 8 matched test relationship(s), and 155 discovered function definitions.

### gateway

This area contains 30 code file(s) and 9290 line(s).

- `clawlite/gateway/server.py`: `clawlite.gateway.server` is a Python module in the `gateway` area. It defines 30 class(es), led by `AutonomyWakeRequest`, `ChannelInboundReplayRequest`, `ChannelRecoverRequest`, `ChannelReplayRequest`. It exposes 194 function(s), including `__getattr__`, `__init__`, `__post_init__`, `__call__`, `_autonomy_snapshot_payload`, `_collect_memory_analysis_metrics`. It depends on 61 import statement target(s).
- `clawlite/gateway/runtime_builder.py`: `clawlite.gateway.runtime_builder` is a Python module in the `gateway` area. It defines 3 class(es), led by `RuntimeContainer`, `_CronAPI`, `_MessageAPI`. It exposes 18 function(s), including `__init__`, `_provider_config`, `_provider_probe_candidates`, `_channel_inbound_interceptor`, `_evo_notify`, `_evo_run_llm`. It depends on 50 import statement target(s).
- `clawlite/gateway/websocket_handlers.py`: `clawlite.gateway.websocket_handlers` is a Python module in the `gateway` area. It defines 1 class(es), led by `GatewayWebSocketHandlers`. It exposes 9 function(s), including `_coerce_req_id`, `_coerce_req_payload`, `_coerce_stream_flag`, `_run_chat_request`, `_run_chat_stream_request`, `_send_ws`. It depends on 7 import statement target(s).
- `clawlite/gateway/lifecycle_runtime.py`: `clawlite.gateway.lifecycle_runtime` is a Python module in the `gateway` area. It exposes 6 function(s), including `_startup_timeout_seconds`, `_handle_autonomy_wake_started`, `_handle_channels_started`, `_rollback_started_subsystems`. It depends on 4 import statement target(s).
- `clawlite/gateway/discord_thread_binding.py`: `clawlite.gateway.discord_thread_binding` is a Python module in the `gateway` area. It exposes 3 function(s), including `_extract_action`, `_reply_discord`, `handle_discord_thread_binding_inbound_action`. It depends on 3 import statement target(s).
- `clawlite/gateway/tuning_loop.py`: `clawlite.gateway.tuning_loop` is a Python module in the `gateway` area. It exposes 2 function(s), including `_call_quality_update_tuning`, `run_memory_quality_tuning_tick`. It depends on 4 import statement target(s).
- `clawlite/gateway/request_handlers.py`: `clawlite.gateway.request_handlers` is a Python module in the `gateway` area. It defines 1 class(es), led by `GatewayRequestHandlers`. It exposes 17 function(s), including `_check_control`, `_cron_counts`, `_cron_list_payload`, `chat`, `cron_add`, `cron_get`. It depends on 8 import statement target(s).
- `clawlite/gateway/engine_diagnostics.py`: `clawlite.gateway.engine_diagnostics` is a Python module in the `gateway` area. It exposes 9 function(s), including `_call_quality_update`, `_memory_method_payload`, `_memory_quality_cache_fingerprint`, `engine_memory_quality_payload`. It depends on 3 import statement target(s).
- `clawlite/gateway/tool_approval.py`: `clawlite.gateway.tool_approval` is a Python module in the `gateway` area. It exposes 8 function(s), including `_extract_action_token`, `build_tool_approval_metadata`, `build_tool_approval_notice`, `_reply_discord`, `_reply_generic`, `_reply_telegram`. It depends on 4 import statement target(s).
- `clawlite/gateway/payloads.py`: `clawlite.gateway.payloads` is a Python module in the `gateway` area. It exposes 10 function(s), including `autonomy_provider_suppression_hint`, `control_plane_to_dict`, `dashboard_asset_text`. It depends on 6 import statement target(s).
- `clawlite/gateway/control_handlers.py`: `clawlite.gateway.control_handlers` is a Python module in the `gateway` area. It defines 1 class(es), led by `GatewayControlHandlers`. It exposes 23 function(s), including `_check_control`, `_require_channel`, `_require_channel_operator`, `autonomy_wake`, `channels_inbound_replay`, `channels_recover`. It depends on 5 import statement target(s).
- `clawlite/gateway/autonomy_notice.py`: `clawlite.gateway.autonomy_notice` is a Python module in the `gateway` area. It exposes 5 function(s), including `_record_autonomy_event`, `default_heartbeat_route`, `latest_route_from_history_tail`, `latest_memory_route`, `send_autonomy_notice`. It depends on 8 import statement target(s).

Operational read:
The `gateway` area has 107 internal Python dependency edge(s), 35 matched test relationship(s), and 376 discovered function definitions.

### core

This area contains 38 code file(s) and 20956 line(s).

- `clawlite/core/memory.py`: `clawlite.core.memory` is a Python module in the `core` area. It defines 4 class(es), led by `MemoryLayer`, `MemoryRecord`, `MemoryStore`, `ResourceContext`. It exposes 269 function(s), including `__init__`, `_advance_branch_head`, `_append`, `_consolidation_loop`, `_decay_loop`, `compact`. It depends on 41 import statement target(s).
- `clawlite/core/engine.py`: `clawlite.core.engine` is a Python module in the `core` area. It defines 21 class(es), led by `AgentCancelledError`, `AgentEngine`, `AgentLoopError`, `InMemorySessionStore`. It exposes 120 function(s), including `__init__`, `_accepts_parameter`, `_append_session_message`, `_attach_subagent_memory_digests`, `_complete_provider`, `_emit_progress`. It depends on 23 import statement target(s).
- `clawlite/core/memory_backend.py`: `clawlite.core.memory_backend` is a Python module in the `core` area. It defines 4 class(es), led by `MemoryBackend`, `PgvectorMemoryBackend`, `SQLiteMemoryBackend`, `SQLiteVecMemoryBackend`. It exposes 38 function(s), including `__post_init__`, `_connect`, `_cosine_similarity`. It depends on 12 import statement target(s).
- `clawlite/core/skills.py`: `clawlite.core.skills` is a Python module in the `core` area. It defines 2 class(es), led by `SkillSpec`, `SkillsLoader`. It exposes 68 function(s), including `__init__`, `_atomic_write_state`, `_build_execution_contract`, `_loop`, `_watcher_loop_poll`, `_watcher_loop_watchfiles`. It depends on 18 import statement target(s).
- `clawlite/core/subagent.py`: `clawlite.core.subagent` is a Python module in the `core` area. It defines 3 class(es), led by `SubagentLimitError`, `SubagentManager`, `SubagentRun`. It exposes 50 function(s), including `__init__`, `_bind_loop`, `_cancel_locked`, `_worker`, `cancel_async`, `cancel_session_async`. It depends on 10 import statement target(s).
- `clawlite/core/memory_working_set.py`: `clawlite.core.memory_working_set` is a Python module in the `core` area. It exposes 24 function(s), including `collect_visible_working_set`, `default_working_memory_share_scope`, `default_working_memory_state`. It depends on 4 import statement target(s).
- `clawlite/core/memory_retrieval.py`: `clawlite.core.memory_retrieval` is a Python module in the `core` area. It exposes 15 function(s), including `_accept`, `_realm_weight`, `build_progressive_retrieval_payload`. It depends on 6 import statement target(s).
- `clawlite/core/memory_monitor.py`: `clawlite.core.memory_monitor` is a Python module in the `core` area. It defines 2 class(es), led by `MemoryMonitor`, `MemorySuggestion`. It exposes 33 function(s), including `__init__`, `_all_records`, `_atomic_write_pending_text`, `scan`. It depends on 13 import statement target(s).
- `clawlite/core/prompt.py`: `clawlite.core.prompt` is a Python module in the `core` area. It defines 2 class(es), led by `PromptArtifacts`, `PromptBuilder`. It exposes 17 function(s), including `__init__`, `_ensure_identity_first`, `_estimate_tokens`. It depends on 9 import statement target(s).
- `clawlite/core/huginn_muninn.py`: `clawlite.core.huginn_muninn` is a Python module in the `core` area. It defines 3 class(es), led by `HuginnInsight`, `MuninnInsight`, `RavensCounsel`. It exposes 12 function(s), including `_hours_since`, `_huginn_analyze_sync`, `_muninn_analyze_sync`, `_huginn_analyze`, `_muninn_analyze`, `_wrapped`. It depends on 5 import statement target(s).
- `clawlite/core/memory_versions.py`: `clawlite.core.memory_versions` is a Python module in the `core` area. It exposes 13 function(s), including `checkout_memory_branch`, `create_memory_branch`, `diff_memory_versions`. It depends on 8 import statement target(s).
- `clawlite/core/injection_guard.py`: `clawlite.core.injection_guard` is a Python module in the `core` area. It defines 2 class(es), led by `ScanResult`, `ThreatLevel`. It exposes 10 function(s), including `_audit`, `_normalize_unicode`, `_scan_encoded_payloads`. It depends on 10 import statement target(s).

Operational read:
The `core` area has 44 internal Python dependency edge(s), 92 matched test relationship(s), and 812 discovered function definitions.

### runtime

This area contains 10 code file(s) and 4855 line(s).

- `clawlite/runtime/self_evolution.py`: `clawlite.runtime.self_evolution` is a Python module in the `runtime` area. It defines 11 class(es), led by `EvolutionLog`, `EvolutionRecord`, `FixProposal`, `FixProposer`. It exposes 43 function(s), including `__init__`, `_approval_metadata`, `_build_prompt`, `_call`, `_do_run`, `_notify_operator`. It depends on 16 import statement target(s).
- `clawlite/runtime/autonomy_actions.py`: `clawlite.runtime.autonomy_actions` is a Python module in the `runtime` area. It defines 1 class(es), led by `AutonomyActionController`. It exposes 33 function(s), including `__init__`, `_action_confidence`, `_append_recent_audits`, `process`. It depends on 8 import statement target(s).
- `clawlite/runtime/autonomy.py`: `clawlite.runtime.autonomy` is a Python module in the `runtime` area. It defines 4 class(es), led by `AutonomyService`, `AutonomyWakeCoordinator`, `_WakeKindPolicy`, `_WakeQueueEntry`. It exposes 32 function(s), including `__init__`, `_build_kind_policies`, `_classify_run_error`, `_persist_journal_locked`, `_read_snapshot`, `_restore_journal_locked`. It depends on 12 import statement target(s).
- `clawlite/runtime/supervisor.py`: `clawlite.runtime.supervisor` is a Python module in the `runtime` area. It defines 3 class(es), led by `RuntimeSupervisor`, `SupervisorComponentPolicy`, `SupervisorIncident`. It exposes 22 function(s), including `__init__`, `_budget_remaining`, `_coerce_component_policy`, `_notify_incident`, `_recover_component`, `_run_loop`. It depends on 8 import statement target(s).
- `clawlite/runtime/volva.py`: `clawlite.runtime.volva` is a Python module in the `runtime` area. It defines 1 class(es), led by `VolvaOracle`. It exposes 13 function(s), including `__init__`, `_audit`, `_fetch_category_records`, `_loop`, `_tend_category`, `_tick`. It depends on 5 import statement target(s).
- `clawlite/runtime/valkyrie.py`: `clawlite.runtime.valkyrie` is a Python module in the `runtime` area. It defines 1 class(es), led by `ValkyrieReaper`. It exposes 15 function(s), including `__init__`, `_audit`, `_classify`, `_archive`, `_loop`, `_maybe_await`. It depends on 5 import statement target(s).
- `clawlite/runtime/gjallarhorn.py`: `clawlite.runtime.gjallarhorn` is a Python module in the `runtime` area. It defines 1 class(es), led by `GjallarhornWatch`. It exposes 13 function(s), including `__init__`, `_count_recent_blocks`, `_utc_now`, `_idle_loop`, `_maybe_ring`, `ring`. It depends on 6 import statement target(s).
- `clawlite/runtime/autonomy_log.py`: `clawlite.runtime.autonomy_log` is a Python module in the `runtime` area. It defines 1 class(es), led by `AutonomyLog`. It exposes 8 function(s), including `__init__`, `_atomic_write`, `_flush_and_fsync`. It depends on 9 import statement target(s).
- `clawlite/runtime/telemetry.py`: `clawlite.runtime.telemetry` is a Python module in the `runtime` area. It defines 2 class(es), led by `_NoopSpan`, `_NoopTracer`. It exposes 10 function(s), including `__enter__`, `__exit__`, `configure_observability`. It depends on 3 import statement target(s).
- `clawlite/runtime/__init__.py`: `clawlite.runtime` is a Python module in the `runtime` area. It depends on 4 import statement target(s).

Operational read:
The `runtime` area has 10 internal Python dependency edge(s), 21 matched test relationship(s), and 189 discovered function definitions.

### providers

This area contains 17 code file(s) and 4480 line(s).

- `clawlite/providers/registry.py`: `clawlite.providers.registry` is a Python module in the `providers` area. It defines 2 class(es), led by `ProviderResolution`, `ProviderSpec`. It exposes 25 function(s), including `_add`, `_build_provider_single`, `_cfg_value`. It depends on 13 import statement target(s).
- `clawlite/providers/litellm.py`: `clawlite.providers.litellm` is a Python module in the `providers` area. It defines 1 class(es), led by `LiteLLMProvider`. It exposes 21 function(s), including `__init__`, `_anthropic_messages`, `_anthropic_tools`, `_complete_anthropic`, `_try_refresh_oauth`, `complete`. It depends on 13 import statement target(s).
- `clawlite/providers/codex.py`: `clawlite.providers.codex` is a Python module in the `providers` area. It defines 1 class(es), led by `CodexProvider`. It exposes 25 function(s), including `__init__`, `_api_model_name`, `_check_circuit`, `complete`. It depends on 11 import statement target(s).
- `clawlite/providers/failover.py`: `clawlite.providers.failover` is a Python module in the `providers` area. It defines 3 class(es), led by `FailoverCandidate`, `FailoverCooldownError`, `FailoverProvider`. It exposes 15 function(s), including `__init__`, `_activate_cooldown`, `_all_in_cooldown_error`, `_attempt_candidate`, `complete`. It depends on 6 import statement target(s).
- `clawlite/providers/hints.py`: `clawlite.providers.hints` is a Python module in the `providers` area. It exposes 6 function(s), including `_append_hint`, `_networkish`, `provider_probe_hints`. It depends on 3 import statement target(s).
- `clawlite/providers/gemini_auth.py`: `clawlite.providers.gemini_auth` is a Python module in the `providers` area. It exposes 8 function(s), including `_extract_client_id_from_id_token`, `_persist_gemini_auth_state`, `_pick_value`, `refresh_gemini_auth_file`. It depends on 8 import statement target(s).
- `clawlite/providers/catalog.py`: `clawlite.providers.catalog` is a Python module in the `providers` area. It defines 1 class(es), led by `ProviderProfile`. It exposes 2 function(s), including `default_provider_model`, `provider_profile`. It depends on 2 import statement target(s).
- `clawlite/providers/qwen_auth.py`: `clawlite.providers.qwen_auth` is a Python module in the `providers` area. It exposes 7 function(s), including `_persist_qwen_auth_state`, `_pick_value`, `_read_oauth_payload`, `refresh_qwen_auth_file`. It depends on 7 import statement target(s).
- `clawlite/providers/discovery.py`: `clawlite.providers.discovery` is a Python module in the `providers` area. It exposes 12 function(s), including `_base_with_path`, `_canonical_model_name`, `_extract_names`. It depends on 4 import statement target(s).
- `clawlite/providers/model_probe.py`: `clawlite.providers.model_probe` is a Python module in the `providers` area. It exposes 6 function(s), including `_match_model`, `_model_variants`, `evaluate_remote_model_check`. It depends on 2 import statement target(s).
- `clawlite/providers/reliability.py`: `clawlite.providers.reliability` is a Python module in the `providers` area. It defines 1 class(es), led by `ReliabilitySettings`. It exposes 5 function(s), including `classify_provider_error`, `is_quota_429_error`, `is_retryable_error`. It depends on 4 import statement target(s).
- `clawlite/providers/codex_auth.py`: `clawlite.providers.codex_auth` is a Python module in the `providers` area. It exposes 4 function(s), including `_codex_auth_path`, `_pick_value`, `load_codex_auth_file`. It depends on 5 import statement target(s).

Operational read:
The `providers` area has 22 internal Python dependency edge(s), 16 matched test relationship(s), and 151 discovered function definitions.

### channels

This area contains 31 code file(s) and 12711 line(s).

- `clawlite/channels/telegram.py`: `clawlite.channels.telegram` is a Python module in the `channels` area. It defines 1 class(es), led by `TelegramChannel`. It exposes 136 function(s), including `__init__`, `_added_reaction_tokens`, `_apply_offset_snapshot`, `_activate_webhook_mode`, `_download_media_items`, `_drop_pending_updates`. It depends on 36 import statement target(s).
- `clawlite/channels/manager.py`: `clawlite.channels.manager` is a Python module in the `channels` area. It defines 3 class(es), led by `ChannelManager`, `EngineProtocol`, `_SessionDispatchSlot`. It exposes 93 function(s), including `__init__`, `_background_task_state`, `_base_target_from_event`, `_acquire_dispatch_slot`, `_clear_persisted_dead_letter`, `_clear_persisted_inbound`. It depends on 30 import statement target(s).
- `clawlite/channels/discord.py`: `clawlite.channels.discord` is a Python module in the `channels` area. It defines 4 class(es), led by `DiscordChannel`, `_DiscordGuildChannelPolicy`, `_DiscordGuildPolicy`, `_DiscordSendTarget`. It exposes 78 function(s), including `__init__`, `_binding_expiration_reason`, `_build_presence_payload`, `_ack_interaction`, `_apply_bound_session`, `_auto_presence_loop`. It depends on 18 import statement target(s).
- `clawlite/channels/email.py`: `clawlite.channels.email` is a Python module in the `channels` area. It defines 1 class(es), led by `EmailChannel`. It exposes 25 function(s), including `__init__`, `_connect_imap`, `_decode_header_value`, `_poll_loop`, `send`, `start`. It depends on 15 import statement target(s).
- `clawlite/channels/whatsapp.py`: `clawlite.channels.whatsapp` is a Python module in the `channels` area. It defines 1 class(es), led by `WhatsAppChannel`. It exposes 22 function(s), including `__init__`, `_bridge_endpoint`, `_extract_retry_after`, `_client_post`, `_get_client`, `_send_typing_once`. It depends on 8 import statement target(s).
- `clawlite/channels/telegram_offset_store.py`: `clawlite.channels.telegram_offset_store` is a Python module in the `channels` area. It defines 2 class(es), led by `TelegramOffsetSnapshot`, `TelegramOffsetStore`. It exposes 24 function(s), including `__init__`, `_advance_safe_watermark_locked`, `_coerce_optional_update_id`. It depends on 9 import statement target(s).
- `clawlite/channels/slack.py`: `clawlite.channels.slack` is a Python module in the `channels` area. It defines 1 class(es), led by `SlackChannel`. It exposes 17 function(s), including `__init__`, `_extract_retry_after`, `_is_allowed_user`, `_ack_socket_envelope`, `_handle_slack_event`, `_handle_socket_envelope`. It depends on 7 import statement target(s).
- `clawlite/channels/telegram_pairing.py`: `clawlite.channels.telegram_pairing` is a Python module in the `channels` area. It defines 2 class(es), led by `TelegramPairingRequest`, `TelegramPairingStore`. It exposes 19 function(s), including `__init__`, `_generate_unique_code`, `_normalize_approved`. It depends on 10 import statement target(s).
- `clawlite/channels/telegram_outbound.py`: `clawlite.channels.telegram_outbound` is a Python module in the `channels` area. It defines 1 class(es), led by `TelegramOutboundRuntime`. It exposes 3 function(s), including `_remember_message_id`, `send_media_items`, `send_text_chunks`. It depends on 7 import statement target(s).
- `clawlite/channels/telegram_delivery.py`: `clawlite.channels.telegram_delivery` is a Python module in the `channels` area. It defines 3 class(es), led by `TelegramAuthCircuitBreaker`, `TelegramCircuitOpenError`, `TelegramRetryPolicy`. It exposes 21 function(s), including `__init__`, `coerce_retry_after_seconds`, `coerce_thread_id`. It depends on 8 import statement target(s).
- `clawlite/channels/telegram_interactions.py`: `clawlite.channels.telegram_interactions` is a Python module in the `channels` area. It defines 2 class(es), led by `TelegramCallbackQueryPayload`, `TelegramMessageReactionPayload`. It exposes 4 function(s), including `callback_query_metadata`, `extract_callback_query_payload`, `extract_message_reaction_payload`. It depends on 3 import statement target(s).
- `clawlite/channels/telegram_aux_updates.py`: `clawlite.channels.telegram_aux_updates` is a Python module in the `channels` area. It defines 1 class(es), led by `TelegramAuxUpdateEvent`. It exposes 1 function(s), including `extract_aux_update_event`. It depends on 3 import statement target(s).

Operational read:
The `channels` area has 57 internal Python dependency edge(s), 42 matched test relationship(s), and 506 discovered function definitions.

### tools

This area contains 21 code file(s) and 8977 line(s).

- `clawlite/tools/registry.py`: `clawlite.tools.registry` is a Python module in the `tools` area. It defines 3 class(es), led by `ToolRegistry`, `ToolResultCache`, `_CacheEntry`. It exposes 49 function(s), including `__init__`, `_add`, `_add_direct`, `execute`. It depends on 12 import statement target(s).
- `clawlite/tools/sessions.py`: `clawlite.tools.sessions` is a Python module in the `tools` area. It defines 7 class(es), led by `SessionStatusTool`, `SessionsHistoryTool`, `SessionsListTool`, `SessionsSendTool`. It exposes 33 function(s), including `__init__`, `_accepts_parameter`, `_apply_continuation_context`, `_lookup_continuation_context`, `_target_runner`, `run`. It depends on 11 import statement target(s).
- `clawlite/tools/skill.py`: `clawlite.tools.skill` is a Python module in the `tools` area. It defines 1 class(es), led by `SkillTool`. It exposes 37 function(s), including `__init__`, `_exec_output_exit_code`, `_exec_output_stream`, `_dispatch_script`, `_fetch_web_payload`, `_load_summary_source`. It depends on 19 import statement target(s).
- `clawlite/tools/exec.py`: `clawlite.tools.exec` is a Python module in the `tools` area. It defines 1 class(es), led by `ExecTool`. It exposes 37 function(s), including `__init__`, `_bash_compatible_path`, `_binary_name`, `health_check`, `run`. It depends on 14 import statement target(s).
- `clawlite/tools/memory.py`: `clawlite.tools.memory` is a Python module in the `tools` area. It defines 6 class(es), led by `MemoryAnalyzeTool`, `MemoryForgetTool`, `MemoryGetTool`, `MemoryLearnTool`. It exposes 20 function(s), including `__init__`, `_accepts_parameter`, `_assert_allowed_scope`, `run`. It depends on 7 import statement target(s).
- `clawlite/tools/web.py`: `clawlite.tools.web` is a Python module in the `tools` area. It defines 2 class(es), led by `WebFetchTool`, `WebSearchTool`. It exposes 26 function(s), including `__init__`, `_build_client`, `_coerce_extra_info_to_ip`, `_request_with_redirects`, `_resolve_ips_async`, `_search_brave`. It depends on 13 import statement target(s).
- `clawlite/tools/discord_admin.py`: `clawlite.tools.discord_admin` is a Python module in the `tools` area. It defines 1 class(es), led by `DiscordAdminTool`. It exposes 15 function(s), including `__init__`, `_build_channel_payload`, `_coerce_bool`, `_apply_layout`, `_ensure_channel`, `_ensure_role`. It depends on 6 import statement target(s).
- `clawlite/tools/process.py`: `clawlite.tools.process` is a Python module in the `tools` area. It defines 2 class(es), led by `ProcessSession`, `ProcessTool`. It exposes 20 function(s), including `__init__`, `_clamp_timeout_ms`, `_get_session`, `_append_output`, `_capture_stream`, `_clear`. It depends on 11 import statement target(s).
- `clawlite/tools/files.py`: `clawlite.tools.files` is a Python module in the `tools` area. It defines 9 class(es), led by `EditFileTool`, `EditTool`, `FileToolError`, `FileToolPermissionError`. It exposes 8 function(s), including `__init__`, `__str__`, `_atomic_write_text`, `run`. It depends on 8 import statement target(s).
- `clawlite/tools/apply_patch.py`: `clawlite.tools.apply_patch` is a Python module in the `tools` area. It defines 5 class(es), led by `AddOp`, `ApplyPatchTool`, `DeleteOp`, `UpdateChunk`. It exposes 10 function(s), including `__init__`, `_apply_update_chunks`, `_parse_patch`, `run`. It depends on 7 import statement target(s).
- `clawlite/tools/mcp.py`: `clawlite.tools.mcp` is a Python module in the `tools` area. It defines 1 class(es), led by `MCPTool`. It exposes 18 function(s), including `__init__`, `_host_matches`, `_ip_literal`, `_resolve_ips_async`, `_validate_transport`, `health_check`. It depends on 10 import statement target(s).
- `clawlite/tools/message.py`: `clawlite.tools.message` is a Python module in the `tools` area. It defines 2 class(es), led by `MessageAPI`, `MessageTool`. It exposes 7 function(s), including `__init__`, `_coerce_int`, `_validate_buttons`, `run`, `send`. It depends on 3 import statement target(s).

Operational read:
The `tools` area has 46 internal Python dependency edge(s), 80 matched test relationship(s), and 334 discovered function definitions.

### scheduler

This area contains 4 code file(s) and 1622 line(s).

- `clawlite/scheduler/cron.py`: `clawlite.scheduler.cron` is a Python module in the `scheduler` area. It defines 1 class(es), led by `CronService`. It exposes 49 function(s), including `__init__`, `_cleanup`, `_clear_lease`, `_cancel_running_tasks`, `_loop`, `_run_claimed_job`. It depends on 18 import statement target(s).
- `clawlite/scheduler/heartbeat.py`: `clawlite.scheduler.heartbeat` is a Python module in the `scheduler` area. It defines 2 class(es), led by `HeartbeatDecision`, `HeartbeatService`. It exposes 19 function(s), including `__init__`, `_bound_excerpt`, `_is_heartbeat_ok_ack`, `_execute_tick`, `_loop`, `_next_trigger_source`. It depends on 10 import statement target(s).
- `clawlite/scheduler/types.py`: `clawlite.scheduler.types` is a Python module in the `scheduler` area. It defines 3 class(es), led by `CronJob`, `CronPayload`, `CronSchedule`. It exposes 1 function(s), including `utc_now`. It depends on 4 import statement target(s).
- `clawlite/scheduler/__init__.py`: `clawlite.scheduler` is a Python module in the `scheduler` area. It depends on 4 import statement target(s).

Operational read:
The `scheduler` area has 6 internal Python dependency edge(s), 5 matched test relationship(s), and 69 discovered function definitions.

### jobs

This area contains 3 code file(s) and 419 line(s).

- `clawlite/jobs/queue.py`: `clawlite.jobs.queue` is a Python module in the `jobs` area. It defines 2 class(es), led by `Job`, `JobQueue`. It exposes 19 function(s), including `__init__`, `_owned_job`, `_pop_pending`, `_run_job`, `_worker_loop`, `stop`. It depends on 7 import statement target(s).
- `clawlite/jobs/journal.py`: `clawlite.jobs.journal` is a Python module in the `jobs` area. It defines 1 class(es), led by `JobJournal`. It exposes 6 function(s), including `__init__`, `close`, `load_all`. It depends on 7 import statement target(s).
- `clawlite/jobs/__init__.py`: `clawlite.jobs` is a Python module in the `jobs` area.

Operational read:
The `jobs` area has 1 internal Python dependency edge(s), 7 matched test relationship(s), and 25 discovered function definitions.

### bus

This area contains 5 code file(s) and 898 line(s).

- `clawlite/bus/queue.py`: `clawlite.bus.queue` is a Python module in the `bus` area. It defines 2 class(es), led by `BusFullError`, `MessageQueue`. It exposes 25 function(s), including `__init__`, `_dead_letter_idempotency_key`, `_dead_letter_matches`, `_enqueue_dead_letter`, `close`, `connect`. It depends on 8 import statement target(s).
- `clawlite/bus/journal.py`: `clawlite.bus.journal` is a Python module in the `bus` area. It defines 1 class(es), led by `BusJournal`. It exposes 12 function(s), including `__init__`, `_row_to_inbound`, `_row_to_outbound`. It depends on 8 import statement target(s).
- `clawlite/bus/redis_queue.py`: `clawlite.bus.redis_queue` is a Python module in the `bus` area. It defines 1 class(es), led by `RedisMessageQueue`. It exposes 13 function(s), including `__init__`, `_build_client`, `_coerce_blpop_payload`, `close`, `connect`, `next_inbound`. It depends on 8 import statement target(s).
- `clawlite/bus/events.py`: `clawlite.bus.events` is a Python module in the `bus` area. It defines 2 class(es), led by `InboundEvent`, `OutboundEvent`. It exposes 2 function(s), including `_new_correlation_id`, `_utc_now`. It depends on 5 import statement target(s).
- `clawlite/bus/__init__.py`: `clawlite.bus` is a Python module in the `bus` area. It depends on 4 import statement target(s).

Operational read:
The `bus` area has 7 internal Python dependency edge(s), 10 matched test relationship(s), and 52 discovered function definitions.

### session

This area contains 2 code file(s) and 519 line(s).

- `clawlite/session/store.py`: `clawlite.session.store` is a Python module in the `session` area. It defines 2 class(es), led by `SessionMessage`, `SessionStore`. It exposes 26 function(s), including `__init__`, `_append_once`, `_atomic_rewrite`. It depends on 9 import statement target(s).
- `clawlite/session/__init__.py`: `clawlite.session` is a Python module in the `session` area. It depends on 2 import statement target(s).

Operational read:
The `session` area has 0 internal Python dependency edge(s), 3 matched test relationship(s), and 26 discovered function definitions.

### workspace

This area contains 5 code file(s) and 932 line(s).

- `clawlite/workspace/loader.py`: `clawlite.workspace.loader` is a Python module in the `workspace` area. It defines 1 class(es), led by `WorkspaceLoader`. It exposes 38 function(s), including `__init__`, `_backup_runtime_file`, `_bootstrap_state_defaults`. It depends on 8 import statement target(s).
- `clawlite/workspace/user_profile.py`: `clawlite.workspace.user_profile` is a Python module in the `workspace` area. It defines 1 class(es), led by `WorkspaceUserProfile`. It exposes 6 function(s), including `_clean_field_value`, `_split_preferences`, `_strip_default_template_profile`. It depends on 4 import statement target(s).
- `clawlite/workspace/identity_enforcer.py`: `clawlite.workspace.identity_enforcer` is a Python module in the `workspace` area. It defines 2 class(es), led by `EnforcementResult`, `IdentityEnforcer`. It exposes 6 function(s), including `__init__`, `_compact`, `_guess_language`. It depends on 7 import statement target(s).
- `clawlite/workspace/bootstrap.py`: `clawlite.workspace.bootstrap` is a Python module in the `workspace` area. It exposes 1 function(s), including `bootstrap_install_workspace`. It depends on 6 import statement target(s).
- `clawlite/workspace/__init__.py`: `clawlite.workspace` is a Python module in the `workspace` area. It depends on 3 import statement target(s).

Operational read:
The `workspace` area has 7 internal Python dependency edge(s), 5 matched test relationship(s), and 51 discovered function definitions.

### skills

This area contains 5 code file(s) and 747 line(s).

- `clawlite/skills/model-usage/scripts/model_usage.py`: `clawlite.skills.model-usage.scripts.model_usage` is a Python module in the `skills` area. It defines 1 class(es), led by `ModelCost`. It exposes 16 function(s), including `aggregate_costs`, `build_json_all`, `build_json_current`. It depends on 8 import statement target(s).
- `clawlite/skills/skill_creator.py`: `clawlite.skills.skill_creator` is a Python module in the `skills` area. It exposes 5 function(s), including `_cli_main`, `init_skill`, `normalize_skill_name`. It depends on 5 import statement target(s).
- `clawlite/skills/tmux/scripts/wait-for-text.sh`: clawlite/skills/tmux/scripts/wait-for-text.sh is an executable script in the skills area.
- `clawlite/skills/tmux/scripts/find-sessions.sh`: clawlite/skills/tmux/scripts/find-sessions.sh is an executable script in the skills area.
- `clawlite/skills/__init__.py`: `clawlite.skills` is a Python module in the `skills` area. It depends on 1 import statement target(s).

Operational read:
The `skills` area has 0 internal Python dependency edge(s), 9 matched test relationship(s), and 21 discovered function definitions.

### dashboard

This area contains 4 code file(s) and 3318 line(s).

- `clawlite/dashboard/dashboard.js`: clawlite/dashboard/dashboard.js is a dashboard file whose first meaningful line is `const bootstrap = window.__CLAWLITE_DASHBOARD_BOOTSTRAP__ || {};`.
- `clawlite/dashboard/dashboard.css`: clawlite/dashboard/dashboard.css is a dashboard file whose first meaningful line is `:root {`.
- `clawlite/dashboard/index.html`: clawlite/dashboard/index.html is a dashboard file whose first meaningful line is `<!doctype html>`.
- `clawlite/dashboard/__init__.py`: `clawlite.dashboard` is a Python module in the `dashboard` area. It depends on 1 import statement target(s).

Operational read:
The `dashboard` area has 0 internal Python dependency edge(s), 8 matched test relationship(s), and 0 discovered function definitions.

### scripts

This area contains 14 code file(s) and 1797 line(s).

- `scripts/generate_architecture_docs.py`: `scripts.generate_architecture_docs` is a Python module in the `scripts` area. It defines 2 class(es), led by `FileInfo`, `PythonAnalyzer`. It exposes 30 function(s), including `__init__`, `_is_excluded`, `build_file_info`. It depends on 9 import statement target(s).
- `scripts/install.sh`: scripts/install.sh is an executable script in the scripts area.
- `scripts/terminal_template.py`: `scripts.terminal_template` is a Python module in the `scripts` area. It defines 1 class(es), led by `TermLine`. It exposes 3 function(s), including `_render_lines`, `_render_prompt_partial`, `build_html`. It depends on 2 import statement target(s).
- `scripts/docker_setup.sh`: scripts/docker_setup.sh is an executable script in the scripts area.
- `scripts/make_demo_gif.py`: `scripts.make_demo_gif` is a Python module in the `scripts` area. It exposes 2 function(s), including `build_frames_spec`, `make_demo_gif`. It depends on 6 import statement target(s).
- `scripts/smoke_test.sh`: scripts/smoke_test.sh is an executable script in the scripts area.
- `scripts/release_preflight.sh`: scripts/release_preflight.sh is an executable script in the scripts area.
- `scripts/install_termux_proot.sh`: scripts/install_termux_proot.sh is an executable script in the scripts area.
- `scripts/update_checkout.sh`: scripts/update_checkout.sh is an executable script in the scripts area.
- `scripts/assemble_gif.py`: `scripts.assemble_gif` is a Python module in the `scripts` area. It exposes 1 function(s), including `assemble_gif`. It depends on 4 import statement target(s).
- `scripts/capture_frames.py`: `scripts.capture_frames` is a Python module in the `scripts` area. It exposes 1 function(s), including `capture_frames`. It depends on 4 import statement target(s).
- `scripts/backup_clawlite.sh`: scripts/backup_clawlite.sh is an executable script in the scripts area.

Operational read:
The `scripts` area has 4 internal Python dependency edge(s), 7 matched test relationship(s), and 37 discovered function definitions.

### tests

This area contains 153 code file(s) and 56932 line(s).

- `tests/gateway/test_server.py`: `tests.gateway.test_server` is a Python module in the `tests` area. It defines 21 class(es), led by `AutonomyIdleProvider`, `FailingProvider`, `FakeBot`, `FakeProvider`. It exposes 214 function(s), including `__init__`, `_analysis_error`, `_analysis_stats`, `_channels_start`, `_channels_stop`, `_close`. It depends on 27 import statement target(s).
- `tests/channels/test_telegram.py`: `tests.channels.test_telegram` is a Python module in the `tests` area. It defines 12 class(es), led by `AuthError`, `FailingBot`, `FakeBot`, `FakeRemoteFile`. It exposes 170 function(s), including `__init__`, `_bind_offset_path`, `_tracking_create_task`, `_allow_handler`, `_block_handler`, `_fake_poll_loop`. It depends on 11 import statement target(s).
- `tests/cli/test_commands.py`: `tests.cli.test_commands` is a Python module in the `tests` area. It defines 6 class(es), led by `_Client`, `_Engine`, `_FakeClient`, `_FakeResponse`. It exposes 136 function(s), including `__enter__`, `__exit__`, `__init__`, `run`. It depends on 14 import statement target(s).
- `tests/core/test_engine.py`: `tests.core.test_engine` is a Python module in the `tests` area. It defines 67 class(es), led by `BlockingConcurrencyProvider`, `ContextCaptureTools`, `ExecNoopTool`, `ExecuteCaptureTools`. It exposes 132 function(s), including `__enter__`, `__exit__`, `__init__`, `_hook`, `_long_execute`, `_scenario`. It depends on 19 import statement target(s).
- `tests/core/test_memory.py`: `tests.core.test_memory` is a Python module in the `tests` area. It defines 5 class(es), led by `_DetailedBackend`, `_FailingBackend`, `_FakeBM25`, `_Headers`. It exposes 143 function(s), including `__enter__`, `__exit__`, `__init__`, `_broken_completion`, `_consolidate_categories`, `_fake_aembedding`. It depends on 11 import statement target(s).
- `tests/channels/test_manager.py`: `tests.channels.test_manager` is a Python module in the `tests` area. It defines 17 class(es), led by `ApprovalEngine`, `ApprovalRegistry`, `BlockingEngine`, `ConcurrentEngine`. It exposes 58 function(s), including `__init__`, `_start_typing_keepalive`, `cancel_session`, `_crash`, `_interceptor`, `_notice`. It depends on 11 import statement target(s).
- `tests/channels/test_discord.py`: `tests.channels.test_discord` is a Python module in the `tests` area. It defines 3 class(es), led by `_FakeClient`, `_FakeVoiceClient`, `_FakeWebSocket`. It exposes 65 function(s), including `__aiter__`, `__init__`, `_factory`, `__aenter__`, `__aexit__`, `__anext__`. It depends on 11 import statement target(s).
- `tests/tools/test_sessions_tools.py`: `tests.tools.test_sessions_tools` is a Python module in the `tests` area. It defines 1 class(es), led by `MemoryStub`. It exposes 31 function(s), including `__init__`, `_resume_runner_factory`, `set_working_memory_share_scope`, `_resume_runner`, `_runner`, `_scenario`. It depends on 8 import statement target(s).
- `tests/tools/test_registry.py`: `tests.tools.test_registry` is a Python module in the `tests` area. It defines 8 class(es), led by `BrowserLikeTool`, `EchoTool`, `ExecLikeTool`, `NestedSchemaTool`. It exposes 52 function(s), including `__enter__`, `__exit__`, `__init__`, `_scenario`, `run`. It depends on 8 import statement target(s).
- `tests/tools/test_skill_tool.py`: `tests.tools.test_skill_tool` is a Python module in the `tests` area. It defines 11 class(es), led by `ExplodingMemory`, `FakeExecCaptureTool`, `FakeExecStatusTool`, `FakeExecTool`. It exposes 41 function(s), including `__init__`, `_write_skill`, `args_schema`, `_scenario`, `complete`, `run`. It depends on 10 import statement target(s).
- `tests/config/test_loader.py`: `tests.config.test_loader` is a Python module in the `tests` area. It exposes 46 function(s), including `_tracking_replace`, `test_app_config_gateway_preserves_explicit_zero_values_and_clamps_minimums`, `test_load_config_agent_defaults_semantic_flags_camel_case`. It depends on 6 import statement target(s).
- `tests/tools/test_memory_tools.py`: `tests.tools.test_memory_tools` is a Python module in the `tests` area. It defines 7 class(es), led by `_AnalyzeAwareMemory`, `_AsyncMemory`, `_Backend`, `_BoundedMemory`. It exposes 49 function(s), including `__init__`, `_callable`, `_counting_signature`, `_scenario`, `memorize`, `retrieve`. It depends on 9 import statement target(s).

Operational read:
The `tests` area has 267 internal Python dependency edge(s), 0 matched test relationship(s), and 2528 discovered function definitions.

## Cross-Cutting Themes

- The gateway is the main orchestration layer. It wires request handlers, runtime state, background services, diagnostics, dashboard payloads, tool approvals, and supervisor recovery.
- Memory is a dedicated internal subsystem, not a helper. The `core/memory*.py` cluster is large enough to act as a mini-package for ingestion, retrieval, pruning, versioning, workflows, quality, policy, and reporting.
- Telegram and Discord support are not thin integrations. The channel area contains protocol-specific logic for offsets, delivery, pairing, interactions, dedupe, runtime state, and transport behavior.
- Runtime autonomy is separated from the gateway but tightly integrated with it. The runtime area owns long-lived loops and safety guards; the gateway area owns lifecycle startup and exposure.
- Test coverage mirrors the package structure heavily, which makes the codebase navigable through adjacent tests.

## Evidence-Backed Hotspots

- `tests/gateway/test_server.py`: 6602 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `tests/channels/test_telegram.py`: 5835 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `tests/cli/test_commands.py`: 5021 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `clawlite/core/memory.py`: 4448 lines, 14 inbound dependency edge(s), 30 matching test file(s)
- `clawlite/channels/telegram.py`: 3903 lines, 5 inbound dependency edge(s), 9 matching test file(s)
- `clawlite/core/engine.py`: 3776 lines, 9 inbound dependency edge(s), 2 matching test file(s)
- `clawlite/gateway/server.py`: 3610 lines, 2 inbound dependency edge(s), 1 matching test file(s)
- `tests/core/test_engine.py`: 3483 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `clawlite/cli/ops.py`: 3283 lines, 4 inbound dependency edge(s), 0 matching test file(s)
- `tests/core/test_memory.py`: 2900 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `clawlite/cli/commands.py`: 2689 lines, 3 inbound dependency edge(s), 1 matching test file(s)
- `clawlite/channels/manager.py`: 2429 lines, 3 inbound dependency edge(s), 1 matching test file(s)
- `clawlite/channels/discord.py`: 2343 lines, 3 inbound dependency edge(s), 3 matching test file(s)
- `clawlite/dashboard/dashboard.js`: 2201 lines, 0 inbound dependency edge(s), 3 matching test file(s)
- `clawlite/config/schema.py`: 1863 lines, 26 inbound dependency edge(s), 1 matching test file(s)
- `clawlite/cli/onboarding.py`: 1812 lines, 4 inbound dependency edge(s), 1 matching test file(s)
- `tests/channels/test_manager.py`: 1639 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `tests/channels/test_discord.py`: 1608 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `clawlite/core/memory_backend.py`: 1399 lines, 3 inbound dependency edge(s), 2 matching test file(s)
- `clawlite/core/skills.py`: 1362 lines, 8 inbound dependency edge(s), 3 matching test file(s)
- `clawlite/runtime/self_evolution.py`: 1282 lines, 2 inbound dependency edge(s), 2 matching test file(s)
- `clawlite/tools/registry.py`: 1280 lines, 9 inbound dependency edge(s), 3 matching test file(s)
- `tests/tools/test_sessions_tools.py`: 1209 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `clawlite/tools/sessions.py`: 1190 lines, 3 inbound dependency edge(s), 2 matching test file(s)
- `tests/tools/test_registry.py`: 1183 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `clawlite/scheduler/cron.py`: 1144 lines, 5 inbound dependency edge(s), 2 matching test file(s)
- `tests/tools/test_skill_tool.py`: 1096 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `tests/config/test_loader.py`: 1054 lines, 0 inbound dependency edge(s), 0 matching test file(s)
- `clawlite/runtime/autonomy_actions.py`: 1048 lines, 2 inbound dependency edge(s), 2 matching test file(s)
- `clawlite/tools/skill.py`: 1047 lines, 3 inbound dependency edge(s), 6 matching test file(s)

## Generated Per-File Corpus

A separate generated Markdown pair exists for every discovered code file:

- `READ_<filename>.md` explains what the file contains and how to read it.
- `CONNECTIONS_<filename>.md` records dependencies, dependents, and matched test relationships.

These files are stored under `docs/generated_architecture/per_file/` in mirrored directory paths.
