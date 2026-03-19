# Project Structure Data

## Snapshot Summary

- Total code files: 359
- Total code lines: 139091

## Subsystem Inventory

### bus

- Files: 5
- Python modules: 5
- Total lines: 898
- Representative files:
  - `clawlite/bus/queue.py` (446 lines)
  - `clawlite/bus/journal.py` (237 lines)
  - `clawlite/bus/redis_queue.py` (164 lines)
  - `clawlite/bus/events.py` (44 lines)
  - `clawlite/bus/__init__.py` (7 lines)

### channels

- Files: 31
- Python modules: 31
- Total lines: 12711
- Representative files:
  - `clawlite/channels/telegram.py` (3903 lines)
  - `clawlite/channels/manager.py` (2429 lines)
  - `clawlite/channels/discord.py` (2343 lines)
  - `clawlite/channels/email.py` (522 lines)
  - `clawlite/channels/whatsapp.py` (401 lines)
  - `clawlite/channels/telegram_offset_store.py` (400 lines)
  - `clawlite/channels/slack.py` (388 lines)
  - `clawlite/channels/telegram_pairing.py` (331 lines)

### clawlite

- Files: 1
- Python modules: 1
- Total lines: 2
- Representative files:
  - `clawlite/__init__.py` (2 lines)

### cli

- Files: 5
- Python modules: 5
- Total lines: 7796
- Representative files:
  - `clawlite/cli/ops.py` (3283 lines)
  - `clawlite/cli/commands.py` (2689 lines)
  - `clawlite/cli/onboarding.py` (1812 lines)
  - `clawlite/cli/__main__.py` (7 lines)
  - `clawlite/cli/__init__.py` (5 lines)

### config

- Files: 6
- Python modules: 6
- Total lines: 2409
- Representative files:
  - `clawlite/config/schema.py` (1863 lines)
  - `clawlite/config/loader.py` (311 lines)
  - `clawlite/config/watcher.py` (94 lines)
  - `clawlite/config/health.py` (67 lines)
  - `clawlite/config/audit.py` (61 lines)
  - `clawlite/config/__init__.py` (13 lines)

### core

- Files: 38
- Python modules: 38
- Total lines: 20956
- Representative files:
  - `clawlite/core/memory.py` (4448 lines)
  - `clawlite/core/engine.py` (3776 lines)
  - `clawlite/core/memory_backend.py` (1399 lines)
  - `clawlite/core/skills.py` (1362 lines)
  - `clawlite/core/subagent.py` (964 lines)
  - `clawlite/core/memory_working_set.py` (835 lines)
  - `clawlite/core/memory_retrieval.py` (759 lines)
  - `clawlite/core/memory_monitor.py` (578 lines)

### dashboard

- Files: 4
- Python modules: 1
- Total lines: 3318
- Representative files:
  - `clawlite/dashboard/dashboard.js` (2201 lines)
  - `clawlite/dashboard/dashboard.css` (653 lines)
  - `clawlite/dashboard/index.html` (463 lines)
  - `clawlite/dashboard/__init__.py` (1 lines)

### gateway

- Files: 30
- Python modules: 30
- Total lines: 9290
- Representative files:
  - `clawlite/gateway/server.py` (3610 lines)
  - `clawlite/gateway/runtime_builder.py` (634 lines)
  - `clawlite/gateway/websocket_handlers.py` (495 lines)
  - `clawlite/gateway/lifecycle_runtime.py` (320 lines)
  - `clawlite/gateway/discord_thread_binding.py` (305 lines)
  - `clawlite/gateway/tuning_loop.py` (285 lines)
  - `clawlite/gateway/request_handlers.py` (284 lines)
  - `clawlite/gateway/engine_diagnostics.py` (257 lines)

### jobs

- Files: 3
- Python modules: 3
- Total lines: 419
- Representative files:
  - `clawlite/jobs/queue.py` (295 lines)
  - `clawlite/jobs/journal.py` (124 lines)
  - `clawlite/jobs/__init__.py` (0 lines)

### providers

- Files: 17
- Python modules: 17
- Total lines: 4480
- Representative files:
  - `clawlite/providers/registry.py` (934 lines)
  - `clawlite/providers/litellm.py` (812 lines)
  - `clawlite/providers/codex.py` (627 lines)
  - `clawlite/providers/failover.py` (333 lines)
  - `clawlite/providers/hints.py` (303 lines)
  - `clawlite/providers/gemini_auth.py` (239 lines)
  - `clawlite/providers/catalog.py` (207 lines)
  - `clawlite/providers/qwen_auth.py` (191 lines)

### root

- Files: 1
- Python modules: 1
- Total lines: 5
- Representative files:
  - `conftest.py` (5 lines)

### runtime

- Files: 10
- Python modules: 10
- Total lines: 4855
- Representative files:
  - `clawlite/runtime/self_evolution.py` (1282 lines)
  - `clawlite/runtime/autonomy_actions.py` (1048 lines)
  - `clawlite/runtime/autonomy.py` (865 lines)
  - `clawlite/runtime/supervisor.py` (464 lines)
  - `clawlite/runtime/volva.py` (335 lines)
  - `clawlite/runtime/valkyrie.py` (313 lines)
  - `clawlite/runtime/gjallarhorn.py` (262 lines)
  - `clawlite/runtime/autonomy_log.py` (142 lines)

### scheduler

- Files: 4
- Python modules: 4
- Total lines: 1622
- Representative files:
  - `clawlite/scheduler/cron.py` (1144 lines)
  - `clawlite/scheduler/heartbeat.py` (425 lines)
  - `clawlite/scheduler/types.py` (46 lines)
  - `clawlite/scheduler/__init__.py` (7 lines)

### scripts

- Files: 14
- Python modules: 6
- Total lines: 1797
- Representative files:
  - `scripts/generate_architecture_docs.py` (801 lines)
  - `scripts/install.sh` (336 lines)
  - `scripts/terminal_template.py` (127 lines)
  - `scripts/docker_setup.sh` (87 lines)
  - `scripts/make_demo_gif.py` (86 lines)
  - `scripts/smoke_test.sh` (86 lines)
  - `scripts/release_preflight.sh` (69 lines)
  - `scripts/install_termux_proot.sh` (66 lines)

### session

- Files: 2
- Python modules: 2
- Total lines: 519
- Representative files:
  - `clawlite/session/store.py` (514 lines)
  - `clawlite/session/__init__.py` (5 lines)

### skills

- Files: 5
- Python modules: 3
- Total lines: 747
- Representative files:
  - `clawlite/skills/model-usage/scripts/model_usage.py` (319 lines)
  - `clawlite/skills/skill_creator.py` (185 lines)
  - `clawlite/skills/tmux/scripts/wait-for-text.sh` (146 lines)
  - `clawlite/skills/tmux/scripts/find-sessions.sh` (94 lines)
  - `clawlite/skills/__init__.py` (3 lines)

### tests

- Files: 153
- Python modules: 153
- Total lines: 56932
- Representative files:
  - `tests/gateway/test_server.py` (6602 lines)
  - `tests/channels/test_telegram.py` (5835 lines)
  - `tests/cli/test_commands.py` (5021 lines)
  - `tests/core/test_engine.py` (3483 lines)
  - `tests/core/test_memory.py` (2900 lines)
  - `tests/channels/test_manager.py` (1639 lines)
  - `tests/channels/test_discord.py` (1608 lines)
  - `tests/tools/test_sessions_tools.py` (1209 lines)

### tools

- Files: 21
- Python modules: 21
- Total lines: 8977
- Representative files:
  - `clawlite/tools/registry.py` (1280 lines)
  - `clawlite/tools/sessions.py` (1190 lines)
  - `clawlite/tools/skill.py` (1047 lines)
  - `clawlite/tools/exec.py` (1029 lines)
  - `clawlite/tools/memory.py` (804 lines)
  - `clawlite/tools/web.py` (552 lines)
  - `clawlite/tools/discord_admin.py` (493 lines)
  - `clawlite/tools/process.py` (378 lines)

### utils

- Files: 4
- Python modules: 4
- Total lines: 426
- Representative files:
  - `clawlite/utils/logger.py` (255 lines)
  - `clawlite/utils/logging.py` (137 lines)
  - `clawlite/utils/helpers.py` (28 lines)
  - `clawlite/utils/__init__.py` (6 lines)

### workspace

- Files: 5
- Python modules: 5
- Total lines: 932
- Representative files:
  - `clawlite/workspace/loader.py` (606 lines)
  - `clawlite/workspace/user_profile.py` (152 lines)
  - `clawlite/workspace/identity_enforcer.py` (132 lines)
  - `clawlite/workspace/bootstrap.py` (36 lines)
  - `clawlite/workspace/__init__.py` (6 lines)

## Largest Files

- `tests/gateway/test_server.py`: 6602 lines, 214 functions, 21 classes
- `tests/channels/test_telegram.py`: 5835 lines, 170 functions, 12 classes
- `tests/cli/test_commands.py`: 5021 lines, 136 functions, 6 classes
- `clawlite/core/memory.py`: 4448 lines, 269 functions, 4 classes
- `clawlite/channels/telegram.py`: 3903 lines, 136 functions, 1 classes
- `clawlite/core/engine.py`: 3776 lines, 120 functions, 21 classes
- `clawlite/gateway/server.py`: 3610 lines, 194 functions, 30 classes
- `tests/core/test_engine.py`: 3483 lines, 132 functions, 67 classes
- `clawlite/cli/ops.py`: 3283 lines, 76 functions, 0 classes
- `tests/core/test_memory.py`: 2900 lines, 143 functions, 5 classes
- `clawlite/cli/commands.py`: 2689 lines, 111 functions, 0 classes
- `clawlite/channels/manager.py`: 2429 lines, 93 functions, 3 classes
- `clawlite/channels/discord.py`: 2343 lines, 78 functions, 4 classes
- `clawlite/dashboard/dashboard.js`: 2201 lines, 0 functions, 0 classes
- `clawlite/config/schema.py`: 1863 lines, 125 functions, 38 classes
- `clawlite/cli/onboarding.py`: 1812 lines, 43 functions, 0 classes
- `tests/channels/test_manager.py`: 1639 lines, 58 functions, 17 classes
- `tests/channels/test_discord.py`: 1608 lines, 65 functions, 3 classes
- `clawlite/core/memory_backend.py`: 1399 lines, 38 functions, 4 classes
- `clawlite/core/skills.py`: 1362 lines, 68 functions, 2 classes
- `clawlite/runtime/self_evolution.py`: 1282 lines, 43 functions, 11 classes
- `clawlite/tools/registry.py`: 1280 lines, 49 functions, 3 classes
- `tests/tools/test_sessions_tools.py`: 1209 lines, 31 functions, 1 classes
- `clawlite/tools/sessions.py`: 1190 lines, 33 functions, 7 classes
- `tests/tools/test_registry.py`: 1183 lines, 52 functions, 8 classes
- `clawlite/scheduler/cron.py`: 1144 lines, 49 functions, 1 classes
- `tests/tools/test_skill_tool.py`: 1096 lines, 41 functions, 11 classes
- `tests/config/test_loader.py`: 1054 lines, 46 functions, 0 classes
- `clawlite/runtime/autonomy_actions.py`: 1048 lines, 33 functions, 1 classes
- `clawlite/tools/skill.py`: 1047 lines, 37 functions, 1 classes
- `clawlite/tools/exec.py`: 1029 lines, 37 functions, 1 classes
- `tests/tools/test_memory_tools.py`: 1027 lines, 49 functions, 7 classes
- `tests/core/test_skills.py`: 1008 lines, 39 functions, 1 classes
- `clawlite/core/subagent.py`: 964 lines, 50 functions, 3 classes
- `clawlite/providers/registry.py`: 934 lines, 25 functions, 2 classes
- `tests/cli/test_onboarding.py`: 898 lines, 33 functions, 3 classes
- `clawlite/runtime/autonomy.py`: 865 lines, 32 functions, 4 classes
- `tests/scheduler/test_cron.py`: 855 lines, 42 functions, 1 classes
- `clawlite/core/memory_working_set.py`: 835 lines, 24 functions, 0 classes
- `clawlite/providers/litellm.py`: 812 lines, 21 functions, 1 classes

## Most Imported Python Modules

- `clawlite/tools/base.py`: imported by 40 file(s), owns 5 functions
- `clawlite/utils/logging.py`: imported by 27 file(s), owns 11 functions
- `clawlite/config/schema.py`: imported by 26 file(s), owns 125 functions
- `clawlite/channels/base.py`: imported by 20 file(s), owns 11 functions
- `clawlite/bus/events.py`: imported by 17 file(s), owns 2 functions
- `clawlite/config/loader.py`: imported by 14 file(s), owns 16 functions
- `clawlite/core/memory.py`: imported by 14 file(s), owns 269 functions
- `clawlite/workspace/loader.py`: imported by 12 file(s), owns 38 functions
- `clawlite/core/subagent.py`: imported by 11 file(s), owns 50 functions
- `clawlite/core/engine.py`: imported by 9 file(s), owns 120 functions
- `clawlite/tools/registry.py`: imported by 9 file(s), owns 49 functions
- `clawlite/bus/queue.py`: imported by 8 file(s), owns 25 functions
- `clawlite/core/skills.py`: imported by 8 file(s), owns 68 functions
- `clawlite/jobs/queue.py`: imported by 8 file(s), owns 19 functions
- `clawlite/providers/base.py`: imported by 8 file(s), owns 3 functions
- `clawlite/core/memory_monitor.py`: imported by 7 file(s), owns 33 functions
- `clawlite/providers/reliability.py`: imported by 7 file(s), owns 5 functions
- `clawlite/session/store.py`: imported by 7 file(s), owns 26 functions
- `clawlite/providers/litellm.py`: imported by 6 file(s), owns 21 functions
- `clawlite/runtime/telemetry.py`: imported by 6 file(s), owns 10 functions
- `clawlite/channels/telegram.py`: imported by 5 file(s), owns 136 functions
- `clawlite/core/runestone.py`: imported by 5 file(s), owns 13 functions
- `clawlite/providers/catalog.py`: imported by 5 file(s), owns 2 functions
- `clawlite/providers/codex.py`: imported by 5 file(s), owns 25 functions
- `clawlite/providers/discovery.py`: imported by 5 file(s), owns 12 functions
- `clawlite/scheduler/cron.py`: imported by 5 file(s), owns 49 functions
- `clawlite/scheduler/heartbeat.py`: imported by 5 file(s), owns 19 functions
- `clawlite/tools/exec.py`: imported by 5 file(s), owns 37 functions
- `clawlite/cli/onboarding.py`: imported by 4 file(s), owns 43 functions
- `clawlite/cli/ops.py`: imported by 4 file(s), owns 76 functions
- `clawlite/core/injection_guard.py`: imported by 4 file(s), owns 10 functions
- `clawlite/core/memory_layers.py`: imported by 4 file(s), owns 6 functions
- `clawlite/core/prompt.py`: imported by 4 file(s), owns 17 functions
- `clawlite/providers/__init__.py`: imported by 4 file(s), owns 0 functions
- `clawlite/providers/hints.py`: imported by 4 file(s), owns 6 functions
- `clawlite/providers/registry.py`: imported by 4 file(s), owns 25 functions
- `clawlite/runtime/__init__.py`: imported by 4 file(s), owns 0 functions
- `scripts/terminal_template.py`: imported by 4 file(s), owns 3 functions
- `clawlite/bus/redis_queue.py`: imported by 3 file(s), owns 13 functions
- `clawlite/channels/discord.py`: imported by 3 file(s), owns 78 functions

