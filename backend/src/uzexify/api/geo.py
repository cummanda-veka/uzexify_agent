"""Country gate for public traffic. Caddy asks /internal/geo (forward_auth) before every request;
the client IP is the one Caddy itself put into X-Forwarded-For, which outside clients cannot forge.
Country data: DB-IP Country Lite (CC BY 4.0, https://db-ip.com)."""

import ipaddress
import logging
from functools import cache
from pathlib import Path

import maxminddb

log = logging.getLogger(__name__)


@cache
def _reader(path: str) -> maxminddb.Reader | None:
    if not Path(path).exists():
        log.warning("geo database %s missing; country gate is open", path)
        return None
    return maxminddb.open_database(path)


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
    """True for allowed countries, private addresses (server-side and local traffic) and when the
    database is absent; False for every other address, including ones the database cannot place."""
    if not countries or ip is None:
        return True
    try:
        if ipaddress.ip_address(ip).is_private or ipaddress.ip_address(ip).is_loopback:
            return True
    except ValueError:
        return False
    if _reader(path) is None:
        return True
    return country(ip, path) in countries
