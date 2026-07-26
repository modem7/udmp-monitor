import os
import sys

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
