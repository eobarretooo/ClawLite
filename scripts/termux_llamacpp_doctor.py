#!/usr/bin/env python3
"""Small Termux-friendly llama.cpp provider doctor for ClawLite."""
from __future__ import annotations

import json
import os
import sys
import time
from urllib import request, error

BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://127.0.0.1:8080/v1").rstrip("/")
PROMPT = os.environ.get("LLAMACPP_TEST_PROMPT", "Return exactly: ClawLite online")
TIMEOUT = float(os.environ.get("LLAMACPP_TIMEOUT", "30"))


def _get_json(url: str) -> tuple[int, object, str]:
    try:
        with request.urlopen(url, timeout=TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(raw), raw
            except Exception:
                return response.status, {}, raw
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, {}, raw
    except Exception as exc:
        return 0, {}, str(exc)


def _post_json(url: str, payload: dict) -> tuple[int, object, str, float]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with request.urlopen(req, timeout=TIMEOUT) as response:
            elapsed = time.perf_counter() - started
            raw = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(raw), raw, elapsed
            except Exception:
                return response.status, {}, raw, elapsed
    except error.HTTPError as exc:
        elapsed = time.perf_counter() - started
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, {}, raw, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return 0, {}, str(exc), elapsed


def main() -> int:
    print("ClawLite llama.cpp doctor")
    print(f"base_url: {BASE_URL}")

    status, payload, raw = _get_json(f"{BASE_URL}/models")
    print(f"/models status: {status}")
    if status != 200:
        print(raw[:1000])
        print("ERROR: llama-server is not reachable. Start it on port 8080 first.")
        return 2

    models = []
    if isinstance(payload, dict):
        rows = payload.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("id"):
                    models.append(str(row["id"]))
    print("models:", ", ".join(models) if models else "unknown")
    model = models[0] if models else "local-model"

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a strict local assistant. Follow the user instruction exactly."},
            {"role": "user", "content": PROMPT},
        ],
        "temperature": 0,
        "max_tokens": 64,
    }
    status, payload, raw, elapsed = _post_json(f"{BASE_URL}/chat/completions", body)
    print(f"/chat/completions status: {status}")
    print(f"elapsed: {elapsed:.3f}s")
    if status != 200:
        print(raw[:2000])
        return 3

    text = ""
    usage = {}
    if isinstance(payload, dict):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                text = str(message.get("content", "") or "")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    print("response:", text.strip() or "<empty>")
    completion_tokens = int(usage.get("completion_tokens") or 0) if usage else 0
    if completion_tokens and elapsed > 0:
        print(f"approx completion tokens/s: {completion_tokens / elapsed:.2f}")
    print("OK: llama.cpp OpenAI-compatible endpoint is usable by ClawLite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
