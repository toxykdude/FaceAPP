# Proposal: Membership Reports, Kiosk Expiration, and Portal Tunnel

## Intent

Deliver custom-period reporting, accurate paid expiration display without early access, and a securely restored customer portal tunnel.

## Scope

### In Scope
- Apply arbitrary valid `start_date`/`end_date` values across dashboard and summary data; retain presets.
- Display the furthest paid expiration immediately while denying access before its `start_date`; invalidate kiosk/CV caches after renewals.
- Verify portal authentication, RLS isolation, webhook integrity, CORS/rate limits, tunnel configuration, and integration tests.

### Out of Scope
- Customer portal UI/Pages code; it belongs to a separate repository.
- Early access, provider replacement, or public CV endpoints.
- Final PR slicing; tasks will auto-forecast against the 800-line budget.

## Capabilities

### New Capabilities
- `custom-report-date-range`: Consistent report data for any valid date interval.
- `membership-expiration-access`: Latest expiration display, independent start/end access enforcement, and renewal-driven cache freshness.
- `customer-portal-runtime`: Portal availability through verified tunnel, auth, RLS, webhook, and runtime controls.

### Modified Capabilities
None; no existing OpenSpec capability specifications are present.

## Approach

Add validated sales date parameters end-to-end. Separate display selection from access eligibility, select the latest paid expiration deterministically, and invalidate caches on renewal paths. Enable the tunnel only after backend tests and an operational checklist pass. Persist no `.env` values.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/api/sales.py`, sales service | Modified | Date aggregation |
| `frontend/src/pages/Reports/`, `frontend/src/api/sales.ts` | Modified | Range selection |
| `cv_service/main.py`, recognition cache | Modified | Expiration/access/cache |
| `backend/api/portal.py`, webhooks, RLS migrations | Modified | Portal security |
| External portal repo/tunnel | Dependency | UI and routing |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Early entry | Medium | Separate predicates; boundary tests |
| Stale expiration | Medium | Event invalidation plus bounded TTL |
| Cross-member exposure | High | RLS isolation tests; deny-by-default checks |
| Forged webhook/secret leak | High | Signature verification; redaction; secret management |

## Rollback Plan

Disable the tunnel and revert API/UI, selection, and invalidation changes. Keep RLS enabled; no destructive migration is required.

## Dependencies

- External portal repository/deployment owner.
- Cloudflare Tunnel/DNS, `member_portal` role with RLS, Redis, Evolution, and Wompi secrets.

## Success Criteria

- [ ] Custom-range dashboard and summary totals match; invalid/reversed ranges fail validation.
- [ ] Tests prove latest expiration display, no pre-`start_date` entry, and renewal visibility within one invalidation cycle.
- [ ] Integration tests deny cross-member access and invalid webhook signatures.
- [ ] Portal health/auth succeeds through the tunnel without public CV routes or leaked secrets.
