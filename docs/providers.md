# Providers

ClawLite can talk to hosted APIs, local runtimes, OAuth-backed free-tier providers, and custom OpenAI-compatible backends. The default model is `gemini/gemini-2.5-flash`.
The interactive wizard now prints provider-specific suggestions before probing: transport family, recommended model ids, expected base URL, and a login hint for OAuth-backed providers such as `openai-codex`.

## Fastest Manual Setup

If you do not want the wizard, this is the smallest useful provider config:

```json
{
  "provider": {
    "model": "openai/gpt-4o-mini"
  },
  "providers": {
    "openai": {
      "api_key": "sk-test-openai",
      "api_base": "https://api.openai.com/v1",
      "extra_headers": {}
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o-mini"
    }
  }
}
```

You can also persist the same settings through the CLI:

```bash
clawlite provider set-auth openai --api-key sk-test-openai
clawlite provider use openai --model openai/gpt-4o-mini
```

## Auth and Base URL Resolution

For API-key providers, ClawLite resolves credentials in this order:

1. `providers.<provider>.api_key`
2. legacy/global `provider.litellm_api_key`
3. provider-specific environment variables such as `OPENAI_API_KEY` or `GEMINI_API_KEY`
4. `CLAWLITE_LITELLM_API_KEY`
5. `CLAWLITE_API_KEY`

Base URL resolution is:

1. `providers.<provider>.api_base`
2. legacy/global `provider.litellm_base_url`
3. the provider default base URL from the registry

Useful environment variables:

- `CLAWLITE_MODEL`
- `CLAWLITE_LITELLM_BASE_URL`
- `CLAWLITE_LITELLM_API_KEY`
- provider-specific key vars such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`
- Codex OAuth vars such as `CLAWLITE_CODEX_ACCESS_TOKEN`, `OPENAI_CODEX_ACCESS_TOKEN`, `OPENAI_ACCESS_TOKEN`, `CLAWLITE_CODEX_ACCOUNT_ID`, `OPENAI_ORG_ID`
- Gemini OAuth vars such as `CLAWLITE_GEMINI_ACCESS_TOKEN`, `GEMINI_ACCESS_TOKEN`, `CLAWLITE_GEMINI_ACCOUNT_ID`
- Qwen OAuth vars such as `CLAWLITE_QWEN_ACCESS_TOKEN`, `QWEN_ACCESS_TOKEN`, `CLAWLITE_QWEN_ACCOUNT_ID`

Important behavior:

- ClawLite rejects obviously mismatched key prefixes when it can detect them.
- If a non-OpenAI provider is pointed at the default OpenAI base URL by mistake, ClawLite swaps to that provider's own default base URL when possible.
- `CLAWLITE_MODEL` overrides both `provider.model` and `agents.defaults.model` when loading the default config path.

## Provider Matrix

### OpenAI-compatible Hosted Providers

| Provider | Aliases | Transport | Default model | Default base URL | Key envs |
| --- | --- | --- | --- | --- | --- |
| `openai` | - | OpenAI-compatible | `openai/gpt-4o-mini` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| `azure-openai` | `azure_openai`, `azure` | OpenAI-compatible | `azure-openai/gpt-4.1-mini` | your Azure resource `/openai/v1` endpoint | `AZURE_OPENAI_API_KEY`, `AZURE_API_KEY` |
| `gemini` | `google` | OpenAI-compatible | `gemini/gemini-2.5-flash` | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY`, `GOOGLE_API_KEY` |
| `groq` | - | OpenAI-compatible | `groq/llama-3.1-8b-instant` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` |
| `deepseek` | - | OpenAI-compatible | `deepseek/deepseek-chat` | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` |
| `cerebras` | - | OpenAI-compatible | `cerebras/zai-glm-4.7` | `https://api.cerebras.ai/v1` | `CEREBRAS_API_KEY` |
| `xai` | - | OpenAI-compatible | `xai/grok-4` | `https://api.x.ai/v1` | `XAI_API_KEY` |
| `mistral` | - | OpenAI-compatible | `mistral/mistral-large-latest` | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` |
| `moonshot` | `kimi` | OpenAI-compatible | `moonshot/kimi-k2.5` | `https://api.moonshot.ai/v1` | `MOONSHOT_API_KEY` |
| `qianfan` | - | OpenAI-compatible | `qianfan/deepseek-v3.2` | `https://qianfan.baidubce.com/v2` | `QIANFAN_API_KEY` |
| `zai` | `zhipu` | OpenAI-compatible | `zai/glm-5` | `https://api.z.ai/api/paas/v4` | `ZAI_API_KEY`, `Z_AI_API_KEY`, `ZHIPUAI_API_KEY` |
| `nvidia` | - | OpenAI-compatible | `nvidia/meta/llama-3.1-70b-instruct` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY`, `NGC_API_KEY` |
| `byteplus` | - | OpenAI-compatible | `byteplus/deepseek-v3.1` | `https://ark.ap-southeast.bytepluses.com/api/v3` | `BYTEPLUS_API_KEY` |
| `doubao` | - | OpenAI-compatible | `doubao/doubao-seed-1-6` | `https://ark.cn-beijing.volces.com/api/v3` | `VOLCANO_ENGINE_API_KEY`, `VOLCENGINE_API_KEY` |
| `volcengine` | - | OpenAI-compatible | `volcengine/doubao-seed-1-6` | `https://ark.cn-beijing.volces.com/api/v3` | `VOLCANO_ENGINE_API_KEY`, `VOLCENGINE_API_KEY` |