## Source/Test Pairings

- `clawlite/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/bus/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/bus/journal.py` is covered by 2 matching test file(s)
  - `tests/bus/test_journal.py`
  - `tests/jobs/test_journal.py`
- `clawlite/bus/queue.py` is covered by 3 matching test file(s)
  - `tests/bus/test_queue.py`
  - `tests/bus/test_redis_queue.py`
  - `tests/jobs/test_queue.py`
- `clawlite/bus/redis_queue.py` is covered by 3 matching test file(s)
  - `tests/bus/test_queue.py`
  - `tests/bus/test_redis_queue.py`
  - `tests/jobs/test_queue.py`
- `clawlite/channels/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/channels/discord.py` is covered by 3 matching test file(s)
  - `tests/channels/test_discord.py`
  - `tests/gateway/test_discord_thread_binding.py`
  - `tests/tools/test_discord_admin_tool.py`
- `clawlite/channels/email.py` is covered by 1 matching test file(s)
  - `tests/channels/test_email.py`
- `clawlite/channels/inbound_text.py` is covered by 1 matching test file(s)
  - `tests/channels/test_inbound_text.py`
- `clawlite/channels/irc.py` is covered by 1 matching test file(s)
  - `tests/channels/test_irc.py`
- `clawlite/channels/manager.py` is covered by 1 matching test file(s)
  - `tests/channels/test_manager.py`
- `clawlite/channels/slack.py` is covered by 1 matching test file(s)
  - `tests/channels/test_slack.py`
- `clawlite/channels/telegram.py` is covered by 9 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_aux_updates.py`
  - `tests/channels/test_telegram_delivery.py`
  - `tests/channels/test_telegram_inbound_dispatch.py`
  - `tests/channels/test_telegram_inbound_message.py`
  - `tests/channels/test_telegram_inbound_runtime.py`
  - `tests/channels/test_telegram_interactions.py`
  - `tests/channels/test_telegram_status.py`
  - `tests/channels/test_telegram_transport.py`
- `clawlite/channels/telegram_aux_updates.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_aux_updates.py`
- `clawlite/channels/telegram_dedupe.py` is covered by 1 matching test file(s)
  - `tests/channels/test_telegram.py`
- `clawlite/channels/telegram_delivery.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_delivery.py`
- `clawlite/channels/telegram_inbound_dispatch.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_inbound_dispatch.py`
- `clawlite/channels/telegram_inbound_message.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_inbound_message.py`
- `clawlite/channels/telegram_inbound_runtime.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_inbound_runtime.py`
- `clawlite/channels/telegram_interactions.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_interactions.py`
- `clawlite/channels/telegram_offset_runtime.py` is covered by 1 matching test file(s)
  - `tests/channels/test_telegram.py`
- `clawlite/channels/telegram_offset_store.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/session/test_store.py`
- `clawlite/channels/telegram_outbound.py` is covered by 1 matching test file(s)
  - `tests/channels/test_telegram.py`
- `clawlite/channels/telegram_pairing.py` is covered by 1 matching test file(s)
  - `tests/channels/test_telegram.py`
- `clawlite/channels/telegram_status.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_status.py`
- `clawlite/channels/telegram_transport.py` is covered by 2 matching test file(s)
  - `tests/channels/test_telegram.py`
  - `tests/channels/test_telegram_transport.py`
- `clawlite/channels/whatsapp.py` is covered by 1 matching test file(s)
  - `tests/channels/test_whatsapp.py`
- `clawlite/cli/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/cli/commands.py` is covered by 1 matching test file(s)
  - `tests/cli/test_commands.py`
- `clawlite/cli/onboarding.py` is covered by 1 matching test file(s)
  - `tests/cli/test_onboarding.py`
- `clawlite/config/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/config/health.py` is covered by 2 matching test file(s)
  - `tests/config/test_health.py`
  - `tests/tools/test_health_check.py`
- `clawlite/config/loader.py` is covered by 2 matching test file(s)
  - `tests/config/test_loader.py`
  - `tests/workspace/test_workspace_loader.py`
- `clawlite/config/schema.py` is covered by 1 matching test file(s)
  - `tests/config/test_schema.py`
- `clawlite/config/watcher.py` is covered by 1 matching test file(s)
  - `tests/config/test_watcher.py`
- `clawlite/core/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/core/context_window.py` is covered by 1 matching test file(s)
  - `tests/core/test_context_window.py`
- `clawlite/core/engine.py` is covered by 2 matching test file(s)
  - `tests/core/test_engine.py`
  - `tests/gateway/test_engine_diagnostics.py`
- `clawlite/core/huginn_muninn.py` is covered by 1 matching test file(s)
  - `tests/core/test_huginn_muninn.py`
- `clawlite/core/injection_guard.py` is covered by 1 matching test file(s)
  - `tests/core/test_injection_guard.py`
- `clawlite/core/memory.py` is covered by 30 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_api.py`
  - `tests/core/test_memory_artifacts.py`
  - `tests/core/test_memory_backend.py`
  - `tests/core/test_memory_classification.py`
  - `tests/core/test_memory_consolidator.py`
  - `tests/core/test_memory_curation.py`
  - `tests/core/test_memory_history.py`
  - `tests/core/test_memory_ingest.py`
  - `tests/core/test_memory_ingest_helpers.py`
- `clawlite/core/memory_add.py` is covered by 1 matching test file(s)
  - `tests/core/test_memory.py`
- `clawlite/core/memory_api.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_api.py`
- `clawlite/core/memory_artifacts.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_artifacts.py`
- `clawlite/core/memory_backend.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_backend.py`
- `clawlite/core/memory_classification.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_classification.py`
- `clawlite/core/memory_consolidator.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_consolidator.py`
- `clawlite/core/memory_curation.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_curation.py`
- `clawlite/core/memory_history.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_history.py`
- `clawlite/core/memory_ingest.py` is covered by 3 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_ingest.py`
  - `tests/core/test_memory_ingest_helpers.py`
- `clawlite/core/memory_layers.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_layers.py`
- `clawlite/core/memory_maintenance.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_maintenance.py`
- `clawlite/core/memory_monitor.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_monitor.py`
- `clawlite/core/memory_policy.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_policy.py`
- `clawlite/core/memory_privacy.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_privacy.py`
- `clawlite/core/memory_proactive.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_proactive.py`
- `clawlite/core/memory_profile.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_profile.py`
- `clawlite/core/memory_prune.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_prune.py`
- `clawlite/core/memory_quality.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_quality.py`
- `clawlite/core/memory_reporting.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory.py`
  - `tests/core/test_memory_reporting.py`
- `clawlite/core/memory_resources.py` is covered by 2 matching test file(s)
  - `tests/core/test_memory_resources.py`
  - `tests/core/test_memory_resources_helpers.py`
- `clawlite/core/memory_retrieval.py` is covered by 1 matching test file(s)
  - `tests/core/test_memory_retrieval.py`
- `clawlite/core/memory_search.py` is covered by 1 matching test file(s)
  - `tests/core/test_memory_search.py`
- `clawlite/core/memory_versions.py` is covered by 1 matching test file(s)
  - `tests/core/test_memory_versions.py`
- `clawlite/core/memory_workflows.py` is covered by 1 matching test file(s)
  - `tests/core/test_memory_workflows.py`
- `clawlite/core/memory_working_set.py` is covered by 1 matching test file(s)
  - `tests/core/test_memory_working_set.py`
- `clawlite/core/norns.py` is covered by 1 matching test file(s)
  - `tests/core/test_norns.py`
- `clawlite/core/prompt.py` is covered by 1 matching test file(s)
  - `tests/core/test_prompt.py`
- `clawlite/core/runestone.py` is covered by 1 matching test file(s)
  - `tests/core/test_runestone.py`
- `clawlite/core/skills.py` is covered by 3 matching test file(s)
  - `tests/core/test_skills.py`
  - `tests/core/test_skills_new.py`
  - `tests/skills/test_markdown_skills.py`
- `clawlite/core/subagent.py` is covered by 3 matching test file(s)
  - `tests/core/test_subagent.py`
  - `tests/core/test_subagent_context.py`
  - `tests/gateway/test_subagents_runtime.py`
- `clawlite/core/subagent_synthesizer.py` is covered by 1 matching test file(s)
  - `tests/core/test_subagent.py`
- `clawlite/dashboard/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/dashboard/dashboard.css` is covered by 3 matching test file(s)
  - `tests/gateway/test_dashboard_runtime.py`
  - `tests/gateway/test_dashboard_state.py`
  - `tests/gateway/test_memory_dashboard.py`
- `clawlite/dashboard/dashboard.js` is covered by 3 matching test file(s)
  - `tests/gateway/test_dashboard_runtime.py`
  - `tests/gateway/test_dashboard_state.py`
  - `tests/gateway/test_memory_dashboard.py`
- `clawlite/gateway/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/gateway/autonomy_notice.py` is covered by 1 matching test file(s)
  - `tests/runtime/test_autonomy.py`
- `clawlite/gateway/background_runners.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_background_runners.py`
- `clawlite/gateway/control_plane.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_control_plane.py`
- `clawlite/gateway/dashboard_runtime.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_dashboard_runtime.py`
- `clawlite/gateway/dashboard_state.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_dashboard_state.py`
- `clawlite/gateway/diagnostics_payload.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_diagnostics_payload.py`
- `clawlite/gateway/discord_thread_binding.py` is covered by 2 matching test file(s)
  - `tests/channels/test_discord.py`
  - `tests/gateway/test_discord_thread_binding.py`
- `clawlite/gateway/engine_diagnostics.py` is covered by 2 matching test file(s)
  - `tests/core/test_engine.py`
  - `tests/gateway/test_engine_diagnostics.py`
- `clawlite/gateway/lifecycle_runtime.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_lifecycle_runtime.py`
- `clawlite/gateway/memory_dashboard.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_memory_dashboard.py`
- `clawlite/gateway/payloads.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_payloads.py`
- `clawlite/gateway/request_handlers.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_request_handlers.py`
- `clawlite/gateway/runtime_state.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_runtime_state.py`
- `clawlite/gateway/self_evolution_approval.py` is covered by 2 matching test file(s)
  - `tests/gateway/test_self_evolution_approval.py`
  - `tests/runtime/test_self_evolution.py`
- `clawlite/gateway/server.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_server.py`
- `clawlite/gateway/status_handlers.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_status_handlers.py`
- `clawlite/gateway/subagents_runtime.py` is covered by 2 matching test file(s)
  - `tests/core/test_subagent.py`
  - `tests/gateway/test_subagents_runtime.py`
- `clawlite/gateway/supervisor_recovery.py` is covered by 2 matching test file(s)
  - `tests/gateway/test_supervisor_recovery.py`
  - `tests/runtime/test_supervisor.py`
- `clawlite/gateway/supervisor_runtime.py` is covered by 2 matching test file(s)
  - `tests/gateway/test_supervisor_runtime.py`
  - `tests/runtime/test_supervisor.py`
- `clawlite/gateway/tool_approval.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_tool_approval.py`
- `clawlite/gateway/tool_catalog.py` is covered by 1 matching test file(s)
  - `tests/providers/test_catalog.py`
- `clawlite/gateway/tuning_decisions.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_tuning_decisions.py`
- `clawlite/gateway/tuning_policy.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_tuning_policy.py`
- `clawlite/gateway/tuning_runtime.py` is covered by 1 matching test file(s)
  - `tests/gateway/test_tuning_runtime.py`
- `clawlite/gateway/webhooks.py` is covered by 1 matching test file(s)
  - `tests/tools/test_web.py`
- `clawlite/gateway/websocket_handlers.py` is covered by 2 matching test file(s)
  - `tests/gateway/test_websocket_handlers.py`
  - `tests/tools/test_web.py`
- `clawlite/jobs/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/jobs/journal.py` is covered by 2 matching test file(s)
  - `tests/bus/test_journal.py`
  - `tests/jobs/test_journal.py`
- `clawlite/jobs/queue.py` is covered by 3 matching test file(s)
  - `tests/bus/test_queue.py`
  - `tests/bus/test_redis_queue.py`
  - `tests/jobs/test_queue.py`
- `clawlite/providers/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/providers/catalog.py` is covered by 1 matching test file(s)
  - `tests/providers/test_catalog.py`
- `clawlite/providers/codex.py` is covered by 1 matching test file(s)
  - `tests/providers/test_codex_retry.py`
- `clawlite/providers/discovery.py` is covered by 1 matching test file(s)
  - `tests/providers/test_discovery.py`
- `clawlite/providers/failover.py` is covered by 1 matching test file(s)
  - `tests/providers/test_failover.py`
- `clawlite/providers/hints.py` is covered by 1 matching test file(s)
  - `tests/providers/test_hints.py`
- `clawlite/providers/litellm.py` is covered by 2 matching test file(s)
  - `tests/providers/test_litellm_anthropic.py`
  - `tests/providers/test_litellm_retry.py`
- `clawlite/providers/model_probe.py` is covered by 1 matching test file(s)
  - `tests/providers/test_model_probe.py`
- `clawlite/providers/registry.py` is covered by 2 matching test file(s)
  - `tests/providers/test_registry_auth_resolution.py`
  - `tests/tools/test_registry.py`
- `clawlite/providers/reliability.py` is covered by 1 matching test file(s)
  - `tests/providers/test_reliability.py`
- `clawlite/providers/telemetry.py` is covered by 2 matching test file(s)
  - `tests/providers/test_telemetry.py`
  - `tests/runtime/test_runtime_telemetry.py`
- `clawlite/providers/transcription.py` is covered by 1 matching test file(s)
  - `tests/providers/test_transcription.py`
- `clawlite/runtime/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/runtime/autonomy.py` is covered by 4 matching test file(s)
  - `tests/runtime/test_autonomy.py`
  - `tests/runtime/test_autonomy_actions.py`
  - `tests/runtime/test_autonomy_log.py`
  - `tests/runtime/test_autonomy_wake.py`
- `clawlite/runtime/autonomy_actions.py` is covered by 2 matching test file(s)
  - `tests/runtime/test_autonomy.py`
  - `tests/runtime/test_autonomy_actions.py`
- `clawlite/runtime/autonomy_log.py` is covered by 2 matching test file(s)
  - `tests/runtime/test_autonomy.py`
  - `tests/runtime/test_autonomy_log.py`
- `clawlite/runtime/gjallarhorn.py` is covered by 1 matching test file(s)
  - `tests/runtime/test_gjallarhorn.py`
- `clawlite/runtime/self_evolution.py` is covered by 2 matching test file(s)
  - `tests/gateway/test_self_evolution_approval.py`
  - `tests/runtime/test_self_evolution.py`
- `clawlite/runtime/supervisor.py` is covered by 4 matching test file(s)
  - `tests/gateway/test_supervisor_recovery.py`
  - `tests/gateway/test_supervisor_runtime.py`
  - `tests/runtime/test_supervisor.py`
  - `tests/runtime/test_supervisor_phase5.py`
- `clawlite/runtime/telemetry.py` is covered by 2 matching test file(s)
  - `tests/providers/test_telemetry.py`
  - `tests/runtime/test_runtime_telemetry.py`
- `clawlite/runtime/valkyrie.py` is covered by 1 matching test file(s)
  - `tests/runtime/test_valkyrie.py`
- `clawlite/runtime/volva.py` is covered by 1 matching test file(s)
  - `tests/runtime/test_volva.py`
- `clawlite/scheduler/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/scheduler/cron.py` is covered by 2 matching test file(s)
  - `tests/scheduler/test_cron.py`
  - `tests/tools/test_cron_message_spawn_mcp.py`
- `clawlite/scheduler/heartbeat.py` is covered by 1 matching test file(s)
  - `tests/scheduler/test_heartbeat.py`
- `clawlite/session/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/session/store.py` is covered by 1 matching test file(s)
  - `tests/session/test_store.py`
- `clawlite/skills/__init__.py` is covered by 3 matching test file(s)
  - `tests/core/test_skills.py`
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/skills/model-usage/scripts/model_usage.py` is covered by 2 matching test file(s)
  - `tests/core/test_skills.py`
  - `tests/skills/test_model_usage_script.py`
