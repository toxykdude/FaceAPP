# Tasks: portal-secure-restore

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | faceapp ~1200–1400 · powerhouse-site ~680–780 · total ~1900–2150 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | auto-chain (cached) |
| Chain strategy | feature-branch-chain |
| Suggested split | PR1 (base=tracker, 650–780) → PR2 (base=PR1 branch, 575–665) → tracker→main; then Pages PR3 → main (680–780) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

> STRICT TDD keeps each unit's tests with its code (work-unit-commits): `.env.example`+config land in PR1 (placeholder scenario tested there), deploy docs land in PR2. Backend PRs merge BEFORE Pages — the relay's new `amount_in_cents` field depends on the new backend accepting it.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Payment integrity: migration, config, webhook-renew rework, internal key | PR1 `feat/portal-payment-integrity` (base = tracker `feat/portal-secure-restore` off main; tracker PR draft/no-merge) | `cd backend && set -a && . ./.env && set +a && pytest tests/test_portal_webhook_integrity.py -q` | uvicorn + live Redis/PG: forged sig → 401 + zero row delta; replay after consumption → exactly one membership; migrator-role `alembic upgrade head && alembic current` | migration + model CheckConstraint + `core/config.py` + `backend/.env.example` + portal.py webhook/schema + internal-key auth + test file; revert + downgrade drops CHECK/index only, no data loss |
| 2 | Guest provisioning: canonical phone service, guest pending endpoint, dedup, docs | PR2 `feat/portal-guest-provisioning` (base = PR1 branch) | `pytest tests/test_guest_provisioning.py -q` | uvicorn + redis-cli: POST guest → v2 key TTL 86400, no member_id; webhook E2E → Member+Membership+Sale committed, key DELed, CV notified | `services/canonical_phone.py` + portal_auth import + guest endpoint + webhook guest branch + tests + docs; revert removes guest path, member renewal intact |
| 3 | Pages: relay amount gate, signature facegymId, guest checkout UI, honest copy | PR3 `feat/portal-guest-checkout` → main (powerhouse-site, after backend merges) | `cd /root/powerhouse-web/powerhouse-site && npx vitest run` | `npm run dev` / `wrangler pages dev`: /comprar → pending record via proxy; renovar consumes response planId (no hardcoded UUID); webhook gate replays fixture Wompi events | signature.ts + webhook.ts + pending-payment-guest.ts + comprar/places/renovar/confirmacion + tests; revert → renewal-only portal, guests to manual staff path |

## Phase 1: Foundation — migration + config (PR1)

- [x] 1.1 RED: `tests/test_portal_webhook_integrity.py::TestPlanPriceConstraint` — price 0 insert and negative update rejected → "Zero-price plan insert is rejected" / "Negative-price update is rejected" (model `create_all` parity)
  — Evidence: 2/2 passed on scratch-DB `create_all` engine (IntegrityError both cases)
- [x] 1.2 GREEN: `models/membership.py` CheckConstraint(price>0); migration `alembic/versions/20260818_1000_8d7e6f5a4b3c_price_check_wompi_reference.py` (`down_revision="7c6d5e4f3a2b"`): fail-loud pre-check lists violating rows, CHECK, `sales_transactions.wompi_reference VARCHAR(100)` + UNIQUE index + regexp backfill from notes; downgrade drops CHECK/index only
  — Evidence: TestPriceCheckWompiReferenceMigration 4/4 passed (head/chain, trap-20 docstring, backfill+CHECK+unique+downgrade on scratch DB, fail-loud listing "Legacy Free"); `alembic upgrade head` + `alembic current` → 8d7e6f5a4b3c (head) on dev DB; HEAD_REVISION in test_member_phone_migrations.py updated
- [x] 1.3 RED→GREEN: `core/config.py` `PORTAL_INTERNAL_API_KEY`; CREATE `backend/.env.example` — placeholders only (MEMBER_PORTAL_DATABASE_URL, WOMPI_PUBLIC_KEY, WOMPI_INTEGRITY_SECRET, EVOLUTION_API_URL/API_KEY/INSTANCE_NAME, PORTAL_INTERNAL_API_KEY) → "Placeholders are present in .env.example"
  — Evidence: TestEnvExamplePlaceholders + TestPortalInternalApiKeySetting 2/2 passed; live secret values asserted absent
- [x] 1.4 Approval-test: `verify_wompi_signature` unset `WOMPI_INTEGRITY_SECRET` → deny → "Missing integrity secret fails closed"; migration docstring records trap-20 mechanics (run via `MIGRATE_DATABASE_URL` migrator role, verify with `alembic current`)
  — Evidence: TestIntegritySecretFailClosed passed (approval); docstring assertion MIGRATE_DATABASE_URL + "alembic current" passed