### Gateway-style OpenAI-compatible Providers

| Provider | Aliases | Transport | Default model | Default base URL | Key envs |
| --- | --- | --- | --- | --- | --- |
| `openrouter` | - | OpenAI-compatible gateway | `openrouter/auto` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| `aihubmix` | - | OpenAI-compatible gateway | `aihubmix/openai/gpt-4.1-mini` | `https://aihubmix.com/v1` | `AIHUBMIX_API_KEY` |
| `siliconflow` | - | OpenAI-compatible gateway | `siliconflow/deepseek-ai/DeepSeek-V3` | `https://api.siliconflow.cn/v1` | `SILICONFLOW_API_KEY` |
| `together` | - | OpenAI-compatible gateway | `together/moonshotai/Kimi-K2.5` | `https://api.together.xyz/v1` | `TOGETHER_API_KEY` |
| `huggingface` | `hf` | OpenAI-compatible gateway | `huggingface/deepseek-ai/DeepSeek-R1` | `https://router.huggingface.co/v1` | `HUGGINGFACE_HUB_TOKEN`, `HF_TOKEN` |
| `kilocode` | `kilo` | OpenAI-compatible gateway | `kilocode/anthropic/claude-opus-4.6` | `https://api.kilo.ai/api/gateway/` | `KILOCODE_API_KEY` |

### Anthropic-compatible Providers

| Provider | Aliases | Transport | Default model | Default base URL | Key envs |
| --- | --- | --- | --- | --- | --- |
| `anthropic` | `claude` | Anthropic `/v1/messages` | `anthropic/claude-3-5-haiku-latest` | `https://api.anthropic.com/v1` | `ANTHROPIC_API_KEY` |
| `minimax` | - | Anthropic-compatible | `minimax/MiniMax-M2.5` | `https://api.minimax.io/anthropic` | `MINIMAX_API_KEY` |
| `xiaomi` | - | Anthropic-compatible | `xiaomi/mimo-v2-flash` | `https://api.xiaomimimo.com/anthropic` | `XIAOMI_API_KEY` |
| `kimi-coding` | `kimi_coding` | Anthropic-compatible | `kimi-coding/k2p5` | `https://api.kimi.com/coding/` | `KIMI_API_KEY`, `KIMICODE_API_KEY` |

### Local, OAuth, and Custom Providers

| Provider | Aliases | Transport | Default model | Default base URL | Auth |
| --- | --- | --- | --- | --- | --- |
| `ollama` | - | Local OpenAI-compatible | `openai/llama3.2` | `http://127.0.0.1:11434/v1` | No API key required |
| `vllm` | - | Local OpenAI-compatible | `vllm/meta-llama/Llama-3.2-3B-Instruct` | `http://127.0.0.1:8000/v1` | No API key required |
| `openai-codex` | `openai_codex`, `codex` | OAuth-backed OpenAI-compatible | `openai-codex/gpt-5.3-codex` | `https://chatgpt.com/backend-api` | OAuth access token and optional account/org ID |
| `gemini-oauth` | `gemini_oauth` | OAuth-backed OpenAI-compatible | `gemini_oauth/gemini-2.0-flash` | `https://generativelanguage.googleapis.com/v1beta/openai` | OAuth access token discovered from config, env, or local CLI auth file |
| `qwen-oauth` | `qwen_oauth` | OAuth-backed OpenAI-compatible | `qwen_oauth/qwen-plus` | `https://api.qwen.ai/v1` | OAuth access token discovered from config, env, or local CLI auth file |
| `custom` | - | User-defined OpenAI-compatible | `custom/<model>` | your choice | API key and headers are fully user-defined |

## Onboarding Support

The interactive wizard currently offers this subset:

- `openai-codex`
- `openai`
- `azure-openai`
- `anthropic`
- `gemini`
- `groq`
- `deepseek`
- `openrouter`
- `aihubmix`
- `siliconflow`
- `cerebras`
- `xai`
- `mistral`
- `moonshot`
- `zai`
- `qianfan`
- `huggingface`
- `together`
- `kilocode`
- `minimax`
- `xiaomi`
- `kimi-coding`
- `ollama`
- `vllm`

