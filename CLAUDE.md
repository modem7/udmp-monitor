# CLAUDE.md

Read this automatically at the start of every session in this repo.

## What this is

A read-only tool against a UniFi Dream Machine Pro, using two separate
credentials against two separate APIs:

- **Official Integration API** (`/proxy/network/integration/v1`), API-key
  auth (`UDMP_API_KEY`). Commands: `sites`, `devices`, `clients`, `radios`.
- **Legacy/undocumented session API** (`/proxy/network/api/...` and
  `/proxy/network/v2/api/...`), cookie auth via a dedicated, read-only-role
  local admin account (`UDMP_UI_USERNAME`/`UDMP_UI_PASSWORD`). Commands:
  `wlans`, `firewall`. This is what community tools like `node-unifi`/
  unifi-poller use — unofficial, undocumented, can change without notice
  on a firmware update. Used only because the Integration API doesn't
  expose WLAN/SSID config or firewall policies at all (confirmed by
  probing, not assumed — see below).

Access is deliberately API-only, not SSH — the user explicitly ruled SSH
out. Nothing in this tool writes to the controller — it only reads.

**This exists for Claude to run directly, not for a human to operate.**
When the user asks about their network (device status, AP channel health,
clients, etc.), the answer is to invoke `python3 udmp.py <command>` via
Bash and report back — not to hand the user a command to run themselves.
Every command emits JSON on stdout for exactly that reason: reliable
machine parsing over human-readable table formatting. Don't add
`--pretty`/table-output modes or other human-CLI ergonomics unless the
user explicitly asks for them — they're not the target user.

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
  controller first.** Both APIs here have surfaces that are easy to get
  wrong by guessing.
  - Integration API: `/sites`, `/sites/{id}/devices`,
    `/sites/{id}/devices/{id}` (detail, including AP radio channel/width),
    `/sites/{id}/clients`, `/sites/{id}/networks` confirmed working.
    Events/alarms/logs/statistics confirmed **not** present (404) — not
    reachable via this API at all, with either credential.
  - Legacy API: `/proxy/network/api/self/sites`,
    `/proxy/network/api/s/{site}/rest/wlanconf`,
    `/proxy/network/api/s/{site}/rest/networkconf`,
    `/proxy/network/api/s/{site}/rest/firewallgroup`, and
    `/proxy/network/v2/api/site/{site}/firewall-policies` (note the v2 path
    and different base — the old flat `rest/firewallrule` returns an empty
    list on zone-based-firewall controllers; the real data is v2's
    `firewall-policies`) are confirmed working. There's no endpoint that
    resolves firewall zone IDs to human names — `zone_id` is passed through
    raw in `firewall` output rather than guessed at.

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

`UDMP_HOST`/`UDMP_API_KEY`/`UDMP_UI_USERNAME`/`UDMP_UI_PASSWORD` come from
the environment or a local `.env` (gitignored) — never from a command-line
argument or a value pasted into chat. See `README.md` for setup. The
`UDMP_UI_*` account is a dedicated local admin scoped to a read-only role
(named "Claude Code" on the controller) — never suggest reusing the
user's own admin login here.

## Workflow

Changes go through a feature branch + PR, never a direct push to `master`
— including CI/config fixes. See existing PRs for the pattern.
