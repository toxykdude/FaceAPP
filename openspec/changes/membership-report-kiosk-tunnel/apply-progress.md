# sdd/membership-report-kiosk-tunnel/apply-progress (REV 6 — adds Work Unit 3 / PR3: Phase 4 portal security)

**Status**: PR1 (Work Unit 1 / date-range reports) committed on `feature/tracker` (`a4613d9`); PR2 (Work Unit 2 / display-access + invalidation) committed on `feature/pr2-membership-expiration-access` (`5e9fec2`, based on `feature/tracker`) — both now MERGED to main (main log shows `5e9fec2` and its chain). This revision ADDS Work Unit 3 (PR3 / "Portal security + tunnel allowlist" — tasks.md Phase 4, tasks 4.1–4.7), implemented as 3 work-unit commits on `feat/portal-security-suite` branched off main: `99659b5`, `8baa902`, `8463d36`. Not pushed; no PR opened (chain strategy `feature-branch-chain` — awaiting explicit go-ahead). Phase 5 (5.1–5.3) deliberately untouched: ops-time, orchestrator-scheduled.

## PR3 scope delivered (Phase 4, all 7 tasks) — STRICT TDD

**4.1 Webhook HMAC (approval — behavior pre-existed)**: `backend/tests/test_portal_security.py::TestWebhookSignatureEnforcement` — missing X-Signature → 401; signature from wrong secret → 401; valid signature over tampered body → 401; each with Membership/SalesTransaction row-count assertions (no state change). Positive control: valid signature over exact bytes → 200 + exactly one Membership and one SalesTransaction created (proves the rejection tests are non-vacuous).

**4.2 CORS (approval — middleware pre-existed)**: `TestCorsOriginRejection` — introspects the app's ACTUAL `CORSMiddleware` kwargs (`app.user_middleware`), so assertions hold regardless of local `.env`: disallowed origin (fresh `https://<uuid>.invalid`) on GET /api/portal/plans → 200 but NO `Access-Control-Allow-Origin`; preflight OPTIONS from disallowed origin → 400 + no ACAO; positive control: configured-allowed origin echoed in both simple + preflight paths.

**4.3 RLS cross-member isolation (genuine RED→GREEN)**: new `backend/tests/portal_rls_bootstrap.py` provisions the `member_portal` role in the test DB BEFORE app import (CREATE/ALTER ROLE via the connecting role when it has CREATEROLE — CI's superuser — else via `su postgres` peer-auth fallback — this dev box; then GRANT CONNECT/USAGE/SELECT + ENABLE RLS + the five `portal_*` policies from `001_rls_setup.sql` §7 verbatim, idempotent DROP+CREATE). Sets `MEMBER_PORTAL_DATABASE_URL` (URL with `render_as_string(hide_password=False)` — `str(url)` masks passwords as `***` in SQLAlchemy 2.0) AND patches `core.database.PortalSessionLocal` directly because **`core/__init__.py` imports `core.database`, so any `from core...` import builds PortalSessionLocal before the env var exists**. `TestPortalRlsIsolation` (6 tests): /portal/me from A's JWT returns exactly A's membership+payments (B's identifiers absent from the full JSON) and symmetrically for B; DB-level: unfiltered portal-role scan sees exactly [A]; targeted read of B's membership under A's session → 0 rows; portal session without app.member_id → 0 rows; INSERT via portal session → `permission denied`. **RED proof**: ran the class with RLS disabled via a /tmp pytest plugin (`portal_red_plugin`, NOT committed) that weakens RLS AFTER the bootstrap's idempotent provisioning — the 3 DB-level tests FAILED (leak caught), the 2 API-level + 1 grant-level passed (expected: route WHERE-clause and GRANTs are independent enforcement layers). GREEN with RLS enabled. No `.github/workflows/ci.yml` change needed: CI's `DATABASE_URL` user is the service-container superuser, so the bootstrap's direct CREATE ROLE path works there.