## Phase 2: Webhook-renew rework + internal key (PR1)

- [x] 2.1 RED: forged/missing HMAC → 401 pre-lookup, no state change → "Forged signature changes no state" / "Forged webhook is rejected"; missing reference/tx_id/`amount_in_cents` → 422
  — Evidence: TestWebhookSignatureGate 3/3 passed (401 no-state ×2 approval-kept; 422 for missing amount_in_cents / tx_id / empty reference via schema min_length=1)
- [x] 2.2 RED: no Redis pending → DB `wompi_reference` hit → `already_processed` → "Replayed reference provisions nothing new"; miss → 404 + alert log → "Unknown reference provisions nothing" / "Webhook without pending record is rejected"
  — Evidence: TestPendingConsumption replay + unknown-reference tests passed (404 + reference in ERROR caplog, zero rows)
- [x] 2.3 RED: `pending.amount != plan.price` OR `amount_in_cents/100 < plan.price` → 400, zero rows, key retained → "Amount not matching the pending record is rejected" / "Backend underpayment yields no membership"
  — Evidence: TestAmountGates 3/3 passed (tampered pending → 400; underpayment by 1 peso → 400 + alert + key retained; overpayment accepted per D4)
- [x] 2.4 RED: commit failure → key retained → "Failed commit retains the pending key"; concurrent same-reference → UNIQUE index aborts loser; no secret in any response → "No secret reaches a client response"
  — Evidence: failed-commit (RuntimeError at commit → key present, 0 rows), race-loser (SAVEPOINT-scoped IntegrityError → already_processed, exactly 1 sale), TestNoSecretReachesClientResponses passed
- [x] 2.5 GREEN: `schemas/portal.py` v2 (`amount_in_cents` required int, `member_id` optional); `portal_webhook_renew` per D9 order: HMAC → parse → Redis load → already_processed → D4 amounts → member resolve → Membership+Sale(+wompi_reference) single commit → post-commit `redis.delete(key)` then `notify_cv_invalidation`; body `member_id` ignored
  — Evidence: TestPendingConsumption 7/7 passed incl. Redis-member-authoritative (body member_id ignored) and stale body plan_id ignored; POST /portal/pending-payment split to PortalPendingPaymentRequest (relay-compatible shape); guest seam = `_resolve_member_from_pending` returning None
- [x] 2.6 RED→GREEN: GET `/portal/pending-payment/{reference}`: correct key → 200 "Pending read with the internal key succeeds"; wrong / SECRET_KEY / unset → uniform 401, no existence disclosure → "Pending read requires the internal key" / "SECRET_KEY no longer authorizes pending reads" / "Pending read with only SECRET_KEY is denied"
  — Evidence: TestInternalKeyPendingReads 6/6 passed (correct 200; wrong/unset/SECRET_KEY → uniform 401; unset key denies all — fail closed; denial bodies byte-identical for existing vs missing reference)

## Phase 3: Canonical phone service (PR2)

- [x] 3.1 RED: `resolve_member_by_phone` — 0 hits → None, 2 hits → None (ambiguous), 1 hit → member; portal_auth login/resend resolution unchanged (reuse proof)
  — Evidence: TestCanonicalizePhone 4/4 + TestResolveMemberByPhone 4/4 (legacy-format single match resolves; formatted+prefixed dupes → None); TestPortalAuthReusesService proves `portal_auth._resolve_member is resolve_member_by_phone` (identity, not copy); test_portal.py + test_portal_security.py PIN suites green (44 passed combined)
- [x] 3.2 GREEN: create `services/canonical_phone.py` extracted from `portal_auth._resolve_member` (SQL regexp canonicalization); `portal_auth.py` imports it — zero behavior change
  — Evidence: same run green; portal_auth drops its inline copies (re-export under historical names), unused sqlalchemy imports removed; flake8/black/mypy clean

## Phase 4: Guest pending endpoint + provisioning (PR2)

- [x] 4.1 RED: POST `/portal/pending-payment/guest` — bad reference format → 422; phone not normalizable to 57+10 → 422 AND no Redis record → "Non-canonical phone is rejected"; valid → v2 record (guest_name, canonical phone, guest_email, plan_id, DB-price amount, wompi_reference; NO member_id; TTL ≤ 86400) → "Pending record carries identity, not a member" / "Pending amount equals plan price"; over-limit → 429 (slowapi)
  — Evidence: TestGuestPendingEndpoint 9/9 — 7 bad phones × [422 + no Redis key], 7 bad references × 422, v2 record field+TTL assertions, amount==plan.price with smuggled client amount ignored, 429 after quota exhaustion (handler-executed 422s consume slowapi budget; nothing stored when blocked)
