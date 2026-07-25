import json
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


def test_cmd_devices_prints_json(capsys):
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
    out = json.loads(capsys.readouterr().out)
    assert out == [{"name": "USW", "model": "US-8", "state": "ONLINE", "ipAddress": "10.0.0.2"}]


def test_build_parser_requires_a_command():
    parser = udmp.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_get_device_detail_returns_json():
    session = fake_session({"/sites/s1/devices/d1": {"id": "d1", "name": "AP"}})
    assert udmp.get_device_detail(session, "s1", "d1") == {"id": "d1", "name": "AP"}


def test_get_ap_radios_skips_non_ap_devices_and_flattens_radios():
    session = fake_session(
        {
            "/sites/s1/devices": {
                "data": [
                    {"id": "ap1", "name": "Legolas", "interfaces": ["radios"]},
                    {"id": "sw1", "name": "Switch", "interfaces": []},
                ]
            },
            "/sites/s1/devices/ap1": {
                "interfaces": {
                    "radios": [
                        {"frequencyGHz": 2.4, "channel": 1, "channelWidthMHz": 20},
                        {"frequencyGHz": 5, "channel": 153, "channelWidthMHz": 80},
                    ]
                }
            },
        }
    )
    radios = udmp.get_ap_radios(session, "s1")
    assert len(radios) == 2
    assert radios[0]["device"] == "Legolas"
    assert radios[0]["channel"] == 1


def test_find_radio_overlaps_flags_co_channel():
    radios = [
        {"device": "AP1", "frequencyGHz": 5, "channel": 100, "channelWidthMHz": 80},
        {"device": "AP2", "frequencyGHz": 5, "channel": 100, "channelWidthMHz": 80},
    ]
    warnings = udmp.find_radio_overlaps(radios)
    assert len(warnings) == 1
    assert "co-channel" in warnings[0]


def test_find_radio_overlaps_flags_close_24ghz_channels():
    radios = [
        {"device": "AP1", "frequencyGHz": 2.4, "channel": 1, "channelWidthMHz": 20},
        {"device": "AP2", "frequencyGHz": 2.4, "channel": 3, "channelWidthMHz": 20},
    ]
    warnings = udmp.find_radio_overlaps(radios)
    assert len(warnings) == 1
    assert "overlap" in warnings[0]


def test_find_radio_overlaps_allows_spaced_24ghz_channels():
    radios = [
        {"device": "AP1", "frequencyGHz": 2.4, "channel": 1, "channelWidthMHz": 20},
        {"device": "AP2", "frequencyGHz": 2.4, "channel": 6, "channelWidthMHz": 20},
        {"device": "AP3", "frequencyGHz": 2.4, "channel": 11, "channelWidthMHz": 20},
    ]
    assert udmp.find_radio_overlaps(radios) == []


def test_find_radio_overlaps_ignores_different_bands():
    radios = [
        {"device": "AP1", "frequencyGHz": 2.4, "channel": 1, "channelWidthMHz": 20},
        {"device": "AP2", "frequencyGHz": 5, "channel": 1, "channelWidthMHz": 80},
    ]
    assert udmp.find_radio_overlaps(radios) == []


def test_cmd_radios_prints_json_with_warnings(capsys):
    session = fake_session(
        {
            "/sites": {"data": [{"id": "s1", "name": "Home"}]},
            "/sites/s1/devices": {
                "data": [
                    {"id": "ap1", "name": "Legolas", "interfaces": ["radios"]},
                    {"id": "ap2", "name": "Aragorn", "interfaces": ["radios"]},
                ]
            },
            "/sites/s1/devices/ap1": {
                "interfaces": {
                    "radios": [{"frequencyGHz": 2.4, "channel": 1, "channelWidthMHz": 20}]
                }
            },
            "/sites/s1/devices/ap2": {
                "interfaces": {
                    "radios": [{"frequencyGHz": 2.4, "channel": 1, "channelWidthMHz": 20}]
                }
            },
        }
    )
    args = MagicMock(site=None)
    udmp.cmd_radios(args, session)
    out = json.loads(capsys.readouterr().out)
    assert len(out["radios"]) == 2
    assert {r["device"] for r in out["radios"]} == {"Legolas", "Aragorn"}
    assert len(out["warnings"]) == 1
    assert "co-channel" in out["warnings"][0]


def test_build_parser_accepts_devices_with_site():
    parser = udmp.build_parser()
    args = parser.parse_args(["devices", "--site", "Home"])
    assert args.command == "devices"
    assert args.site == "Home"
