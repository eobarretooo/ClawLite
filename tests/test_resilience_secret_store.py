from __future__ import annotations

import tempfile
from pathlib import Path

from clawlite.runtime.resilience import RateLimiter, retry_call
from clawlite.runtime.secret_store import load_dotenv, load_vault_json


def test_retry_call_eventually_succeeds():
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("x")
        return "ok"

    assert retry_call(fn, retries=3, base_delay_s=0.0, jitter=0.0) == "ok"


def test_rate_limiter_blocks_after_burst():
    rl = RateLimiter(rate_per_sec=1, burst=2)
    assert rl.allow() is True
    assert rl.allow() is True
    assert rl.allow() is False


def test_load_dotenv_and_vault_json():
    with tempfile.TemporaryDirectory() as td:
        envp = Path(td) / ".env"
        envp.write_text("A=1\nB=2\n", encoding="utf-8")
        out = load_dotenv(str(envp))
        assert out["A"] == "1"

        vp = Path(td) / "vault.json"
        vp.write_text('{"TOKEN":"abc"}', encoding="utf-8")
        v = load_vault_json(str(vp))
        assert v["TOKEN"] == "abc"
