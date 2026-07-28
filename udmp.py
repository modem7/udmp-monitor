#!/usr/bin/env python3
import argparse
import json
import os
import sys

import requests
import urllib3
from dotenv import load_dotenv

load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Commands routed through the legacy session API (UDMP_UI_USERNAME/PASSWORD)
# rather than the Integration API (UDMP_API_KEY).
LEGACY_API_COMMANDS = {"wlans", "firewall", "networks", "ports", "known-clients"}


def _env(name):
    """Read an env var and strip whitespace + one layer of matching
    quotes, since a value can reach os.environ already-quoted through
    paths python-dotenv never touches:

    - `docker run --env-file .env` / Compose's `env_file:` pass KEY="value"
      lines through literally, quotes and all — confirmed by testing
      directly (`docker run --env-file .env alpine sh -c 'echo $VAR'`
      prints the quotes). python-dotenv's own quote-stripping only
      applies when *it* parses the .env file; it never runs inside a
      container using --env-file.
    - Even locally, `load_dotenv()` defaults to `override=False`, so a
      value already exported in the shell (e.g. a stray
      `export UDMP_HOST='"192.168.0.200"'`) wins over the correctly-parsed
      .env file value and keeps its literal quotes.

    Without this, a quoted value produces a working-looking config that
    fails deep inside `requests` with a confusing NameResolutionError
    quoting a URL-encoded hostname, rather than a clear error here.
    """
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def get_host():
    return _env("UDMP_HOST")


def get_api_key():
    return _env("UDMP_API_KEY")


def get_ui_username():
    return _env("UDMP_UI_USERNAME")


def get_ui_password():
    return _env("UDMP_UI_PASSWORD")


def get_protect_host():
    return _env("UDMP_PROTECT_HOST")


def get_protect_api_key():
    return _env("UDMP_PROTECT_API_KEY")


def get_verify_ssl():
    # UniFi OS ships a self-signed cert by default, so TLS verification is
    # off unless the controller has a trusted cert and UDMP_VERIFY_SSL=true
    # is set. This is a same-LAN, API-key-authenticated connection, not an
    # internet-facing one — MITM risk is limited to the local network.
    return (_env("UDMP_VERIFY_SSL") or "false").lower() == "true"


def base_url():
    return f"https://{get_host()}/proxy/network/integration/v1"


def require_api_config():
    if not get_host() or not get_api_key():
        sys.exit("UDMP_HOST and UDMP_API_KEY must be set (env vars or .env file)")


def require_ui_config():
    if not get_host() or not get_ui_username() or not get_ui_password():
        sys.exit(
            "UDMP_HOST, UDMP_UI_USERNAME, and UDMP_UI_PASSWORD must be set "
            "(env vars or .env file) for this command"
        )


def require_protect_config():
    if not get_protect_host() or not get_protect_api_key():
        sys.exit(
            "UDMP_PROTECT_HOST and UDMP_PROTECT_API_KEY must be set "
            "(env vars or .env file) for this command"
        )


def make_session():
    session = requests.Session()
    session.headers.update({"X-API-Key": get_api_key(), "Accept": "application/json"})
    session.verify = get_verify_ssl()
    return session


def protect_base_url():
    return f"https://{get_protect_host()}/proxy/protect/integration/v1"


def make_protect_session():
    """UniFi Protect's own official, versioned Integration API — a separate
    app/host/API-key from the Network side, since the NVR here is a
    standalone appliance (not running on the same console as the gateway).
    Unlike the legacy Network session API, this one is documented and
    versioned (see /meta/info), so no undocumented-API caveat applies.
    """
    session = requests.Session()
    session.headers.update({"X-API-Key": get_protect_api_key(), "Accept": "application/json"})
    session.verify = get_verify_ssl()
    return session


def get_protect_meta(session):
    r = session.get(f"{protect_base_url()}/meta/info", timeout=10)
    r.raise_for_status()
    return r.json()


def get_protect_nvr(session):
    r = session.get(f"{protect_base_url()}/nvrs", timeout=10)
    r.raise_for_status()
    return r.json()


def get_protect_cameras(session):
    r = session.get(f"{protect_base_url()}/cameras", timeout=10)
    r.raise_for_status()
    return r.json()


def get_protect_chimes(session):
    r = session.get(f"{protect_base_url()}/chimes", timeout=10)
    r.raise_for_status()
    return r.json()


