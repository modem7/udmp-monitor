# udmp-monitor

[![CI](https://github.com/modem7/udmp-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/modem7/udmp-monitor/actions/workflows/ci.yml)
[![Last Commit](https://img.shields.io/github/last-commit/modem7/udmp-monitor)](https://github.com/modem7/udmp-monitor/commits/master)

Read-only tooling for querying a UniFi Dream Machine Pro over its local
UniFi OS Network Integration API (`/proxy/network/integration/v1`).

This is not a general-purpose CLI for humans to run interactively — it's
built for Claude to invoke directly (via `python3 udmp.py <command>`) to
answer diagnostic questions about the network on request. Output is JSON
on stdout for reliable machine parsing rather than human-formatted tables.
See `CLAUDE.md` for the operating rules.

## Setup

This uses two separate credentials against two separate APIs — set up
whichever commands you need.

1. **Official Integration API** (`sites`/`devices`/`clients`/`radios`):
   on the UDMP, **Settings > Control Plane > Integrations**, enable the
   Network API, and generate an API key (`UDMP_API_KEY`).

2. **Legacy session API** (`wlans`/`firewall`): the Integration API
   doesn't expose WLAN/SSID config or firewall policies at all (confirmed
   by probing the controller, not assumed). These commands fall back to
   UniFi's older, undocumented session-cookie API instead, which needs a
   **dedicated local admin account** — not your personal login. Create one
   under **Settings > Admins** with the most restrictive role that still
   has Network-app read access, and set `UDMP_UI_USERNAME`/
   `UDMP_UI_PASSWORD` for it. This API can change or break without notice
   on a firmware update, unlike the versioned Integration API.

3. Install dependencies:
   ```bash
   pip install --break-system-packages -r requirements.txt
   ```

4. Credentials live in `.env` (gitignored) or shell env vars
   (`UDMP_HOST`, `UDMP_API_KEY`, `UDMP_UI_USERNAME`, `UDMP_UI_PASSWORD`) —
   never pasted into chat or passed as a command-line argument.

   The controller's cert is self-signed by default, so TLS verification is
   off unless `UDMP_VERIFY_SSL=true` is set.

## Commands

```bash
python3 udmp.py sites
python3 udmp.py devices  [--site <id-or-name>]
python3 udmp.py clients  [--site <id-or-name>]
python3 udmp.py radios   [--site <id-or-name>]   # AP channel/width + overlap warnings

# legacy API — needs UDMP_UI_USERNAME/UDMP_UI_PASSWORD
python3 udmp.py wlans          [--site <name-or-desc>]  # SSID config: security, roaming, isolation, VLAN
python3 udmp.py firewall       [--site <name-or-desc>]  # custom firewall policies, priority order
python3 udmp.py networks       [--site <name-or-desc>]  # VLANs, subnets, DHCP, WAN config
python3 udmp.py ports          [--site <name-or-desc>]  # per-switch port name/VLAN/PoE assignments
python3 udmp.py known-clients  [--site <name-or-desc>] [--all]  # all clients ever seen, not just connected (fixed-IP only by default)
```

If `--site` is omitted, the first site returned by the controller is used.

## Documentation

`docs/NETWORK.md` is a disaster-recovery-level writeup of the whole
network (hardware, WAN, VLANs, switch ports, wireless, firewall, clients)
generated from live controller data — regenerate by re-running the
gathering steps described at the bottom of that file.

**`docs/dashboard-live.html`** + **`docs/dashboard_server.py`** is a
local-only live dashboard that queries the controller fresh on every load.
It imports `udmp.py`, so it needs the same dependencies and `.env`/env vars
as the CLI (see Setup above — `pip install -r requirements.txt` first if
you haven't already):

```bash
python3 docs/dashboard_server.py
# open http://127.0.0.1:8765
```

Binds to `127.0.0.1` by default (this machine only). Set
`UDMP_DASHBOARD_HOST=0.0.0.0` to make it reachable from elsewhere on your
LAN — it has no authentication of its own, so don't expose it beyond a
trusted network (it does validate the `Host` header to block DNS-rebinding
attacks, but that's not the same thing as auth).

**Static snapshots** are generated on demand, not committed to the repo —
click **Save snapshot** in the live dashboard's header. It exports
whatever's currently rendered (same styling, same data, search/filters
still work) as one self-contained HTML file with no server dependency,
safe to share, store, or back up as-is. There's no separate generation
script to keep in sync; the live dashboard *is* the source, and a snapshot
is just "what it showed, frozen," downloaded straight from the browser.

## Development

```bash
pip install --break-system-packages -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```