- `clawlite/skills/skill_creator.py` is covered by 2 matching test file(s)
  - `tests/core/test_skills.py`
  - `tests/skills/test_skill_creator.py`
- `clawlite/skills/tmux/scripts/find-sessions.sh` is covered by 1 matching test file(s)
  - `tests/core/test_skills.py`
- `clawlite/skills/tmux/scripts/wait-for-text.sh` is covered by 1 matching test file(s)
  - `tests/core/test_skills.py`
- `clawlite/tools/__init__.py` is covered by 3 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/agents.py` is covered by 3 matching test file(s)
  - `tests/gateway/test_subagents_runtime.py`
  - `tests/tools/test_agents_tool.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/apply_patch.py` is covered by 2 matching test file(s)
  - `tests/tools/test_apply_patch.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/base.py` is covered by 1 matching test file(s)
  - `tests/tools/test_tools.py`
- `clawlite/tools/browser.py` is covered by 2 matching test file(s)
  - `tests/tools/test_browser_tool.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/cron.py` is covered by 3 matching test file(s)
  - `tests/scheduler/test_cron.py`
  - `tests/tools/test_cron_message_spawn_mcp.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/discord_admin.py` is covered by 3 matching test file(s)
  - `tests/channels/test_discord.py`
  - `tests/tools/test_discord_admin_tool.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/exec.py` is covered by 3 matching test file(s)
  - `tests/tools/test_exec_files.py`
  - `tests/tools/test_exec_network_guard.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/files.py` is covered by 3 matching test file(s)
  - `tests/tools/test_exec_files.py`
  - `tests/tools/test_files_edge_cases.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/jobs.py` is covered by 2 matching test file(s)
  - `tests/tools/test_jobs_tool.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/mcp.py` is covered by 3 matching test file(s)
  - `tests/tools/test_cron_message_spawn_mcp.py`
  - `tests/tools/test_mcp.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/memory.py` is covered by 30 matching test file(s)
  - `tests/core/test_memory_api.py`
  - `tests/core/test_memory_artifacts.py`
  - `tests/core/test_memory_backend.py`
  - `tests/core/test_memory_classification.py`
  - `tests/core/test_memory_consolidator.py`
  - `tests/core/test_memory_curation.py`
  - `tests/core/test_memory_history.py`
  - `tests/core/test_memory_ingest.py`
  - `tests/core/test_memory_ingest_helpers.py`
  - `tests/core/test_memory_layers.py`
- `clawlite/tools/message.py` is covered by 3 matching test file(s)
  - `tests/channels/test_telegram_inbound_message.py`
  - `tests/tools/test_cron_message_spawn_mcp.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/pdf.py` is covered by 1 matching test file(s)
  - `tests/tools/test_tools.py`
- `clawlite/tools/process.py` is covered by 2 matching test file(s)
  - `tests/tools/test_process_tool.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/registry.py` is covered by 3 matching test file(s)
  - `tests/providers/test_registry_auth_resolution.py`
  - `tests/tools/test_registry.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/sessions.py` is covered by 2 matching test file(s)
  - `tests/tools/test_sessions_tools.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/skill.py` is covered by 6 matching test file(s)
  - `tests/core/test_skills.py`
  - `tests/core/test_skills_new.py`
  - `tests/skills/test_markdown_skills.py`
  - `tests/skills/test_skill_creator.py`
  - `tests/tools/test_skill_tool.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/spawn.py` is covered by 2 matching test file(s)
  - `tests/tools/test_cron_message_spawn_mcp.py`
  - `tests/tools/test_tools.py`
- `clawlite/tools/tts.py` is covered by 1 matching test file(s)
  - `tests/tools/test_tools.py`
- `clawlite/tools/web.py` is covered by 2 matching test file(s)
  - `tests/gateway/test_websocket_handlers.py`
  - `tests/tools/test_web.py`
- `clawlite/utils/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/utils/helpers.py` is covered by 3 matching test file(s)
  - `tests/core/test_memory_ingest_helpers.py`
  - `tests/core/test_memory_resources_helpers.py`
  - `tests/utils/test_helpers.py`
- `clawlite/utils/logging.py` is covered by 1 matching test file(s)
  - `tests/utils/test_logging.py`
- `clawlite/workspace/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `clawlite/workspace/loader.py` is covered by 2 matching test file(s)
  - `tests/config/test_loader.py`
  - `tests/workspace/test_workspace_loader.py`
- `clawlite/workspace/user_profile.py` is covered by 1 matching test file(s)
  - `tests/workspace/test_user_profile.py`
- `scripts/__init__.py` is covered by 2 matching test file(s)
  - `tests/jobs/__init__.py`
  - `tests/skills/__init__.py`
- `scripts/assemble_gif.py` is covered by 1 matching test file(s)
  - `tests/scripts/test_assemble_gif.py`
- `scripts/capture_frames.py` is covered by 1 matching test file(s)
  - `tests/scripts/test_capture_frames.py`
- `scripts/make_demo_gif.py` is covered by 1 matching test file(s)
  - `tests/scripts/test_make_demo_gif.py`
- `scripts/restore_clawlite.sh` is covered by 1 matching test file(s)
  - `tests/session/test_store.py`
- `scripts/terminal_template.py` is covered by 1 matching test file(s)
  - `tests/scripts/test_terminal_template.py`

## Raw Manifest

