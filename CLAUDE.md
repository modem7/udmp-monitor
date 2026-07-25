# CLAUDE.md

Read this automatically at the start of every session in this repo.

## What this is

A read-only CLI against a UniFi Dream Machine Pro's local UniFi OS Network
Integration API (`/proxy/network/integration/v1`), authenticated with an
API key. Nothing in this tool writes to the controller — it only reads.

## Ground rules, non-negotiable

- **Never read, log, or print the API key.** `udmp.py` reads
  `UDMP_API_KEY`/`UDMP_HOST` from the environment at call time (see
  `get_host()`/`get_api_key()`/`base_url()`) — don't refactor those back
  into module-level constants captured at import time, since that's what
  makes the test suite able to monkeypatch env vars per-test without
  `importlib.reload`.
- **Read-only, by design.** This tool does not modify controller state.
  If a task seems to need a write (changing a firewall rule, radio
  channel, etc.), that's a scope change to raise explicitly, not something
  to add quietly under an existing read-only command.
- **Don't assume an endpoint exists — verify it against the real
  controller first.** The Integration API's surface is small and easy to
  get wrong by guessing: `/sites`, `/sites/{id}/devices`,
  `/sites/{id}/devices/{id}` (detail, including AP radio channel/width),
  `/sites/{id}/clients`, and `/sites/{id}/networks` are confirmed working.
  Firewall rules, events/alarms, logs, and statistics are confirmed **not**
  present in this API (all return 404) — don't add code that assumes
  they'll show up; that data only exists via the older private/session-auth
  API or SSH onto the device itself, which is a different credential and a
  separate discussion with the user before building against it.

## Before considering any change "done"

1. `ruff check .` and `ruff format --check .` — both run in CI, fix before
   committing rather than relying on CI to catch it.
2. `pytest -v` — every new API-calling function needs a test using the
   `fake_session()` helper in `tests/test_udmp.py` (mocks `session.get` by
   URL suffix, no real network or `requests-mock` dependency needed).
   Pure logic (like `find_radio_overlaps`) should be tested directly,
   without going through a fake session at all.
3. If a change touches actual API calls, run it against the real
   controller once (`python3 udmp.py <command>`) before opening a PR —
   don't rely solely on mocked tests for functions that shape data from a
   real, external API response.

## Credentials

`UDMP_HOST`/`UDMP_API_KEY` come from the environment or a local `.env`
(gitignored) — never from a command-line argument or a value pasted into
chat. See `README.md` for setup.

## Workflow

Changes go through a feature branch + PR, never a direct push to `master`
— including CI/config fixes. See existing PRs for the pattern.
