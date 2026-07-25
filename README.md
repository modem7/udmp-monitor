# udmp-monitor

[![CI](https://github.com/modem7/udmp-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/modem7/udmp-monitor/actions/workflows/ci.yml)
[![Last Commit](https://img.shields.io/github/last-commit/modem7/udmp-monitor)](https://github.com/modem7/udmp-monitor/commits/master)

Read-only CLI for querying a UniFi Dream Machine Pro over its local UniFi OS
Network Integration API (`/proxy/network/integration/v1`).

## Setup

1. On the UDMP: **Settings > Control Plane > Integrations**, enable the
   Network API, and generate an API key.

2. Install dependencies:
   ```bash
   pip install --break-system-packages -r requirements.txt
   ```

3. Provide credentials via environment variables — **never pass the key on
   the command line or paste it into chat.** Either export them in your
   shell:
   ```bash
   export UDMP_HOST=192.168.1.1
   export UDMP_API_KEY='...'
   ```
   or copy `.env.example` to `.env` and fill it in (`.env` is gitignored):
   ```bash
   cp .env.example .env
   ```

   The controller's cert is self-signed by default, so TLS verification is
   off unless you set `UDMP_VERIFY_SSL=true`.

## Usage

```bash
python3 udmp.py sites
python3 udmp.py devices [--site <id-or-name>]
python3 udmp.py clients [--site <id-or-name>]
```

If `--site` is omitted, the first site returned by the controller is used.

## Development

```bash
pip install --break-system-packages -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```
