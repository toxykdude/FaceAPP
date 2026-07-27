# Tasks: membership-report-kiosk-tunnel

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~825 |
| Suggested split | PR1(base=feature/tracker) → PR2(base=PR1) → PR3(base=PR2) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Date-range reports | PR1 | `pytest backend/tests/test_sales_date_range.py backend/tests/test_report_window.py -q` + `npm test -- --run src/test/reportRange.test.ts` (frontend) | `uvicorn`+httpx (real DB): reversed->422 both endpoints, dashboard sum(revenue_trend)==summary total_revenue | sales.py + dashboard_service.py + report_window.py + sales.ts + Reports.tsx + translations.ts + reportRange.ts + 3 slice test files + package.json/lock (@testing-library/dom harness enabler) |
| 2 | Display/access + 3-path invalidation | PR2 | `pytest backend/tests/test_memberships.py backend/tests/test_portal.py (new) -k "display or access or portal_write or invalidation" -q` | `uvicorn`+cv_service: renew `/memberships/{id}` -> `/cv/templates` new expiration, `/cv/members/{id}` access gate held, CV logs `/invalidate/{id}` | display/access predicates + 3 renewal paths |
| 3 | Portal security + tunnel allowlist | PR3 | `pytest backend/tests/test_portal_security.py (new) -q` | cloudflared: `/api/health` ok, `/cv/*` 404 | portal rate limits + tunnel allowlist config + verification doc |

## Phase 1: Foundation

- [x] 1.1 RED: `notify_cv_invalidation(id)` POSTs `{CV_SERVICE_URL}/invalidate/{id}` with `X-API-Key: settings.CV_API_KEY`
- [x] 1.2 GREEN: extract `backend/api/members.py:31` to util

## Phase 2: Date-Range Reports

- [x] 2.1 RED: reversed/malformed window → 422; single-day included; half-open `[start 00:00, (end+1) 00:00)` app tz
- [x] 2.2 RED: dashboard+summary totals agree, same window
- [x] 2.3 GREEN: `start_date`/`end_date` params on BOTH `/sales/dashboard` + `/sales/report/summary` (`backend/api/sales.py`); half-open window in `backend/services/dashboard_service.py`
- [x] 2.4 GREEN: `sales.ts`+`Reports.tsx` range select; trend window-relative
- [x] 2.5 REFACTOR: half-open window builder

PR1 status: committed on `feature/tracker` (commit `a4613d9`), 798 changed
lines (within the 800-line budget). Genuine forward RED→GREEN evidence for
the previously-missing frontend wiring gap (invalid custom range now blocks
both fetches and shows an inline message) — see
`sdd/membership-report-kiosk-tunnel/apply-progress` rev 4. Not pushed; no PR
opened (awaiting explicit go-ahead).

## Phase 3: Display vs Access + Invalidation

- [x] 3.1 RED: furthest expiration deterministic on ties; cross-member isolation
- [x] 3.2 GREEN: `sync_templates` correlated `MAX(end_date)` + tie-break `MAX(created_at)`,`MAX(id)`; DROP `start_date<=today` on DISPLAY
- [x] 3.3 RED: access denies pre-start, grants at start boundary (`start_date<=today AND end_date>=today`)
- [x] 3.4 GREEN: `get_member_membership` for ACCESS; `access_validator.py` `start_date<=today`
- [x] 3.5 RED: post-commit invalidation on 3 paths: `POST /invalidate/{membership.member_id}` + `X-API-Key`; NO eviction on rollback
- [x] 3.6 RED: `portal_renew` writes under `get_db` after JWT + `member.id` scope; `member_portal` CANNOT INSERT (SELECT-only)
- [x] 3.7 GREEN: `renew_membership` (`memberships.py:208`) → `async`; post-commit `await notify_cv_invalidation(str(membership.member_id))`
- [x] 3.8 GREEN: `portal_renew` (`portal.py:95`): `get_portal_session`→`get_db`; `async`; post-commit invalidation
- [x] 3.9 GREEN: `portal_webhook_renew` (`portal.py:204`): post-commit invalidation
- [x] 3.10 REFACTOR: invalidation helper

PR2 status: implemented on `feature/pr2-membership-expiration-access`
(branched off `feature/tracker`), 692 changed lines (within the 800-line
budget). Genuine forward RED→GREEN evidence for all Phase 1 + Phase 3
tasks — see `sdd/membership-report-kiosk-tunnel/apply-progress` rev 5.
Not committed to `feature/tracker`; not pushed; no PR opened.

## Phase 4: Portal Security

- [ ] 4.1 RED: forged/missing HMAC-SHA256 webhook → 401, no state change
- [ ] 4.2 RED: disallowed CORS rejected
- [ ] 4.3 RED: cross-member `/portal/me` denied under RLS (SELECT-only)
- [ ] 4.4 RED: exceeded-rate on 3 `/api/auth/member-*` rejected
- [ ] 4.5 GREEN: slowapi per-route limits on 3 `/auth/member-*` (`rate_limiter.py`, `config.py`)
- [ ] 4.6 RED: allowlist — `GET /api/health` + 3 `/api/auth/member-*` + `/api/portal/*` reachable; `/cv/*`, `/api/health/db`, `/api/health/full` denied
- [ ] 4.7 GREEN: allowlist config + verification doc

## Phase 5: Deployment Prerequisites

- [ ] 5.1 Tunnel prereqs (no secrets): cloudflared, Pages
- [ ] 5.2 Verify RLS `001_rls_setup.sql` APPLIED (`member_portal` SELECT-only, `MEMBER_PORTAL_DATABASE_URL`) pre-open
- [ ] 5.3 Confirm deps (Redis, Evolution, Wompi, cloudflared); then open
