#!/usr/bin/env python3
"""Local-only live dashboard for the UDMP network documentation.

Binds to 127.0.0.1 by default (VM-local only, no auth) — set
UDMP_DASHBOARD_HOST=0.0.0.0 to expose it to the rest of the LAN if you
want to check it from another device. Never expose this beyond the LAN;
it holds no auth of its own and the credentials it uses live server-side
in .env.

Usage:
    python3 docs/dashboard_server.py
    open http://127.0.0.1:8765
"""

import ipaddress
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import udmp

HOST = os.environ.get("UDMP_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("UDMP_DASHBOARD_PORT", "8765"))
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard-live.html")


def gather_live():
    session = udmp.make_session()
    site_id = udmp.resolve_site_id(session, None)
    devices = udmp.get_devices(session, site_id)
    # get_devices (list) doesn't include `uplink` — only device *detail* does.
    for d in devices:
        d["uplink"] = udmp.get_device_detail(session, site_id, d["id"]).get("uplink")
    clients = udmp.get_clients(session, site_id)
    radios = udmp.get_ap_radios(session, site_id)

    legacy = udmp.make_legacy_session()
    site_name = udmp.resolve_legacy_site_name(legacy, None)
    networks = udmp.get_legacy_networks(legacy, site_name)
    legacy_devices = udmp.get_legacy_devices(legacy, site_name)
    wlans = udmp.summarize_wlans(udmp.get_wlans(legacy, site_name), networks)
    firewall_policies = udmp.summarize_firewall_policies(
        udmp.get_firewall_policies(legacy, site_name), udmp.get_firewall_groups(legacy, site_name)
    )
    firewall_groups = udmp.get_firewall_groups(legacy, site_name)
    ports = udmp.summarize_switch_ports(legacy_devices, networks)
    known_clients = udmp.summarize_known_clients(
        udmp.get_known_clients(legacy, site_name), networks, fixed_ip_only=True
    )

    return {
        "devices": devices,
        "clients": clients,
        "radios": radios,
        "radio_warnings": udmp.find_radio_overlaps(radios),
        "networks": udmp.summarize_networks(networks),
        "ports": ports,
        "wlans": wlans,
        "firewall_policies": firewall_policies,
        "firewall_groups": [
            {
                "name": g.get("name"),
                "type": g.get("group_type"),
                "members": g.get("group_members", []),
            }
            for g in firewall_groups
        ],
        "known_clients": known_clients,
    }


def _host_is_allowed(host_header):
    """DNS-rebinding defense: only serve requests whose Host header is
    'localhost' or a literal IP address — never an arbitrary DNS name.

    A rebinding attack works by having some-domain.com resolve to this
    server's IP *after* the browser already loaded a page from
    some-domain.com, so its same-origin checks think it's still talking to
    that domain — but the Host header it sends is still "some-domain.com",
    not an IP or "localhost". Rejecting anything that isn't one of those
    two shapes closes that off regardless of what UDMP_DASHBOARD_HOST is
    bound to.
    """
    if not host_header:
        return False
    hostname = host_header.rsplit(":", 1)[0] if ":" in host_header else host_header
    hostname = hostname.strip("[]")  # IPv6 literals arrive as [::1]:port
    if hostname == "localhost":
        return True
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep stdout quiet; errors still raise

    def do_GET(self):
        if not _host_is_allowed(self.headers.get("Host")):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Forbidden: Host header not allowed (DNS-rebinding protection)")
            return
        if self.path == "/api/data":
            self._serve_data()
        elif self.path in ("/", "/index.html"):
            self._serve_template()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_data(self):
        try:
            data = gather_live()
            body = json.dumps(data).encode()
            status = 200
        except Exception as e:
            body = json.dumps({"error": str(e)}).encode()
            status = 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_template(self):
        with open(TEMPLATE_PATH, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    udmp.require_api_config()
    udmp.require_ui_config()
    server = HTTPServer((HOST, PORT), Handler)
    print(f"Live dashboard: http://{HOST}:{PORT}  (Ctrl+C to stop)")
    if HOST == "0.0.0.0":
        print("Exposed to the LAN — no auth on this server, only expose on a trusted network.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
