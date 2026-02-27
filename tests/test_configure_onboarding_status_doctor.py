from __future__ import annotations

import tempfile
from pathlib import Path

from clawlite.config import settings
from clawlite.configure_menu import _ensure_defaults, run_configure_menu
from clawlite.onboarding import run_onboarding
from clawlite.runtime.doctor import run_doctor
from clawlite.runtime.locale import detect_language
from clawlite.runtime.status import runtime_status


def _patch_config_home(tmpdir: str):
    old_dir = settings.CONFIG_DIR
    old_path = settings.CONFIG_PATH
    settings.CONFIG_DIR = Path(tmpdir) / "cfg"
    settings.CONFIG_PATH = settings.CONFIG_DIR / "config.json"
    return old_dir, old_path


def test_detect_language_ptbr(monkeypatch):
    monkeypatch.setenv("LANG", "pt_BR.UTF-8")
    assert detect_language() == "pt-br"


def test_ensure_defaults_contains_required_sections():
    cfg = {}
    _ensure_defaults(cfg)
    assert "hooks" in cfg
    assert "web_tools" in cfg
    assert "security" in cfg
    assert "language" in cfg
    assert "whatsapp" in cfg["channels"]
    assert "slack" in cfg["channels"]
    assert "teams" in cfg["channels"]


def test_doctor_and_status_minimum_output():
    tmp = tempfile.TemporaryDirectory()
    old_dir, old_path = _patch_config_home(tmp.name)
    try:
        settings.save_config(settings.DEFAULT_CONFIG)
        out_doctor = run_doctor()
        out_status = runtime_status()
        assert "ClawLite Doctor" in out_doctor
        assert "sqlite:" in out_doctor
        assert "ClawLite Status" in out_status
        assert "gateway:" in out_status
    finally:
        settings.CONFIG_DIR = old_dir
        settings.CONFIG_PATH = old_path
        tmp.cleanup()


def test_configure_menu_non_tty_fallback(monkeypatch):
    import clawlite.configure_menu as configure_menu

    tmp = tempfile.TemporaryDirectory()
    old_dir, old_path = _patch_config_home(tmp.name)

    try:
        settings.save_config(settings.DEFAULT_CONFIG)
        monkeypatch.setattr(configure_menu.sys.stdin, "isatty", lambda: False, raising=False)
        monkeypatch.setattr(configure_menu.sys.stdout, "isatty", lambda: False, raising=False)
        run_configure_menu()
        cfg = settings.load_config()
        assert "gateway" in cfg
        assert "language" in cfg
    finally:
        settings.CONFIG_DIR = old_dir
        settings.CONFIG_PATH = old_path
        tmp.cleanup()


def test_onboarding_wizard_saves_without_manual_json(monkeypatch):
    import clawlite.onboarding as onboarding

    tmp = tempfile.TemporaryDirectory()
    old_dir, old_path = _patch_config_home(tmp.name)

    def fake_step(cfg):
        cfg["model"] = "openai/gpt-4o-mini"

    class _Q:
        def ask(self):
            return True

    try:
        monkeypatch.setattr(onboarding, "_section_language", fake_step)
        monkeypatch.setattr(onboarding, "_section_model", fake_step)
        monkeypatch.setattr(onboarding, "_section_identity", fake_step)
        monkeypatch.setattr(onboarding, "_section_channels", fake_step)
        monkeypatch.setattr(onboarding, "_skills_quickstart_profile", fake_step)
        monkeypatch.setattr(onboarding, "_section_skills", fake_step)
        monkeypatch.setattr(onboarding, "_section_hooks", fake_step)
        monkeypatch.setattr(onboarding, "_section_gateway", fake_step)
        monkeypatch.setattr(onboarding, "_section_web_tools", fake_step)
        monkeypatch.setattr(onboarding, "_section_security", fake_step)
        monkeypatch.setattr(onboarding.questionary, "confirm", lambda *a, **k: _Q())

        run_onboarding()
        cfg = settings.load_config()
        assert cfg["model"] == "openai/gpt-4o-mini"
    finally:
        settings.CONFIG_DIR = old_dir
        settings.CONFIG_PATH = old_path
        tmp.cleanup()
