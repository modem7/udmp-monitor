# CLAUDE.md

Read this automatically at the start of every session in this repo.

## What this is

A read-only tool against UniFi hardware, using three separate credentials
against three separate APIs:

- **Official Network Integration API** (`/proxy/network/integration/v1`),
  API-key auth (`UDMP_API_KEY`) against the UDM Pro. Commands: `sites`,
  `devices`, `clients`, `radios`.
- **Legacy/undocumented Network session API** (`/proxy/network/api/...`
  and `/proxy/network/v2/api/...`), cookie auth via a dedicated,
  read-only-role local admin account (`UDMP_UI_USERNAME`/
  `UDMP_UI_PASSWORD`). Commands: `wlans`, `firewall`, `networks`, `ports`,
  `known-clients`. This is what community tools like `node-unifi`/
  unifi-poller use — unofficial, undocumented, can change without notice
  on a firmware update. Used only because the Integration API doesn't
  expose WLAN/SSID config or firewall policies at all (confirmed by
  probing, not assumed — see below).
- **Official Protect Integration API**
  (`/proxy/protect/integration/v1`), API-key auth (`UDMP_PROTECT_HOST`/
  `UDMP_PROTECT_API_KEY`) against the NVR — often a **separate physical
  appliance** from the UDM Pro, not the same console, hence its own host
  var. Command: `protect-status`. Official and versioned like the Network
  Integration API (confirmed via `/meta/info`) — no undocumented-API
  caveat here. **Status/health only, by explicit scope decision** —
  snapshots, recordings, and live view are a meaningfully more sensitive
  surface (actual video/privacy data) and were deliberately left out;
  don't add them without raising that as its own explicit decision, the
  same way write access was for the Network side.

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
  - `rest/user` (all clients ever seen, not just connected) has a
    `product_line`/`unifi_device_info_from_ucore` field on Protect devices
    (cameras, NVR, chime) that reveals their real model — those devices
    never show up as adopted Network-app devices, only as clients. Worth
    checking there before assuming Protect hardware is undocumentable.
  - `port_overrides` (per-port name/native-VLAN/PoE intent) only exists on
    `stat/device` (legacy), not the Integration API's device detail —
    that endpoint only has live port state/speed, not configured intent.
- **`firewall-policies` has a real duplication quirk, not a bug in this
  code**: a rule targeting "any network" on one side gets stored as one
  policy document per concrete zone pair — the same index/name/action
  repeated 3-4x with only `zone_id` differing. `summarize_firewall_policies`
  dedupes by `(index, name, action)`, keeping the first occurrence. This
  was caught by the `known-clients`/dashboard work producing a 96-row
  firewall table that should have been ~44 rows — always sanity-check a
  new summarize function's output count against what a human would expect,
  not just against a green test suite.

## Local dashboards (`docs/`)

`docs/dashboard-live.html` + `docs/dashboard_server.py` is the one HTML
view of this tool's read-only data — see `README.md` for how to run it.
There is no separate static-generation script or committed static HTML
file; the **Save snapshot** button in the live page exports whatever's
currently rendered (same CSS/markup, pulled straight from the DOM) as a
standalone file with no server dependency. Don't reintroduce a second,
separately-maintained static build — it will drift from the live version.

`docs/dashboard_server.py` binds `127.0.0.1` by default; if testing it
manually (not through the webapp-testing skill's `with_server.py`, which
cleans up after itself), check `lsof -i :8765` for an orphaned process
from a previous run before trusting `curl`/browser output against it —
a stale process silently serving old code looks identical to a real bug.
This bit twice while building this feature: once making a real fix look
like it hadn't worked, once making a DNS-rebinding fix look like it hadn't
worked either. Always check first.

**Every value interpolated into `innerHTML` in `dashboard-live.html` must
go through `esc()`, including inside `data-search="..."` attributes.**
`esc()` escapes `"`/`'` as well as `&<>` for exactly this reason — a value
placed inside a double-quoted attribute can break out of it via an
unescaped quote even if `&<>` are handled. Device names, network/SSID
names, firewall rule/group names, and switch port names are all
UniFi-side user-editable strings (some, like client hostnames, can even
be attacker-supplied via DHCP) — treat all of them as untrusted input, not
just the ones that "feel" attacker-controlled. Two real XSS bugs here came
from raw (non-`esc()`) interpolation slipping through code review; caught
only by a security scan, not by testing, so also grep for bare `+ <field>
+` concatenation patterns when reviewing this file, don't just trust the
functions that do call `esc()` correctly.

`docs/dashboard_server.py`'s `_host_is_allowed()` exists specifically to
block DNS-rebinding attacks: it only serves requests whose `Host` header
is `localhost` or a literal IP, never an arbitrary DNS name, regardless of
what `UDMP_DASHBOARD_HOST` is bound to. Don't relax this to allow specific
hostnames without understanding why it's IP-or-localhost-only in the first
place — the whole point is that a rebinding attack's `Host` header is
always a real domain name, never an IP.

## Docker

`Dockerfile` runs the live dashboard only (`docs/dashboard_server.py`) —
not the CLI, which isn't meant to run in a container. Non-root by default
(`ARG UID`/`GID`, default 101, override at build time or with `docker run
-u`). Deliberately **no PUID/PGID env vars or s6-overlay** — that pattern
exists to fix ownership on bind-mounted volumes at container startup, and
this container has no volumes at all (no persistent state, credentials
come in via env vars). Don't add that complexity back without a real
volume need driving it. `UDMP_DASHBOARD_HOST=0.0.0.0` is baked in via
`ENV` since `127.0.0.1` inside a container is unreachable through Docker's
port mapping — the `_host_is_allowed()` DNS-rebinding check still applies
regardless of bind address.

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

`UDMP_HOST`/`UDMP_API_KEY`/`UDMP_UI_USERNAME`/`UDMP_UI_PASSWORD`/
`UDMP_PROTECT_HOST`/`UDMP_PROTECT_API_KEY` come from the environment or a
local `.env` (gitignored) — never from a command-line argument or a value
pasted into chat. See `README.md` for setup. The `UDMP_UI_*` account is a
dedicated local admin scoped to a read-only role (named "Claude Code" on
the controller) — never suggest reusing the user's own admin login here.

## Workflow

Changes go through a feature branch + PR, never a direct push to `master`
— including CI/config fixes. See existing PRs for the pattern.