```json
[
  {
    "path": "clawlite/__init__.py",
    "area": "clawlite",
    "ext": ".py",
    "lines": 2,
    "size_bytes": 50,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/bus/__init__.py",
    "area": "bus",
    "ext": ".py",
    "lines": 7,
    "size_bytes": 277,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/bus/queue.py",
      "clawlite/bus/redis_queue.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/bus/events.py",
    "area": "bus",
    "ext": ".py",
    "lines": 44,
    "size_bytes": 1106,
    "imports": [],
    "imported_by_count": 17,
    "tests_for": []
  },
  {
    "path": "clawlite/bus/journal.py",
    "area": "bus",
    "ext": ".py",
    "lines": 237,
    "size_bytes": 8012,
    "imports": [
      "clawlite/bus/events.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/bus/test_journal.py",
      "tests/jobs/test_journal.py"
    ]
  },
  {
    "path": "clawlite/bus/queue.py",
    "area": "bus",
    "ext": ".py",
    "lines": 446,
    "size_bytes": 16880,
    "imports": [
      "clawlite/bus/events.py"
    ],
    "imported_by_count": 8,
    "tests_for": [
      "tests/bus/test_queue.py",
      "tests/bus/test_redis_queue.py",
      "tests/jobs/test_queue.py"
    ]
  },
  {
    "path": "clawlite/bus/redis_queue.py",
    "area": "bus",
    "ext": ".py",
    "lines": 164,
    "size_bytes": 6141,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/bus/queue.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/bus/test_queue.py",
      "tests/bus/test_redis_queue.py",
      "tests/jobs/test_queue.py"
    ]
  },
  {
    "path": "clawlite/channels/__init__.py",
    "area": "channels",
    "ext": ".py",
    "lines": 7,
    "size_bytes": 299,
    "imports": [
      "clawlite/channels/base.py",
      "clawlite/channels/manager.py",
      "clawlite/channels/telegram.py"
    ],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/channels/base.py",
    "area": "channels",
    "ext": ".py",
    "lines": 154,
    "size_bytes": 5054,
    "imports": [
      "clawlite/channels/inbound_text.py",
      "clawlite/core/injection_guard.py",
      "clawlite/core/runestone.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 20,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/dingtalk.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 273,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/discord.py",
    "area": "channels",
    "ext": ".py",
    "lines": 2343,
    "size_bytes": 92085,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/channels/test_discord.py",
      "tests/gateway/test_discord_thread_binding.py",
      "tests/tools/test_discord_admin_tool.py"
    ]
  },
  {
    "path": "clawlite/channels/email.py",
    "area": "channels",
    "ext": ".py",
    "lines": 522,
    "size_bytes": 19852,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_email.py"
    ]
  },
  {
    "path": "clawlite/channels/feishu.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 269,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/googlechat.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 277,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/imessage.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 273,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/inbound_text.py",
    "area": "channels",
    "ext": ".py",
    "lines": 26,
    "size_bytes": 937,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_inbound_text.py"
    ]
  },
  {
    "path": "clawlite/channels/irc.py",
    "area": "channels",
    "ext": ".py",
    "lines": 132,
    "size_bytes": 5226,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_irc.py"
    ]
  },
  {
    "path": "clawlite/channels/manager.py",
    "area": "channels",
    "ext": ".py",
    "lines": 2429,
    "size_bytes": 104694,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/bus/queue.py",
      "clawlite/channels/base.py",
      "clawlite/channels/dingtalk.py",
      "clawlite/channels/discord.py",
      "clawlite/channels/email.py",
      "clawlite/channels/feishu.py",
      "clawlite/channels/googlechat.py",
      "clawlite/channels/imessage.py",
      "clawlite/channels/irc.py",
      "clawlite/channels/matrix.py",
      "clawlite/channels/mochat.py",
      "clawlite/channels/qq.py",
      "clawlite/channels/signal.py",
      "clawlite/channels/slack.py",
      "clawlite/channels/telegram.py",
      "clawlite/channels/whatsapp.py",
      "clawlite/gateway/tool_approval.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/channels/test_manager.py"
    ]
  },
  {
    "path": "clawlite/channels/matrix.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 269,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/mochat.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 269,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/qq.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 261,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/signal.py",
    "area": "channels",
    "ext": ".py",
    "lines": 8,
    "size_bytes": 269,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/channels/slack.py",
    "area": "channels",
    "ext": ".py",
    "lines": 388,
    "size_bytes": 15624,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/channels/test_slack.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram.py",
    "area": "channels",
    "ext": ".py",
    "lines": 3903,
    "size_bytes": 155767,
    "imports": [
      "clawlite/channels/base.py",
      "clawlite/channels/telegram_aux_updates.py",
      "clawlite/channels/telegram_dedupe.py",
      "clawlite/channels/telegram_delivery.py",
      "clawlite/channels/telegram_inbound_dispatch.py",
      "clawlite/channels/telegram_inbound_message.py",
      "clawlite/channels/telegram_inbound_runtime.py",
      "clawlite/channels/telegram_interactions.py",
      "clawlite/channels/telegram_offset_runtime.py",
      "clawlite/channels/telegram_offset_store.py",
      "clawlite/channels/telegram_outbound.py",
      "clawlite/channels/telegram_pairing.py",
      "clawlite/channels/telegram_status.py",
      "clawlite/channels/telegram_transport.py",
      "clawlite/config/schema.py",
      "clawlite/providers/transcription.py"
    ],
    "imported_by_count": 5,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_aux_updates.py",
      "tests/channels/test_telegram_delivery.py",
      "tests/channels/test_telegram_inbound_dispatch.py",
      "tests/channels/test_telegram_inbound_message.py",
      "tests/channels/test_telegram_inbound_runtime.py",
      "tests/channels/test_telegram_interactions.py",
      "tests/channels/test_telegram_status.py",
      "tests/channels/test_telegram_transport.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_aux_updates.py",
    "area": "channels",
    "ext": ".py",
    "lines": 167,
    "size_bytes": 6952,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_aux_updates.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_dedupe.py",
    "area": "channels",
    "ext": ".py",
    "lines": 131,
    "size_bytes": 4056,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/channels/test_telegram.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_delivery.py",
    "area": "channels",
    "ext": ".py",
    "lines": 288,
    "size_bytes": 9027,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_delivery.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_inbound_dispatch.py",
    "area": "channels",
    "ext": ".py",
    "lines": 39,
    "size_bytes": 1005,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_inbound_dispatch.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_inbound_message.py",
    "area": "channels",
    "ext": ".py",
    "lines": 87,
    "size_bytes": 2563,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_inbound_message.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_inbound_runtime.py",
    "area": "channels",
    "ext": ".py",
    "lines": 128,
    "size_bytes": 3981,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_inbound_runtime.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_interactions.py",
    "area": "channels",
    "ext": ".py",
    "lines": 177,
    "size_bytes": 6056,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_interactions.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_offset_runtime.py",
    "area": "channels",
    "ext": ".py",
    "lines": 65,
    "size_bytes": 2439,
    "imports": [
      "clawlite/channels/telegram_offset_store.py"
    ],
    "imported_by_count": 1,
    "tests_for": [
      "tests/channels/test_telegram.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_offset_store.py",
    "area": "channels",
    "ext": ".py",
    "lines": 400,
    "size_bytes": 15012,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/session/test_store.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_outbound.py",
    "area": "channels",
    "ext": ".py",
    "lines": 310,
    "size_bytes": 12240,
    "imports": [
      "clawlite/channels/telegram_delivery.py"
    ],
    "imported_by_count": 1,
    "tests_for": [
      "tests/channels/test_telegram.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_pairing.py",
    "area": "channels",
    "ext": ".py",
    "lines": 331,
    "size_bytes": 12719,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/channels/test_telegram.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_status.py",
    "area": "channels",
    "ext": ".py",
    "lines": 102,
    "size_bytes": 3808,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_status.py"
    ]
  },
  {
    "path": "clawlite/channels/telegram_transport.py",
    "area": "channels",
    "ext": ".py",
    "lines": 117,
    "size_bytes": 3650,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram.py",
      "tests/channels/test_telegram_transport.py"
    ]
  },
  {
    "path": "clawlite/channels/whatsapp.py",
    "area": "channels",
    "ext": ".py",
    "lines": 401,
    "size_bytes": 14633,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/channels/test_whatsapp.py"
    ]
  },
  {
    "path": "clawlite/cli/__init__.py",
    "area": "cli",
    "ext": ".py",
    "lines": 5,
    "size_bytes": 95,
    "imports": [
      "clawlite/cli/commands.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/cli/__main__.py",
    "area": "cli",
    "ext": ".py",
    "lines": 7,
    "size_bytes": 124,
    "imports": [
      "clawlite/cli/__init__.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "clawlite/cli/commands.py",
    "area": "cli",
    "ext": ".py",
    "lines": 2689,
    "size_bytes": 113757,
    "imports": [
      "clawlite/__init__.py",
      "clawlite/cli/onboarding.py",
      "clawlite/cli/ops.py",
      "clawlite/config/loader.py",
      "clawlite/core/skills.py",
      "clawlite/gateway/server.py",
      "clawlite/jobs/journal.py",
      "clawlite/scheduler/cron.py",
      "clawlite/tools/registry.py",
      "clawlite/utils/logger.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/cli/test_commands.py"
    ]
  },
  {
    "path": "clawlite/cli/onboarding.py",
    "area": "cli",
    "ext": ".py",
    "lines": 1812,
    "size_bytes": 70861,
    "imports": [
      "clawlite/config/loader.py",
      "clawlite/config/schema.py",
      "clawlite/providers/catalog.py",
      "clawlite/providers/codex.py",
      "clawlite/providers/codex_auth.py",
      "clawlite/providers/discovery.py",
      "clawlite/providers/hints.py",
      "clawlite/providers/model_probe.py",
      "clawlite/providers/registry.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/cli/test_onboarding.py"
    ]
  },
  {
    "path": "clawlite/cli/ops.py",
    "area": "cli",
    "ext": ".py",
    "lines": 3283,
    "size_bytes": 121941,
    "imports": [
      "clawlite/channels/telegram_pairing.py",
      "clawlite/config/loader.py",
      "clawlite/config/schema.py",
      "clawlite/core/memory.py",
      "clawlite/core/memory_monitor.py",
      "clawlite/providers/catalog.py",
      "clawlite/providers/codex.py",
      "clawlite/providers/codex_auth.py",
      "clawlite/providers/discovery.py",
      "clawlite/providers/gemini_auth.py",
      "clawlite/providers/hints.py",
      "clawlite/providers/model_probe.py",
      "clawlite/providers/qwen_auth.py",
      "clawlite/providers/registry.py",
      "clawlite/providers/reliability.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 4,
    "tests_for": []
  },
  {
    "path": "clawlite/config/__init__.py",
    "area": "config",
    "ext": ".py",
    "lines": 13,
    "size_bytes": 325,
    "imports": [
      "clawlite/config/loader.py",
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/config/audit.py",
    "area": "config",
    "ext": ".py",
    "lines": 61,
    "size_bytes": 1963,
    "imports": [
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "clawlite/config/health.py",
    "area": "config",
    "ext": ".py",
    "lines": 67,
    "size_bytes": 2135,
    "imports": [
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/config/test_health.py",
      "tests/tools/test_health_check.py"
    ]
  },
  {
    "path": "clawlite/config/loader.py",
    "area": "config",
    "ext": ".py",
    "lines": 311,
    "size_bytes": 11796,
    "imports": [
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 14,
    "tests_for": [
      "tests/config/test_loader.py",
      "tests/workspace/test_workspace_loader.py"
    ]
  },
  {
    "path": "clawlite/config/schema.py",
    "area": "config",
    "ext": ".py",
    "lines": 1863,
    "size_bytes": 69941,
    "imports": [],
    "imported_by_count": 26,
    "tests_for": [
      "tests/config/test_schema.py"
    ]
  },
  {
    "path": "clawlite/config/watcher.py",
    "area": "config",
    "ext": ".py",
    "lines": 94,
    "size_bytes": 3170,
    "imports": [
      "clawlite/bus/__init__.py",
      "clawlite/bus/events.py",
      "clawlite/config/loader.py",
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 1,
    "tests_for": [
      "tests/config/test_watcher.py"
    ]
  },
  {
    "path": "clawlite/core/__init__.py",
    "area": "core",
    "ext": ".py",
    "lines": 2,
    "size_bytes": 86,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/core/context_window.py",
    "area": "core",
    "ext": ".py",
    "lines": 77,
    "size_bytes": 3063,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_context_window.py"
    ]
  },
  {
    "path": "clawlite/core/engine.py",
    "area": "core",
    "ext": ".py",
    "lines": 3776,
    "size_bytes": 163121,
    "imports": [
      "clawlite/bus/__init__.py",
      "clawlite/core/context_window.py",
      "clawlite/core/injection_guard.py",
      "clawlite/core/memory.py",
      "clawlite/core/prompt.py",
      "clawlite/core/skills.py",
      "clawlite/core/subagent.py",
      "clawlite/core/subagent_synthesizer.py",
      "clawlite/runtime/telemetry.py",
      "clawlite/session/store.py",
      "clawlite/utils/logging.py",
      "clawlite/workspace/identity_enforcer.py"
    ],
    "imported_by_count": 9,
    "tests_for": [
      "tests/core/test_engine.py",
      "tests/gateway/test_engine_diagnostics.py"
    ]
  },
  {
    "path": "clawlite/core/huginn_muninn.py",
    "area": "core",
    "ext": ".py",
    "lines": 408,
    "size_bytes": 17107,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_huginn_muninn.py"
    ]
  },
  {
    "path": "clawlite/core/injection_guard.py",
    "area": "core",
    "ext": ".py",
    "lines": 380,
    "size_bytes": 17198,
    "imports": [
      "clawlite/core/runestone.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/core/test_injection_guard.py"
    ]
  },
  {
    "path": "clawlite/core/memory.py",
    "area": "core",
    "ext": ".py",
    "lines": 4448,
    "size_bytes": 183233,
    "imports": [
      "clawlite/core/memory_add.py",
      "clawlite/core/memory_api.py",
      "clawlite/core/memory_artifacts.py",
      "clawlite/core/memory_backend.py",
      "clawlite/core/memory_classification.py",
      "clawlite/core/memory_curation.py",
      "clawlite/core/memory_history.py",
      "clawlite/core/memory_ingest.py",
      "clawlite/core/memory_layers.py",
      "clawlite/core/memory_maintenance.py",
      "clawlite/core/memory_policy.py",
      "clawlite/core/memory_privacy.py",
      "clawlite/core/memory_profile.py",
      "clawlite/core/memory_prune.py",
      "clawlite/core/memory_quality.py",
      "clawlite/core/memory_reporting.py",
      "clawlite/core/memory_resources.py",
      "clawlite/core/memory_retrieval.py",
      "clawlite/core/memory_search.py",
      "clawlite/core/memory_versions.py",
      "clawlite/core/memory_workflows.py",
      "clawlite/core/memory_working_set.py"
    ],
    "imported_by_count": 14,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_api.py",
      "tests/core/test_memory_artifacts.py",
      "tests/core/test_memory_backend.py",
      "tests/core/test_memory_classification.py",
      "tests/core/test_memory_consolidator.py",
      "tests/core/test_memory_curation.py",
      "tests/core/test_memory_history.py",
      "tests/core/test_memory_ingest.py",
      "tests/core/test_memory_ingest_helpers.py",
      "tests/core/test_memory_layers.py",
      "tests/core/test_memory_maintenance.py",
      "tests/core/test_memory_monitor.py",
      "tests/core/test_memory_policy.py",
      "tests/core/test_memory_privacy.py",
      "tests/core/test_memory_proactive.py",
      "tests/core/test_memory_profile.py",
      "tests/core/test_memory_prune.py",
      "tests/core/test_memory_quality.py",
      "tests/core/test_memory_reporting.py",
      "tests/core/test_memory_resources.py",
      "tests/core/test_memory_resources_helpers.py",
      "tests/core/test_memory_retrieval.py",
      "tests/core/test_memory_search.py",
      "tests/core/test_memory_ttl.py",
      "tests/core/test_memory_versions.py",
      "tests/core/test_memory_workflows.py",
      "tests/core/test_memory_working_set.py",
      "tests/gateway/test_memory_dashboard.py",
      "tests/tools/test_memory_tools.py"
    ]
  },
  {
    "path": "clawlite/core/memory_add.py",
    "area": "core",
    "ext": ".py",
    "lines": 133,
    "size_bytes": 4770,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/core/test_memory.py"
    ]
  },
  {
    "path": "clawlite/core/memory_api.py",
    "area": "core",
    "ext": ".py",
    "lines": 253,
    "size_bytes": 8511,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_api.py"
    ]
  },
  {
    "path": "clawlite/core/memory_artifacts.py",
    "area": "core",
    "ext": ".py",
    "lines": 137,
    "size_bytes": 4915,
    "imports": [
      "clawlite/core/memory_layers.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_artifacts.py"
    ]
  },
  {
    "path": "clawlite/core/memory_backend.py",
    "area": "core",
    "ext": ".py",
    "lines": 1399,
    "size_bytes": 52997,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_backend.py"
    ]
  },
  {
    "path": "clawlite/core/memory_classification.py",
    "area": "core",
    "ext": ".py",
    "lines": 315,
    "size_bytes": 11317,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_classification.py"
    ]
  },
  {
    "path": "clawlite/core/memory_consolidator.py",
    "area": "core",
    "ext": ".py",
    "lines": 60,
    "size_bytes": 2114,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_consolidator.py"
    ]
  },
  {
    "path": "clawlite/core/memory_curation.py",
    "area": "core",
    "ext": ".py",
    "lines": 362,
    "size_bytes": 13766,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_curation.py"
    ]
  },
  {
    "path": "clawlite/core/memory_history.py",
    "area": "core",
    "ext": ".py",
    "lines": 232,
    "size_bytes": 7622,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_history.py"
    ]
  },
  {
    "path": "clawlite/core/memory_ingest.py",
    "area": "core",
    "ext": ".py",
    "lines": 181,
    "size_bytes": 5996,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_ingest.py",
      "tests/core/test_memory_ingest_helpers.py"
    ]
  },
  {
    "path": "clawlite/core/memory_layers.py",
    "area": "core",
    "ext": ".py",
    "lines": 154,
    "size_bytes": 4511,
    "imports": [
      "clawlite/core/memory_yggdrasil.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_layers.py"
    ]
  },
  {
    "path": "clawlite/core/memory_maintenance.py",
    "area": "core",
    "ext": ".py",
    "lines": 176,
    "size_bytes": 5516,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_maintenance.py"
    ]
  },
  {
    "path": "clawlite/core/memory_monitor.py",
    "area": "core",
    "ext": ".py",
    "lines": 578,
    "size_bytes": 24931,
    "imports": [
      "clawlite/core/memory.py"
    ],
    "imported_by_count": 7,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_monitor.py"
    ]
  },
  {
    "path": "clawlite/core/memory_policy.py",
    "area": "core",
    "ext": ".py",
    "lines": 157,
    "size_bytes": 5474,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_policy.py"
    ]
  },
  {
    "path": "clawlite/core/memory_privacy.py",
    "area": "core",
    "ext": ".py",
    "lines": 299,
    "size_bytes": 10733,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_privacy.py"
    ]
  },
  {
    "path": "clawlite/core/memory_proactive.py",
    "area": "core",
    "ext": ".py",
    "lines": 95,
    "size_bytes": 3325,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_proactive.py"
    ]
  },
  {
    "path": "clawlite/core/memory_profile.py",
    "area": "core",
    "ext": ".py",
    "lines": 262,
    "size_bytes": 9834,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_profile.py"
    ]
  },
  {
    "path": "clawlite/core/memory_prune.py",
    "area": "core",
    "ext": ".py",
    "lines": 281,
    "size_bytes": 9692,
    "imports": [
      "clawlite/core/memory_layers.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_prune.py"
    ]
  },
  {
    "path": "clawlite/core/memory_quality.py",
    "area": "core",
    "ext": ".py",
    "lines": 354,
    "size_bytes": 15570,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_quality.py"
    ]
  },
  {
    "path": "clawlite/core/memory_reporting.py",
    "area": "core",
    "ext": ".py",
    "lines": 178,
    "size_bytes": 7986,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory.py",
      "tests/core/test_memory_reporting.py"
    ]
  },
  {
    "path": "clawlite/core/memory_resources.py",
    "area": "core",
    "ext": ".py",
    "lines": 146,
    "size_bytes": 4520,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory_resources.py",
      "tests/core/test_memory_resources_helpers.py"
    ]
  },
  {
    "path": "clawlite/core/memory_retrieval.py",
    "area": "core",
    "ext": ".py",
    "lines": 759,
    "size_bytes": 29131,
    "imports": [
      "clawlite/core/memory_yggdrasil.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory_retrieval.py"
    ]
  },
  {
    "path": "clawlite/core/memory_search.py",
    "area": "core",
    "ext": ".py",
    "lines": 235,
    "size_bytes": 9318,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory_search.py"
    ]
  },
  {
    "path": "clawlite/core/memory_versions.py",
    "area": "core",
    "ext": ".py",
    "lines": 381,
    "size_bytes": 14659,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory_versions.py"
    ]
  },
  {
    "path": "clawlite/core/memory_workflows.py",
    "area": "core",
    "ext": ".py",
    "lines": 279,
    "size_bytes": 9643,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory_workflows.py"
    ]
  },
  {
    "path": "clawlite/core/memory_working_set.py",
    "area": "core",
    "ext": ".py",
    "lines": 835,
    "size_bytes": 33968,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory_working_set.py"
    ]
  },
  {
    "path": "clawlite/core/memory_yggdrasil.py",
    "area": "core",
    "ext": ".py",
    "lines": 130,
    "size_bytes": 4612,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/core/norns.py",
    "area": "core",
    "ext": ".py",
    "lines": 217,
    "size_bytes": 8833,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_norns.py"
    ]
  },
  {
    "path": "clawlite/core/prompt.py",
    "area": "core",
    "ext": ".py",
    "lines": 506,
    "size_bytes": 20711,
    "imports": [
      "clawlite/core/injection_guard.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/core/test_prompt.py"
    ]
  },
  {
    "path": "clawlite/core/runestone.py",
    "area": "core",
    "ext": ".py",
    "lines": 301,
    "size_bytes": 10535,
    "imports": [],
    "imported_by_count": 5,
    "tests_for": [
      "tests/core/test_runestone.py"
    ]
  },
  {
    "path": "clawlite/core/skills.py",
    "area": "core",
    "ext": ".py",
    "lines": 1362,
    "size_bytes": 53033,
    "imports": [
      "clawlite/config/loader.py"
    ],
    "imported_by_count": 8,
    "tests_for": [
      "tests/core/test_skills.py",
      "tests/core/test_skills_new.py",
      "tests/skills/test_markdown_skills.py"
    ]
  },
  {
    "path": "clawlite/core/subagent.py",
    "area": "core",
    "ext": ".py",
    "lines": 964,
    "size_bytes": 39197,
    "imports": [],
    "imported_by_count": 11,
    "tests_for": [
      "tests/core/test_subagent.py",
      "tests/core/test_subagent_context.py",
      "tests/gateway/test_subagents_runtime.py"
    ]
  },
  {
    "path": "clawlite/core/subagent_synthesizer.py",
    "area": "core",
    "ext": ".py",
    "lines": 144,
    "size_bytes": 6298,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_subagent.py"
    ]
  },
  {
    "path": "clawlite/dashboard/__init__.py",
    "area": "dashboard",
    "ext": ".py",
    "lines": 1,
    "size_bytes": 35,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/dashboard/dashboard.css",
    "area": "dashboard",
    "ext": ".css",
    "lines": 653,
    "size_bytes": 11395,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/gateway/test_dashboard_runtime.py",
      "tests/gateway/test_dashboard_state.py",
      "tests/gateway/test_memory_dashboard.py"
    ]
  },
  {
    "path": "clawlite/dashboard/dashboard.js",
    "area": "dashboard",
    "ext": ".js",
    "lines": 2201,
    "size_bytes": 76907,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/gateway/test_dashboard_runtime.py",
      "tests/gateway/test_dashboard_state.py",
      "tests/gateway/test_memory_dashboard.py"
    ]
  },
  {
    "path": "clawlite/dashboard/index.html",
    "area": "dashboard",
    "ext": ".html",
    "lines": 463,
    "size_bytes": 25241,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "clawlite/gateway/__init__.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 0,
    "size_bytes": 0,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/gateway/autonomy_notice.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 220,
    "size_bytes": 6261,
    "imports": [
      "clawlite/core/memory_monitor.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/runtime/test_autonomy.py"
    ]
  },
  {
    "path": "clawlite/gateway/background_runners.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 95,
    "size_bytes": 3993,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_background_runners.py"
    ]
  },
  {
    "path": "clawlite/gateway/control_handlers.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 227,
    "size_bytes": 11020,
    "imports": [
      "clawlite/core/memory_monitor.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/gateway/control_plane.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 97,
    "size_bytes": 3035,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_control_plane.py"
    ]
  },
  {
    "path": "clawlite/gateway/dashboard_runtime.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 124,
    "size_bytes": 5878,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_dashboard_runtime.py"
    ]
  },
  {
    "path": "clawlite/gateway/dashboard_state.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 167,
    "size_bytes": 6140,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_dashboard_state.py"
    ]
  },
  {
    "path": "clawlite/gateway/diagnostics_payload.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 146,
    "size_bytes": 6267,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_diagnostics_payload.py"
    ]
  },
  {
    "path": "clawlite/gateway/discord_thread_binding.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 305,
    "size_bytes": 11925,
    "imports": [
      "clawlite/bus/events.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_discord.py",
      "tests/gateway/test_discord_thread_binding.py"
    ]
  },
  {
    "path": "clawlite/gateway/engine_diagnostics.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 257,
    "size_bytes": 8543,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_engine.py",
      "tests/gateway/test_engine_diagnostics.py"
    ]
  },
  {
    "path": "clawlite/gateway/lifecycle_runtime.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 320,
    "size_bytes": 15369,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_lifecycle_runtime.py"
    ]
  },
  {
    "path": "clawlite/gateway/memory_dashboard.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 58,
    "size_bytes": 1895,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_memory_dashboard.py"
    ]
  },
  {
    "path": "clawlite/gateway/payloads.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 245,
    "size_bytes": 9964,
    "imports": [
      "clawlite/providers/hints.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_payloads.py"
    ]
  },
  {
    "path": "clawlite/gateway/request_handlers.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 284,
    "size_bytes": 11667,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_request_handlers.py"
    ]
  },
  {
    "path": "clawlite/gateway/runtime_builder.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 634,
    "size_bytes": 27649,
    "imports": [
      "clawlite/bus/journal.py",
      "clawlite/bus/queue.py",
      "clawlite/bus/redis_queue.py",
      "clawlite/channels/manager.py",
      "clawlite/config/schema.py",
      "clawlite/core/engine.py",
      "clawlite/core/memory.py",
      "clawlite/core/memory_backend.py",
      "clawlite/core/memory_monitor.py",
      "clawlite/core/prompt.py",
      "clawlite/core/skills.py",
      "clawlite/gateway/autonomy_notice.py",
      "clawlite/gateway/discord_thread_binding.py",
      "clawlite/gateway/self_evolution_approval.py",
      "clawlite/gateway/tool_approval.py",
      "clawlite/jobs/journal.py",
      "clawlite/jobs/queue.py",
      "clawlite/providers/__init__.py",
      "clawlite/providers/discovery.py",
      "clawlite/runtime/__init__.py",
      "clawlite/runtime/self_evolution.py",
      "clawlite/runtime/telemetry.py",
      "clawlite/scheduler/cron.py",
      "clawlite/scheduler/heartbeat.py",
      "clawlite/session/store.py",
      "clawlite/tools/agents.py",
      "clawlite/tools/apply_patch.py",
      "clawlite/tools/browser.py",
      "clawlite/tools/cron.py",
      "clawlite/tools/discord_admin.py",
      "clawlite/tools/exec.py",
      "clawlite/tools/files.py",
      "clawlite/tools/jobs.py",
      "clawlite/tools/mcp.py",
      "clawlite/tools/memory.py",
      "clawlite/tools/message.py",
      "clawlite/tools/pdf.py",
      "clawlite/tools/process.py",
      "clawlite/tools/registry.py",
      "clawlite/tools/sessions.py",
      "clawlite/tools/skill.py",
      "clawlite/tools/spawn.py",
      "clawlite/tools/tts.py",
      "clawlite/tools/web.py",
      "clawlite/utils/logging.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/gateway/runtime_state.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 142,
    "size_bytes": 3824,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_runtime_state.py"
    ]
  },
  {
    "path": "clawlite/gateway/self_evolution_approval.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 177,
    "size_bytes": 6277,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_self_evolution_approval.py",
      "tests/runtime/test_self_evolution.py"
    ]
  },
  {
    "path": "clawlite/gateway/server.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 3610,
    "size_bytes": 160889,
    "imports": [
      "clawlite/bus/queue.py",
      "clawlite/channels/base.py",
      "clawlite/cli/onboarding.py",
      "clawlite/cli/ops.py",
      "clawlite/config/loader.py",
      "clawlite/config/schema.py",
      "clawlite/core/engine.py",
      "clawlite/core/huginn_muninn.py",
      "clawlite/core/memory_monitor.py",
      "clawlite/core/norns.py",
      "clawlite/core/runestone.py",
      "clawlite/gateway/autonomy_notice.py",
      "clawlite/gateway/background_runners.py",
      "clawlite/gateway/control_handlers.py",
      "clawlite/gateway/control_plane.py",
      "clawlite/gateway/dashboard_runtime.py",
      "clawlite/gateway/dashboard_state.py",
      "clawlite/gateway/diagnostics_payload.py",
      "clawlite/gateway/engine_diagnostics.py",
      "clawlite/gateway/lifecycle_runtime.py",
      "clawlite/gateway/memory_dashboard.py",
      "clawlite/gateway/payloads.py",
      "clawlite/gateway/request_handlers.py",
      "clawlite/gateway/runtime_builder.py",
      "clawlite/gateway/runtime_state.py",
      "clawlite/gateway/status_handlers.py",
      "clawlite/gateway/subagents_runtime.py",
      "clawlite/gateway/supervisor_recovery.py",
      "clawlite/gateway/supervisor_runtime.py",
      "clawlite/gateway/tool_catalog.py",
      "clawlite/gateway/tuning_decisions.py",
      "clawlite/gateway/tuning_loop.py",
      "clawlite/gateway/tuning_policy.py",
      "clawlite/gateway/tuning_runtime.py",
      "clawlite/gateway/webhooks.py",
      "clawlite/gateway/websocket_handlers.py",
      "clawlite/providers/__init__.py",
      "clawlite/providers/catalog.py",
      "clawlite/providers/reliability.py",
      "clawlite/runtime/__init__.py",
      "clawlite/runtime/gjallarhorn.py",
      "clawlite/runtime/valkyrie.py",
      "clawlite/runtime/volva.py",
      "clawlite/scheduler/heartbeat.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_server.py"
    ]
  },
  {
    "path": "clawlite/gateway/status_handlers.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 91,
    "size_bytes": 3452,
    "imports": [
      "clawlite/config/health.py",
      "clawlite/providers/telemetry.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_status_handlers.py"
    ]
  },
  {
    "path": "clawlite/gateway/subagents_runtime.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 155,
    "size_bytes": 5495,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_subagent.py",
      "tests/gateway/test_subagents_runtime.py"
    ]
  },
  {
    "path": "clawlite/gateway/supervisor_recovery.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 92,
    "size_bytes": 2818,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_supervisor_recovery.py",
      "tests/runtime/test_supervisor.py"
    ]
  },
  {
    "path": "clawlite/gateway/supervisor_runtime.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 152,
    "size_bytes": 7115,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_supervisor_runtime.py",
      "tests/runtime/test_supervisor.py"
    ]
  },
  {
    "path": "clawlite/gateway/tool_approval.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 253,
    "size_bytes": 9277,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/gateway/test_tool_approval.py"
    ]
  },
  {
    "path": "clawlite/gateway/tool_catalog.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 137,
    "size_bytes": 3924,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/providers/test_catalog.py"
    ]
  },
  {
    "path": "clawlite/gateway/tuning_decisions.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 115,
    "size_bytes": 3636,
    "imports": [
      "clawlite/gateway/tuning_policy.py",
      "clawlite/gateway/tuning_runtime.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_tuning_decisions.py"
    ]
  },
  {
    "path": "clawlite/gateway/tuning_loop.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 285,
    "size_bytes": 12906,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/gateway/tuning_policy.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 194,
    "size_bytes": 7442,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/gateway/test_tuning_policy.py"
    ]
  },
  {
    "path": "clawlite/gateway/tuning_runtime.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 108,
    "size_bytes": 3489,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/gateway/test_tuning_runtime.py"
    ]
  },
  {
    "path": "clawlite/gateway/webhooks.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 105,
    "size_bytes": 4598,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/tools/test_web.py"
    ]
  },
  {
    "path": "clawlite/gateway/websocket_handlers.py",
    "area": "gateway",
    "ext": ".py",
    "lines": 495,
    "size_bytes": 21033,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_websocket_handlers.py",
      "tests/tools/test_web.py"
    ]
  },
  {
    "path": "clawlite/jobs/__init__.py",
    "area": "jobs",
    "ext": ".py",
    "lines": 0,
    "size_bytes": 0,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/jobs/journal.py",
    "area": "jobs",
    "ext": ".py",
    "lines": 124,
    "size_bytes": 4640,
    "imports": [
      "clawlite/jobs/queue.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/bus/test_journal.py",
      "tests/jobs/test_journal.py"
    ]
  },
  {
    "path": "clawlite/jobs/queue.py",
    "area": "jobs",
    "ext": ".py",
    "lines": 295,
    "size_bytes": 10107,
    "imports": [],
    "imported_by_count": 8,
    "tests_for": [
      "tests/bus/test_queue.py",
      "tests/bus/test_redis_queue.py",
      "tests/jobs/test_queue.py"
    ]
  },
  {
    "path": "clawlite/providers/__init__.py",
    "area": "providers",
    "ext": ".py",
    "lines": 6,
    "size_bytes": 276,
    "imports": [
      "clawlite/providers/base.py",
      "clawlite/providers/registry.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/providers/base.py",
    "area": "providers",
    "ext": ".py",
    "lines": 42,
    "size_bytes": 980,
    "imports": [],
    "imported_by_count": 8,
    "tests_for": []
  },
  {
    "path": "clawlite/providers/catalog.py",
    "area": "providers",
    "ext": ".py",
    "lines": 207,
    "size_bytes": 9123,
    "imports": [],
    "imported_by_count": 5,
    "tests_for": [
      "tests/providers/test_catalog.py"
    ]
  },
  {
    "path": "clawlite/providers/codex.py",
    "area": "providers",
    "ext": ".py",
    "lines": 627,
    "size_bytes": 27112,
    "imports": [
      "clawlite/providers/base.py",
      "clawlite/providers/reliability.py"
    ],
    "imported_by_count": 5,
    "tests_for": [
      "tests/providers/test_codex_retry.py"
    ]
  },
  {
    "path": "clawlite/providers/codex_auth.py",
    "area": "providers",
    "ext": ".py",
    "lines": 121,
    "size_bytes": 3697,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": []
  },
  {
    "path": "clawlite/providers/custom.py",
    "area": "providers",
    "ext": ".py",
    "lines": 7,
    "size_bytes": 193,
    "imports": [
      "clawlite/providers/litellm.py"
    ],
    "imported_by_count": 1,
    "tests_for": []
  },
  {
    "path": "clawlite/providers/discovery.py",
    "area": "providers",
    "ext": ".py",
    "lines": 180,
    "size_bytes": 6785,
    "imports": [],
    "imported_by_count": 5,
    "tests_for": [
      "tests/providers/test_discovery.py"
    ]
  },
  {
    "path": "clawlite/providers/failover.py",
    "area": "providers",
    "ext": ".py",
    "lines": 333,
    "size_bytes": 14140,
    "imports": [
      "clawlite/providers/base.py",
      "clawlite/providers/reliability.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/providers/test_failover.py"
    ]
  },
  {
    "path": "clawlite/providers/gemini_auth.py",
    "area": "providers",
    "ext": ".py",
    "lines": 239,
    "size_bytes": 8245,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/providers/hints.py",
    "area": "providers",
    "ext": ".py",
    "lines": 303,
    "size_bytes": 15990,
    "imports": [
      "clawlite/providers/catalog.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/providers/test_hints.py"
    ]
  },
  {
    "path": "clawlite/providers/litellm.py",
    "area": "providers",
    "ext": ".py",
    "lines": 812,
    "size_bytes": 38268,
    "imports": [
      "clawlite/core/engine.py",
      "clawlite/providers/base.py",
      "clawlite/providers/reliability.py",
      "clawlite/providers/telemetry.py"
    ],
    "imported_by_count": 6,
    "tests_for": [
      "tests/providers/test_litellm_anthropic.py",
      "tests/providers/test_litellm_retry.py"
    ]
  },
  {
    "path": "clawlite/providers/model_probe.py",
    "area": "providers",
    "ext": ".py",
    "lines": 135,
    "size_bytes": 4833,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/providers/test_model_probe.py"
    ]
  },
  {
    "path": "clawlite/providers/qwen_auth.py",
    "area": "providers",
    "ext": ".py",
    "lines": 191,
    "size_bytes": 6794,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/providers/registry.py",
    "area": "providers",
    "ext": ".py",
    "lines": 934,
    "size_bytes": 34235,
    "imports": [
      "clawlite/providers/base.py",
      "clawlite/providers/codex.py",
      "clawlite/providers/codex_auth.py",
      "clawlite/providers/custom.py",
      "clawlite/providers/discovery.py",
      "clawlite/providers/failover.py",
      "clawlite/providers/gemini_auth.py",
      "clawlite/providers/litellm.py",
      "clawlite/providers/qwen_auth.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/providers/test_registry_auth_resolution.py",
      "tests/tools/test_registry.py"
    ]
  },
  {
    "path": "clawlite/providers/reliability.py",
    "area": "providers",
    "ext": ".py",
    "lines": 128,
    "size_bytes": 3985,
    "imports": [],
    "imported_by_count": 7,
    "tests_for": [
      "tests/providers/test_reliability.py"
    ]
  },
  {
    "path": "clawlite/providers/telemetry.py",
    "area": "providers",
    "ext": ".py",
    "lines": 117,
    "size_bytes": 3164,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/providers/test_telemetry.py",
      "tests/runtime/test_runtime_telemetry.py"
    ]
  },
  {
    "path": "clawlite/providers/transcription.py",
    "area": "providers",
    "ext": ".py",
    "lines": 98,
    "size_bytes": 4277,
    "imports": [
      "clawlite/providers/reliability.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/providers/test_transcription.py"
    ]
  },
  {
    "path": "clawlite/runtime/__init__.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 14,
    "size_bytes": 513,
    "imports": [
      "clawlite/runtime/autonomy.py",
      "clawlite/runtime/autonomy_actions.py",
      "clawlite/runtime/autonomy_log.py",
      "clawlite/runtime/supervisor.py"
    ],
    "imported_by_count": 4,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/runtime/autonomy.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 865,
    "size_bytes": 35992,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/runtime/test_autonomy.py",
      "tests/runtime/test_autonomy_actions.py",
      "tests/runtime/test_autonomy_log.py",
      "tests/runtime/test_autonomy_wake.py"
    ]
  },
  {
    "path": "clawlite/runtime/autonomy_actions.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 1048,
    "size_bytes": 44830,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/runtime/test_autonomy.py",
      "tests/runtime/test_autonomy_actions.py"
    ]
  },
  {
    "path": "clawlite/runtime/autonomy_log.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 142,
    "size_bytes": 4941,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/runtime/test_autonomy.py",
      "tests/runtime/test_autonomy_log.py"
    ]
  },
  {
    "path": "clawlite/runtime/gjallarhorn.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 262,
    "size_bytes": 11707,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/runtime/test_gjallarhorn.py"
    ]
  },
  {
    "path": "clawlite/runtime/self_evolution.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 1282,
    "size_bytes": 51749,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_self_evolution_approval.py",
      "tests/runtime/test_self_evolution.py"
    ]
  },
  {
    "path": "clawlite/runtime/supervisor.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 464,
    "size_bytes": 19706,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/gateway/test_supervisor_recovery.py",
      "tests/gateway/test_supervisor_runtime.py",
      "tests/runtime/test_supervisor.py",
      "tests/runtime/test_supervisor_phase5.py"
    ]
  },
  {
    "path": "clawlite/runtime/telemetry.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 130,
    "size_bytes": 3902,
    "imports": [],
    "imported_by_count": 6,
    "tests_for": [
      "tests/providers/test_telemetry.py",
      "tests/runtime/test_runtime_telemetry.py"
    ]
  },
  {
    "path": "clawlite/runtime/valkyrie.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 313,
    "size_bytes": 12055,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/runtime/test_valkyrie.py"
    ]
  },
  {
    "path": "clawlite/runtime/volva.py",
    "area": "runtime",
    "ext": ".py",
    "lines": 335,
    "size_bytes": 13900,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/runtime/test_volva.py"
    ]
  },
  {
    "path": "clawlite/scheduler/__init__.py",
    "area": "scheduler",
    "ext": ".py",
    "lines": 7,
    "size_bytes": 343,
    "imports": [
      "clawlite/scheduler/cron.py",
      "clawlite/scheduler/heartbeat.py",
      "clawlite/scheduler/types.py"
    ],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/scheduler/cron.py",
    "area": "scheduler",
    "ext": ".py",
    "lines": 1144,
    "size_bytes": 49759,
    "imports": [
      "clawlite/scheduler/types.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 5,
    "tests_for": [
      "tests/scheduler/test_cron.py",
      "tests/tools/test_cron_message_spawn_mcp.py"
    ]
  },
  {
    "path": "clawlite/scheduler/heartbeat.py",
    "area": "scheduler",
    "ext": ".py",
    "lines": 425,
    "size_bytes": 18368,
    "imports": [
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 5,
    "tests_for": [
      "tests/scheduler/test_heartbeat.py"
    ]
  },
  {
    "path": "clawlite/scheduler/types.py",
    "area": "scheduler",
    "ext": ".py",
    "lines": 46,
    "size_bytes": 1008,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/session/__init__.py",
    "area": "session",
    "ext": ".py",
    "lines": 5,
    "size_bytes": 96,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/session/store.py",
    "area": "session",
    "ext": ".py",
    "lines": 514,
    "size_bytes": 20303,
    "imports": [],
    "imported_by_count": 7,
    "tests_for": [
      "tests/session/test_store.py"
    ]
  },
  {
    "path": "clawlite/skills/__init__.py",
    "area": "skills",
    "ext": ".py",
    "lines": 3,
    "size_bytes": 60,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/core/test_skills.py",
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/skills/model-usage/scripts/model_usage.py",
    "area": "skills",
    "ext": ".py",
    "lines": 319,
    "size_bytes": 10776,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/core/test_skills.py",
      "tests/skills/test_model_usage_script.py"
    ]
  },
  {
    "path": "clawlite/skills/skill_creator.py",
    "area": "skills",
    "ext": ".py",
    "lines": 185,
    "size_bytes": 5952,
    "imports": [],
    "imported_by_count": 1,
    "tests_for": [
      "tests/core/test_skills.py",
      "tests/skills/test_skill_creator.py"
    ]
  },
  {
    "path": "clawlite/skills/tmux/scripts/find-sessions.sh",
    "area": "skills",
    "ext": ".sh",
    "lines": 94,
    "size_bytes": 1742,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/core/test_skills.py"
    ]
  },
  {
    "path": "clawlite/skills/tmux/scripts/wait-for-text.sh",
    "area": "skills",
    "ext": ".sh",
    "lines": 146,
    "size_bytes": 3029,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/core/test_skills.py"
    ]
  },
  {
    "path": "clawlite/tools/__init__.py",
    "area": "tools",
    "ext": ".py",
    "lines": 17,
    "size_bytes": 462,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/memory.py",
      "clawlite/tools/registry.py",
      "clawlite/tools/skill.py"
    ],
    "imported_by_count": 1,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/agents.py",
    "area": "tools",
    "ext": ".py",
    "lines": 218,
    "size_bytes": 9233,
    "imports": [
      "clawlite/core/subagent.py",
      "clawlite/tools/base.py",
      "clawlite/tools/sessions.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/gateway/test_subagents_runtime.py",
      "tests/tools/test_agents_tool.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/apply_patch.py",
    "area": "tools",
    "ext": ".py",
    "lines": 309,
    "size_bytes": 11546,
    "imports": [
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/tools/test_apply_patch.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/base.py",
    "area": "tools",
    "ext": ".py",
    "lines": 78,
    "size_bytes": 2032,
    "imports": [],
    "imported_by_count": 40,
    "tests_for": [
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/browser.py",
    "area": "tools",
    "ext": ".py",
    "lines": 210,
    "size_bytes": 8983,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/web.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/tools/test_browser_tool.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/cron.py",
    "area": "tools",
    "ext": ".py",
    "lines": 179,
    "size_bytes": 7632,
    "imports": [
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/scheduler/test_cron.py",
      "tests/tools/test_cron_message_spawn_mcp.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/discord_admin.py",
    "area": "tools",
    "ext": ".py",
    "lines": 493,
    "size_bytes": 19242,
    "imports": [
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_discord.py",
      "tests/tools/test_discord_admin_tool.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/exec.py",
    "area": "tools",
    "ext": ".py",
    "lines": 1029,
    "size_bytes": 42941,
    "imports": [
      "clawlite/core/runestone.py",
      "clawlite/tools/base.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 5,
    "tests_for": [
      "tests/tools/test_exec_files.py",
      "tests/tools/test_exec_network_guard.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/files.py",
    "area": "tools",
    "ext": ".py",
    "lines": 341,
    "size_bytes": 12411,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/tools/test_exec_files.py",
      "tests/tools/test_files_edge_cases.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/jobs.py",
    "area": "tools",
    "ext": ".py",
    "lines": 89,
    "size_bytes": 3924,
    "imports": [
      "clawlite/jobs/queue.py",
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/tools/test_jobs_tool.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/mcp.py",
    "area": "tools",
    "ext": ".py",
    "lines": 291,
    "size_bytes": 12585,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/tools/base.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/tools/test_cron_message_spawn_mcp.py",
      "tests/tools/test_mcp.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/memory.py",
    "area": "tools",
    "ext": ".py",
    "lines": 804,
    "size_bytes": 32439,
    "imports": [
      "clawlite/core/memory.py",
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/core/test_memory_api.py",
      "tests/core/test_memory_artifacts.py",
      "tests/core/test_memory_backend.py",
      "tests/core/test_memory_classification.py",
      "tests/core/test_memory_consolidator.py",
      "tests/core/test_memory_curation.py",
      "tests/core/test_memory_history.py",
      "tests/core/test_memory_ingest.py",
      "tests/core/test_memory_ingest_helpers.py",
      "tests/core/test_memory_layers.py",
      "tests/core/test_memory_maintenance.py",
      "tests/core/test_memory_monitor.py",
      "tests/core/test_memory_policy.py",
      "tests/core/test_memory_privacy.py",
      "tests/core/test_memory_proactive.py",
      "tests/core/test_memory_profile.py",
      "tests/core/test_memory_prune.py",
      "tests/core/test_memory_quality.py",
      "tests/core/test_memory_reporting.py",
      "tests/core/test_memory_resources.py",
      "tests/core/test_memory_resources_helpers.py",
      "tests/core/test_memory_retrieval.py",
      "tests/core/test_memory_search.py",
      "tests/core/test_memory_ttl.py",
      "tests/core/test_memory_versions.py",
      "tests/core/test_memory_workflows.py",
      "tests/core/test_memory_working_set.py",
      "tests/gateway/test_memory_dashboard.py",
      "tests/tools/test_memory_tools.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/message.py",
    "area": "tools",
    "ext": ".py",
    "lines": 250,
    "size_bytes": 10755,
    "imports": [
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/channels/test_telegram_inbound_message.py",
      "tests/tools/test_cron_message_spawn_mcp.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/pdf.py",
    "area": "tools",
    "ext": ".py",
    "lines": 92,
    "size_bytes": 3960,
    "imports": [
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/process.py",
    "area": "tools",
    "ext": ".py",
    "lines": 378,
    "size_bytes": 14517,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/exec.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/tools/test_process_tool.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/registry.py",
    "area": "tools",
    "ext": ".py",
    "lines": 1280,
    "size_bytes": 54008,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/runtime/telemetry.py",
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 9,
    "tests_for": [
      "tests/providers/test_registry_auth_resolution.py",
      "tests/tools/test_registry.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/sessions.py",
    "area": "tools",
    "ext": ".py",
    "lines": 1190,
    "size_bytes": 44703,
    "imports": [
      "clawlite/core/subagent.py",
      "clawlite/session/store.py",
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/tools/test_sessions_tools.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/skill.py",
    "area": "tools",
    "ext": ".py",
    "lines": 1047,
    "size_bytes": 44520,
    "imports": [
      "clawlite/cli/ops.py",
      "clawlite/config/loader.py",
      "clawlite/core/skills.py",
      "clawlite/session/store.py",
      "clawlite/tools/base.py",
      "clawlite/tools/registry.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/core/test_skills.py",
      "tests/core/test_skills_new.py",
      "tests/skills/test_markdown_skills.py",
      "tests/skills/test_skill_creator.py",
      "tests/tools/test_skill_tool.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/spawn.py",
    "area": "tools",
    "ext": ".py",
    "lines": 84,
    "size_bytes": 2902,
    "imports": [
      "clawlite/core/subagent.py",
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/tools/test_cron_message_spawn_mcp.py",
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/tts.py",
    "area": "tools",
    "ext": ".py",
    "lines": 46,
    "size_bytes": 2132,
    "imports": [
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/tools/test_tools.py"
    ]
  },
  {
    "path": "clawlite/tools/web.py",
    "area": "tools",
    "ext": ".py",
    "lines": 552,
    "size_bytes": 21796,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 3,
    "tests_for": [
      "tests/gateway/test_websocket_handlers.py",
      "tests/tools/test_web.py"
    ]
  },
  {
    "path": "clawlite/utils/__init__.py",
    "area": "utils",
    "ext": ".py",
    "lines": 6,
    "size_bytes": 228,
    "imports": [
      "clawlite/utils/helpers.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/utils/helpers.py",
    "area": "utils",
    "ext": ".py",
    "lines": 28,
    "size_bytes": 725,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/core/test_memory_ingest_helpers.py",
      "tests/core/test_memory_resources_helpers.py",
      "tests/utils/test_helpers.py"
    ]
  },
  {
    "path": "clawlite/utils/logger.py",
    "area": "utils",
    "ext": ".py",
    "lines": 255,
    "size_bytes": 8884,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/utils/logging.py",
    "area": "utils",
    "ext": ".py",
    "lines": 137,
    "size_bytes": 4102,
    "imports": [
      "clawlite/utils/logger.py"
    ],
    "imported_by_count": 27,
    "tests_for": [
      "tests/utils/test_logging.py"
    ]
  },
  {
    "path": "clawlite/workspace/__init__.py",
    "area": "workspace",
    "ext": ".py",
    "lines": 6,
    "size_bytes": 221,
    "imports": [
      "clawlite/workspace/bootstrap.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "clawlite/workspace/bootstrap.py",
    "area": "workspace",
    "ext": ".py",
    "lines": 36,
    "size_bytes": 1110,
    "imports": [
      "clawlite/config/loader.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/workspace/identity_enforcer.py",
    "area": "workspace",
    "ext": ".py",
    "lines": 132,
    "size_bytes": 5523,
    "imports": [
      "clawlite/workspace/loader.py",
      "clawlite/workspace/user_profile.py"
    ],
    "imported_by_count": 2,
    "tests_for": []
  },
  {
    "path": "clawlite/workspace/loader.py",
    "area": "workspace",
    "ext": ".py",
    "lines": 606,
    "size_bytes": 23821,
    "imports": [
      "clawlite/workspace/user_profile.py"
    ],
    "imported_by_count": 12,
    "tests_for": [
      "tests/config/test_loader.py",
      "tests/workspace/test_workspace_loader.py"
    ]
  },
  {
    "path": "clawlite/workspace/user_profile.py",
    "area": "workspace",
    "ext": ".py",
    "lines": 152,
    "size_bytes": 5267,
    "imports": [],
    "imported_by_count": 3,
    "tests_for": [
      "tests/workspace/test_user_profile.py"
    ]
  },
  {
    "path": "conftest.py",
    "area": "root",
    "ext": ".py",
    "lines": 5,
    "size_bytes": 140,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/__init__.py",
    "area": "scripts",
    "ext": ".py",
    "lines": 0,
    "size_bytes": 0,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/jobs/__init__.py",
      "tests/skills/__init__.py"
    ]
  },
  {
    "path": "scripts/assemble_gif.py",
    "area": "scripts",
    "ext": ".py",
    "lines": 33,
    "size_bytes": 1004,
    "imports": [],
    "imported_by_count": 2,
    "tests_for": [
      "tests/scripts/test_assemble_gif.py"
    ]
  },
  {
    "path": "scripts/backup_clawlite.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 16,
    "size_bytes": 386,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/capture_frames.py",
    "area": "scripts",
    "ext": ".py",
    "lines": 33,
    "size_bytes": 1246,
    "imports": [
      "scripts/terminal_template.py"
    ],
    "imported_by_count": 2,
    "tests_for": [
      "tests/scripts/test_capture_frames.py"
    ]
  },
  {
    "path": "scripts/docker_setup.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 87,
    "size_bytes": 2526,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/generate_architecture_docs.py",
    "area": "scripts",
    "ext": ".py",
    "lines": 801,
    "size_bytes": 31737,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/install.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 336,
    "size_bytes": 10713,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/install_termux_proot.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 66,
    "size_bytes": 1880,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/make_demo_gif.py",
    "area": "scripts",
    "ext": ".py",
    "lines": 86,
    "size_bytes": 3267,
    "imports": [
      "scripts/assemble_gif.py",
      "scripts/capture_frames.py",
      "scripts/terminal_template.py"
    ],
    "imported_by_count": 1,
    "tests_for": [
      "tests/scripts/test_make_demo_gif.py"
    ]
  },
  {
    "path": "scripts/release_preflight.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 69,
    "size_bytes": 1258,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/restore_clawlite.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 14,
    "size_bytes": 297,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": [
      "tests/session/test_store.py"
    ]
  },
  {
    "path": "scripts/smoke_test.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 86,
    "size_bytes": 3152,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "scripts/terminal_template.py",
    "area": "scripts",
    "ext": ".py",
    "lines": 127,
    "size_bytes": 4574,
    "imports": [],
    "imported_by_count": 4,
    "tests_for": [
      "tests/scripts/test_terminal_template.py"
    ]
  },
  {
    "path": "scripts/update_checkout.sh",
    "area": "scripts",
    "ext": ".sh",
    "lines": 43,
    "size_bytes": 1343,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/bus/test_journal.py",
    "area": "tests",
    "ext": ".py",
    "lines": 219,
    "size_bytes": 6715,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/bus/journal.py",
      "clawlite/bus/queue.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/bus/test_queue.py",
    "area": "tests",
    "ext": ".py",
    "lines": 357,
    "size_bytes": 12835,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/bus/queue.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/bus/test_redis_queue.py",
    "area": "tests",
    "ext": ".py",
    "lines": 66,
    "size_bytes": 2237,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/bus/redis_queue.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_discord.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1608,
    "size_bytes": 56097,
    "imports": [
      "clawlite/channels/discord.py",
      "clawlite/core/engine.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_email.py",
    "area": "tests",
    "ext": ".py",
    "lines": 228,
    "size_bytes": 7892,
    "imports": [
      "clawlite/channels/email.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_inbound_text.py",
    "area": "tests",
    "ext": ".py",
    "lines": 71,
    "size_bytes": 2227,
    "imports": [
      "clawlite/channels/inbound_text.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_irc.py",
    "area": "tests",
    "ext": ".py",
    "lines": 103,
    "size_bytes": 2923,
    "imports": [
      "clawlite/channels/irc.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_manager.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1639,
    "size_bytes": 55902,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/bus/queue.py",
      "clawlite/channels/base.py",
      "clawlite/channels/manager.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_outbound_adapters.py",
    "area": "tests",
    "ext": ".py",
    "lines": 180,
    "size_bytes": 6628,
    "imports": [
      "clawlite/channels/discord.py",
      "clawlite/channels/matrix.py",
      "clawlite/channels/slack.py",
      "clawlite/channels/whatsapp.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_rate_limiter.py",
    "area": "tests",
    "ext": ".py",
    "lines": 64,
    "size_bytes": 1956,
    "imports": [
      "clawlite/channels/base.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_slack.py",
    "area": "tests",
    "ext": ".py",
    "lines": 334,
    "size_bytes": 10439,
    "imports": [
      "clawlite/channels/slack.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram.py",
    "area": "tests",
    "ext": ".py",
    "lines": 5835,
    "size_bytes": 192307,
    "imports": [
      "clawlite/channels/telegram.py",
      "clawlite/channels/telegram_offset_store.py",
      "clawlite/core/engine.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_aux_updates.py",
    "area": "tests",
    "ext": ".py",
    "lines": 53,
    "size_bytes": 1934,
    "imports": [
      "clawlite/channels/telegram_aux_updates.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_delivery.py",
    "area": "tests",
    "ext": ".py",
    "lines": 102,
    "size_bytes": 3552,
    "imports": [
      "clawlite/channels/telegram_delivery.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_inbound_dispatch.py",
    "area": "tests",
    "ext": ".py",
    "lines": 47,
    "size_bytes": 1396,
    "imports": [
      "clawlite/channels/telegram.py",
      "clawlite/channels/telegram_inbound_dispatch.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_inbound_message.py",
    "area": "tests",
    "ext": ".py",
    "lines": 73,
    "size_bytes": 2248,
    "imports": [
      "clawlite/channels/telegram_inbound_message.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_inbound_runtime.py",
    "area": "tests",
    "ext": ".py",
    "lines": 94,
    "size_bytes": 3186,
    "imports": [
      "clawlite/channels/telegram_inbound_runtime.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_interactions.py",
    "area": "tests",
    "ext": ".py",
    "lines": 100,
    "size_bytes": 3232,
    "imports": [
      "clawlite/channels/telegram_interactions.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_status.py",
    "area": "tests",
    "ext": ".py",
    "lines": 70,
    "size_bytes": 2323,
    "imports": [
      "clawlite/channels/telegram_status.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_telegram_transport.py",
    "area": "tests",
    "ext": ".py",
    "lines": 92,
    "size_bytes": 2894,
    "imports": [
      "clawlite/channels/telegram_transport.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/channels/test_whatsapp.py",
    "area": "tests",
    "ext": ".py",
    "lines": 275,
    "size_bytes": 8737,
    "imports": [
      "clawlite/channels/whatsapp.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/cli/test_commands.py",
    "area": "tests",
    "ext": ".py",
    "lines": 5021,
    "size_bytes": 165804,
    "imports": [
      "clawlite/channels/telegram_pairing.py",
      "clawlite/cli/commands.py",
      "clawlite/cli/ops.py",
      "clawlite/config/loader.py",
      "clawlite/core/skills.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/cli/test_configure_wizard.py",
    "area": "tests",
    "ext": ".py",
    "lines": 194,
    "size_bytes": 9717,
    "imports": [
      "clawlite/cli/commands.py",
      "clawlite/cli/onboarding.py",
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/cli/test_onboarding.py",
    "area": "tests",
    "ext": ".py",
    "lines": 898,
    "size_bytes": 33778,
    "imports": [
      "clawlite/cli/__init__.py",
      "clawlite/cli/onboarding.py",
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/config/test_health.py",
    "area": "tests",
    "ext": ".py",
    "lines": 94,
    "size_bytes": 3056,
    "imports": [
      "clawlite/config/health.py",
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/config/test_loader.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1054,
    "size_bytes": 38332,
    "imports": [
      "clawlite/config/loader.py",
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/config/test_schema.py",
    "area": "tests",
    "ext": ".py",
    "lines": 520,
    "size_bytes": 19655,
    "imports": [
      "clawlite/config/loader.py",
      "clawlite/config/schema.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/config/test_watcher.py",
    "area": "tests",
    "ext": ".py",
    "lines": 109,
    "size_bytes": 3202,
    "imports": [
      "clawlite/config/loader.py",
      "clawlite/config/schema.py",
      "clawlite/config/watcher.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_context_window.py",
    "area": "tests",
    "ext": ".py",
    "lines": 95,
    "size_bytes": 2730,
    "imports": [
      "clawlite/core/context_window.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_engine.py",
    "area": "tests",
    "ext": ".py",
    "lines": 3483,
    "size_bytes": 129228,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/core/engine.py",
      "clawlite/core/memory.py",
      "clawlite/core/prompt.py",
      "clawlite/core/subagent.py",
      "clawlite/core/subagent_synthesizer.py",
      "clawlite/runtime/telemetry.py",
      "clawlite/session/store.py",
      "clawlite/tools/base.py",
      "clawlite/tools/registry.py",
      "clawlite/utils/logging.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_huginn_muninn.py",
    "area": "tests",
    "ext": ".py",
    "lines": 193,
    "size_bytes": 6945,
    "imports": [
      "clawlite/core/huginn_muninn.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_injection_guard.py",
    "area": "tests",
    "ext": ".py",
    "lines": 118,
    "size_bytes": 4434,
    "imports": [
      "clawlite/core/injection_guard.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory.py",
    "area": "tests",
    "ext": ".py",
    "lines": 2900,
    "size_bytes": 117851,
    "imports": [
      "clawlite/core/memory.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_api.py",
    "area": "tests",
    "ext": ".py",
    "lines": 101,
    "size_bytes": 3405,
    "imports": [
      "clawlite/core/memory_api.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_artifacts.py",
    "area": "tests",
    "ext": ".py",
    "lines": 83,
    "size_bytes": 3112,
    "imports": [
      "clawlite/core/memory_artifacts.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_backend.py",
    "area": "tests",
    "ext": ".py",
    "lines": 658,
    "size_bytes": 23026,
    "imports": [
      "clawlite/core/memory_backend.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_classification.py",
    "area": "tests",
    "ext": ".py",
    "lines": 100,
    "size_bytes": 3643,
    "imports": [
      "clawlite/core/memory_classification.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_consolidator.py",
    "area": "tests",
    "ext": ".py",
    "lines": 50,
    "size_bytes": 1826,
    "imports": [
      "clawlite/core/memory_consolidator.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_curation.py",
    "area": "tests",
    "ext": ".py",
    "lines": 92,
    "size_bytes": 3618,
    "imports": [
      "clawlite/core/memory.py",
      "clawlite/core/memory_curation.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_history.py",
    "area": "tests",
    "ext": ".py",
    "lines": 113,
    "size_bytes": 4456,
    "imports": [
      "clawlite/core/memory_history.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_ingest.py",
    "area": "tests",
    "ext": ".py",
    "lines": 41,
    "size_bytes": 1392,
    "imports": [
      "clawlite/core/memory.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_ingest_helpers.py",
    "area": "tests",
    "ext": ".py",
    "lines": 69,
    "size_bytes": 2118,
    "imports": [
      "clawlite/core/memory_ingest.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_layers.py",
    "area": "tests",
    "ext": ".py",
    "lines": 74,
    "size_bytes": 2604,
    "imports": [
      "clawlite/core/memory_layers.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_maintenance.py",
    "area": "tests",
    "ext": ".py",
    "lines": 73,
    "size_bytes": 2495,
    "imports": [
      "clawlite/core/memory_maintenance.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_monitor.py",
    "area": "tests",
    "ext": ".py",
    "lines": 306,
    "size_bytes": 10453,
    "imports": [
      "clawlite/core/memory.py",
      "clawlite/core/memory_monitor.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_policy.py",
    "area": "tests",
    "ext": ".py",
    "lines": 67,
    "size_bytes": 2113,
    "imports": [
      "clawlite/core/memory_policy.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_privacy.py",
    "area": "tests",
    "ext": ".py",
    "lines": 67,
    "size_bytes": 1890,
    "imports": [
      "clawlite/core/memory_privacy.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_proactive.py",
    "area": "tests",
    "ext": ".py",
    "lines": 59,
    "size_bytes": 2186,
    "imports": [
      "clawlite/core/memory_proactive.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_profile.py",
    "area": "tests",
    "ext": ".py",
    "lines": 131,
    "size_bytes": 4682,
    "imports": [
      "clawlite/core/memory_profile.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_prune.py",
    "area": "tests",
    "ext": ".py",
    "lines": 146,
    "size_bytes": 4932,
    "imports": [
      "clawlite/core/memory_prune.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_quality.py",
    "area": "tests",
    "ext": ".py",
    "lines": 64,
    "size_bytes": 2731,
    "imports": [
      "clawlite/core/memory_quality.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_reporting.py",
    "area": "tests",
    "ext": ".py",
    "lines": 118,
    "size_bytes": 4341,
    "imports": [
      "clawlite/core/memory_reporting.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_resources.py",
    "area": "tests",
    "ext": ".py",
    "lines": 53,
    "size_bytes": 1944,
    "imports": [
      "clawlite/core/memory.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_resources_helpers.py",
    "area": "tests",
    "ext": ".py",
    "lines": 107,
    "size_bytes": 3431,
    "imports": [
      "clawlite/core/memory_resources.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_retrieval.py",
    "area": "tests",
    "ext": ".py",
    "lines": 285,
    "size_bytes": 12645,
    "imports": [
      "clawlite/core/memory_retrieval.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_search.py",
    "area": "tests",
    "ext": ".py",
    "lines": 118,
    "size_bytes": 3900,
    "imports": [
      "clawlite/core/memory_search.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_ttl.py",
    "area": "tests",
    "ext": ".py",
    "lines": 40,
    "size_bytes": 1285,
    "imports": [
      "clawlite/core/memory.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_versions.py",
    "area": "tests",
    "ext": ".py",
    "lines": 97,
    "size_bytes": 3441,
    "imports": [
      "clawlite/core/memory_versions.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_workflows.py",
    "area": "tests",
    "ext": ".py",
    "lines": 121,
    "size_bytes": 4506,
    "imports": [
      "clawlite/core/memory_workflows.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_memory_working_set.py",
    "area": "tests",
    "ext": ".py",
    "lines": 369,
    "size_bytes": 15999,
    "imports": [
      "clawlite/core/memory_working_set.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_norns.py",
    "area": "tests",
    "ext": ".py",
    "lines": 160,
    "size_bytes": 5422,
    "imports": [
      "clawlite/core/norns.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_prompt.py",
    "area": "tests",
    "ext": ".py",
    "lines": 319,
    "size_bytes": 11191,
    "imports": [
      "clawlite/core/prompt.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_runestone.py",
    "area": "tests",
    "ext": ".py",
    "lines": 112,
    "size_bytes": 3542,
    "imports": [
      "clawlite/core/runestone.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_skills.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1008,
    "size_bytes": 34467,
    "imports": [
      "clawlite/core/skills.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_skills_new.py",
    "area": "tests",
    "ext": ".py",
    "lines": 25,
    "size_bytes": 779,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_subagent.py",
    "area": "tests",
    "ext": ".py",
    "lines": 703,
    "size_bytes": 24298,
    "imports": [
      "clawlite/core/subagent.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/core/test_subagent_context.py",
    "area": "tests",
    "ext": ".py",
    "lines": 69,
    "size_bytes": 2175,
    "imports": [
      "clawlite/core/subagent.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_background_runners.py",
    "area": "tests",
    "ext": ".py",
    "lines": 73,
    "size_bytes": 2299,
    "imports": [
      "clawlite/gateway/background_runners.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_control_plane.py",
    "area": "tests",
    "ext": ".py",
    "lines": 80,
    "size_bytes": 2565,
    "imports": [
      "clawlite/gateway/control_plane.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_dashboard_runtime.py",
    "area": "tests",
    "ext": ".py",
    "lines": 62,
    "size_bytes": 3425,
    "imports": [
      "clawlite/gateway/dashboard_runtime.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_dashboard_state.py",
    "area": "tests",
    "ext": ".py",
    "lines": 150,
    "size_bytes": 5368,
    "imports": [
      "clawlite/gateway/dashboard_state.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_diagnostics_payload.py",
    "area": "tests",
    "ext": ".py",
    "lines": 109,
    "size_bytes": 4815,
    "imports": [
      "clawlite/gateway/diagnostics_payload.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_discord_thread_binding.py",
    "area": "tests",
    "ext": ".py",
    "lines": 307,
    "size_bytes": 10733,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/gateway/discord_thread_binding.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_engine_diagnostics.py",
    "area": "tests",
    "ext": ".py",
    "lines": 107,
    "size_bytes": 4006,
    "imports": [
      "clawlite/gateway/engine_diagnostics.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_lifecycle_runtime.py",
    "area": "tests",
    "ext": ".py",
    "lines": 117,
    "size_bytes": 4278,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/gateway/lifecycle_runtime.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_memory_dashboard.py",
    "area": "tests",
    "ext": ".py",
    "lines": 65,
    "size_bytes": 2365,
    "imports": [
      "clawlite/gateway/memory_dashboard.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_payloads.py",
    "area": "tests",
    "ext": ".py",
    "lines": 100,
    "size_bytes": 3403,
    "imports": [
      "clawlite/gateway/payloads.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_request_handlers.py",
    "area": "tests",
    "ext": ".py",
    "lines": 91,
    "size_bytes": 4144,
    "imports": [
      "clawlite/gateway/request_handlers.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_runtime_state.py",
    "area": "tests",
    "ext": ".py",
    "lines": 38,
    "size_bytes": 1382,
    "imports": [
      "clawlite/gateway/runtime_state.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_self_evolution_approval.py",
    "area": "tests",
    "ext": ".py",
    "lines": 139,
    "size_bytes": 4710,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/gateway/self_evolution_approval.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_server.py",
    "area": "tests",
    "ext": ".py",
    "lines": 6602,
    "size_bytes": 263482,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/channels/base.py",
      "clawlite/config/schema.py",
      "clawlite/core/engine.py",
      "clawlite/core/memory.py",
      "clawlite/core/memory_monitor.py",
      "clawlite/core/subagent.py",
      "clawlite/gateway/runtime_builder.py",
      "clawlite/gateway/server.py",
      "clawlite/providers/base.py",
      "clawlite/scheduler/heartbeat.py",
      "clawlite/utils/__init__.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_status_handlers.py",
    "area": "tests",
    "ext": ".py",
    "lines": 62,
    "size_bytes": 2458,
    "imports": [
      "clawlite/gateway/status_handlers.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_subagents_runtime.py",
    "area": "tests",
    "ext": ".py",
    "lines": 83,
    "size_bytes": 3024,
    "imports": [
      "clawlite/gateway/subagents_runtime.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_supervisor_recovery.py",
    "area": "tests",
    "ext": ".py",
    "lines": 64,
    "size_bytes": 2396,
    "imports": [
      "clawlite/gateway/supervisor_recovery.py",
      "clawlite/runtime/__init__.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_supervisor_runtime.py",
    "area": "tests",
    "ext": ".py",
    "lines": 79,
    "size_bytes": 3934,
    "imports": [
      "clawlite/gateway/supervisor_runtime.py",
      "clawlite/runtime/__init__.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_tool_approval.py",
    "area": "tests",
    "ext": ".py",
    "lines": 139,
    "size_bytes": 4599,
    "imports": [
      "clawlite/bus/events.py",
      "clawlite/gateway/tool_approval.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_tuning_decisions.py",
    "area": "tests",
    "ext": ".py",
    "lines": 112,
    "size_bytes": 3904,
    "imports": [
      "clawlite/gateway/tuning_decisions.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_tuning_policy.py",
    "area": "tests",
    "ext": ".py",
    "lines": 47,
    "size_bytes": 1841,
    "imports": [
      "clawlite/gateway/tuning_policy.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_tuning_runtime.py",
    "area": "tests",
    "ext": ".py",
    "lines": 67,
    "size_bytes": 2353,
    "imports": [
      "clawlite/gateway/tuning_runtime.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/gateway/test_websocket_handlers.py",
    "area": "tests",
    "ext": ".py",
    "lines": 170,
    "size_bytes": 5871,
    "imports": [
      "clawlite/core/engine.py",
      "clawlite/gateway/websocket_handlers.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/jobs/__init__.py",
    "area": "tests",
    "ext": ".py",
    "lines": 0,
    "size_bytes": 0,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/jobs/test_journal.py",
    "area": "tests",
    "ext": ".py",
    "lines": 83,
    "size_bytes": 2017,
    "imports": [
      "clawlite/jobs/journal.py",
      "clawlite/jobs/queue.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/jobs/test_queue.py",
    "area": "tests",
    "ext": ".py",
    "lines": 177,
    "size_bytes": 5013,
    "imports": [
      "clawlite/jobs/queue.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/jobs/test_worker_status.py",
    "area": "tests",
    "ext": ".py",
    "lines": 74,
    "size_bytes": 1827,
    "imports": [
      "clawlite/jobs/queue.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_catalog.py",
    "area": "tests",
    "ext": ".py",
    "lines": 30,
    "size_bytes": 982,
    "imports": [
      "clawlite/providers/catalog.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_codex_retry.py",
    "area": "tests",
    "ext": ".py",
    "lines": 524,
    "size_bytes": 18519,
    "imports": [
      "clawlite/providers/codex.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_discovery.py",
    "area": "tests",
    "ext": ".py",
    "lines": 167,
    "size_bytes": 6175,
    "imports": [
      "clawlite/providers/discovery.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_failover.py",
    "area": "tests",
    "ext": ".py",
    "lines": 357,
    "size_bytes": 13897,
    "imports": [
      "clawlite/providers/base.py",
      "clawlite/providers/failover.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_hints.py",
    "area": "tests",
    "ext": ".py",
    "lines": 91,
    "size_bytes": 2758,
    "imports": [
      "clawlite/providers/hints.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_litellm_anthropic.py",
    "area": "tests",
    "ext": ".py",
    "lines": 134,
    "size_bytes": 4501,
    "imports": [
      "clawlite/providers/litellm.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_litellm_retry.py",
    "area": "tests",
    "ext": ".py",
    "lines": 401,
    "size_bytes": 15425,
    "imports": [
      "clawlite/providers/litellm.py",
      "clawlite/providers/reliability.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_model_probe.py",
    "area": "tests",
    "ext": ".py",
    "lines": 38,
    "size_bytes": 1076,
    "imports": [
      "clawlite/providers/model_probe.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_registry_auth_resolution.py",
    "area": "tests",
    "ext": ".py",
    "lines": 577,
    "size_bytes": 20638,
    "imports": [
      "clawlite/providers/__init__.py",
      "clawlite/providers/codex.py",
      "clawlite/providers/failover.py",
      "clawlite/providers/litellm.py",
      "clawlite/providers/registry.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_reliability.py",
    "area": "tests",
    "ext": ".py",
    "lines": 29,
    "size_bytes": 1177,
    "imports": [
      "clawlite/providers/__init__.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_streaming_recovery.py",
    "area": "tests",
    "ext": ".py",
    "lines": 180,
    "size_bytes": 6775,
    "imports": [
      "clawlite/core/engine.py",
      "clawlite/providers/litellm.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_telemetry.py",
    "area": "tests",
    "ext": ".py",
    "lines": 98,
    "size_bytes": 2933,
    "imports": [
      "clawlite/providers/telemetry.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/providers/test_transcription.py",
    "area": "tests",
    "ext": ".py",
    "lines": 69,
    "size_bytes": 2646,
    "imports": [
      "clawlite/providers/transcription.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_autonomy.py",
    "area": "tests",
    "ext": ".py",
    "lines": 333,
    "size_bytes": 11184,
    "imports": [
      "clawlite/runtime/autonomy.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_autonomy_actions.py",
    "area": "tests",
    "ext": ".py",
    "lines": 418,
    "size_bytes": 15558,
    "imports": [
      "clawlite/runtime/autonomy_actions.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_autonomy_log.py",
    "area": "tests",
    "ext": ".py",
    "lines": 52,
    "size_bytes": 2134,
    "imports": [
      "clawlite/runtime/autonomy_log.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_autonomy_wake.py",
    "area": "tests",
    "ext": ".py",
    "lines": 403,
    "size_bytes": 14943,
    "imports": [
      "clawlite/runtime/autonomy.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_gjallarhorn.py",
    "area": "tests",
    "ext": ".py",
    "lines": 168,
    "size_bytes": 6401,
    "imports": [
      "clawlite/runtime/gjallarhorn.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_runtime_telemetry.py",
    "area": "tests",
    "ext": ".py",
    "lines": 23,
    "size_bytes": 882,
    "imports": [
      "clawlite/runtime/telemetry.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_self_evolution.py",
    "area": "tests",
    "ext": ".py",
    "lines": 656,
    "size_bytes": 26239,
    "imports": [
      "clawlite/runtime/self_evolution.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_supervisor.py",
    "area": "tests",
    "ext": ".py",
    "lines": 341,
    "size_bytes": 11325,
    "imports": [
      "clawlite/runtime/supervisor.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_supervisor_phase5.py",
    "area": "tests",
    "ext": ".py",
    "lines": 138,
    "size_bytes": 4425,
    "imports": [
      "clawlite/jobs/queue.py",
      "clawlite/runtime/supervisor.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_valkyrie.py",
    "area": "tests",
    "ext": ".py",
    "lines": 133,
    "size_bytes": 4737,
    "imports": [
      "clawlite/runtime/valkyrie.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/runtime/test_volva.py",
    "area": "tests",
    "ext": ".py",
    "lines": 184,
    "size_bytes": 5843,
    "imports": [
      "clawlite/runtime/volva.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/scheduler/test_cron.py",
    "area": "tests",
    "ext": ".py",
    "lines": 855,
    "size_bytes": 29484,
    "imports": [
      "clawlite/scheduler/cron.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/scheduler/test_heartbeat.py",
    "area": "tests",
    "ext": ".py",
    "lines": 402,
    "size_bytes": 13928,
    "imports": [
      "clawlite/scheduler/heartbeat.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/scripts/test_assemble_gif.py",
    "area": "tests",
    "ext": ".py",
    "lines": 48,
    "size_bytes": 1536,
    "imports": [
      "scripts/assemble_gif.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/scripts/test_capture_frames.py",
    "area": "tests",
    "ext": ".py",
    "lines": 46,
    "size_bytes": 1684,
    "imports": [
      "scripts/capture_frames.py",
      "scripts/terminal_template.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/scripts/test_make_demo_gif.py",
    "area": "tests",
    "ext": ".py",
    "lines": 37,
    "size_bytes": 1177,
    "imports": [
      "scripts/make_demo_gif.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/scripts/test_terminal_template.py",
    "area": "tests",
    "ext": ".py",
    "lines": 42,
    "size_bytes": 1269,
    "imports": [
      "scripts/terminal_template.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/session/test_store.py",
    "area": "tests",
    "ext": ".py",
    "lines": 290,
    "size_bytes": 9920,
    "imports": [
      "clawlite/session/store.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/skills/__init__.py",
    "area": "tests",
    "ext": ".py",
    "lines": 0,
    "size_bytes": 0,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/skills/test_markdown_skills.py",
    "area": "tests",
    "ext": ".py",
    "lines": 26,
    "size_bytes": 592,
    "imports": [
      "clawlite/core/skills.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/skills/test_model_usage_script.py",
    "area": "tests",
    "ext": ".py",
    "lines": 49,
    "size_bytes": 1684,
    "imports": [],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/skills/test_skill_creator.py",
    "area": "tests",
    "ext": ".py",
    "lines": 71,
    "size_bytes": 2540,
    "imports": [
      "clawlite/skills/skill_creator.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_agents_tool.py",
    "area": "tests",
    "ext": ".py",
    "lines": 211,
    "size_bytes": 7870,
    "imports": [
      "clawlite/core/subagent.py",
      "clawlite/tools/agents.py",
      "clawlite/tools/base.py",
      "clawlite/tools/spawn.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_apply_patch.py",
    "area": "tests",
    "ext": ".py",
    "lines": 164,
    "size_bytes": 5718,
    "imports": [
      "clawlite/tools/apply_patch.py",
      "clawlite/tools/base.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_browser_tool.py",
    "area": "tests",
    "ext": ".py",
    "lines": 196,
    "size_bytes": 6835,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/browser.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_cron_message_spawn_mcp.py",
    "area": "tests",
    "ext": ".py",
    "lines": 428,
    "size_bytes": 15363,
    "imports": [
      "clawlite/core/subagent.py",
      "clawlite/tools/base.py",
      "clawlite/tools/cron.py",
      "clawlite/tools/message.py",
      "clawlite/tools/spawn.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_discord_admin_tool.py",
    "area": "tests",
    "ext": ".py",
    "lines": 228,
    "size_bytes": 7926,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/discord_admin.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_exec_files.py",
    "area": "tests",
    "ext": ".py",
    "lines": 276,
    "size_bytes": 10143,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/exec.py",
      "clawlite/tools/files.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_exec_network_guard.py",
    "area": "tests",
    "ext": ".py",
    "lines": 106,
    "size_bytes": 3603,
    "imports": [
      "clawlite/tools/exec.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_files_edge_cases.py",
    "area": "tests",
    "ext": ".py",
    "lines": 84,
    "size_bytes": 2834,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/files.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_health_check.py",
    "area": "tests",
    "ext": ".py",
    "lines": 128,
    "size_bytes": 3932,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/tools/base.py",
      "clawlite/tools/exec.py",
      "clawlite/tools/mcp.py",
      "clawlite/tools/pdf.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_jobs_tool.py",
    "area": "tests",
    "ext": ".py",
    "lines": 111,
    "size_bytes": 3662,
    "imports": [
      "clawlite/jobs/queue.py",
      "clawlite/tools/base.py",
      "clawlite/tools/jobs.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_mcp.py",
    "area": "tests",
    "ext": ".py",
    "lines": 209,
    "size_bytes": 7272,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/tools/base.py",
      "clawlite/tools/mcp.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_memory_tools.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1027,
    "size_bytes": 37730,
    "imports": [
      "clawlite/core/memory.py",
      "clawlite/tools/__init__.py",
      "clawlite/tools/base.py",
      "clawlite/tools/memory.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_process_tool.py",
    "area": "tests",
    "ext": ".py",
    "lines": 259,
    "size_bytes": 9900,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/process.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_registry.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1183,
    "size_bytes": 41509,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/runtime/telemetry.py",
      "clawlite/tools/base.py",
      "clawlite/tools/registry.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_result_cache.py",
    "area": "tests",
    "ext": ".py",
    "lines": 121,
    "size_bytes": 3555,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/registry.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_sessions_tools.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1209,
    "size_bytes": 45603,
    "imports": [
      "clawlite/core/subagent.py",
      "clawlite/session/store.py",
      "clawlite/tools/base.py",
      "clawlite/tools/sessions.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_skill_tool.py",
    "area": "tests",
    "ext": ".py",
    "lines": 1096,
    "size_bytes": 38156,
    "imports": [
      "clawlite/config/schema.py",
      "clawlite/core/skills.py",
      "clawlite/providers/base.py",
      "clawlite/tools/base.py",
      "clawlite/tools/registry.py",
      "clawlite/tools/skill.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_timeout_middleware.py",
    "area": "tests",
    "ext": ".py",
    "lines": 141,
    "size_bytes": 4386,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/registry.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_tools.py",
    "area": "tests",
    "ext": ".py",
    "lines": 55,
    "size_bytes": 1816,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/browser.py",
      "clawlite/tools/pdf.py",
      "clawlite/tools/tts.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/tools/test_web.py",
    "area": "tests",
    "ext": ".py",
    "lines": 315,
    "size_bytes": 11480,
    "imports": [
      "clawlite/tools/base.py",
      "clawlite/tools/web.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/utils/test_helpers.py",
    "area": "tests",
    "ext": ".py",
    "lines": 16,
    "size_bytes": 408,
    "imports": [
      "clawlite/utils/helpers.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/utils/test_logging.py",
    "area": "tests",
    "ext": ".py",
    "lines": 114,
    "size_bytes": 3613,
    "imports": [
      "clawlite/channels/telegram.py",
      "clawlite/scheduler/cron.py",
      "clawlite/utils/__init__.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/workspace/test_user_profile.py",
    "area": "tests",
    "ext": ".py",
    "lines": 101,
    "size_bytes": 3314,
    "imports": [
      "clawlite/workspace/identity_enforcer.py",
      "clawlite/workspace/loader.py",
      "clawlite/workspace/user_profile.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  },
  {
    "path": "tests/workspace/test_workspace_loader.py",
    "area": "tests",
    "ext": ".py",
    "lines": 260,
    "size_bytes": 9040,
    "imports": [
      "clawlite/config/loader.py",
      "clawlite/config/schema.py",
      "clawlite/workspace/bootstrap.py",
      "clawlite/workspace/loader.py"
    ],
    "imported_by_count": 0,
    "tests_for": []
  }
]
```
