"""Tests for exec network-fetch guard (upstream port + VikingEdition integration)."""
from __future__ import annotations

import pytest

from clawlite.tools.exec import ExecTool


def _tool() -> ExecTool:
    return ExecTool()


# ── _validate_network_fetch_url ────────────────────────────────────────────────

def test_validate_allows_public_url():
    assert _tool()._validate_network_fetch_url("https://example.com/data") is None


def test_validate_blocks_localhost():
    err = _tool()._validate_network_fetch_url("http://localhost/api")
    assert err is not None
    assert "internal_url" in err


def test_validate_blocks_metadata_ip():
    err = _tool()._validate_network_fetch_url("http://169.254.169.254/latest/meta-data")
    assert err is not None
    assert "internal_url" in err


def test_validate_blocks_127_0_0_1():
    err = _tool()._validate_network_fetch_url("http://127.0.0.1/admin")
    assert err is not None
    assert "internal_url" in err


def test_validate_non_http_scheme_ignored():
    # ftp:// is not http/https — guard ignores it (not an HTTP fetch target)
    assert _tool()._validate_network_fetch_url("ftp://example.com") is None


def test_validate_empty_url():
    assert _tool()._validate_network_fetch_url("") is None


# ── _guard_inline_runtime_fetch_targets ───────────────────────────────────────

def test_python_inline_network_fetch_blocked():
    import shlex
    argv = shlex.split('python3 -c "import requests; requests.get(\'http://169.254.169.254/\')"')
    err = _tool()._guard_inline_runtime_fetch_targets(argv)
    assert err is not None
    assert "internal_url" in err


def test_python_inline_public_url_allowed():
    import shlex
    argv = shlex.split('python3 -c "import requests; requests.get(\'https://api.example.com/\')"')
    assert _tool()._guard_inline_runtime_fetch_targets(argv) is None


def test_node_inline_fetch_blocked():
    import shlex
    argv = shlex.split('node -e "fetch(\'http://localhost:8080/secret\')"')
    err = _tool()._guard_inline_runtime_fetch_targets(argv)
    assert err is not None


def test_non_network_python_allowed():
    import shlex
    argv = shlex.split('python3 -c "print(1+1)"')
    assert _tool()._guard_inline_runtime_fetch_targets(argv) is None


def test_node_print_flag_blocked():
    import shlex
    argv = shlex.split('node -p "fetch(\'http://127.0.0.1/\').then(r=>r.text())"')
    err = _tool()._guard_inline_runtime_fetch_targets(argv)
    assert err is not None


# ── _guard_network_fetch_targets ──────────────────────────────────────────────

def test_curl_internal_url_blocked():
    argv = ["curl", "http://169.254.169.254/latest/meta-data"]
    err = _tool()._guard_network_fetch_targets(argv)
    assert err is not None
    assert "internal_url" in err


def test_curl_public_url_allowed():
    argv = ["curl", "https://example.com/data"]
    assert _tool()._guard_network_fetch_targets(argv) is None


def test_wget_internal_blocked():
    argv = ["wget", "http://localhost/secret"]
    err = _tool()._guard_network_fetch_targets(argv)
    assert err is not None


def test_env_wrapped_python_blocked():
    import shlex
    argv = shlex.split('env python3 -c "import requests; requests.get(\'http://127.0.0.1/\')"')
    err = _tool()._guard_network_fetch_targets(argv)
    assert err is not None
