"""SSRF protection for agent-controlled URL fetching.

Blocks requests to private/internal networks, loopback addresses,
link-local ranges, and known cloud IMDS endpoints to prevent
Server-Side Request Forgery when the LLM is influenced by
attacker-controlled profile data (e.g. a GitHub bio containing
``http://169.254.169.254/latest/meta-data/``).

See: https://github.com/Doble-2/osint-d2/issues/25
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# ── Blocked hostnames (case-insensitive) ──────────────────────────────────

_BLOCKED_HOSTS: frozenset[str] = frozenset({
    "localhost",
    "0.0.0.0",
    # Cloud IMDS endpoints
    "metadata.google.internal",         # GCP
    "metadata.goog",                    # GCP alternative
    "169.254.169.254",                  # AWS / Azure / most clouds
    "metadata.azure.com",              # Azure
})

# ── Private / reserved IP ranges ──────────────────────────────────────────

_PRIVATE_RANGES: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),        # "this" network
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),    # carrier-grade NAT
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / IMDS
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),     # IETF protocol assignments
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),    # benchmarking
    # IPv6
    ipaddress.ip_network("::1/128"),          # loopback
    ipaddress.ip_network("fc00::/7"),         # unique local
    ipaddress.ip_network("fe80::/10"),        # link-local
)


def _is_private_ip(host: str) -> bool:
    """Return True if *host* is a literal IP in a private/reserved range."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _PRIVATE_RANGES)


def _resolves_to_private(hostname: str) -> bool:
    """Resolve *hostname* via DNS and check whether any result is private.

    This catches cases like a custom domain that DNS-resolves to 127.0.0.1
    or an internal IP (DNS rebinding / split-horizon scenarios).
    """
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        # DNS resolution failed — allow the request to proceed (httpx will
        # raise its own error).
        return False

    for _family, _type, _proto, _canonname, sockaddr in results:
        ip_str = sockaddr[0]
        if _is_private_ip(ip_str):
            return True
    return False


class SSRFBlockedError(Exception):
    """Raised when a URL targets a blocked host or private network."""


def validate_url(url: str) -> str:
    """Validate *url* for SSRF safety and return the normalised URL.

    Raises
    ------
    SSRFBlockedError
        If the URL targets a private/internal address or a blocked host.
    ValueError
        If the URL is malformed.
    """
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()

    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {scheme!r}")

    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError("URL has no hostname")

    # 1) Blocked hostname check
    if host in _BLOCKED_HOSTS:
        raise SSRFBlockedError(
            f"Blocked: {host!r} is a known internal/IMDS hostname"
        )

    # 2) Literal IP check
    if _is_private_ip(host):
        raise SSRFBlockedError(
            f"Blocked: {host!r} is in a private/reserved IP range"
        )

    # 3) DNS resolution check (catches DNS rebinding to internal IPs)
    if _resolves_to_private(host):
        raise SSRFBlockedError(
            f"Blocked: {host!r} resolves to a private/reserved IP address"
        )

    return url
