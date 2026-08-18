# Proposal: Portal Secure Restore — Guest Purchase and Payment Integrity

## Intent

Restore the customer portal at powerhousegym.co/portal — members check and renew memberships on the web, and NEW guests buy online so a Wompi-confirmed payment provisions Member + Membership + SalesTransaction atomically in FaceAPP. Make payment integrity structural: no free/$0 memberships, no client-trusted amounts, no leaked secrets. Implements the documented-but-missing SECURITY.md:498-504 pending-payment contract; closes WS-1 and the $0-plan hole.

## Scope

### In Scope
- Backend: `/portal/webhook-renew` consumes the Redis pending record, verifies amounts (DB plan price + Wompi-verified amount from the relay), and deletes the key inside the same atomic transaction.
- Backend: guest provisioning — pending record without a member creates Member (active, `consent_given_at=NULL`, `facial_data_enrolled=false`) + Membership + Sale atomically; canonical-phone (57+10) dedup attaches to an existing member. Post-commit CV invalidation.
- Backend: migration adding `CHECK (price > 0)` on `membership_plans` (migrator-role mechanics, trap 20); dedicated internal key for `GET /portal/pending-payment/{reference}` (replaces `SECRET_KEY`, WS-1 — design picks the setting name); `.env.example` gains `MEMBER_PORTAL_DATABASE_URL`, `WOMPI_*`, `EVOLUTION_*` placeholders.
- Portal repo (powerhouse-site): relay verifies Wompi `amount_in_cents` + currency vs plan before calling webhook-renew; guest checkout for the 4 gym plans captures name/phone/email; pending amounts become server-authored (never client-sent); honest `/pago/confirmacion` messaging; fix renovar.astro plan-UUID drift.
- STRICT TDD: pytest (`backend/tests/`), vitest (`powerhouse-site/__tests__/`).

### Out of Scope
- PT plans (9 `pt-*`) — stay on the manual staff-email path; backend PT modeling is a future change.
- Web biometric enrollment/consent — onboarding gap documented as "buy on web, enroll at gym"; kiosk denies unknown faces.
- member-verify rate limiting — owned by in-flight `membership-report-kiosk-tunnel` (dependency, excluded to avoid collision).
- Ops-layer: cloudflared allowlist, secret provisioning (Cloudflare + LXC 114), PAT rotation — tracked as dependencies.

## Capabilities

### New Capabilities
- `guest-purchase-provisioning`: guest checkout → identity capture → payment → atomic provisioning with phone dedup and no biometric consent.
- `payment-integrity`: server-authoritative amounts end-to-end; $0 plans impossible at DB level; activation only with a persisted sale ≥ plan price; idempotent replay; secrets server-side only.

### Modified Capabilities
- `customer-portal-runtime` (introduced by in-flight `membership-report-kiosk-tunnel`): webhook reconciliation consumes/verifies pending records; internal-key auth on pending reads; documented portal env placeholders.

## Approach

Every amount becomes server-derived (Pages plan table / backend catalogue — never client-sent). The relay checks the Wompi transaction amount against the plan before signing the webhook; the backend re-verifies against DB price and consumes the pending key inside the atomic commit (webhook-only activation). Guest identity rides the pending record. Exact key naming and pending-record shape are design decisions.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/api/portal.py` | Modified | Reconciliation, guest provisioning, internal-key auth |
| `backend/models/membership.py` + new alembic migration | Modified | `CHECK (price > 0)` via migrator role |
| `backend/core/config.py`, `backend/.env.example`, `backend/tests/` | Modified | Key setting; env placeholders; TDD suites |
| `powerhouse-site/functions/api/payment/{webhook,signature}.ts` | Modified | Amount/currency verification; guest branch; server-authored amounts |
| `powerhouse-site/renovar.astro`, `planes.astro`, `entrenadores/[slug].astro`, `pago/confirmacion.astro`, `__tests__/` | Modified | Guest identity capture, honest messaging, UUID-drift fix, vitest |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Underpayment slips through | High | Relay cents-vs-plan check + backend DB-price re-check + sale required in the atomic commit |
| Duplicate member on guest purchase | Medium | Canonical-phone lookup before INSERT; existing unique index |
| Migration run as wrong role (trap 20) | Medium | MIGRATE_DATABASE_URL mechanics; verify with `alembic current` |
| Collision with in-flight portal change | Medium | portal_auth excluded; rebase onto its landed portal.py edits |
| Two-repo deploy drift (secrets/env) | Medium | Fail-closed defaults; deploy checklist as success criteria |

## Rollback Plan

Revert both repos' commits; downgrade migration drops the CHECK only (no data loss); unconsumed Redis keys expire via 24h TTL; portal returns to renewal-only and guests to the manual staff path. Retain the WS-1 key fix even on partial rollback.

## Dependencies

- In-flight `membership-report-kiosk-tunnel` (rebase point; member-verify limits land there).
- Ops: cloudflared allowlist; Cloudflare Pages + LXC 114 secret provisioning (internal key, WOMPI); PAT removal from remote URL + rotation at deploy time.
- Live Redis/Postgres; Wompi credentials.

## Success Criteria

- [ ] E2E guest purchase: webhook APPROVED → Member + Membership + SalesTransaction committed atomically; kiosk-visible after CV invalidation.
- [ ] Existing-phone dedup: membership attaches to the existing member, no duplicate.
- [ ] Amount mismatch (Wompi amount < plan price) → NO membership + staff alert.
- [ ] DB rejects $0 plans (`CHECK (price > 0)`).
- [ ] Pending key consumed exactly once; replayed reference → one membership (idempotent).
- [ ] No secret leakage: integrity/events/internal keys never client-visible; PAT out of remote URL at deploy.
- [ ] Backend pytest green (exported `.env`, db+redis up); Pages-function vitest green.
