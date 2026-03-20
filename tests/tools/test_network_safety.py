from __future__ import annotations

import ipaddress

import pytest

from clawlite.tools.network_safety import is_blocked_host, is_blocked_network_address, parse_ip_literal


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("100.64.0.1", True),
        ("169.254.169.254", True),
        ("192.88.99.1", True),
        ("198.18.0.1", True),
        ("::1", True),
        ("fe80::1", True),
        ("::ffff:169.254.169.254", True),
        ("64:ff9b::169.254.169.254", True),
        ("93.184.216.34", False),
        ("2606:4700:4700::1111", False),
    ],
)
def test_network_safety_classifies_ip_ranges(value: str, expected: bool) -> None:
    parsed = parse_ip_literal(value)
    assert parsed is not None
    assert is_blocked_network_address(parsed) is expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("localhost", True),
        ("api.localhost", True),
        ("svc.local", True),
        ("db.internal", True),
        ("metadata.google.internal", True),
        ("example.com", False),
    ],
)
def test_network_safety_classifies_hostnames(host: str, expected: bool) -> None:
    assert is_blocked_host(host) is expected


def test_network_safety_accepts_ipaddress_objects() -> None:
    assert is_blocked_network_address(ipaddress.ip_address("100.64.1.10")) is True
    assert is_blocked_network_address(ipaddress.ip_address("93.184.216.34")) is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("127.1", "127.0.0.1"),
        ("2130706433", "127.0.0.1"),
        ("0177.0.0.1", "127.0.0.1"),
    ],
)
def test_network_safety_parses_legacy_ipv4_literals(value: str, expected: str) -> None:
    assert parse_ip_literal(value) == ipaddress.ip_address(expected)
