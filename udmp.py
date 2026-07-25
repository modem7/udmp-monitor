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


def get_host():
    return os.environ.get("UDMP_HOST")


def get_api_key():
    return os.environ.get("UDMP_API_KEY")


def get_verify_ssl():
    # UniFi OS ships a self-signed cert by default, so TLS verification is
    # off unless the controller has a trusted cert and UDMP_VERIFY_SSL=true
    # is set. This is a same-LAN, API-key-authenticated connection, not an
    # internet-facing one — MITM risk is limited to the local network.
    return os.environ.get("UDMP_VERIFY_SSL", "false").lower() == "true"


def base_url():
    return f"https://{get_host()}/proxy/network/integration/v1"


def require_config():
    if not get_host() or not get_api_key():
        sys.exit("UDMP_HOST and UDMP_API_KEY must be set (env vars or .env file)")


def make_session():
    session = requests.Session()
    session.headers.update({"X-API-Key": get_api_key(), "Accept": "application/json"})
    session.verify = get_verify_ssl()
    return session


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

    return parser


def main():
    require_config()

    args = build_parser().parse_args()
    session = make_session()

    commands = {
        "sites": cmd_sites,
        "devices": cmd_devices,
        "clients": cmd_clients,
        "radios": cmd_radios,
    }
    try:
        commands[args.command](args, session)
    except requests.HTTPError as e:
        sys.exit(f"API request failed: {e}")
    except requests.ConnectionError as e:
        sys.exit(f"Could not reach {get_host()}: {e}")


if __name__ == "__main__":
    main()