def summarize_protect_status(meta, nvr, cameras, chimes):
    """Status/health only — deliberately excludes anything image/video
    related (snapshots, recordings, live view), which is a separate,
    more sensitive scope than what this was built for. No storage/disk
    usage endpoint exists in this API version (confirmed 404, not
    assumed) so that isn't included either.
    """
    return {
        "application_version": meta.get("applicationVersion"),
        "nvr": {
            "name": nvr.get("name"),
            "arm_status": nvr.get("armMode", {}).get("status"),
        },
        "cameras": [
            {"name": c.get("name"), "mac": c.get("mac"), "state": c.get("state")} for c in cameras
        ],
        "chimes": [
            {"name": c.get("name"), "mac": c.get("mac"), "state": c.get("state")} for c in chimes
        ],
    }


def legacy_base_url():
    return f"https://{get_host()}/proxy/network/api"


def make_legacy_session():
    """Session-cookie auth against UniFi OS's older, undocumented network API.

    Only used for data the official Integration API doesn't expose (WLAN/SSID
    config as of writing — confirmed via direct probing, not assumed). Uses a
    dedicated, read-only-role local admin account, not the API key.
    """
    session = requests.Session()
    session.verify = get_verify_ssl()
    r = session.post(
        f"https://{get_host()}/api/auth/login",
        json={"username": get_ui_username(), "password": get_ui_password()},
        timeout=10,
    )
    r.raise_for_status()
    session.headers.update({"x-csrf-token": r.headers.get("x-csrf-token", "")})
    return session


