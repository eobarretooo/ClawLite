from __future__ import annotations

import ipaddress
import socket

_BLOCKED_HOST_EXACT = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
    }
)
_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal")
_EXPLICIT_BLOCKED_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),  # carrier-grade NAT
    ipaddress.ip_network("100.100.100.200/32"),  # Alibaba cloud metadata endpoint
    ipaddress.ip_network("192.88.99.0/24"),  # deprecated 6to4 relay anycast
    ipaddress.ip_network("198.18.0.0/15"),  # RFC 2544 benchmark range
    ipaddress.ip_network("192.0.2.0/24"),  # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),  # TEST-NET-3
    ipaddress.ip_network("fec0::/10"),  # deprecated site-local
)
_NAT64_PREFIXES = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)


def parse_ip_literal(value: str) -> ipaddress._BaseAddress | None:
    raw = str(value or "").strip().strip("[]")
    if not raw:
        return None
    if "%" in raw:
        raw = raw.split("%", 1)[0]
    try:
        return ipaddress.ip_address(raw)
    except ValueError:
        if ":" in raw:
            return None
    try:
        return ipaddress.IPv4Address(socket.inet_aton(raw))
    except (OSError, ipaddress.AddressValueError):
        return None


def is_blocked_host(host: str) -> bool:
    normalized = str(host or "").strip().lower().rstrip(".")
    if not normalized:
        return False
    if normalized in _BLOCKED_HOST_EXACT:
        return True
    return any(normalized.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES)


def is_blocked_network_address(ip: ipaddress._BaseAddress) -> bool:
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    if getattr(ip, "is_site_local", False):
        return True
    if any(ip in network for network in _EXPLICIT_BLOCKED_NETWORKS):
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None and is_blocked_network_address(mapped):
            return True
        six_to_four = ip.sixtofour
        if six_to_four is not None and is_blocked_network_address(six_to_four):
            return True
        teredo = ip.teredo
        if teredo is not None and is_blocked_network_address(teredo[1]):
            return True
        if any(ip in network for network in _NAT64_PREFIXES):
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
            if is_blocked_network_address(embedded):
                return True
    return False
