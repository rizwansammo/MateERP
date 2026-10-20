"""Client address resolution that only trusts configured proxies."""

import ipaddress
from functools import lru_cache

from django.conf import settings
from django.http import HttpRequest

Network = ipaddress.IPv4Network | ipaddress.IPv6Network


@lru_cache(maxsize=8)
def _trusted_networks(cidrs: tuple[str, ...]) -> tuple[Network, ...]:
    return tuple(ipaddress.ip_network(c.strip(), strict=False) for c in cidrs if c.strip())


def _is_trusted(address: str, networks: tuple[Network, ...]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in networks)


def client_ip(request: HttpRequest) -> str | None:
    """Best-effort client IP for security decisions.

    ``REMOTE_ADDR`` is authoritative. ``X-Forwarded-For`` is consulted only
    when the direct peer is a trusted proxy, and then the right-most address
    that is not itself a trusted proxy is used, so a client cannot spoof its
    address by prepending entries.
    """
    remote = request.META.get("REMOTE_ADDR") or None
    networks = _trusted_networks(tuple(settings.MATEERP_TRUSTED_PROXIES))
    if not remote or not networks or not _is_trusted(remote, networks):
        return remote

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    for candidate in reversed([part.strip() for part in forwarded.split(",") if part.strip()]):
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            return remote
        if not _is_trusted(candidate, networks):
            return candidate
    return remote
