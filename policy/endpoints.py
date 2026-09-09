from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def validate_http_endpoint(
    url: str,
    *,
    allowed_hosts: list[str],
    allow_http_loopback: bool = True,
) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Endpoint scheme must be http or https")
    if not parsed.hostname:
        raise ValueError("Endpoint must include a hostname")
    if parsed.username or parsed.password:
        raise ValueError("Endpoint must not contain embedded credentials")
    if parsed.fragment or parsed.query:
        raise ValueError("Endpoint base URL must not contain query or fragment")

    hostname = parsed.hostname.lower().rstrip(".")
    normalized_allowed = {host.lower().rstrip(".") for host in allowed_hosts}
    if hostname not in normalized_allowed:
        raise ValueError(f"Endpoint host is not allowlisted: {hostname}")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None

    if address is not None:
        if address.is_link_local:
            raise ValueError("Link-local and metadata endpoints are forbidden")
        if address.is_private and not address.is_loopback and hostname not in normalized_allowed:
            raise ValueError("Private endpoint is not explicitly allowlisted")

    if parsed.scheme == "http":
        is_loopback = hostname == "localhost" or (address is not None and address.is_loopback)
        if not (allow_http_loopback and is_loopback):
            raise ValueError("Non-loopback endpoints must use HTTPS")
    return url.rstrip("/")
