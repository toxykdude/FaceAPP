# Design: WiFi Captive Portal

## Context

pfSense (recommended 2.7+, any version with per-zone CP) fronts the member
WiFi. The AP must be in **bridge/AP mode** on a pfSense interface (or VLAN)
dedicated to member WiFi. The captive portal intercepts HTTP(S) attempts from
unauthenticated clients and renders a login page until a session is allowed.

```
[Member phone] ──WiFi── [AP (bridge mode)] ── [pfSense CP zone: MEMBER_WIFI]
                                                    │ RADIUS PAP (UDP 1812)
                                                    │ RADIUS Acct (UDP 1813)
                                                    ▼
                                    [radius_service on app host (pyrad)]
                                                    │ HTTPS/X-Internal-Secret
                                                    ▼
                              [backend POST /api/wifi/authorize|accounting]
                                                    │
                                               [Postgres]
```

## Decision 1 — RADIUS, not a custom PHP portal page

pfSense offers custom portal pages (HTML or PHP). A PHP page could call the
backend directly and invoke pfSense internals (`portal_allow`), but that API is
unsupported and changes across pfSense upgrades. RADIUS is the documented
external-auth mechanism; it also delivers accounting and per-session timeouts
(`Session-Timeout`, `Idle-Timeout`) that pfSense honors natively.

## Decision 2 — Component layout

| Component | Location | Responsibility |
|---|---|---|
| Portal page | uploaded to pfSense (authored at `deploy/pfsense/powerhouse-portal.html`) | cédula form; posts `auth_user`/`auth_pass` to `$PORTAL_ACTION$` |
| pfSense CP zone | per interface | interception, session table, idle/hard timeouts |
| `radius_service` | app host, systemd `facegym-radius` | RADIUS protocol, PAP extraction, brute-force cooldown, backend HTTP calls |
| backend `/api/wifi/*` | `backend/api/wifi.py` | membership decision (source of truth), accounting persistence |
| `wifi_sessions` | Postgres | audit trail: who, which MAC/IP, bytes, start/stop |

Auth flow: portal → pfSense → `Access-Request(User-Name=cédula,
User-Password=cédula [PAP])` → radius_service → `POST /api/wifi/authorize` →
`Access-Accept(Session-Timeout, Idle-Timeout, Acct-Interim-Interval,
Reply-Message)` or `Access-Reject(Reply-Message)`.

pfSense CP speaks PAP; the portal page therefore submits the cédula as BOTH
`auth_user` and `auth_pass` (the backend ignores the password — the RADIUS
secret + firewall protect the hop, and the credential itself is the document).

## Decision 3 — Authorization semantics (mirror the kiosk)

Same order and vocabulary as `cv_service/validation/access_validator.py`:

1. Normalize document: strip non-alphanumerics, uppercase, cap 20 chars.
2. Match `Member.id_number` on `upper(regexp_replace(id_number,'[^0-9A-Za-z]','','g'))`.
   No member → `member_not_found`; only inactive/suspended members → `member_inactive`.
3. For each matching **active** member, best membership with
   `start_date <= today <= end_date` (today in `get_app_tz`), ordered
   `end_date desc` → status must be `active` (`suspended_membership` if not),
   else `membership_not_started` / `no_active_membership` / `expired_membership`
   from the closest non-qualifying record.
4. Payment gate: `payment_status == "pending"` → `unpaid_membership`
   (nothing collected). Partial opens WiFi, same as the door.
5. Device cap: active sessions (`ended_at IS NULL` and refreshed within
   `WIFI_STALE_SESSION_HOURS`) ≥ `WIFI_MAX_DEVICES_PER_MEMBER` → `device_limit`.
6. Grant: `Session-Timeout = min(WIFI_SESSION_TIMEOUT_CAP_SECONDS, seconds
   until local midnight after end_date)`, floor 60 s; `Idle-Timeout` from
   settings; interim interval 600 s.

Deliberately NOT applied to WiFi: `access_rules` day/time/location windows and
camera location binding — they encode *facility entry* policy. Recorded as an
explicit scoping decision, revisitable by flipping it into `services/wifi_auth.py`.

Duplicate cédulas: grant if ANY matching member qualifies (data-quality reality;
`id_number` has no unique constraint).

## Decision 4 — Fail-closed posture

- `verify_internal_secret` (reused from `api/cv_internal.py`): unconfigured
  secret → 503 for every request; wrong secret → 401 (`hmac.compare_digest`).
- radius_service: backend unreachable/erroring → `Access-Reject` with a
  "service unavailable" Reply-Message. Never grant on uncertainty.
- Accounting delivery failures are retried never (logged only) — accounting is
  telemetry; authorization is the security boundary.

## Decision 5 — Brute force

Per-document in-memory cooldown in radius_service: after 5 consecutive rejects
for the same normalized document, reject immediately for 60 s. State is
per-process (a restart clears it — acceptable; the target is cheap scripted
spray, not a patient adversary).

## Decision 6 — Data model & RLS

`wifi_sessions` (UUID pk, `member_id` FK nullable ON DELETE SET NULL, snapshot
`username`, `nas_ip`, `acct_session_id`, `framed_ip`, `calling_station_id`,
octet counters, `acct_session_time`, `started_at`, `last_update_at`,
`ended_at`, `terminate_cause`; unique `(nas_ip, acct_session_id)`).

Migration enables RLS and creates the app-role policy **guarded by a
`pg_roles` existence check** — `backend_app` exists on production but not in
dev/CI, and an unconditional `CREATE POLICY … TO backend_app` would abort the
dev migration (trap 20 family). Deploy runs the migration as `powerhouse_migrator`
with the mandatory `alembic current` confirmation.

## Decision 7 — Re-auth cadence and expiry enforcement

There is no push channel from membership-lapse to pfSense CP (CoA for CP zones
is unreliable across versions). Instead every grant carries a bounded
`Session-Timeout`; a lapsed member is re-presented the portal within ≤ cap
(default 4 h) and rejected then. Idle devices drop at `Idle-Timeout` (30 min).

## Testing strategy

- Backend: `pytest tests/test_wifi_authorize.py tests/test_wifi_accounting.py`
  against live Postgres (house pattern) covering every denial reason, the
  payment gate, device cap, timeout math (America/Bogota default), auth
  fail-closed, normalization, and accounting upserts.
- radius_service: offline pytest — packet→request mapping, PAP extraction,
  accept/reject attribute assembly, backend-failure → reject, cooldown,
  accounting field mapping, `VerifyAcctRequest` gate.
- End-to-end: `radius_service/tools/radtest.py` against a running service;
  then a phone on the member SSID (runbook checklist).
