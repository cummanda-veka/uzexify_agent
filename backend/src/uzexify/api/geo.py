"""Country gate for public traffic. Caddy asks /internal/geo (forward_auth) before every request;
the client IP is the one Caddy itself put into X-Forwarded-For, which outside clients cannot forge.
Country data: DB-IP Country Lite (CC BY 4.0, https://db-ip.com)."""

import ipaddress
import logging
from pathlib import Path

import maxminddb

log = logging.getLogger(__name__)

_readers: dict[str, maxminddb.Reader] = {}


def _reader(path: str) -> maxminddb.Reader | None:
    """Open once; a missing file is retried on the next request, not cached."""
    if path not in _readers:
        if not Path(path).exists():
            log.error("geo database %s missing; country gate denies all public traffic", path)
            return None
        _readers[path] = maxminddb.open_database(path)
    return _readers[path]


def country(ip: str, path: str) -> str | None:
    reader = _reader(path)
    if reader is None:
        return None
    try:
        record = reader.get(ip)
    except ValueError:
        return None
    if isinstance(record, dict):
        found = record.get("country")
        code = found.get("iso_code") if isinstance(found, dict) else None
        return code if isinstance(code, str) else None
    return None


def allowed(ip: str | None, countries: set[str], path: str) -> bool:
    """An empty country list disables the gate. Otherwise only allowed countries and private
    addresses (internal traffic) pass; no IP, an unparsable IP, an unknown country or a missing
    database all deny."""
    if not countries:
        return True
    if ip is None:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.is_private or addr.is_loopback:
        return True
    return country(ip, path) in countries
