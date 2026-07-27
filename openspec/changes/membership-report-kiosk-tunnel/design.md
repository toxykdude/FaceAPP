# Design: Membership Reports, Kiosk Expiration, and Portal Tunnel

## Technical Approach

Three outcomes on the existing FastAPI backend + CV service + React/Vite SPA: (1) half-open custom date window on `/sales/dashboard` + `/sales/report/summary`; (2) split membership **display** from **access** via two predicates, select the furthest paid expiration deterministically, invalidate CV cache on every renewal path; (3) re-enable the external portal via a route-restricted Cloudflare Tunnel after RLS/webhook/CORS/rate-limit verification.

## Architecture Decisions

| Decision | Choice | Rejected (why) |
|---|---|---|
| Display vs access | Two predicates | Shared query grants early access (spec violation) |
| Furthest expiration | Correlated `MAX(end_date)` + tie-break `MAX(created_at)`, `MAX(id)` | `.first()` non-deterministic on ties (members.py:103) |
| Cache freshness | Invalidate on renewal + bounded TTL | TTL-only serves stale up to `CACHE_TTL` |
| Dashboard range | Optional `start_date`/`end_date` on `/sales/dashboard` | New route duplicates aggregation |
| Tunnel exposure | Exact allowlist (below) | Whole backend leaks `/cv/*` |
| Portal write path | `portal_renew` uses privileged `get_db` after JWT ownership check (same as `portal_webhook_renew`) | Broad portal-role writes weaken RLS; `get_portal_session` is SELECT-only |

### Invariants (no open questions)

- **Display** returns the furthest paid expiration regardless of `start_date`; never gates entry.
- **Access** always enforces `start_date <= today AND end_date >= today`; early entry is NEVER granted.
- **`member_portal` RLS role stays SELECT-only**; no INSERT/UPDATE grant, no policy weakening.

## Portal Write Boundary (corrected)

`get_portal_session` binds the `member_portal` role (SELECT-only, `001_rls_setup.sql`:147–151). Reads (`/portal/me`, active-membership lookups) keep this RLS session; writes cannot use it.

- **Write paths:** `portal_renew` (portal.py:95) and `portal_webhook_renew` (portal.py:204). Both insert `Membership` + `SalesTransaction`.
- **Secure path:** switch `portal_renew`'s DB dep `get_portal_session` → **`get_db`** (privileged backend session) — the exact pattern `portal_webhook_renew` already uses. Ownership is enforced **before** the write via `Depends(get_current_member)` (JWT) + explicit `member.id` filters; webhook adds HMAC-SHA256. No DB function — not the repo's pattern.
- **Transaction/commit boundary:** each path issues a **single `db.commit()`** (`portal_renew`:161, `portal_webhook_renew`:315) after both inserts; rollback is atomic.
- **Cache invalidation:** `notify_cv_invalidation` fires **post-commit only** (no eviction on rollback).

## Data Flow

```
DB --display: MAX(end_date)/member, active, end_date>=today--> /cv/templates --> Redis --> kiosk
DB --access:  start_date<=today<=end_date--> /cv/members/{id} --> AccessValidator
renew(admin/portal/webhook) --commit--> notify_cv_invalidation(<owner>) --POST /invalidate/{id} (X-API-Key)--> CV
External Pages --Cloudflare Tunnel(allowlist)--> /api/auth/member-* + /api/portal/* + /api/health
```

## File Changes (all Modify)

- `backend/api/members.py` — extract `notify_cv_invalidation` (31) to shared util; keep `X-API-Key: settings.CV_API_KEY`.
- `backend/api/memberships.py` — `renew_membership` (208, commit 235): make `async`; post-commit `await notify_cv_invalidation(str(membership.member_id))`.
- `backend/api/portal.py` — `portal_renew` (95): dep `get_portal_session` → `get_db`; make `async`; post-commit invalidation. `portal_webhook_renew` (204, commit 315): already `async` + `get_db`; add post-commit invalidation.
- `backend/api/cv_internal.py` — `sync_templates`: correlated `MAX` + tie-break, drop `start_date<=today` on DISPLAY only; `get_member_membership`: KEEP it for ACCESS.
- `cv_service/validation/access_validator.py` — defense-in-depth `start_date <= today` guard (backend is source of truth).
- `backend/services/dashboard_service.py`, `backend/api/sales.py` + `schemas/sale.py`, `frontend/src/api/sales.ts` + `Reports.tsx` — optional `start_date`/`end_date` end-to-end; trend series window-relative.
- `backend/core/rate_limiter.py` + routes, `backend/core/config.py` — slowapi per-route limits on the three `/auth/member-*`; document (no values) tunnel prerequisites.

## Interfaces / Contracts

**Half-open window (app timezone):** `[start_date 00:00, (end_date+1) 00:00)`. Single-day = that day. `start>end` → 422.

**Two predicates:**
```
DISPLAY (sync_templates): status='active' AND end_date>=today   # NO start_date filter
  per member: end_date = (SELECT MAX(end_date) FROM memberships
              WHERE member_id=:m AND status='active' AND end_date>=today)
ACCESS (get_member_membership + AccessValidator):
  status='active' AND start_date<=today AND end_date>=today
```
Unlike `events.py:101` (`.offset().limit()`, non-deterministic on ties), display uses correlated `MAX`.

**Invalidation (existing contract, no new secret):** `notify_cv_invalidation(id)` POSTs `{CV_SERVICE_URL}/invalidate/{id}` with `X-API-Key: settings.CV_API_KEY`; verified by `cv_service/main.py` via `verify_api_key`.

## Testing Strategy (Strict TDD — RED first)

**Unit:** reversed/malformed window 422; single-day included; half-open boundary; dashboard/summary agree for same window; display `MAX` deterministic on ties; access denies pre-start, grants at start boundary; renewal invalidation fires post-commit on all 3 paths asserting `POST /invalidate/{id}` + `X-API-Key`; **`portal_renew` write succeeds under `get_db` after JWT auth while `member_portal` still cannot INSERT (grant unchanged)**; cross-member cache isolation; forged/missing HMAC rejected.

**Integration:** CORS rejection of disallowed origin on portal routes + rate limiting on three `/auth/member-*`; `/portal/me` cross-member denied under RLS; tunnel allowlist — exact health + 3 `/api/auth/member-*` + `/api/portal/*` reachable, `/cv/*` and `/api/health/db` denied.

## Threat Matrix

Routing boundary only (tunnel allowlist + webhook + CV invalidate); no executable/git/PR boundary.

**Public allowlist (exact):** `POST /api/auth/member-login`, `POST /api/auth/member-verify`, `POST /api/auth/member-resend`, `/api/portal/*` (self-service), `GET /api/health` (basic). All others denied — explicitly all `/cv/*` and `/api/health/db`, `/api/health/full`.
- **RED:** allowlist reachability + forged webhook → 401, no state change (see Testing). Non-allowlisted denied at cloudflared ingress.

**Migration / Rollout:** No destructive migration. RLS `001_rls_setup.sql` verified **applied** (`member_portal` role, `MEMBER_PORTAL_DATABASE_URL` set) before tunnel opens. **Rollback:** disable cloudflared; revert dashboard/selection/invalidation/session switch; keep RLS enabled.

## Open Questions

- [ ] Portal frontend (Cloudflare Pages) owner + tunnel config location (server-side, outside repo).
- [ ] External dependencies (Evolution API, Wompi, Redis, cloudflared) availability — any down blocks outcome 3.
