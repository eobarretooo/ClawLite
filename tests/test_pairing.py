from __future__ import annotations

import importlib


def _boot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = importlib.import_module("clawlite.config.settings")
    importlib.reload(settings)
    pairing = importlib.import_module("clawlite.runtime.pairing")
    importlib.reload(pairing)
    return settings, pairing


def test_pairing_issue_approve_and_allowlist(monkeypatch, tmp_path):
    settings, pairing = _boot(monkeypatch, tmp_path)

    cfg = settings.load_config()
    cfg.setdefault("security", {}).setdefault("pairing", {})
    cfg["security"]["pairing"]["enabled"] = True
    settings.save_config(cfg)

    req = pairing.issue_pairing_code("telegram", "123456", display="@alice")
    assert req["channel"] == "telegram"
    assert req["peer_id"] == "123456"
    assert len(req["code"]) == 6

    pending = pairing.list_pending("telegram")
    assert any(item["code"] == req["code"] for item in pending)

    allowed_before = pairing.is_sender_allowed("telegram", ["123456"], [])
    assert allowed_before is False

    approved = pairing.approve_pairing("telegram", req["code"])
    assert approved["peer_id"] == "123456"

    allowed_after = pairing.is_sender_allowed("telegram", ["123456"], [])
    assert allowed_after is True

    cfg_after = settings.load_config()
    allow = cfg_after["channels"]["telegram"]["allowFrom"]
    assert "123456" in allow


def test_pairing_reject_removes_pending(monkeypatch, tmp_path):
    settings, pairing = _boot(monkeypatch, tmp_path)

    cfg = settings.load_config()
    cfg.setdefault("security", {}).setdefault("pairing", {})
    cfg["security"]["pairing"]["enabled"] = True
    settings.save_config(cfg)

    req = pairing.issue_pairing_code("whatsapp", "+5511999999999")
    assert pairing.list_pending("whatsapp")

    rejected = pairing.reject_pairing("whatsapp", req["code"])
    assert rejected["peer_id"] == "+5511999999999"
    assert pairing.list_pending("whatsapp") == []
