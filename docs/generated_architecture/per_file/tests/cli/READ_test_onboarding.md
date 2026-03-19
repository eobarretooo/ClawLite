# READ tests/cli/test_onboarding.py

## Identity

- Path: `tests/cli/test_onboarding.py`
- Area: `tests`
- Extension: `.py`
- Lines: 898
- Size bytes: 33778
- SHA1: `fc3e68a18a1b0a57538ccc51cf6c35443c8fd0f3`

## Summary

`tests.cli.test_onboarding` is a Python module in the `tests` area. It defines 3 class(es), led by `_Client`, `_FakeWorkspaceLoader`, `_Response`. It exposes 33 function(s), including `__enter__`, `__exit__`, `__init__`. It depends on 6 import statement target(s).

## Structural Data

- Classes: 3
- Functions: 33
- Async functions: 0
- Constants: 0
- Internal imports: 3
- Imported by: 0
- Matching tests: 0

## Classes

- `_Client`
- `_FakeWorkspaceLoader`
- `_Response`

## Functions

- `__enter__`
- `__exit__`
- `__init__`
- `_fake_confirm_ask`
- `_fake_prompt_ask`
- `bootstrap`
- `get`
- `json`
- `post`
- `test_apply_provider_selection_aihubmix_uses_default_gateway_base`
- `test_apply_provider_selection_ollama_normalizes_runtime_base_url`
- `test_apply_provider_selection_openai_codex_updates_auth_and_model`
- `test_apply_provider_selection_openai_updates_config`
- `test_apply_provider_selection_xai_updates_dynamic_provider_block`
- `test_build_dashboard_handoff_reports_configured_web_search_backends`
- `test_build_dashboard_handoff_reports_default_web_search_guidance`
- `test_configure_model_prompts_for_azure_openai_base_url`
- `test_configure_model_uses_provider_specific_default_and_prints_suggestions`
- `test_ensure_gateway_token_generates_when_missing`
- `test_probe_provider_cerebras_success`
- `test_probe_provider_minimax_uses_anthropic_messages_transport`
- `test_probe_provider_ollama_accepts_runtime_base_url_with_v1`
- `test_probe_provider_openai_codex_expired_token_suggests_relogin`
- `test_probe_provider_openai_codex_success`
- `test_probe_provider_openai_missing_api_key_returns_actionable_hint`
- `test_probe_provider_openai_model_not_listed_returns_soft_warning`
- `test_probe_provider_openai_success`
- `test_probe_telegram_handles_network_error`
- `test_resolve_codex_auth_prefers_current_auth_file_over_stale_file_snapshot`
- `test_run_onboarding_wizard_advanced_persists_custom_model_and_gateway`
- `test_run_onboarding_wizard_disables_existing_telegram_when_user_declines`
- `test_run_onboarding_wizard_quickstart_supports_openai_codex`
- `test_run_onboarding_wizard_quickstart_uses_guided_defaults`

## Notable String Markers

- `clawlite provider`
- `test_apply_provider_selection_aihubmix_uses_default_gateway_base`
- `test_apply_provider_selection_ollama_normalizes_runtime_base_url`
- `test_apply_provider_selection_openai_codex_updates_auth_and_model`
- `test_apply_provider_selection_openai_updates_config`
- `test_apply_provider_selection_xai_updates_dynamic_provider_block`
- `test_build_dashboard_handoff_reports_configured_web_search_backends`
- `test_build_dashboard_handoff_reports_default_web_search_guidance`
- `test_configure_model_prompts_for_azure_openai_base_url`
- `test_configure_model_uses_provider_specific_default_and_prints_suggestions`
- `test_ensure_gateway_token_generates_when_missing`
- `test_probe_provider_cerebras_success`

## Reading Guidance

- Start with the file summary, then scan the symbols list for `tests/cli/test_onboarding.py`.
- Cross-reference `CONNECTIONS_test_onboarding.md` to see how this file fits into the wider system.
