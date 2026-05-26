# Termux + llama.cpp local provider

This profile lets ClawLite use a local `llama-server` running on Android/Termux.
It is intentionally OpenAI-compatible and does not require an API key.

## 1. Start a model in Termux

Example with the model that performed well in local tests:

```bash
cd ~/llama.cpp
./build/bin/llama-server \
  -m ~/models/qwen25-15b/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 2048 \
  -t 8
```

Other good candidates for Android:

- `Qwen2.5-1.5B-Instruct-Q4_K_M` — best speed/quality balance.
- `GLM-Edge-1.5B-Chat-Q4_K_M` — higher quality, slower.
- `MiniCPM4-0.5B-Q4_K_M` — fastest fallback.

## 2. Configure ClawLite

Add this to your config file:

```json
{
  "provider": {
    "model": "llamacpp/qwen2.5-1.5b-instruct-q4_k_m"
  },
  "providers": {
    "llamacpp": {
      "api_key": "",
      "api_base": "http://127.0.0.1:8080/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "llamacpp/qwen2.5-1.5b-instruct-q4_k_m",
      "max_tokens": 1024,
      "temperature": 0.2
    }
  }
}
```

The model name after `llamacpp/` is used by ClawLite for routing and diagnostics.
`llama-server` may report a different model id from `/v1/models`; this is acceptable as long as completions work.

## 3. Diagnose the runtime

Run:

```bash
python scripts/termux_llamacpp_doctor.py
```

Useful environment overrides:

```bash
LLAMACPP_BASE_URL=http://127.0.0.1:8080/v1 python scripts/termux_llamacpp_doctor.py
LLAMACPP_TEST_PROMPT="Responda apenas: ClawLite online" python scripts/termux_llamacpp_doctor.py
```

## 4. Notes

- Keep `llama-server` running before starting ClawLite.
- Use `-c 2048` first. Increase only if RAM/temperature are stable.
- On Android, prefer Q4 models before Q5/Q8.
- If the phone gets hot, lower threads with `-t 4`.
