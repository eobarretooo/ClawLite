from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest


def _load_model_usage_module():
    script_path = Path(__file__).resolve().parents[2] / "clawlite" / "skills" / "model-usage" / "scripts" / "model_usage.py"
    spec = importlib.util.spec_from_file_location("clawlite_model_usage_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_positive_int_accepts_valid_numbers() -> None:
    module = _load_model_usage_module()
    assert module.positive_int("1") == 1
    assert module.positive_int("7") == 7


def test_positive_int_rejects_zero_and_negative() -> None:
    module = _load_model_usage_module()
    with pytest.raises(argparse.ArgumentTypeError):
        module.positive_int("0")
    with pytest.raises(argparse.ArgumentTypeError):
        module.positive_int("-3")


def test_filter_by_days_keeps_recent_entries() -> None:
    module = _load_model_usage_module()
    today = date.today()
    entries = [
        {"date": (today - timedelta(days=5)).strftime("%Y-%m-%d"), "modelBreakdowns": []},
        {"date": (today - timedelta(days=1)).strftime("%Y-%m-%d"), "modelBreakdowns": []},
        {"date": today.strftime("%Y-%m-%d"), "modelBreakdowns": []},
    ]

    filtered = module.filter_by_days(entries, 2)

    assert len(filtered) == 2
    assert filtered[0]["date"] == (today - timedelta(days=1)).strftime("%Y-%m-%d")
    assert filtered[1]["date"] == today.strftime("%Y-%m-%d")
