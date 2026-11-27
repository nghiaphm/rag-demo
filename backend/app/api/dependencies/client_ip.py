"""Safe client IP extraction with explicit trusted reverse-proxy allowlist."""

from __future__ import annotations

from collections.abc import Sequence
import ipaddress
from typing import Any


def _is_trusted_proxy(direct_host: str, trusted_proxy_ips: Sequence[str]) -> bool:
    if not direct_host or not trusted_proxy_ips:
        return False
    try:
        direct_ip = ipaddress.ip_address(direct_host)
    except ValueError:
        return direct_host in {entry.strip() for entry in trusted_proxy_ips if entry and entry.strip()}

    for raw_entry in trusted_proxy_ips:
        entry = (raw_entry or "").strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if direct_ip in ipaddress.ip_network(entry, strict=False):
                    return True
            elif direct_ip == ipaddress.ip_address(entry):
                return True
        except ValueError:
            if direct_host == entry:
                return True
    return False


def resolve_client_ip(request: Any, trusted_proxy_ips: Sequence[str] = ()) -> str:
    """Return real client IP safely, trusting X-Forwarded-For ONLY from trusted proxies."""
    client_obj = getattr(request, "client", None)
    direct_host = str(getattr(client_obj, "host", "") or "").strip()

    if direct_host and _is_trusted_proxy(direct_host, trusted_proxy_ips):
        headers = getattr(request, "headers", None) or {}
        xff = str(headers.get("x-forwarded-for", "") or "").strip()
        if xff:
            first_hop = xff.split(",", 1)[0].strip()
            if first_hop:
                try:
                    return str(ipaddress.ip_address(first_hop))
                except ValueError:
                    pass

    return direct_host or "anonymous"
