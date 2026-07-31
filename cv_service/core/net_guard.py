"""
Outbound camera-URL safety guard (SSRF mitigation).

Before the CV service connects to a camera stream (RTSP or HTTP
snapshot), the URL's hostname must resolve to public, non-private
address space. Private/loopback/link-local/reserved/unspecified targets
raise ValueError so callers abort the camera start with an HTTP 400.

Local sources are explicitly allowed because they are not network URLs:
``/dev/video*`` USB cameras and the internal ``browser:`` / ``client:``
WebSocket camera modes.

The check resolves hostnames through the system resolver (socket)
because a bare string comparison cannot catch names that resolve to
internal IPs.
"""

import ipaddress
import socket
from typing import List
from urllib.parse import urlparse

_ALLOWED_SCHEMES = ("rtsp://", "http://", "https://")
_LOCAL_PREFIXES = ("/dev/video", "browser:", "client:")
_BLOCKED_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


def _resolve_host(hostname: str) -> List[ipaddress._BaseAddress]:
    """Resolve a hostname to every IP address it maps to (v4 + v6).

    Raises ValueError when the hostname does not resolve, so a
    non-DNS-safe URL is rejected rather than connected to later.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Could not resolve hostname {hostname!r}: {exc}") from exc

    addresses: List[ipaddress._BaseAddress] = []
    for info in infos:
        ip_str = info[4][0]
        try:
            addresses.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue

    if not addresses:
        raise ValueError(f"Hostname {hostname!r} resolved to no usable addresses")
    return addresses


def assert_safe_rtsp(url: str) -> str:
    """Validate that a camera URL is safe to connect to.

    Returns the URL unchanged on success. Raises ValueError when the URL
    is empty, malformed, uses a disallowed scheme, or points at
    private/loopback/link-local/reserved/unspecified address space —
    directly or through DNS resolution.
    """
    if not url or not url.strip():
        raise ValueError("Camera URL cannot be empty")
    url = url.strip()

    if ".." in url or "\n" in url or "\r" in url:
        raise ValueError("Invalid characters in URL")

    # Local sources are not network URLs.
    if url.startswith(_LOCAL_PREFIXES):
        return url

    if not url.lower().startswith(_ALLOWED_SCHEMES):
        raise ValueError(
            "URL must start with one of: rtsp://, http://, https://, /dev/video"
        )

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")

    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError("URLs pointing to internal addresses are not allowed")

    for address in _resolve_host(hostname):
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ValueError(
                f"URL host {hostname!r} resolves to a non-public address ({address})"
            )

    return url