def get_legacy_sites(session):
    r = session.get(f"{legacy_base_url()}/self/sites", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def resolve_legacy_site_name(session, site_arg):
    sites = get_legacy_sites(session)
    if not sites:
        sys.exit("No sites returned by controller")
    if site_arg:
        for s in sites:
            if site_arg in (s.get("name"), s.get("desc")):
                return s["name"]
        sys.exit(f"Site '{site_arg}' not found")
    return sites[0]["name"]


def get_wlans(session, site_name):
    r = session.get(f"{legacy_base_url()}/s/{site_name}/rest/wlanconf", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def get_legacy_networks(session, site_name):
    r = session.get(f"{legacy_base_url()}/s/{site_name}/rest/networkconf", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


NETWORK_SUMMARY_FIELDS = [
    "name",
    "purpose",
    "enabled",
    "vlan",
    "vlan_enabled",
    "ip_subnet",
    "dhcpd_enabled",
    "dhcpd_start",
    "dhcpd_stop",
    "dhcpd_dns_1",
    "dhcpd_dns_2",
    "domain_name",
    "wan_type",
    "wan_username",
    "firewall_zone_id",
]


def summarize_networks(networks):
    return [{f: n.get(f) for f in NETWORK_SUMMARY_FIELDS} for n in networks]


def get_legacy_devices(session, site_name):
    """Legacy stat/device — the only place port_overrides (per-port name and
    native VLAN assignment) lives; the Integration API's device detail only
    has live port state/speed/PoE, not the configured VLAN intent."""
    r = session.get(f"{legacy_base_url()}/s/{site_name}/stat/device", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def summarize_switch_ports(legacy_devices, networks):
    net_by_id = {n["_id"]: n for n in networks}
    switches = []
    for d in legacy_devices:
        overrides = d.get("port_overrides")
        if not overrides:
            continue
        ports = []
        for p in sorted(overrides, key=lambda x: x.get("port_idx", 0)):
            net = net_by_id.get(p.get("native_networkconf_id"), {})
            ports.append(
                {
                    "port_idx": p.get("port_idx"),
                    "name": p.get("name"),
                    "native_network": net.get("name"),
                    "poe_mode": p.get("poe_mode"),
                    "forward": p.get("forward"),
                    "tagged_vlan_mgmt": p.get("tagged_vlan_mgmt"),
                }
            )
        switches.append({"device": d.get("name", d.get("mac")), "ports": ports})
    return switches


def get_known_clients(session, site_name):
    """All clients the controller has ever seen (incl. offline), not just
    currently-connected ones — the Integration API's `clients` only covers
    live connections. This is where static/fixed IP reservations live."""
    r = session.get(f"{legacy_base_url()}/s/{site_name}/rest/user", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def summarize_known_clients(clients, networks, fixed_ip_only=True):
    net_by_id = {n["_id"]: n for n in networks}
    rows = []
    for c in clients:
        if fixed_ip_only and not c.get("use_fixedip"):
            continue
        protect_info = c.get("unifi_device_info_from_ucore", {})
        rows.append(
            {
                "name": c.get("name") or c.get("hostname"),
                "mac": c.get("mac"),
                "ip": c.get("fixed_ip") or c.get("last_ip"),
                "fixed_ip": bool(c.get("use_fixedip")),
                "network": net_by_id.get(c.get("network_id"), {}).get("name")
                or c.get("last_connection_network_name"),
                "product_model": protect_info.get("computed_model") or c.get("product_model"),
                "is_wired": c.get("is_wired"),
            }
        )
    rows.sort(key=lambda r: r.get("ip") or "")
    return rows


def summarize_protect_ai_ports(clients):
    """UP-AI-Port devices (add AI processing to a non-AI camera) don't
    appear anywhere in the Protect Integration API — confirmed by probing
    /cameras, /sensors, /lights, /viewers, /bridges, and /nvrs directly,
    none contain it. It only shows up via the legacy Network API's
    rest/user client list (see get_known_clients), identified the same way
    summarize_known_clients spots other Protect hardware:
    unifi_device_info_from_ucore.computed_model. Kept separate from that
    function rather than folded in, since AI Port has no fixed IP here and
    would be dropped by fixed_ip_only filtering, and belongs conceptually
    with the Protect dashboard section, not the general client list.
    """
    rows = []
    for c in clients:
        info = c.get("unifi_device_info_from_ucore") or {}
        if info.get("computed_model") != "AI Port":
            continue
        rows.append(
            {
                "name": info.get("name") or c.get("name") or c.get("hostname"),
                "mac": c.get("mac"),
                "ip": c.get("last_ip"),
                "state": info.get("device_state"),
                "fw_version": info.get("fw_version"),
            }
        )
    return rows


# Fields worth surfacing for a WiFi config review — security posture and
# roaming/isolation behavior, not every low-level radio knob wlanconf has.
WLAN_SUMMARY_FIELDS = [
    "name",
    "enabled",
    "is_guest",
    "security",
    "wpa_mode",
    "wpa3_support",
    "wpa3_transition",
    "pmf_mode",
    "fast_roaming_enabled",
    "bss_transition",
    "rrm_enabled",
    "hide_ssid",
    "wlan_bands",
    "mac_filter_enabled",
    "l2_isolation",
    "mcastenhance_enabled",
]


def summarize_wlans(wlans, networks):
    net_by_id = {n["_id"]: n for n in networks}
    summary = []
    for w in wlans:
        row = {f: w.get(f) for f in WLAN_SUMMARY_FIELDS}
        net = net_by_id.get(w.get("networkconf_id"), {})
        row["vlan_id"] = net.get("vlan")
        row["network_name"] = net.get("name")
        summary.append(row)
    return summary


def legacy_v2_base_url():
    return f"https://{get_host()}/proxy/network/v2/api"


def get_firewall_policies(session, site_name):
    r = session.get(f"{legacy_v2_base_url()}/site/{site_name}/firewall-policies", timeout=10)
    r.raise_for_status()
    return r.json()


def get_firewall_groups(session, site_name):
    r = session.get(f"{legacy_base_url()}/s/{site_name}/rest/firewallgroup", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def summarize_firewall_policies(policies, groups):
    """Custom (non-predefined) policies only, sorted by priority order.

    `predefined` policies are the built-in zone-matrix defaults (dozens of
    near-duplicate allow/block-established rules per zone pair) — noise for
    a review, so they're filtered out here. `index` is the actual priority:
    lower is evaluated first, and this API is first-match-wins, so ordering
    matters for understanding which rule actually applies.

    Zone names aren't resolvable — the controller has no endpoint exposing
    them (confirmed 404) — so `zone_id` is passed through raw rather than
    guessed at.

    When a rule targets "any network" on one side, the API stores one
    policy document per concrete zone pair rather than a single rule —
    the same name/action/index repeated 3-4x with only the zone_id on one
    side differing. Deduplicated here by (index, name, action): safe
    because the resolved `source`/`destination` group name (when present)
    doesn't depend on which zone pair produced it, so nothing observable
    is lost by keeping only the first occurrence.
    """
    group_by_id = {g["_id"]: g.get("name") for g in groups}

    def resolve_endpoint(ep):
        out = {"zone_id": ep.get("zone_id")}
        if ep.get("ip_group_id"):
            out["group"] = group_by_id.get(ep["ip_group_id"], ep["ip_group_id"])
        return out

    custom = [p for p in policies if not p.get("predefined")]
    custom.sort(key=lambda p: p.get("index", 0))
    seen = set()
    result = []
    for p in custom:
        key = (p.get("index"), p.get("name"), p.get("action"))
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "index": p.get("index"),
                "name": p.get("name"),
                "action": p.get("action"),
                "enabled": p.get("enabled"),
                "protocol": p.get("protocol"),
                "source": resolve_endpoint(p.get("source", {})),
                "destination": resolve_endpoint(p.get("destination", {})),
            }
        )
    return result


def get_sites(session):
    r = session.get(f"{base_url()}/sites", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def resolve_site_id(session, site_arg):
    sites = get_sites(session)
    if not sites:
        sys.exit("No sites returned by controller")
    if site_arg:
        for s in sites:
            if site_arg in (s.get("id"), s.get("name")):
                return s["id"]
        sys.exit(f"Site '{site_arg}' not found")
    return sites[0]["id"]


def get_devices(session, site_id):
    r = session.get(f"{base_url()}/sites/{site_id}/devices", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def get_clients(session, site_id):
    r = session.get(f"{base_url()}/sites/{site_id}/clients", timeout=10)
    r.raise_for_status()
    return r.json().get("data", [])


def get_device_detail(session, site_id, device_id):
    r = session.get(f"{base_url()}/sites/{site_id}/devices/{device_id}", timeout=10)
    r.raise_for_status()
    return r.json()


def get_ap_radios(session, site_id):
    """Return one entry per radio, across every access point at the site.

    Only channel/width/frequency are available from this API — no TX power,
    per-radio client count, or satisfaction score are exposed by the
    Integration API's device-detail endpoint as of writing.
    """
    radios = []
    for d in get_devices(session, site_id):
        if "radios" not in d.get("interfaces", []):
            continue
        detail = get_device_detail(session, site_id, d["id"])
        for r in detail.get("interfaces", {}).get("radios", []):
            radios.append(
                {
                    "device": d.get("name", "?"),
                    "frequencyGHz": r.get("frequencyGHz"),
                    "channel": r.get("channel"),
                    "channelWidthMHz": r.get("channelWidthMHz"),
                }
            )
    return radios


def find_radio_overlaps(radios):
    """Pairwise-compare same-band radios and flag co-channel/adjacent-channel overlap.

    2.4GHz channels closer together than 5 (e.g. 1 and 6) overlap in practice;
    5GHz/6GHz channels only meaningfully collide when identical, since UniFi's
    channel numbering there is already non-overlapping by design.
    """
    warnings = []
    by_band = {}
    for r in radios:
        by_band.setdefault(r["frequencyGHz"], []).append(r)

    for freq, group in by_band.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a["channel"] == b["channel"]:
                    warnings.append(
                        f"{a['device']} and {b['device']} both on {freq}GHz channel "
                        f"{a['channel']} — co-channel interference"
                    )
                elif freq == 2.4 and abs(a["channel"] - b["channel"]) < 5:
                    warnings.append(
                        f"{a['device']} (ch{a['channel']}) and {b['device']} (ch{b['channel']}) "
                        f"on 2.4GHz are close enough to overlap — space by >=5 channels (1/6/11)"
                    )
    return warnings


def emit(data):
    print(json.dumps(data, indent=2))


def cmd_sites(args, session):
    emit(get_sites(session))


def cmd_devices(args, session):
    site_id = resolve_site_id(session, args.site)
    emit(get_devices(session, site_id))


def cmd_clients(args, session):
    site_id = resolve_site_id(session, args.site)
    emit(get_clients(session, site_id))


def cmd_radios(args, session):
    site_id = resolve_site_id(session, args.site)
    radios = get_ap_radios(session, site_id)
    emit({"radios": radios, "warnings": find_radio_overlaps(radios)})


def cmd_wlans(args, session):
    site_name = resolve_legacy_site_name(session, args.site)
    wlans = get_wlans(session, site_name)
    networks = get_legacy_networks(session, site_name)
    emit(summarize_wlans(wlans, networks))


def cmd_firewall(args, session):
    site_name = resolve_legacy_site_name(session, args.site)
    policies = get_firewall_policies(session, site_name)
    groups = get_firewall_groups(session, site_name)
    emit(summarize_firewall_policies(policies, groups))


def cmd_networks(args, session):
    site_name = resolve_legacy_site_name(session, args.site)
    emit(summarize_networks(get_legacy_networks(session, site_name)))


def cmd_ports(args, session):
    site_name = resolve_legacy_site_name(session, args.site)
    legacy_devices = get_legacy_devices(session, site_name)
    networks = get_legacy_networks(session, site_name)
    emit(summarize_switch_ports(legacy_devices, networks))


def cmd_known_clients(args, session):
    site_name = resolve_legacy_site_name(session, args.site)
    clients = get_known_clients(session, site_name)
    networks = get_legacy_networks(session, site_name)
    emit(summarize_known_clients(clients, networks, fixed_ip_only=not args.all))


def cmd_protect_status(args, session):
    meta = get_protect_meta(session)
    nvr = get_protect_nvr(session)
    cameras = get_protect_cameras(session)
    chimes = get_protect_chimes(session)
    emit(summarize_protect_status(meta, nvr, cameras, chimes))


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Query a UniFi Dream Machine Pro via the local Network Integration API. "
            "Emits JSON on stdout for programmatic consumption."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sites", help="List sites")

    p_devices = sub.add_parser("devices", help="List UniFi devices")
    p_devices.add_argument("--site", help="Site id or name (default: first site)")

    p_clients = sub.add_parser("clients", help="List connected clients")
    p_clients.add_argument("--site", help="Site id or name (default: first site)")

    p_radios = sub.add_parser(
        "radios", help="List AP radios (channel/width) and flag overlapping channels"
    )
    p_radios.add_argument("--site", help="Site id or name (default: first site)")

    p_wlans = sub.add_parser(
        "wlans",
        help=(
            "List WLAN/SSID config (security, roaming, isolation, VLAN) via the "
            "legacy session API — requires UDMP_UI_USERNAME/UDMP_UI_PASSWORD"
        ),
    )
    p_wlans.add_argument("--site", help="Site short name or description (default: first site)")

    p_firewall = sub.add_parser(
        "firewall",
        help=(
            "List custom firewall policies (priority order) via the legacy session "
            "API — requires UDMP_UI_USERNAME/UDMP_UI_PASSWORD"
        ),
    )
    p_firewall.add_argument("--site", help="Site short name or description (default: first site)")

    p_networks = sub.add_parser(
        "networks",
        help=(
            "List VLANs/networks (subnet, DHCP, WAN config) via the legacy session "
            "API — requires UDMP_UI_USERNAME/UDMP_UI_PASSWORD"
        ),
    )
    p_networks.add_argument("--site", help="Site short name or description (default: first site)")

    p_ports = sub.add_parser(
        "ports",
        help=(
            "List per-switch port name/native-VLAN/PoE assignments via the legacy "
            "session API — requires UDMP_UI_USERNAME/UDMP_UI_PASSWORD"
        ),
    )
    p_ports.add_argument("--site", help="Site short name or description (default: first site)")

    p_known_clients = sub.add_parser(
        "known-clients",
        help=(
            "List all clients the controller has ever seen, not just currently "
            "connected ones — requires UDMP_UI_USERNAME/UDMP_UI_PASSWORD"
        ),
    )
    p_known_clients.add_argument(
        "--site", help="Site short name or description (default: first site)"
    )
    p_known_clients.add_argument(
        "--all",
        action="store_true",
        help="Include clients without a static/fixed IP reservation (default: fixed-IP only)",
    )

    sub.add_parser(
        "protect-status",
        help=(
            "UniFi Protect NVR/camera/chime status — requires "
            "UDMP_PROTECT_HOST/UDMP_PROTECT_API_KEY (separate credential, "
            "no --site: Protect isn't organized by Network-app site)"
        ),
    )

    return parser


def main():
    args = build_parser().parse_args()

    commands = {
        "sites": cmd_sites,
        "devices": cmd_devices,
        "clients": cmd_clients,
        "radios": cmd_radios,
        "wlans": cmd_wlans,
        "firewall": cmd_firewall,
        "networks": cmd_networks,
        "ports": cmd_ports,
        "known-clients": cmd_known_clients,
        "protect-status": cmd_protect_status,
    }
    try:
        if args.command == "protect-status":
            require_protect_config()
            session = make_protect_session()
            target_host = get_protect_host()
        elif args.command in LEGACY_API_COMMANDS:
            require_ui_config()
            session = make_legacy_session()
            target_host = get_host()
        else:
            require_api_config()
            session = make_session()
            target_host = get_host()
        commands[args.command](args, session)
    except requests.HTTPError as e:
        sys.exit(f"API request failed: {e}")
    except requests.ConnectionError as e:
        sys.exit(f"Could not reach {target_host}: {e}")


if __name__ == "__main__":
    main()
