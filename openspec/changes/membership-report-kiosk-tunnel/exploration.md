# Exploration: membership-report-kiosk-tunnel

> Three requested outcomes investigated against real code: (1) report
> filtering by arbitrary custom start/end dates, (2) kiosk must show the
> furthest membership expiration for multi-membership / advance-paid
> customers, (3) re-enable the public webpage/tunnel members use to check
> status. Outcome 2 has two confirmed code bugs; outcomes 1 and 3 are
> feature/infra gaps. No product code was modified.

## Quick verdict

| Outcome | Type | Verdict | Primary surface |
|---|---|---|---|
| 1 — Custom date reports | Feature gap | Backend already supports dates on `/sales` + `/sales/report/summary`; missing on `/sales/dashboard` + UI | `Reports.tsx`, `DashboardService`, `sales.py` |
| 2 — Furthest expiry on kiosk | **Two bugs** | Display date comes from Redis cache via `/cv/templates` (no ordering); both cache + access query exclude future-dated prepaid memberships | `cv_internal.py`, `cv_service/main.py` |
| 3 — Re-enable public tunnel | Infra + verify | Portal backend exists and is wired; tunnel + portal frontend live OUTSIDE this repo; requires `MEMBER_PORTAL_DATABASE_URL`, RLS, secrets, cloudflared | `portal.py`, `portal_auth.py`, `001_rls_setup.sql`, runtime |

## Current State

### Architecture (relevant slice)
Three-service platform. Backend (FastAPI/SQLAlchemy) owns `/api`. CV service
(OpenCV/FaceNet) owns `/cv/*` and a WebSocket the kiosk connects to. Frontend
is a React/Vite SPA. PostgreSQL roles: `backend_app`, `backend_readonly`,
`member_portal` (RLS-isolated). Redis holds the CV template cache + portal
PIN/lockout state. Public exposure is a runtime Cloudflare Tunnel (cloudflared)
pointing at the backend; the member-facing portal FRONTEND is a separate
Cloudflare Pages site (no `/portal` route exists in `frontend/src/App.tsx`).

### Outcome 1 — Reports today
- `GET /api/sales` (`backend/api/sales.py:35`) and `GET /api/sales/report/summary`
  (`sales.py:172`) ALREADY accept optional `start_date` / `end_date` query params.
- `GET /api/sales/dashboard` (`sales.py:156`) takes ONLY `days` (preset window).
- `DashboardService` (`backend/services/dashboard_service.py`) computes every
  series as `now - timedelta(days=days)`; methods are `days`-based only.
- Frontend `Reports.tsx` offers only preset ranges (today / 7 / 30 / 90 / year)
  via a `<Select>`; `salesApi.getReportSummary()` is called with NO params
  (`Reports.tsx:143`) so the summary is effectively all-time regardless of the
  selected range. No `<DatePicker>` anywhere in `Reports.tsx` or `SalesList.tsx`.
- Tests: `test_sales.py` only asserts routes are reachable; no date-range test.

### Outcome 2 — Kiosk expiry today
The kiosk `membership_end_date` is NOT read live from the DB per recognition.
Data flow:

1. CV service loads templates into Redis via `_load_templates()`
   (`cv_service/main.py:165`) → `GET /cv/templates` (`cv_internal.py:45`).
2. On each WebSocket frame the matcher returns `member_data` from the Redis
   cache (`cv_service/main.py:536`), and the handler emits
   `membership_end_date` from that cache (`main.py:607`).
3. Separately, `AccessValidator.validate_access()` calls
   `GET /cv/members/{id}/membership` (`cv_internal.py:109`) for the
   grant/deny decision.

**Bug A — arbitrary row wins in the cache.** The `/cv/templates` join filters
`status='active' AND start_date <= today AND end_date >= today` with NO
`order_by(end_date.desc())` and `.distinct()` (`cv_internal.py:70-78`). A member
can hold multiple concurrent active memberships (no uniqueness guard in
`memberships.py create_membership`, `memberships.py:86`), so the join yields
multiple rows; the cache stores one record per `member_id`, so the LAST iterated
row wins arbitrarily — frequently an older/current end date, not the furthest.

**Bug B — advance-paid (future-dated) memberships are invisible.** Portal
renewal sets `start_date = active.end_date + 1 day` (`portal.py:128-133`), so
prepaid memberships legitimately have future start dates. Both the cache join
and `/cv/members/{id}/membership` filter `start_date <= today`, so a prepaid
membership is excluded from both display AND access. If the current membership
has expired but a prepaid one is queued, access can be denied despite payment.

**Reference (correct) logic already exists** at `events.py:196-204`
(`/events/today-recognized`): filters `end_date >= today`, orders by
`end_date.desc()`, and does NOT require `start_date <= today` — this is the
pattern outcomes 2 should adopt.