**4.4/4.5 Rate limits (RED→GREEN)**: `TestMemberAuthRateLimits` — 11 requests per route with app-level Redis cooldown/lockout/pin keys purged before each request (so responses 1–10 are clean 200/401 — proving no app-level throttle fired — and the 11th is 429 with body `"Rate limit exceeded"` = slowapi's handler, distinguishable from the Spanish cooldown message). RED: member-verify's 11th was 401 (`AssertionError: (401, '{"detail":"Código incorrecto o expirado"}')`); login/resend passed immediately (pre-existing decorators — approval). GREEN: new `settings.MEMBER_AUTH_RATE_LIMIT` (default `10/minute`, `core/config.py`) used by all three decorators in `portal_auth.py`; `member-verify` gained `@limiter.limit(...)` + `request: Request` param (body param renamed to `body`; two `request.phone`/`request.pin` references updated — caught by the suite, not by eye). `core/rate_limiter.py` unchanged (shared limiter already existed — design deviation noted). ALSO: conftest gained an autouse `fresh_rate_limits` fixture resetting the process-global slowapi storage around EVERY test — without it, per-route quotas accumulate across tests in one process and later suites inherit half-spent limits (test_portal.py's 19 tests started failing 429 until this).

**4.6/4.7 Tunnel allowlist (RED→GREEN)**: `backend/tests/test_tunnel_allowlist.py` (35 tests) parses `scripts/cloudflared/config.yml` and replays cloudflared ingress semantics (first-match-wins; `path` = unanchored regex search ≙ Go RE2 MatchString). Asserts: final catch-all `service: http_status:404` with no hostname/path; every allow rule targets the same `http://127.0.0.1:8000`; hostname is an RFC 2606 `.example.com` placeholder; allowed set = `/api/health`, the 3 member-auth routes, 5 `/api/portal/*` paths; denied set = `/cv/*`, `/api/cv/*`, `/api/health/{db,full,redis}`, admin API (`/api/members`, `/api/users`, `/api/sales/dashboard`, `/api/system/db-export`, `/api/system/backup-config`), static (`/`, `/api-status`, `/docs`, `/openapi.json`); near-miss class denied (`/api/healthx`, `/api/auth/member-loginX`, `/api/auth/member-login/extra`, `/api/portalx/me`, bare `/api/portal`). RED: FileNotFoundError before the config existed. GREEN: `scripts/cloudflared/config.yml` (anchored `^…$` regexes, placeholders only) + `docs/portal-tunnel-allowlist.md` (provisioning steps, exact curl checks with expected statuses, Cloudflare dashboard walkthrough, rollback; notes method-level control stays at the app — ingress is path-level). `backend/mypy.ini` gained `[mypy-yaml.*] ignore_missing_imports` (pyyaml ships no py.typed; types-PyYAML not a runtime dep — TODO noted in file).

## Genuine forward RED→GREEN evidence (this session)

| Task | Test file | RED (captured before fix) | GREEN |
|---|---|---|---|
| 4.1 | `tests/test_portal_security.py` | Approval — behavior pre-existed (`verify_wompi_signature`); no RED possible, documented as spec-lock | 4/4 passed |
| 4.2 | `tests/test_portal_security.py` | Approval — CORSMiddleware pre-existed | 3/3 passed |
| 4.3 | `tests/test_portal_security.py` + `tests/portal_rls_bootstrap.py` | 3 DB-level tests FAILED with RLS disabled post-provisioning (unfiltered scan saw other members; targeted cross-member read returned B's row; no-context session saw rows) — via external /tmp plugin, not committed | 6/6 passed |
| 4.4 | `tests/test_portal_security.py` | `test_member_verify_exceeding_rate_rejected` FAILED: 11th request `401 {"detail":"Código incorrecto o expirado"}` instead of 429; login/resend passed (approval) | 3/3 passed |
| 4.5 | `api/portal_auth.py` + `core/config.py` | (paired with 4.4 RED) | suite green |
| 4.6 | `tests/test_tunnel_allowlist.py` | FileNotFoundError: scripts/cloudflared/config.yml (config absent) | 35/35 passed |
| 4.7 | `scripts/cloudflared/config.yml` + `docs/portal-tunnel-allowlist.md` | (paired with 4.6 RED) | 35/35 passed |

## Verification performed THIS session (real, not inferred)

- Full backend suite (safety net BEFORE: **372 passed**; AFTER: **423 passed**) — `cd backend && set -a && . ./.env && set +a && python -m pytest tests/ -q` (interpreter `/root/faceapp/.venv/bin/python`). 423 = 372 + 16 portal-security + 35 tunnel-allowlist. Zero regressions.
- Lint trio: `flake8 .` clean; `black --check .` → 130 files unchanged; `mypy .` → Success, no issues in 118 files.
- Env repair this session: `alembic==1.13.1` was MISSING from `/root/faceapp/.venv` (collection error on `tests/test_member_phone_migrations.py`: local `backend/alembic/` dir shadows as a namespace package when the real alembic isn't installed). Installed per requirements.txt pin — pre-existing environment defect, not a code change.

## Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command + result | `python -m pytest tests/test_portal_security.py tests/test_tunnel_allowlist.py -q` → **51 passed** (16 + 35) |
| Runtime harness command + result | N/A as a live-server harness — the tunnel's runtime enforcement point (cloudflared on LXC 114) is Phase 5 ops-time; in-repo runtime evidence is the DB-level RLS tests (real member_portal TCP login + real policies) and the TestClient integration tests above. `docs/portal-tunnel-allowlist.md` carries the exact post-open curl checks. |
| Rollback boundary | 3 commits on `feat/portal-security-suite`, 9 files, +1212/−19: `99659b5` (tests/test_portal_security.py + conftest fixture + portal_auth rate limit + config.py), `8baa902` (tests/portal_rls_bootstrap.py + RLS tests + conftest bootstrap wiring), `8463d36` (test_tunnel_allowlist.py + scripts/cloudflared/config.yml + docs/portal-tunnel-allowlist.md + mypy.ini). Revert per-commit or drop the branch; no shared state beyond the dev DB's `member_portal` role + RLS-enabled tables (mirrors prod `001_rls_setup.sql`; intentionally left in place, idempotent). |

## Deviations from design

- `core/rate_limiter.py` NOT modified (task 4.5 lists it): the shared limiter already existed there; the change is the configurable `MEMBER_AUTH_RATE_LIMIT` in `core/config.py` consumed by the route decorators — the limiter module had nothing left to add.
- RLS provisioning lives in a test bootstrap module rather than applying `001_rls_setup.sql` wholesale: the full script also creates backend_app/backend_readonly, FORCEs audit_logs RLS (would affect even the owner locally) and grants for roles the test DB doesn't use; the bootstrap applies the member_portal-relevant subset (§7 + RLS enable) VERBATIM instead.

## Learned (new this session)

- `str(sqlalchemy_url)` masks the password as `***` (SQLAlchemy 2.0) — always `render_as_string(hide_password=False)` when a usable connection string is needed.
- `backend/core/__init__.py` imports `core.database`, so ANY `from core.x import ...` transitively builds `PortalSessionLocal` — import-time env manipulation must patch `core.database` directly, not just `os.environ`.
- slowapi counters are process-global in-memory state shared across ALL tests: an autouse reset fixture is required the moment any route gets a limit, or unrelated suites fail with mystery 429s.
- Local dev `membership` role: not superuser, no CREATEROLE, but IS DB+table owner → cannot CREATE ROLE (falls back to `su postgres` peer auth) yet CAN grant/enable-RLS/create-policies. Table owners bypass non-FORCE RLS, so enabling RLS in the dev DB does not affect the privileged suite.
- A test provisioning script that idempotently re-applies its guarantees will silently un-do a manual RED setup — RED for security invariants needs the weakening applied AFTER provisioning (external plugin).
- FastAPI body param named `request` collides with slowapi's required `Request`: renaming to `body` means updating every body-field reference in the handler (2 here) — the existing suite caught it instantly.

## Remaining

Phase 5 (5.1 tunnel prereqs / 5.2 prod RLS verification / 5.3 deps + open) — ops-time, orchestrator-scheduled. 24/27 tasks complete (2.1–2.5, 1.1–1.2, 3.1–3.10, 4.1–4.7). Branch `feat/portal-security-suite` NOT pushed; PR3 not opened (chain strategy `feature-branch-chain`).

## Review budget note

PR3 slice = 1231 changed lines (9 files) — above the 800-line budget for a single PR, as forecast (tasks.md: High risk, chained PRs). The branch's 3 commits are work-unit shaped (controls / RLS / allowlist) and can be promoted to stacked PRs as-is if the orchestrator prefers slices under budget.
