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

1. On the UDMP: **Settings > Control Plane > Integrations**, enable the
   Network API, and generate an API key.

2. Install dependencies:
   ```bash
   pip install --break-system-packages -r requirements.txt
   ```

3. Credentials live in `.env` (gitignored) or shell env vars
   (`UDMP_HOST`, `UDMP_API_KEY`) — never pasted into chat or passed as a
   command-line argument.

   The controller's cert is self-signed by default, so TLS verification is
   off unless `UDMP_VERIFY_SSL=true` is set.

## Commands

```bash
python3 udmp.py sites
python3 udmp.py devices [--site <id-or-name>]
python3 udmp.py clients [--site <id-or-name>]
python3 udmp.py radios  [--site <id-or-name>]   # AP channel/width + overlap warnings
```

If `--site` is omitted, the first site returned by the controller is used.

## Development

```bash
pip install --break-system-packages -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```