**Cache staleness:** templates refresh only every 10 minutes
(`_periodic_refresh`, `main.py:232`). Portal/webhook renewals (`portal.py`,
`portal.py:204`) never call `/cv/reload` or `/cv/invalidate/{member_id}`, so
even after fixing the query a renewal takes up to 10 min to reach the kiosk.

### Outcome 3 — Public tunnel today
- Portal backend EXISTS and is registered in `main.py:191-192`:
  `/api/auth/member-login|member-verify|member-resend`, `/api/portal/me|plans|
  renew|webhook-renew|pending-payment`.
- Auth model: phone + WhatsApp PIN (Evolution API) → member JWT with
  `type: "member"` (`portal_auth.py`, `deps.py:139`).
- DB isolation: `/portal/me` and `/portal/renew` use `get_portal_session`
  (`deps.py:190`) → `PortalSessionLocal` under the `member_portal` DB role with
  `SET LOCAL app.member_id` and RLS policies (`scripts/migrations/
  001_rls_setup.sql:147-171`) restricting a member to their own rows.
  `MEMBER_PORTAL_DATABASE_URL` unset → `get_portal_session` raises RuntimeError.
- Static SPA serving at `/` exists "for when tunnel hits backend directly"
  (`main.py:197-219`).
- Tunnel mechanism is NOT in this repo (no cloudflared config, no `tunnel`
  references anywhere). It is a runtime Cloudflare Tunnel on the server. The
  public portal FRONTEND is a separate Cloudflare Pages project; the Wompi
  webhook is relayed by a "Cloudflare Pages Function webhook"
  (`portal.py:208-216`).

## Affected Areas

- `backend/api/cv_internal.py` — `sync_templates` join (Bug A) and
  `get_member_membership` filter (Bug B); both must select furthest end_date
  across active + future-dated active memberships.
- `backend/services/dashboard_service.py` — every method is `days`-based; needs
  optional `start_date`/`end_date` override path for outcome 1.
- `backend/api/sales.py` — `/sales/dashboard` route should accept optional
  `start_date`/`end_date` (fall back to `days`); pass through to service.
- `frontend/src/pages/Reports/Reports.tsx` — add custom date pickers, thread
  dates into `getDashboardReport` + `getReportSummary`, replace/augment preset
  select.
- `frontend/src/api/sales.ts` — extend `getDashboardReport` signature to accept
  optional `start_date`/`end_date`.
- `cv_service/main.py` — `_load_templates` cache shape; consider caching the
  furthest end_date per member; optionally call CV invalidate from backend
  renewals to cut the 10-min staleness window.
- `backend/api/portal.py` + `backend/api/portal_auth.py` — verify endpoints
  still pass under current auth/RLS once the tunnel returns; add tests.
- `backend/core/database.py` + `scripts/migrations/001_rls_setup.sql` — runtime
  prerequisites for the tunnel (`MEMBER_PORTAL_DATABASE_URL`, `member_portal`
  role + password, RLS applied).
- `backend/api/events.py:196-204` — reference implementation to mirror for
  outcome 2; not itself broken.

## Approaches

### Outcome 1 — custom date reports
1. **Extend dashboard to optional date range** — Add optional
   `start_date`/`end_date` to `/sales/dashboard` and `DashboardService`;
   when present, compute series from the explicit window instead of `days`.
   Frontend adds two MUI `<DatePicker>` inputs + a "Custom" preset.
   - Pros: Single endpoint, consistent with `/sales` + `/report/summary`,
     small backend change, predictable review size.
   - Cons: Must refactor ~6 `DashboardService` methods off `timedelta(days=)`;
     member-growth + new-signups are calendar-month anchored and need care.
   - Effort: Medium.
2. **New `/sales/dashboard/range` endpoint** — Leave `days` version untouched;
   add a parallel range-based endpoint + service method.
   - Pros: Zero risk to existing dashboard; explicit API.
   - Cons: Two code paths to maintain; duplicated aggregation logic.
   - Effort: Medium.

### Outcome 2 — furthest expiry
1. **Fix both CV queries + cache shape (recommended)** — In `/cv/templates`,
   select the furthest active membership per member via a correlated subquery /
   `MAX(end_date)` window (include `status='active' AND end_date >= today`,
   drop `start_date <= today`). Apply the same selection in
   `/cv/members/{id}/membership`. Cache the furthest end_date. Optionally have
   `portal.py`/webhook renewals POST `/cv/invalidate/{member_id}`.
   - Pros: Correct at the source; fixes both display and access; aligns with
     the `events.py:196` reference; modest change.
   - Cons: Cross-service touch (backend query consumed by CV cache); cache
     refresh window remains unless invalidate is wired.
   - Effort: Medium.