- [x] 4.2 GREEN: guest endpoint per D10 — reference regex `^PH-[a-z0-9-]+-\d{10}-[a-f0-9]{6}$`, canonicalize phone, resolve DB plan price, `@limiter.limit` (MEMBER_AUTH_RATE_LIMIT pattern)
  — Evidence: schemas/portal.py PortalGuestPendingPaymentRequest (pattern + EmailStr + name-collapse validator — NO amount field exists); api/portal.py endpoint; config GUEST_CHECKOUT_RATE_LIMIT ("10/minute" default); RED was 8 failures on 404 → GREEN 18/18 in file
- [x] 4.3 RED: webhook guest branch — no Redis `member_id` → create Member per D5 (first token/remainder, active, `consent_given_at=NULL`, `facial_data_enrolled=false`) → "New phone creates a new member"; existing canonical phone → attach, no duplicate → "Existing phone attaches to the existing member"; email unique-collision → retry email=NULL + log; atomic Member+Membership+Sale → "Approved payment provisions all records"; mid-commit abort → zero rows → "Failure mid-commit leaves no partial records"; CV notify carries X-API-Key → "Commit triggers CV invalidation with API key"; CV unreachable → rows intact + logged → "CV unreachable leaves the sale intact"
  — Evidence: TestGuestProvisioningWebhook 15/15 — RED was 14 failures on Unit-1's 404 seam; X-API-Key proven through the REAL notify_cv_invalidation with fake httpx capture; ambiguous phone → 422 + alert + no writes + key retained; honest-confirmation data (pending GET not_found + committed sale); member_id-present-but-missing-member stays 404 (guest branch only on member_id absent)
- [x] 4.4 GREEN: guest resolve in webhook — advisory lock `SET member-provision:{phone} NX EX 15`, dedup via `resolve_member_by_phone`, membership stacks from furthest end_date
  — Evidence: `_begin_guest_provisioning` (lock spans resolution→commit, released in finally; EX 15 crash net); stacking test proves start = furthest active end_date+1; lock-held → 409 no writes key retained, released → replay succeeds (harness limit documented: TestClient cannot race two webhooks — contract proven, not a true race); email savepoint-retry with NULL + warning log

## Phase 5: Pages relay integrity (PR3)

- [x] 5.1 RED (vitest, extend `__tests__/api/webhook.test.ts`): amount ≥ plan + COP → forwarded with `amount_in_cents` → "Matching amount is forwarded"; under → no forward + staff alert + 200 to Wompi → "Underpayment is blocked before forwarding"; currency ≠ COP or missing → blocked → "Currency mismatch is blocked"; guest pending → forwarded WITHOUT member_id/identity in body; existing webhook suite stays green
  — Evidence: RED run 8 failures (gate/key/guest contracts absent); new suites: match + overpayment forward w/ amount_in_cents, underpayment/currency-USD/missing-currency blocked (0 `/api/portal/` calls + 1 MailChannels alert + 200), guest forward body has NO member_id/guest_* keys and raw body free of identity, PT ref → staff email + no webhook-renew; 18/18 in file after GREEN
- [x] 5.2 GREEN: `webhook.ts` — add `currency` to `WompiTransaction`; gym-amount gate (`tx.amount_in_cents >= PLANS.amountInCents && tx.currency === "COP"`; overpayment forwards); forward = current shape + `amount_in_cents`; `member_id` only when pending has one; pending lookup switched to `X-API-Key: FACEGYM_PORTAL_INTERNAL_KEY` (strict — old FACEGYM_INTERNAL_API_KEY removed; missing env → log + 200, no forward, fail-closed); PT plans unchanged manual staff-email path via new `sendAmountMismatchAlert` (same MailChannels pattern)
- [x] 5.3 RED (extend `__tests__/payment/signature.test.ts`): PLANS gains `facegymId` (4 gym plans); response gains `facegymPlanId`; client-sent amount ignored → "Client-sent amount is ignored"; existing signature suite stays green
  — Evidence: RED run 4 failures (facegymPlanId absent on gym plans); GREEN 23/23 incl. client amount/amountInCents/amount_in_cents smuggled → 6990000 wins, secret never in response, PT plans respond WITHOUT facegymPlanId
- [x] 5.4 GREEN: `signature.ts` facegymId mapping + response field (D7) — PLANS + PlanConfig exported (webhook imports PLANS as the single gate source)

## Phase 6: Pages guest UI + honest copy (PR3)

