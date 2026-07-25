#!/usr/bin/env python3
import argparse
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


def cmd_sites(args, session):
    for s in get_sites(session):
        print(f"{s.get('id')}  {s.get('name', '')}")


def cmd_devices(args, session):
    site_id = resolve_site_id(session, args.site)
    for d in get_devices(session, site_id):
        print(
            f"{d.get('name', '?'):20} {d.get('model', '?'):15} "
            f"{d.get('state', '?'):10} {d.get('ipAddress', '')}"
        )


def cmd_clients(args, session):
    site_id = resolve_site_id(session, args.site)
    for c in get_clients(session, site_id):
        name = c.get("name") or c.get("hostname") or c.get("macAddress")
        print(f"{name:25} {c.get('ipAddress', ''):15} {c.get('macAddress', '')}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Query a UniFi Dream Machine Pro via the local Network Integration API"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sites", help="List sites")

    p_devices = sub.add_parser("devices", help="List UniFi devices")
    p_devices.add_argument("--site", help="Site id or name (default: first site)")

    p_clients = sub.add_parser("clients", help="List connected clients")
    p_clients.add_argument("--site", help="Site id or name (default: first site)")

    return parser


def main():
    require_config()

    args = build_parser().parse_args()
    session = make_session()

    commands = {"sites": cmd_sites, "devices": cmd_devices, "clients": cmd_clients}
    try:
        commands[args.command](args, session)
    except requests.HTTPError as e:
        sys.exit(f"API request failed: {e}")
    except requests.ConnectionError as e:
        sys.exit(f"Could not reach {get_host()}: {e}")


if __name__ == "__main__":
    main()