Runtime support is broader than wizard support. `custom`, `gemini-oauth`, `qwen-oauth`, `nvidia`, `byteplus`, `doubao`, and `volcengine` are supported in code but not surfaced by the onboarding wizard.

Notes:

- `azure-openai` needs your own resource-scoped base URL, for example `https://<resource>.openai.azure.com/openai/v1`.
- If `openai-codex` fails with `http_status:401` and an expired token detail, refresh the local OAuth session with `clawlite provider login openai-codex`.

## Example Configs

### OpenAI

```json
{
  "provider": {
    "model": "openai/gpt-4o-mini"
  },
  "providers": {
    "openai": {
      "api_key": "sk-test-openai",
      "api_base": "https://api.openai.com/v1",
      "extra_headers": {}
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/gpt-4o-mini"
    }
  }
}
```

### Azure OpenAI

```json
{
  "provider": {
    "model": "azure-openai/gpt-4.1-mini"
  },
  "providers": {
    "azure_openai": {
      "api_key": "azure-key",
      "api_base": "https://example-resource.openai.azure.com/openai/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "azure-openai/gpt-4.1-mini"
    }
  }
}
```

### Anthropic-compatible MiniMax

```json
{
  "provider": {
    "model": "minimax/MiniMax-M2.5"
  },
  "providers": {
    "minimax": {
      "api_key": "mini-key",
      "api_base": "https://api.minimax.io/anthropic"
    }
  },
  "agents": {
    "defaults": {
      "model": "minimax/MiniMax-M2.5"
    }
  }
}
```

### Ollama

```json
{
  "provider": {
    "model": "openai/llama3.2"
  },
  "providers": {
    "ollama": {
      "api_key": "",
      "api_base": "http://127.0.0.1:11434/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "openai/llama3.2"
    }
  }
}
```

`api_base` can point directly to Ollama (`http://127.0.0.1:11434/v1`) or to a reverse-proxied prefix that still ends in `/v1`, such as `https://llm.internal/ollama/v1`.

### OpenAI Codex OAuth

```json
{
  "provider": {
    "model": "openai-codex/gpt-5.3-codex"
  },
  "auth": {
    "providers": {
      "openai_codex": {
        "access_token": "oauth-token",
        "account_id": "org-123",
        "source": "config:test"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": "openai-codex/gpt-5.3-codex"
    }
  }
}
```

### Gemini OAuth

```json
{
  "provider": {
    "model": "gemini_oauth/gemini-2.0-flash"
  },
  "auth": {
    "providers": {
      "gemini_oauth": {
        "access_token": "oauth-token",
        "source": "config:test"
      }
    }
  }
}
```

### Qwen OAuth

```json
{
  "provider": {
    "model": "qwen_oauth/qwen-plus"
  },
  "auth": {
    "providers": {
      "qwen_oauth": {
        "access_token": "oauth-token",
        "source": "config:test"
      }
    }
  }
}
```

### Custom OpenAI-compatible Endpoint

```json
{
  "provider": {
    "model": "custom/my-model"
  },
  "providers": {
    "custom": {
      "api_key": "custom-secret",
      "api_base": "http://127.0.0.1:4000/v1",
      "extra_headers": {
        "X-Workspace": "dev"
      }
    }
  }
}
```

## Local Runtime Probing

ClawLite probes local runtimes at startup:

- Ollama: derives the runtime root from the configured base URL, preserves reverse-proxy prefixes, then checks `/api/tags` and `/api/show`.
- vLLM: preserves reverse-proxy prefixes when checking `/health` and `/v1/models`.

If every local candidate is unavailable, gateway startup fails fast with an explicit provider config error. If a local primary is down but a non-local fallback exists, startup continues and the failover provider takes over at request time.

## Failover and Reliability

What exists in code today:

- `LiteLLMProvider` and `CodexProvider` both have retry and circuit-breaker behavior.
- Retryable 429s and 5xx/network errors back off with jitter.
- Hard quota-style 429s fail fast instead of retrying.
- `build_provider()` supports `fallback_model`, `fallback_models`, and `fallbacks`, building a `FailoverProvider` with per-candidate cooldowns.
- When multiple fallback candidates are ready, `FailoverProvider` now ranks them by a lightweight health score derived from recent error rate, consecutive failures, cooldown state, and provider latency telemetry instead of always trying them in static order.

What you can persist in config today:

```json
{
  "provider": {
    "model": "openai/gpt-4o-mini",
    "retry_max_attempts": 3,
    "retry_initial_backoff_s": 0.5,
    "retry_max_backoff_s": 8.0,
    "retry_jitter_s": 0.2,
    "circuit_failure_threshold": 3,
    "circuit_cooldown_s": 30.0,
    "fallback_model": "openai/gpt-4.1-mini"
  }
}
```