- [x] 6.1 GREEN: `src/pages/portal/renovar.astro` drops hardcoded plan UUIDs, consumes `facegymPlanId` from signature response
  — Evidence: `__tests__/pages/renovar.test.ts` 3/3 (no UUID regex in source; pending body `plan_id: sigData.facegymPlanId`; fail-closed guard when absent); built bundle `dist/_astro/renovar*.js` references facegymPlanId with 0 UUIDs shipped
- [x] 6.2 GREEN: create `functions/api/portal/pending-payment-guest.ts` proxy → backend guest endpoint
  — Evidence: `__tests__/api/pending-payment-guest.test.ts` 4/4 (POST → `/api/portal/pending-payment/guest` body-passthrough of the 5 fields, no Authorization header, 422 passthrough, 502 on upstream failure, CORS 204); E2E through `wrangler pages dev` → HTTP 200 `{"status":"stored"}` + Redis key TTL 86400
- [x] 6.3 GREEN (page-data tests where harness allows): create `src/pages/comprar.astro` — guest checkout (name/email/phone; 4 gym plans only; `pt-*` refused → manual staff path → "PT plan is not guest-purchasable" / "Guest identity captured for a gym plan"); `planes.astro` guest CTA
  — Evidence: `__tests__/pages/guest-checkout.test.ts` — comprar offers exactly the 4 gym plans, refuses `pt-*` to WhatsApp manual path, captures name/phone/email with client validation (10-digit or 57+10) + escapeHtml, proxy body = exactly {wompi_reference, guest_name, guest_phone, guest_email, plan_id} (NO amount), fails closed without facegymPlanId, no hardcoded UUIDs; planes.astro routes `[data-plan-id]` → `/comprar?plan=` with no direct WidgetCheckout
- [x] 6.4 RED: `src/pages/pago/confirmacion.astro` — APPROVED-guest copy "compra registrada — activa tu membresía en el gimnasio con tu registro facial"; PENDING/DECLINED show no success → "Confirmation directs enrollment to the gym" / "Non-approved payment shows no success" (D11)
  — Evidence: page-data tests — APPROVED block matches "Compra registrada" + "registro facial"; "Tu membresía está activa" gone; pending/declined blocks contain no success copy; built `dist/pago/confirmacion/index.html` contains "Compra registrada"

## Phase 7: Docs + spec boundary + verification

- [x] 7.1 Docs (PR2): `docs/portal-secure-restore-deploy.md` — secrets stay placeholders in repo (Cloudflare + LXC 114 provisioning is orchestrator/ops-owned, never committed), deploy order backend FIRST then Pages, deploy-gap risk: old relay omits `amount_in_cents` → backend 400s those renewals loudly until Pages deploys (relay logs, Wompi still 200)
  — Evidence: docs/portal-secure-restore-deploy.md created — backend-first order + trap-20 migrator migration block, deploy-gap window behavior (422 pre-lookup no-state, pending TTL ≤24h replay path), PORTAL_INTERNAL_API_KEY / FACEGYM_PORTAL_INTERNAL_KEY / GUEST_CHECKOUT_RATE_LIMIT provisioning table (placeholder-only), post-deploy verification + rollback
- [x] 7.2 D12 spec boundary note (PR2): append to this change's design addendum — payment-integrity sale-gated activation is enforced structurally on ALL public/portal surfaces via webhook-renew ONLY; staff `POST /api/memberships` + `/{id}/renew` intentionally descoped (trap 21: reception assigns membership then takes payment; kiosk zero-paid gate `access_validator.py:159-178` already DENIES unpaid at the door, regression-tested)
  — Evidence: design.md "Spec Boundary Addendum (D12)" section — portal-surface reading, staff descope rationale (trap 21 + MemberForm assign-flow ordering + kiosk gate), reopen-condition for future staff-surface changes
- [x] 7.3 Verify: backend `flake8 . && black --check . && mypy . && pytest tests/ -q` (423 baseline + new; exported `.env`; db+redis up); powerhouse-site `npx vitest run` all green; grep both repos — no real secret values
  — Evidence: backend verified in batches 1–2 (`pytest tests/ -q` → 485 passed; flake8/black/mypy clean); powerhouse-site `npm run test` → **85 passed** (7 files), `npx eslint .` clean, `npm run typecheck` (astro check) 0 errors, `npm run build` → 24 pages incl. `/comprar`; runtime harness E2E via `wrangler pages dev` + live backend: guest pending via proxy → stored + TTL 86400 → APPROVED replay → Member(active, consent NULL, facial false)+Membership(30d)+Sale($69,900, wompi_reference) committed + Redis key consumed; underpayment → gate blocked + 200 + key retained + zero rows; secret grep over both repo diffs clean (harness used throwaway env overrides — dev `.env` lacks PORTAL_INTERNAL_API_KEY/WOMPI_INTEGRITY_SECRET, provisioning documented in deploy runbook)
