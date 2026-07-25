from unittest.mock import MagicMock

import pytest
import requests

import udmp


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def fake_session(routes):
    """routes: dict mapping URL suffix -> payload"""
    session = MagicMock()

    def get(url, timeout=10):
        for suffix, payload in routes.items():
            if url.endswith(suffix):
                return FakeResponse(payload)
        raise AssertionError(f"unexpected URL: {url}")

    session.get.side_effect = get
    return session


@pytest.fixture(autouse=True)
def udmp_env(monkeypatch):
    monkeypatch.setenv("UDMP_HOST", "udmp.test")
    monkeypatch.setenv("UDMP_API_KEY", "test-key")


def test_base_url_uses_current_env(monkeypatch):
    monkeypatch.setenv("UDMP_HOST", "10.0.0.1")
    assert udmp.base_url() == "https://10.0.0.1/proxy/network/integration/v1"


def test_require_config_exits_when_missing(monkeypatch):
    monkeypatch.delenv("UDMP_HOST", raising=False)
    with pytest.raises(SystemExit):
        udmp.require_config()


def test_require_config_passes_when_set():
    udmp.require_config()


def test_make_session_sets_api_key_header():
    session = udmp.make_session()
    assert session.headers["X-API-Key"] == "test-key"


def test_get_sites_returns_data_list():
    session = fake_session({"/sites": {"data": [{"id": "s1", "name": "Home"}]}})
    assert udmp.get_sites(session) == [{"id": "s1", "name": "Home"}]


def test_resolve_site_id_defaults_to_first_site():
    session = fake_session(
        {"/sites": {"data": [{"id": "s1", "name": "Home"}, {"id": "s2", "name": "Office"}]}}
    )
    assert udmp.resolve_site_id(session, None) == "s1"


def test_resolve_site_id_matches_by_name():
    session = fake_session(
        {"/sites": {"data": [{"id": "s1", "name": "Home"}, {"id": "s2", "name": "Office"}]}}
    )
    assert udmp.resolve_site_id(session, "Office") == "s2"


def test_resolve_site_id_matches_by_id():
    session = fake_session({"/sites": {"data": [{"id": "s1", "name": "Home"}]}})
    assert udmp.resolve_site_id(session, "s1") == "s1"


def test_resolve_site_id_unknown_site_exits():
    session = fake_session({"/sites": {"data": [{"id": "s1", "name": "Home"}]}})
    with pytest.raises(SystemExit):
        udmp.resolve_site_id(session, "nope")


def test_resolve_site_id_no_sites_exits():
    session = fake_session({"/sites": {"data": []}})
    with pytest.raises(SystemExit):
        udmp.resolve_site_id(session, None)


def test_get_devices_returns_data_list():
    session = fake_session({"/sites/s1/devices": {"data": [{"name": "Switch"}]}})
    assert udmp.get_devices(session, "s1") == [{"name": "Switch"}]


def test_get_clients_returns_data_list():
    session = fake_session({"/sites/s1/clients": {"data": [{"name": "laptop"}]}})
    assert udmp.get_clients(session, "s1") == [{"name": "laptop"}]


def test_cmd_devices_prints_rows(capsys):
    session = fake_session(
        {
            "/sites": {"data": [{"id": "s1", "name": "Home"}]},
            "/sites/s1/devices": {
                "data": [
                    {"name": "USW", "model": "US-8", "state": "ONLINE", "ipAddress": "10.0.0.2"}
                ]
            },
        }
    )
    args = MagicMock(site=None)
    udmp.cmd_devices(args, session)
    out = capsys.readouterr().out
    assert "USW" in out
    assert "10.0.0.2" in out


def test_build_parser_requires_a_command():
    parser = udmp.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_build_parser_accepts_devices_with_site():
    parser = udmp.build_parser()
    args = parser.parse_args(["devices", "--site", "Home"])
    assert args.command == "devices"
    assert args.site == "Home"
