import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
)
import dashboard_server


def test_allows_localhost():
    assert dashboard_server._host_is_allowed("localhost:8765")


def test_allows_localhost_without_port():
    assert dashboard_server._host_is_allowed("localhost")


def test_allows_ipv4_literal():
    assert dashboard_server._host_is_allowed("127.0.0.1:8765")


def test_allows_lan_ipv4_literal():
    assert dashboard_server._host_is_allowed("192.168.0.50:8765")


def test_allows_ipv6_literal():
    assert dashboard_server._host_is_allowed("[::1]:8765")


def test_rejects_arbitrary_dns_name():
    assert not dashboard_server._host_is_allowed("evil.example.com:8765")


def test_rejects_dns_name_without_port():
    assert not dashboard_server._host_is_allowed("attacker.test")


def test_rejects_missing_host_header():
    assert not dashboard_server._host_is_allowed(None)
    assert not dashboard_server._host_is_allowed("")


def test_get_lan_ip_returns_detected_address():
    fake_socket = MagicMock()
    fake_socket.getsockname.return_value = ("192.168.0.42", 0)
    with patch.object(dashboard_server.socket, "socket", return_value=fake_socket):
        assert dashboard_server._get_lan_ip() == "192.168.0.42"
    fake_socket.close.assert_called_once()


def test_get_lan_ip_returns_none_when_no_network():
    fake_socket = MagicMock()
    fake_socket.connect.side_effect = OSError("network unreachable")
    with patch.object(dashboard_server.socket, "socket", return_value=fake_socket):
        assert dashboard_server._get_lan_ip() is None
    fake_socket.close.assert_called_once()


def _fake_udmp_for_gather():
    """Stub every udmp function gather_live() touches with empty-but-iterable
    defaults, so tests can override just the Protect-related behavior."""
    fake = MagicMock()
    for name in (
        "get_devices",
        "get_clients",
        "get_ap_radios",
        "get_legacy_networks",
        "get_legacy_devices",
        "get_wlans",
        "summarize_wlans",
        "get_firewall_policies",
        "get_firewall_groups",
        "summarize_firewall_policies",
        "summarize_switch_ports",
        "get_known_clients",
        "summarize_known_clients",
        "summarize_networks",
        "summarize_protect_ai_ports",
        "find_radio_overlaps",
    ):
        getattr(fake, name).return_value = []
    fake.get_protect_host.return_value = None
    fake.get_protect_api_key.return_value = None
    return fake


def test_gather_live_omits_protect_when_not_configured():
    fake_udmp = _fake_udmp_for_gather()
    with patch.object(dashboard_server, "udmp", fake_udmp):
        result = dashboard_server.gather_live()
    assert result["protect"] is None
    fake_udmp.make_protect_session.assert_not_called()


def test_gather_live_includes_protect_when_configured():
    fake_udmp = _fake_udmp_for_gather()
    fake_udmp.get_protect_host.return_value = "192.168.0.207"
    fake_udmp.get_protect_api_key.return_value = "key"
    fake_udmp.summarize_protect_status.return_value = {
        "application_version": "7.1.87",
        "nvr": {"name": "Sauron", "arm_status": "disabled"},
        "cameras": [],
        "chimes": [],
    }
    with patch.object(dashboard_server, "udmp", fake_udmp):
        result = dashboard_server.gather_live()
    assert result["protect"] == fake_udmp.summarize_protect_status.return_value
    fake_udmp.make_protect_session.assert_called_once()


def test_gather_live_reports_protect_error_without_failing_whole_payload():
    fake_udmp = _fake_udmp_for_gather()
    fake_udmp.get_protect_host.return_value = "192.168.0.207"
    fake_udmp.get_protect_api_key.return_value = "key"
    fake_udmp.make_protect_session.side_effect = Exception("connection refused")
    with patch.object(dashboard_server, "udmp", fake_udmp):
        result = dashboard_server.gather_live()
    assert result["protect"] == {"error": "connection refused"}
    assert result["devices"] == []


def test_gather_live_includes_ai_ports_independent_of_protect_config():
    fake_udmp = _fake_udmp_for_gather()
    fake_udmp.summarize_protect_ai_ports.return_value = [
        {
            "name": "UVC AI Port",
            "mac": "1c:0b:8b:da:d1:e8",
            "ip": "192.168.40.189",
            "state": "CONNECTED",
            "fw_version": "aiport4G.mt8390.v4.72.14.67.67484d6.241008.0451",
        }
    ]
    with patch.object(dashboard_server, "udmp", fake_udmp):
        result = dashboard_server.gather_live()
    assert result["ai_ports"] == fake_udmp.summarize_protect_ai_ports.return_value
    assert result["protect"] is None
