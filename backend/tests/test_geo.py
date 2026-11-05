from pathlib import Path

import pytest

from uzexify.api.geo import allowed

DB = str(Path(__file__).parents[2] / "geo" / "dbip-country-lite.mmdb")


@pytest.mark.skipif(not Path(DB).exists(), reason="geo database not downloaded")
def test_country_gate():
    uz = {"UZ"}
    assert allowed("213.230.64.1", uz, DB)  # Uzbektelecom
    assert not allowed("8.8.8.8", uz, DB)
    assert not allowed("not-an-ip", uz, DB)
    assert allowed("172.18.0.3", uz, DB)  # internal docker traffic (the bot)
    assert allowed("8.8.8.8", set(), DB)  # empty list disables the gate


def test_gate_fails_closed(tmp_path):
    missing = str(tmp_path / "none.mmdb")
    assert not allowed("213.230.64.1", {"UZ"}, missing)  # no database: deny, not open
    assert not allowed(None, {"UZ"}, missing)  # no client IP
    assert allowed("213.230.64.1", set(), missing)  # explicit disable still works