The gateway runtime forwards these top-level `provider.*` settings into `build_provider()`, so retry, circuit-breaker, and `fallback_model` behavior match the persisted config.

The CLI still lets you persist fallback intent:

```bash
clawlite provider use anthropic \
  --model anthropic/claude-3-5-haiku-latest \
  --fallback-model anthropic/claude-3-7-sonnet-latest
```

## Codex OAuth Details

OpenAI Codex auth is resolved in this order:

1. `auth.providers.openai_codex` in config
2. `CLAWLITE_CODEX_ACCESS_TOKEN`
3. `OPENAI_CODEX_ACCESS_TOKEN`
4. `OPENAI_ACCESS_TOKEN`
5. auth file at `~/.codex/auth.json` or `CLAWLITE_CODEX_AUTH_PATH`

If the config entry was originally imported from `file:...`, ClawLite now re-reads the current auth file instead of trusting the stale snapshot saved in `config.json`. That keeps the wizard, `provider status`, and runtime provider aligned with the latest local Codex session.

Supported config aliases:

- provider keys: `openai_codex`, `openai-codex`, `codex`, `openaiCodex`
- token keys: `access_token`, `accessToken`, `token`
- account keys: `account_id`, `accountId`, `org_id`, `orgId`, `organization`

CLI helpers:

```bash
clawlite provider login openai-codex
clawlite provider status codex
clawlite provider logout
```

`--set-model` is kept as a deprecated compatibility flag. Use `--keep-model` if you want to persist Codex auth without switching the active model.

## Gemini and Qwen OAuth Details

Gemini OAuth is resolved in this order:

1. `auth.providers.gemini_oauth` in config
2. `CLAWLITE_GEMINI_ACCESS_TOKEN`
3. `GEMINI_ACCESS_TOKEN`
4. auth file at `~/.gemini/oauth_creds.json` or `CLAWLITE_GEMINI_AUTH_PATH`

When the resolved Gemini token came from the local auth file and a request gets an HTTP `401`, ClawLite refreshes that file-backed token once through Google's OAuth token endpoint, writes the renewed access token back to the same file, and retries the provider call once.

Qwen OAuth is resolved in this order:

1. `auth.providers.qwen_oauth` in config
2. `CLAWLITE_QWEN_ACCESS_TOKEN`
3. `QWEN_ACCESS_TOKEN`
4. auth file at `~/.qwen/oauth_creds.json`, `~/.qwen/auth.json`, or `CLAWLITE_QWEN_AUTH_PATH`

When the resolved Qwen token came from the local auth file and a request gets an HTTP `401`, ClawLite refreshes that file-backed token once through the Qwen portal OAuth token endpoint, persists the renewed token back to the same auth file, and retries the provider call once.

CLI helpers:

```bash
clawlite provider login gemini-oauth
clawlite provider status gemini-oauth
clawlite provider logout gemini-oauth

clawlite provider login qwen-oauth
clawlite provider status qwen-oauth
clawlite provider logout qwen-oauth
```

## Validation and Troubleshooting

Useful commands:

```bash
clawlite validate provider
clawlite provider status openai
clawlite validate preflight --provider-live
```

Common checks:

- Wrong key or missing billing: `clawlite validate preflight --provider-live`
- Wrong active model: `clawlite status`
- Wrong provider prefix: make sure the model matches the selected provider, for example `openai/...`, `anthropic/...`, `openrouter/...`
- Local runtime down: verify Ollama or vLLM is listening on the configured base URL

`clawlite validate preflight --provider-live` now also persists the latest live probe snapshot in local state. After that, `clawlite provider status <provider>` and `clawlite validate provider` reuse that additive cache in two ways: `last_live_probe` keeps the last known raw result, timestamp, and model/base-url match flags, while `last_capability_probe` summarizes the last remote model-list/capability signal (`checked`, `current_model_listed`, listed-model count, and a bounded sample) without re-running a network probe every time.

That same cached provider surface is now also visible from the live runtime itself: `GET /v1/control/provider/status` and `GET /api/provider/status` expose the same compact cached status for the currently selected provider, and the packaged dashboard Automation tab reuses that snapshot through `Inspect provider cache` plus the additive `provider.status` block in `GET /api/dashboard/state`.

## Telegram Transcription Provider

Telegram voice/audio transcription is a separate provider path from the main LLM provider. It uses:

- `channels.telegram.transcription_api_key`
- fallback env `GROQ_API_KEY`
- default base URL `https://api.groq.com/openai/v1`
- default model `whisper-large-v3-turbo`

See `docs/channels.md` for the full Telegram transcription config.
