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
    # Clear first, not just set — otherwise real values from a developer's
    # local .env (loaded once at module import time) leak into any test
    # that doesn't explicitly override a given var, which is exactly what
    # happened with UDMP_UI_USERNAME/PASSWORD before this fixture covered them.
    for var in (
        "UDMP_HOST",
        "UDMP_API_KEY",
        "UDMP_UI_USERNAME",
        "UDMP_UI_PASSWORD",
        "UDMP_PROTECT_HOST",
        "UDMP_PROTECT_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("UDMP_HOST", "udmp.test")
    monkeypatch.setenv("UDMP_API_KEY", "test-key")


def test_base_url_uses_current_env(monkeypatch):
    monkeypatch.setenv("UDMP_HOST", "10.0.0.1")
    assert udmp.base_url() == "https://10.0.0.1/proxy/network/integration/v1"


def test_require_api_config_exits_when_missing(monkeypatch):
    monkeypatch.delenv("UDMP_HOST", raising=False)
    with pytest.raises(SystemExit):
        udmp.require_api_config()


def test_require_api_config_passes_when_set():
    udmp.require_api_config()


def test_require_ui_config_exits_when_missing():
    with pytest.raises(SystemExit):
        udmp.require_ui_config()


def test_require_ui_config_passes_when_set(monkeypatch):
    monkeypatch.setenv("UDMP_UI_USERNAME", "placeholder-user")
    monkeypatch.setenv("UDMP_UI_PASSWORD", "placeholder-pw")
    udmp.require_ui_config()


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


def test_make_legacy_session_logs_in_and_sets_csrf_header(monkeypatch):
    fake_response = MagicMock()
    fake_response.headers = {"x-csrf-token": "tok123"}
    fake_response.raise_for_status = MagicMock()

    class FakeSession:
        def __init__(self):
            self.verify = None
            self.headers = {}

        def post(self, url, json, timeout):
            self.login_url = url
            self.login_payload = json
            return fake_response

    monkeypatch.setenv("UDMP_UI_USERNAME", "placeholder-user")
    monkeypatch.setenv("UDMP_UI_PASSWORD", "placeholder-pw")
    monkeypatch.setattr(udmp.requests, "Session", FakeSession)

    session = udmp.make_legacy_session()
    assert session.headers["x-csrf-token"] == "tok123"
    assert session.login_url == "https://udmp.test/api/auth/login"
    assert session.login_payload == {"username": "placeholder-user", "password": "placeholder-pw"}


def test_get_legacy_sites_returns_data_list():
    session = fake_session({"/self/sites": {"data": [{"name": "default", "desc": "Home"}]}})
    assert udmp.get_legacy_sites(session) == [{"name": "default", "desc": "Home"}]


def test_resolve_legacy_site_name_defaults_to_first_site():
    session = fake_session(
        {
            "/self/sites": {
                "data": [{"name": "default", "desc": "Home"}, {"name": "s2", "desc": "Office"}]
            }
        }
    )
    assert udmp.resolve_legacy_site_name(session, None) == "default"


def test_resolve_legacy_site_name_matches_by_desc():
    session = fake_session(
        {
            "/self/sites": {
                "data": [{"name": "default", "desc": "Home"}, {"name": "s2", "desc": "Office"}]
            }
        }
    )
    assert udmp.resolve_legacy_site_name(session, "Office") == "s2"


def test_resolve_legacy_site_name_unknown_exits():
    session = fake_session({"/self/sites": {"data": [{"name": "default", "desc": "Home"}]}})
    with pytest.raises(SystemExit):
        udmp.resolve_legacy_site_name(session, "nope")


def test_get_wlans_returns_data_list():
    session = fake_session({"/s/default/rest/wlanconf": {"data": [{"name": "MySSID"}]}})
    assert udmp.get_wlans(session, "default") == [{"name": "MySSID"}]


def test_get_legacy_networks_returns_data_list():
    session = fake_session({"/s/default/rest/networkconf": {"data": [{"name": "Default"}]}})
    assert udmp.get_legacy_networks(session, "default") == [{"name": "Default"}]


def test_summarize_wlans_resolves_vlan_and_selects_fields():
    wlans = [
        {
            "name": "Mordor-Guest",
            "enabled": True,
            "is_guest": False,
            "security": "wpapsk",
            "networkconf_id": "net1",
            "some_irrelevant_field": "xyz",
        }
    ]
    networks = [{"_id": "net1", "vlan": 20, "name": "Guest"}]
    summary = udmp.summarize_wlans(wlans, networks)
    assert len(summary) == 1
    row = summary[0]
    assert row["name"] == "Mordor-Guest"
    assert row["is_guest"] is False
    assert row["vlan_id"] == 20
    assert row["network_name"] == "Guest"
    assert "some_irrelevant_field" not in row


def test_summarize_wlans_handles_missing_network():
    wlans = [{"name": "Orphan", "networkconf_id": "missing"}]
    summary = udmp.summarize_wlans(wlans, [])
    assert summary[0]["vlan_id"] is None
    assert summary[0]["network_name"] is None


def test_cmd_wlans_prints_json(capsys):
    session = fake_session(
        {
            "/self/sites": {"data": [{"name": "default", "desc": "Home"}]},
            "/s/default/rest/wlanconf": {
                "data": [{"name": "Mordor", "networkconf_id": "net1", "is_guest": False}]
            },
            "/s/default/rest/networkconf": {
                "data": [{"_id": "net1", "vlan": 1, "name": "Default"}]
            },
        }
    )
    args = MagicMock(site=None)
    udmp.cmd_wlans(args, session)
    out = json.loads(capsys.readouterr().out)
    assert out[0]["name"] == "Mordor"
    assert out[0]["vlan_id"] == 1


def test_get_firewall_policies_returns_raw_list():
    session = fake_session({"/site/default/firewall-policies": [{"name": "Allow X"}]})
    assert udmp.get_firewall_policies(session, "default") == [{"name": "Allow X"}]


def test_get_firewall_groups_returns_data_list():
    session = fake_session({"/s/default/rest/firewallgroup": {"data": [{"name": "Pihole"}]}})
    assert udmp.get_firewall_groups(session, "default") == [{"name": "Pihole"}]


def test_summarize_firewall_policies_filters_predefined_and_sorts_by_index():
    policies = [
        {"index": 10001, "name": "Custom B", "predefined": False, "action": "ALLOW"},
        {"index": 2147483647, "name": "Allow All Traffic", "predefined": True, "action": "ALLOW"},
        {"index": 10000, "name": "Custom A", "predefined": False, "action": "BLOCK"},
    ]
    summary = udmp.summarize_firewall_policies(policies, [])
    assert [p["name"] for p in summary] == ["Custom A", "Custom B"]


def test_summarize_firewall_policies_resolves_group_names():
    policies = [
        {
            "index": 10003,
            "name": "Allow Guest network to Pihole",
            "predefined": False,
            "action": "ALLOW",
            "protocol": "all",
            "enabled": True,
            "source": {"zone_id": "zoneA"},
            "destination": {"zone_id": "zoneB", "ip_group_id": "grp1"},
        }
    ]
    groups = [{"_id": "grp1", "name": "Pihole"}]
    summary = udmp.summarize_firewall_policies(policies, groups)
    assert summary[0]["destination"] == {"zone_id": "zoneB", "group": "Pihole"}
    assert summary[0]["source"] == {"zone_id": "zoneA"}


def test_summarize_firewall_policies_dedupes_repeated_zone_pairs():
    # "any network" rules get stored as one policy doc per concrete zone
    # pair — same index/name/action, different zone_id/destination.
    policies = [
        {
            "index": 10010,
            "name": "Allow Guest to Plex",
            "predefined": False,
            "action": "ALLOW",
            "source": {"zone_id": "zoneA"},
            "destination": {"zone_id": "zoneB", "ip_group_id": "grp1"},
        },
        {
            "index": 10010,
            "name": "Allow Guest to Plex",
            "predefined": False,
            "action": "ALLOW",
            "source": {"zone_id": "zoneA"},
            "destination": {"zone_id": "zoneC", "ip_group_id": "grp1"},
        },
        {
            "index": 10010,
            "name": "Allow Guest to Plex",
            "predefined": False,
            "action": "ALLOW",
            "source": {"zone_id": "zoneA"},
            "destination": {"zone_id": "zoneD", "ip_group_id": "grp1"},
        },
    ]
    groups = [{"_id": "grp1", "name": "HDA Server"}]
    summary = udmp.summarize_firewall_policies(policies, groups)
    assert len(summary) == 1
    assert summary[0]["destination"]["group"] == "HDA Server"


def test_cmd_firewall_prints_json(capsys):
    session = fake_session(
        {
            "/self/sites": {"data": [{"name": "default", "desc": "Home"}]},
            "/site/default/firewall-policies": [
                {
                    "index": 10000,
                    "name": "Custom rule",
                    "predefined": False,
                    "action": "ALLOW",
                    "source": {"zone_id": "z1"},
                    "destination": {"zone_id": "z2"},
                }
            ],
            "/s/default/rest/firewallgroup": {"data": []},
        }
    )
    args = MagicMock(site=None)
    udmp.cmd_firewall(args, session)
    out = json.loads(capsys.readouterr().out)
    assert out[0]["name"] == "Custom rule"


def test_summarize_networks_selects_fields():
    networks = [
        {
            "name": "IoT",
            "purpose": "corporate",
            "vlan": 30,
            "ip_subnet": "192.168.30.1/24",
            "irrelevant_field": "x",
        }
    ]
    summary = udmp.summarize_networks(networks)
    assert summary[0]["name"] == "IoT"
    assert summary[0]["vlan"] == 30
    assert "irrelevant_field" not in summary[0]


def test_get_legacy_devices_returns_data_list():
    session = fake_session({"/s/default/stat/device": {"data": [{"mac": "aa:bb"}]}})
    assert udmp.get_legacy_devices(session, "default") == [{"mac": "aa:bb"}]


def test_summarize_switch_ports_skips_devices_without_overrides():
    devices = [
        {"name": "Gimli", "port_overrides": [{"port_idx": 2, "native_networkconf_id": "net1"}]},
        {"name": "NoOverrides"},
    ]
    networks = [{"_id": "net1", "name": "Default"}]
    summary = udmp.summarize_switch_ports(devices, networks)
    assert len(summary) == 1
    assert summary[0]["device"] == "Gimli"
    assert summary[0]["ports"][0]["native_network"] == "Default"


def test_summarize_switch_ports_sorts_by_port_idx():
    devices = [
        {
            "name": "Gimli",
            "port_overrides": [
                {"port_idx": 3, "native_networkconf_id": "net1"},
                {"port_idx": 1, "native_networkconf_id": "net1"},
            ],
        }
    ]
    summary = udmp.summarize_switch_ports(devices, [{"_id": "net1", "name": "Default"}])
    assert [p["port_idx"] for p in summary[0]["ports"]] == [1, 3]


def test_get_known_clients_returns_data_list():
    session = fake_session({"/s/default/rest/user": {"data": [{"mac": "aa:bb"}]}})
    assert udmp.get_known_clients(session, "default") == [{"mac": "aa:bb"}]


def test_summarize_known_clients_filters_to_fixed_ip_by_default():
    clients = [
        {"name": "Server", "mac": "aa", "use_fixedip": True, "fixed_ip": "192.168.0.5"},
        {"name": "Phone", "mac": "bb", "use_fixedip": False, "last_ip": "192.168.0.99"},
    ]
    summary = udmp.summarize_known_clients(clients, [])
    assert len(summary) == 1
    assert summary[0]["name"] == "Server"
    assert summary[0]["fixed_ip"] is True


def test_summarize_known_clients_all_includes_dynamic():
    clients = [
        {"name": "Server", "mac": "aa", "use_fixedip": True, "fixed_ip": "192.168.0.5"},
        {"name": "Phone", "mac": "bb", "use_fixedip": False, "last_ip": "192.168.0.99"},
    ]
    summary = udmp.summarize_known_clients(clients, [], fixed_ip_only=False)
    assert len(summary) == 2


def test_summarize_known_clients_resolves_network_and_protect_model():
    clients = [
        {
            "name": "Sauron",
            "mac": "cc",
            "use_fixedip": True,
            "fixed_ip": "192.168.0.207",
            "network_id": "net1",
            "unifi_device_info_from_ucore": {"computed_model": "UNVR"},
        }
    ]
    networks = [{"_id": "net1", "name": "Default"}]
    summary = udmp.summarize_known_clients(clients, networks)
    assert summary[0]["network"] == "Default"
    assert summary[0]["product_model"] == "UNVR"


def test_cmd_networks_prints_json(capsys):
    session = fake_session(
        {
            "/self/sites": {"data": [{"name": "default", "desc": "Home"}]},
            "/s/default/rest/networkconf": {"data": [{"name": "IoT", "vlan": 30}]},
        }
    )
    args = MagicMock(site=None)
    udmp.cmd_networks(args, session)
    out = json.loads(capsys.readouterr().out)
    assert out[0]["name"] == "IoT"


def test_cmd_ports_prints_json(capsys):
    session = fake_session(
        {
            "/self/sites": {"data": [{"name": "default", "desc": "Home"}]},
            "/s/default/stat/device": {
                "data": [
                    {
                        "name": "Gimli",
                        "port_overrides": [{"port_idx": 1, "native_networkconf_id": "net1"}],
                    }
                ]
            },
            "/s/default/rest/networkconf": {"data": [{"_id": "net1", "name": "Default"}]},
        }
    )
    args = MagicMock(site=None)
    udmp.cmd_ports(args, session)
    out = json.loads(capsys.readouterr().out)
    assert out[0]["device"] == "Gimli"


def test_cmd_known_clients_prints_json(capsys):
    session = fake_session(
        {
            "/self/sites": {"data": [{"name": "default", "desc": "Home"}]},
            "/s/default/rest/user": {
                "data": [
                    {"name": "Server", "mac": "aa", "use_fixedip": True, "fixed_ip": "10.0.0.1"}
                ]
            },
            "/s/default/rest/networkconf": {"data": []},
        }
    )
    args = MagicMock(site=None, all=False)
    udmp.cmd_known_clients(args, session)
    out = json.loads(capsys.readouterr().out)
    assert out[0]["name"] == "Server"


def test_require_protect_config_exits_when_missing():
    with pytest.raises(SystemExit):
        udmp.require_protect_config()


def test_require_protect_config_passes_when_set(monkeypatch):
    monkeypatch.setenv("UDMP_PROTECT_HOST", "protect.test")
    monkeypatch.setenv("UDMP_PROTECT_API_KEY", "protect-key")
    udmp.require_protect_config()


def test_make_protect_session_sets_api_key_header(monkeypatch):
    monkeypatch.setenv("UDMP_PROTECT_HOST", "protect.test")
    monkeypatch.setenv("UDMP_PROTECT_API_KEY", "protect-key")
    session = udmp.make_protect_session()
    assert session.headers["X-API-Key"] == "protect-key"


def test_get_protect_meta_returns_json():
    session = fake_session({"/meta/info": {"applicationVersion": "7.1.87"}})
    assert udmp.get_protect_meta(session) == {"applicationVersion": "7.1.87"}


def test_get_protect_nvr_returns_json():
    session = fake_session({"/nvrs": {"name": "Sauron"}})
    assert udmp.get_protect_nvr(session) == {"name": "Sauron"}


def test_get_protect_cameras_returns_json():
    session = fake_session({"/cameras": [{"name": "Doorbell"}]})
    assert udmp.get_protect_cameras(session) == [{"name": "Doorbell"}]


def test_get_protect_chimes_returns_json():
    session = fake_session({"/chimes": [{"name": "Upstairs Chime"}]})
    assert udmp.get_protect_chimes(session) == [{"name": "Upstairs Chime"}]


def test_summarize_protect_status_shapes_output():
    meta = {"applicationVersion": "7.1.87"}
    nvr = {"name": "Sauron", "armMode": {"status": "disabled"}}
    cameras = [{"name": "Doorbell", "mac": "aa:bb", "state": "CONNECTED"}]
    chimes = [{"name": "Chime", "mac": "cc:dd", "state": "CONNECTED"}]
    summary = udmp.summarize_protect_status(meta, nvr, cameras, chimes)
    assert summary["application_version"] == "7.1.87"
    assert summary["nvr"] == {"name": "Sauron", "arm_status": "disabled"}
    assert summary["cameras"] == [{"name": "Doorbell", "mac": "aa:bb", "state": "CONNECTED"}]
    assert summary["chimes"] == [{"name": "Chime", "mac": "cc:dd", "state": "CONNECTED"}]


def test_summarize_protect_status_handles_missing_arm_mode():
    summary = udmp.summarize_protect_status({}, {"name": "Sauron"}, [], [])
    assert summary["nvr"]["arm_status"] is None


def test_cmd_protect_status_prints_json(capsys):
    session = fake_session(
        {
            "/meta/info": {"applicationVersion": "7.1.87"},
            "/nvrs": {"name": "Sauron", "armMode": {"status": "disabled"}},
            "/cameras": [{"name": "Doorbell", "mac": "aa:bb", "state": "CONNECTED"}],
            "/chimes": [{"name": "Chime", "mac": "cc:dd", "state": "CONNECTED"}],
        }
    )
    args = MagicMock()
    udmp.cmd_protect_status(args, session)
    out = json.loads(capsys.readouterr().out)
    assert out["application_version"] == "7.1.87"
    assert out["cameras"][0]["name"] == "Doorbell"
