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
python3 udmp.py wlans    [--site <name-or-desc>]  # SSID config: security, roaming, isolation, VLAN
python3 udmp.py firewall [--site <name-or-desc>]  # custom firewall policies, priority order
```

If `--site` is omitted, the first site returned by the controller is used.

## Development

```bash
pip install --break-system-packages -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```