2. **Live lookup per recognition** — Have the CV WebSocket fetch membership on
   each recognition instead of relying on the cache for the date.
   - Pros: Always fresh; no cache-shape change.
   - Cons: Adds a backend round-trip per face match (latency, load); the
     `validate_access` path already does one lookup — doubling it; undermines
     the cache design.
   - Effort: Medium-High.

### Outcome 3 — re-enable tunnel
1. **Infra-first, then verify + test (recommended)** — Provision/confirm
   `MEMBER_PORTAL_DATABASE_URL`, `member_portal` role + RLS migration applied,
   `EVOLUTION_API_KEY`, `WOMPI_*` secrets, CORS allowlisting the public domain,
   and restart cloudflared. Re-deploy the Cloudflare Pages portal frontend.
   Code-side: add backend integration tests for `/portal/me`, login/verify,
   webhook HMAC; harden if any drift found.
   - Pros: Matches reality (tunnel config lives outside the repo); smallest
     safe code change; security posture preserved.
   - Cons: Cannot be fully done from this repo alone; depends on ops access.
   - Effort: Low (code) / Variable (infra).
2. **Embed portal route in this SPA** — Add `/portal` to `App.tsx` served from
   the same build.
   - Pros: One artifact to deploy.
   - Cons: Contradicts current architecture (separate Pages site exists);
     mixes admin auth context with member auth; larger, riskier change.
   - Effort: High.

## Recommendation

- **Outcome 1:** Approach 1 — extend `/sales/dashboard` + `DashboardService`
  with optional `start_date`/`end_date`, add date pickers in `Reports.tsx`,
  and pass the same window to `getReportSummary`. Lowest-risk, consistent with
  the existing `/sales` filtering convention.
- **Outcome 2:** Approach 1 — fix `/cv/templates` and
  `/cv/members/{id}/membership` to select the furthest `end_date` among
  `status='active' AND end_date >= today` (mirroring `events.py:196-204`),
  cache the furthest date, and wire renewal endpoints to call
  `/cv/invalidate/{member_id}` to cut the 10-min staleness.
- **Outcome 3:** Approach 1 — treat as infra re-enablement first (cloudflared,
  secrets, RLS, Pages deploy), then add backend portal tests in this repo and
  verify HMAC + RLS behavior. Do not absorb the portal frontend into this SPA.

## Risks

- **Bug B is also a payment/access correctness risk**, not just display: a
  member who prepaid while current is active, then the current lapses, may be
  denied entry despite holding a paid future membership. Confirm intended
  access semantics before shipping (grant on any `end_date >= today` active
  membership, regardless of `start_date`).
- **RLS misconfiguration on re-enable** would expose other members' data; the
  `member_portal` role, its password, and `001_rls_setup.sql` must be verified
  applied in the production DB before the tunnel is opened.
- **Webhook security** depends on `WOMPI_INTEGRITY_SECRET`; code safely returns
  401 if unset (`portal.py:190-201`), but the secret MUST be provisioned or
  renewals silently fail.
- **Rate limiting** is global (slowapi) with prod relying on Nginx per-route
  limits (per README). Re-opening the tunnel without Nginx limits exposes
  `/auth/member-login` to PIN-request flooding (mitigated partly by the 60s
  cooldown + 3-attempt lockout in `portal_auth.py`).
- **Cache staleness** (10-min refresh) can make a freshly renewed membership
  appear expired on the kiosk until next sync unless CV invalidate is wired.
- **Dashboard refactoring** for calendar-anchored series (member growth, new
  signups) is not a pure `days` substitution; tests must cover custom ranges
  crossing month boundaries.
- **Review size:** the three outcomes span backend, CV service, and frontend;
  an 800-line single PR is plausible but tight — chained PRs (one per outcome)
  are likely cleaner.
- **Dependencies:** Evolution API (WhatsApp), Wompi (payments), Redis, Postgres
  RLS, cloudflared — any unavailable blocks outcome 3 specifically.

## Uncertainties

- Location/source of the public portal FRONTEND (Cloudflare Pages project,
  likely a separate repo) — not in this repo.
- Whether cloudflared is installed/running and its tunnel config — lives on
  the server, not here.
- Whether the RLS migration is currently applied in the production database.
- Exact intended access rule for advance-paid memberships (grant immediately vs
  only when `start_date` is reached) — needs product confirmation; this
  exploration assumes "show + grant on furthest active end_date".
- Whether `/sales/dashboard` consumers other than `Reports.tsx` exist (none
  found, but external dashboards could call it).

## Ready for Proposal

**Yes.** All three outcomes are well-scoped against real code. Before proposal
the orchestrator should confirm with the user:
1. Intended access semantics for future-dated prepaid memberships (grant on
   `end_date >= today` regardless of `start_date`?).
2. Where the portal frontend lives and whether outcome 3 is ops-only or also
   requires code in this repo.
3. Delivery preference: single PR vs chained PRs per outcome (recommend
   chained given the 800-line budget and cross-service spread).
