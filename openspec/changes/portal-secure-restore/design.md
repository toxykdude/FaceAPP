# Design: Portal Secure Restore — Guest Purchase & Payment Integrity

## Context

`portal_webhook_renew` (portal.py:208) never reads the Redis pending record — SECURITY.md:498-504 is documented-but-missing; `GET /portal/pending-payment/{ref}` authenticates with global `SECRET_KEY` (WS-1); relay forwards client-context amounts. Member `phone` has NO unique index (dropped deliberately, `6b5c4d3e2f1a`) — dedup cannot race on it. Idempotency is fuzzy `notes LIKE`. Alembic head: `7c6d5e4f3a2b`.

## Architecture Decisions

| # | Decision | Choice | Rejected (why) |
|---|---|---|---|
| 1 | Redis↔PG atomicity | Delete-key strictly AFTER `db.commit()`, inside handler; DB idempotency via NEW unique `sales_transactions.wompi_reference` column (backfilled from notes) | Outbox (two stores, no 2PC — overkill); GETDEL-claim-first (crash before commit loses the key — violates "not consumed unless commit") |
| 2 | WS-1 internal key | New `PORTAL_INTERNAL_API_KEY` (backend) / `FACEGYM_PORTAL_INTERNAL_KEY` (Pages env). Unset/empty → deny-all 401, uniform (no existence disclosure) | Reuse `INTERNAL_API_SECRET` (Pages env leak would expose CV-service auth); `SECRET_KEY` (current, WS-1) |
| 3 | Pending record v2 | `{v:2, plan_id, member_id\|null, guest_name, guest_phone "57+10d", guest_email, amount:"69900.00"(DB price, Decimal str), wompi_reference}` — TTL stays 86400s | Extra amount_in_cents in Redis (derivable; one authoritative amount) |
| 4 | Amount transport | Webhook-renew body ADDS required int `amount_in_cents` (from `tx.amount_in_cents`). Backend: `pending.amount == plan.price` (server-authored, unchanged) AND `tx.amount_in_cents/100 >= plan.price` else 400 + alert log + relay staff email; key retained | Trusting relay `amount` (client-derivable); tx==pending equality (blocks legitimate overpayment) |
| 5 | Guest member mapping | `first_name`=first token, `last_name`=remainder or `""`; status=active, `consent_given_at=NULL`, `facial_data_enrolled=false`; membership `today…+plan.duration_days` (stack from furthest end_date, existing logic). Dedup: SQL canonical lookup (extract `_resolve_member` → `services/canonical_phone.py`, reused by portal_auth). Email unique-collision → retry email=NULL + log. Concurrency: Redis advisory lock `SET member-provision:{phone} NX EX 15` | Unique phone index (repo decision: phone is non-unique contact data, `5a4b3c2d1e0f`/`6b5c4d3e2f1a`); accept race silently (duplicate members confuse kiosk + billing) |
| 6 | Migration | `down_revision="7c6d5e4f3a2b"`: `CHECK (price > 0)` on `membership_plans` (fail-loud pre-check lists violating rows) + `wompi_reference VARCHAR(100) NULL` + UNIQUE index + regexp backfill from notes. CheckConstraint also in `MembershipPlan` model so `create_all` test DBs enforce it. Notes-LIKE alone: insufficient (substring false-positives; no race safety) | Wompi tx id as the idempotency key (reference is the user-visible contract + already in notes) |
| 7 | Plan encoding | `signature.ts` PLANS gains `facegymId` for the 4 gym plans (single Pages-side source); response gains `facegymPlanId`; renovar.astro DROPS hardcoded UUIDs, consumes response | Fetch `/api/portal/plans` dynamically (no stable slug key on backend plans; heuristic name/price matching fragile) |
| 8 | Relay restructure | After Wompi checksum + APPROVED: resolve planId via `parsePlanId`; gym plan (`facegymId` present) → require `tx.amount_in_cents >= PLANS.amountInCents && tx.currency === "COP"` (overpayment forwards) else staff alert, NO forward, still 200 to Wompi. Add `currency` to `WompiTransaction`. Forward = current shape + `amount_in_cents`; `member_id` only when pending has one; guest identity NEVER travels in the body (backend reads Redis) | Forwarding mismatch for backend to catch (relay is the cheap early wall; both check independently) |
| 9 | Webhook-renew order | HMAC → parse (require reference/tx_id/amount_in_cents) → Redis load (missing → check `wompi_reference` in DB → `already_processed`, else 404 + alert: covers TTL-expired legit payments, relay emails staff) → amount check (#4) → resolve member (Redis `member_id`, or guest #5) → Membership+Sale(+`wompi_reference`) single commit → post-commit: delete key, then `notify_cv_invalidation` (failure logged, sale intact). Body `member_id` ignored — Redis is authoritative; renovar member path unchanged (pending stores member_id at JWT-authed creation) | Reusing body member_id (pending record is the server-authored truth) |
| 10 | Guest endpoint | `POST /portal/pending-payment/guest` (no JWT): validates `wompi_reference` format `^PH-[a-z0-9-]+-\d{10}-[a-f0-9]{6}$`, normalizes phone (57+10 else 422, no record stored), resolves DB price. slowapi limit (pattern of `MEMBER_AUTH_RATE_LIMIT`) caps Redis stuffing | Reusing JWT endpoint (guests have no token) |
| 11 | Confirmation UX | confirmacion.astro APPROVED-guest copy: "compra registrada — activa tu membresía en el gimnasio con tu registro facial"; PENDING/DECLINED keep non-success states | Claiming enrollment/kiosk access (spec forbids) |
| 12 | Sale-gated activation scope | DESCOPE staff path (explicit): spec "any code path" (payment-integrity ~75-83) is enforced structurally on ALL public/portal surfaces — activation exists ONLY via webhook-renew (this design); guest + member renewals both land there. Staff `POST /api/memberships` (memberships.py:165-172) and `/{id}/renew` (:277) keep creating ACTIVE memberships without a same-commit sale: reception intentionally creates membership first and takes payment moments later via `POST /sales` (trap 21 — same-commit requirement breaks the assign flow and reads unpaid at the kiosk), and the kiosk payment gate (access_validator.py:159-178, regression-tested) already DENIES zero-paid (pending) memberships at the door. Read the requirement as portal-surface activation; tasks phase MUST encode this as a documented spec boundary | Same-commit staff sale (trap-21 regression; substitutes a kiosk gate that already exists and is tested) |

Amount-check rationale: `pending` stays `==` the plan price because it is server-authored (any deviation is tampering or staleness), while the Wompi amount may exceed it — overpayment is accepted, underpayment never.

## Data Flow

```
Guest: /comprar form → POST signature {plan} → {ref,sig,amountInCents,facegymPlanId}
       → POST /api/portal/pending-payment/guest (proxy) → Redis v2 record (no member_id)
Wompi → Pages webhook: checksum → gym-amount gate → GET pending (internal key)
       → POST webhook-renew {plan_id?, ref, tx_id, amount_in_cents, member_id?} (HMAC)
Backend: pending==plan.price AND tx/100 ≥ plan.price → member(dedup|create) → Membership+Sale commit
       → DEL pending key → CV invalidate → kiosk-visible
```

## File Changes

| File | Action |
|---|---|
| `backend/api/portal.py` | Modify: webhook-renew restructure; guest pending endpoint; internal-key GET |
| `backend/schemas/portal.py` | Modify: v2 request schemas (amount_in_cents req, member_id opt, guest schema) |
| `backend/services/canonical_phone.py` | Create: canonicalize + resolve_member_by_phone (portal_auth refactored to import) |
| `backend/models/membership.py`, `models/sale.py` | Modify: CheckConstraint; wompi_reference unique column |
| `backend/alembic/versions/20260818_*_price_check_wompi_reference.py` | Create |
| `backend/core/config.py` | Modify: PORTAL_INTERNAL_API_KEY |
| `backend/.env.example` | Create (file does NOT exist; only root `.env.example` does): placeholder keys MEMBER_PORTAL_DATABASE_URL, WOMPI_PUBLIC_KEY, WOMPI_INTEGRITY_SECRET, EVOLUTION_API_URL/EVOLUTION_API_KEY/EVOLUTION_INSTANCE_NAME, PORTAL_INTERNAL_API_KEY — placeholder values only, never real secrets |
| `powerhouse-site/functions/api/payment/signature.ts`, `webhook.ts` | Modify: #7, #8 |
| `powerhouse-site/functions/api/portal/pending-payment-guest.ts` | Create: proxy |
| `powerhouse-site/src/pages/comprar.astro` | Create: guest checkout (name/email/phone, 4 gym plans only) |
| `renovar.astro`, `planes.astro`, `pago/confirmacion.astro` | Modify: UUID fix; guest CTA; honest messaging |
| `backend/tests/test_portal_webhook_integrity.py`, `test_guest_provisioning.py`; `__tests__/api/webhook.test.ts` (+guest/amount suites) | Create/extend |

## Testing Strategy (STRICT TDD — RED first)

Pytest (exported `.env`, db+redis up): pending-missing→already_processed vs 404+alert; forged/missing HMAC no state; amount mismatch (pending, DB price) → no rows, key retained; commit-failure → key retained; replay after consumption → one membership/sale; concurrent same-reference → unique aborts loser; zero/negative price rejected (model+migration); guest: 57+10 normalize, bad phone 422 no record, phone dedup attach vs create, atomic Member+Membership+Sale (mid-commit abort), post-commit CV with X-API-Key + failure-tolerant; internal key: correct 200 / wrong / SECRET_KEY / unset → uniform 401; no secret in responses; `.env.example` placeholders.
Vitest: amount/currency gate (match forwarded, under/mismatch blocked + alert, wrong currency blocked); guest pending forwarded without member_id; client amount ignored (signature server-authored); confirmacion copy via page-data tests where harness allows; existing signature/webhook suites stay green.

## Threat Matrix

Skill rows (docs-like paths, git repo/commit/push/PR automation): **N/A** — HTTP/payment boundary only, no shell/VCS/process integration. Routing-boundary adversarial cases: forged Wompi checksum → 401 no forward; forged relay HMAC → 401 pre-lookup; key brute on pending GET → uniform 401; guest-endpoint reference stuffing → format regex + rate limit; secret leakage → response assertions. RED tests listed above.

## Migration / Rollout

Backend deploys FIRST (migrator role, trap 20): `set -a; . ./.env; . /etc/faceapp/migrate-db.env; set +a && ./venv/bin/alembic upgrade head && ./venv/bin/alembic current`; add `PORTAL_INTERNAL_API_KEY` to backend `.env` + `FACEGYM_PORTAL_INTERNAL_KEY` in Cloudflare dashboard (placeholders in repo only). Pages deploys minutes later (same window) — in the gap, old relay sends no `amount_in_cents`; new backend rejects those renewals loudly (relay logs, Wompi still gets 200). Rollback: revert commits; downgrade drops CHECK/index; un-consumed keys expire ≤24h.

## Delivery (feature-branch-chain)

faceapp: tracker `feat/portal-secure-restore` off main → PR1 `feat/portal-payment-integrity` (migration, config, webhook restructure, internal key) targets tracker → PR2 `feat/portal-guest-provisioning` (guest endpoint, dedup, canonical service, comprar proxy support) targets PR1 branch → tracker→main. powerhouse-site: single `feat/portal-guest-checkout`→main (relay gate + guest UI + tests). Backend merges before Pages; secrets provisioned at deploy, never committed.

## Open Questions

- [ ] Wompi event payload field name for currency in `data.transaction` (verify against live event docs during apply; relay treats missing currency as mismatch).
- [ ] MailChannels still available on this Pages plan (staff alerts depend on it; fallback: log-only alert).

## Spec Boundary Addendum (D12): sale-gated activation scope

Recorded at apply time (Unit 2) as the durable reading of the
payment-integrity spec's "any code path" requirement:

**Payment-integrity sale-gated activation is enforced structurally on ALL
public/portal surfaces via `/portal/webhook-renew` ONLY.** Both member
renewals (JWT pending record) and guest purchases (v2 identity record)
land in that single HMAC-verified endpoint, which alone creates
memberships from Wompi payments.

**Staff paths are intentionally descoped** from the same-commit sale
requirement:

- `POST /api/memberships` (memberships.py) and `POST /api/memberships/{id}/renew`
  keep creating ACTIVE memberships without a same-commit sale.
- Rationale (trap 21): reception intentionally creates the membership
  first and takes the payment moments later via `POST /sales` — the
  assign flow (`MemberForm.tsx`) depends on that ordering, and
  `POST /sales` must travel with `POST /memberships` for exactly this
  reason. Forcing a same-commit sale breaks the flow and leaves
  memberships reading as unpaid at the kiosk.
- The door is still guarded: the kiosk zero-paid gate
  (`cv_service/validation/access_validator.py`, zero-paid DENY) already
  refuses unpaid/pending memberships at entry and is regression-tested.
  A membership without its payment never gets a member through the door.

**Requirement reading:** "activation exists only via webhook-renew" is a
*portal-surface* activation contract. Any future staff-surface change that
lets a membership activate without either a committed sale or the kiosk
gate MUST reopen this boundary — it is a deliberate scope line, not an
oversight.
