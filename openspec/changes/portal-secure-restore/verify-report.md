# Verify Report: portal-secure-restore

- Verdict: **PASS WITH WARNINGS** (0 CRITICAL · 2 WARNING · 2 SUGGESTION)
- Mode: STRICT TDD · artifact store: both (file + engram)
- Verified at: faceapp `main` @ `7d45ecb` (PR #82 `36a682b` + PR #83 `7d45ecb`, both merged) · powerhouse-site `feat/portal-guest-checkout` @ `448f966` (PR #30, unmerged by design — deploy-order hold)
- Verified by: independent sdd-verify agent, 2026-08-18

## 1. Completeness (tasks)

All 27 tasks (1.1–7.3) checked in tasks.md. No unchecked task. 100% complete.

## 2. Runtime evidence (this session, re-executed)

| Command | Working dir | Result |
|---|---|---|
| `set -a && . ./.env && set +a && /root/faceapp/.venv/bin/python -m pytest tests/ -q` | `backend/` (main @ 7d45ecb) | **485 passed**, 0 failed (27.78s) — matches claim |
| `/root/faceapp/.venv/bin/flake8 .` | `backend/` | clean, exit 0 |
| `/root/faceapp/.venv/bin/black --check .` | `backend/` | 134 files unchanged |
| `/root/faceapp/.venv/bin/mypy .` | `backend/` | Success: no issues found in 121 source files |
| `alembic current` (dev DB, exported `.env`) | `backend/` | **`8d7e6f5a4b3c (head)`** — matches claim |
| `pytest tests/test_portal_webhook_integrity.py tests/test_guest_provisioning.py -q` | `backend/` | 62 passed (29 + 33 — per-file counts match claims exactly) |
| `pytest tests/test_portal.py tests/test_portal_security.py -q` | `backend/` | 35 passed (legacy portal suites green under new contracts) |
| `npm run test` (vitest run) | powerhouse-site (branch) | **85 passed / 7 files** — matches claim; per-file: webhook 18, signature 23, guest-checkout 14, shared 14, status 9, guest-proxy 4, renovar 3 |
| `npm run typecheck` (astro check) | powerhouse-site (branch) | **0 errors**, 0 warnings, 16 pre-existing hints — matches claim |
| `npm run build` | powerhouse-site (branch) | **"24 page(s) built"** incl. new `/comprar/index.html` — matches claim (23 index.html + 404.html) |

Postgres + Redis live on host (127.0.0.1:5432 / :6379); backend suite ran against them with exported `backend/.env` per the env-export caveat.

## 3. Spec compliance matrix

Scenario counts derived from the retrieved spec files (never from claims): payment-integrity 7 requirements / 16 scenarios; guest-purchase-provisioning 7 / 13; customer-portal-runtime delta 3 requirements (1 MODIFIED + 2 ADDED) / 8 scenarios. **37 scenarios total — all COMPLIANT** (each covered by a test that passed at runtime this session).

"[on branch]" = covering vitest lives on the unmerged Pages branch `feat/portal-guest-checkout` (verified there; merge held for backend-first deploy order — backend is now merged, so PR #30 is unblocked at deploy time).

### payment-integrity (7 req / 16 scenarios)

| # | Scenario | Tag | Covering test (passed) | Status |
|---|---|---|---|---|
| 1 | Client-sent amount is ignored | vitest | signature.test.ts › server-originated amounts › client-sent amount is ignored [on branch] | COMPLIANT |
| 2 | Pending amount equals plan price | pytest | test_guest_provisioning.py › TestGuestPendingEndpoint::test_pending_amount_equals_plan_price | COMPLIANT |
| 3 | Matching amount is forwarded | vitest | webhook.test.ts › matching amount is forwarded with amount_in_cents [on branch] | COMPLIANT |
| 4 | Underpayment is blocked before forwarding | vitest | webhook.test.ts › underpayment is blocked before forwarding (staff alert asserted) [on branch] | COMPLIANT |
| 5 | Currency mismatch is blocked | vitest | webhook.test.ts › currency mismatch is blocked + missing currency treated as mismatch [on branch] | COMPLIANT |
| 6 | Approved webhook commits and consumes the key | pytest | TestPendingConsumption::test_approved_webhook_commits_and_consumes_the_key | COMPLIANT |
| 7 | Unknown reference provisions nothing | pytest | TestPendingConsumption::test_unknown_reference_provisions_nothing (404 + ERROR log, zero rows) | COMPLIANT |
| 8 | Forged signature changes no state | pytest | TestWebhookSignatureGate::test_forged_signature_changes_no_state + test_missing_signature_is_rejected_before_lookup | COMPLIANT |
| 9 | Failed commit retains the pending key | pytest | TestPendingConsumption::test_failed_commit_retains_the_pending_key | COMPLIANT |
| 10 | No membership activates without a qualifying sale | pytest | TestAmountGates::test_backend_underpayment_yields_no_membership + webhook-only activation surface; staff paths descoped per design D12 boundary addendum (documented, kiosk zero-paid gate regression-tested in cv_service) | COMPLIANT* |
| 11 | Zero-price plan insert is rejected | pytest | TestPlanPriceConstraint::test_zero_price_plan_insert_is_rejected + TestPriceCheckWompiReferenceMigration (4/4) | COMPLIANT |
| 12 | Negative-price update is rejected | pytest | TestPlanPriceConstraint::test_negative_price_update_is_rejected | COMPLIANT |
| 13 | Backend underpayment yields no membership | pytest | TestAmountGates::test_backend_underpayment_yields_no_membership (400, alert, key retained) | COMPLIANT |
| 14 | Pending read requires the internal key | pytest | TestInternalKeyPendingReads::test_pending_read_requires_the_internal_key + ..._succeeds (+ unset → fail-closed; uniform denial bodies) | COMPLIANT |
| 15 | SECRET_KEY no longer authorizes pending reads | pytest | TestInternalKeyPendingReads::test_secret_key_no_longer_authorizes_pending_reads + test_pending_read_with_only_secret_key_is_denied | COMPLIANT |
| 16 | No secret reaches a client response | pytest+vitest | TestNoSecretReachesClientResponses (pytest) + signature.test.ts › never leaks the integrity secret [on branch] | COMPLIANT |

\* Scenario 10 is compliant under the recorded D12 spec-boundary reading: "any code path" = portal-surface activation contract; activation exists only via `/portal/webhook-renew` (both member renewals and guest purchases land there); staff `POST /api/memberships` + `/{id}/renew` intentionally keep assign-then-pay ordering (trap 21) with the kiosk zero-paid gate (`access_validator.py` DENY) as the door control. Boundary + reopen condition recorded in design.md.

### guest-purchase-provisioning (7 req / 13 scenarios)

| # | Scenario | Tag | Covering test (passed) | Status |
|---|---|---|---|---|
| 1 | Guest identity captured for a gym plan | vitest+pytest | guest-checkout.test.ts › captures guest identity [on branch] + TestGuestPendingEndpoint::test_phone_normalization_variants | COMPLIANT |
| 2 | PT plan is not guest-purchasable | vitest | guest-checkout.test.ts › refuses pt-* plans → manual staff path [on branch] + signature.test.ts PT-absence ×3 [on branch] | COMPLIANT |
| 3 | Non-canonical phone is rejected | pytest | TestGuestPendingEndpoint::test_non_canonical_phone_is_rejected (422 + no Redis record) | COMPLIANT |
| 4 | Pending record carries identity, not a member | pytest | TestGuestPendingEndpoint::test_guest_identity_stores_v2_pending_record (no member_id, TTL ≤ 86400) | COMPLIANT |
| 5 | Approved payment provisions all records | pytest | TestGuestProvisioningWebhook::test_guest_payment_provisions_all_records (active, consent NULL, facial false) | COMPLIANT |
| 6 | Failure mid-commit leaves no partial records | pytest | TestGuestProvisioningWebhook::test_failure_mid_commit_leaves_no_partial_records | COMPLIANT |
| 7 | Existing phone attaches to the existing member | pytest | TestGuestProvisioningWebhook::test_existing_phone_attaches_no_duplicate | COMPLIANT |
| 8 | New phone creates a new member | pytest | test_guest_payment_provisions_all_records + test_single_token_name_maps_to_empty_last_name | COMPLIANT |
| 9 | Commit triggers CV invalidation with API key | pytest | TestGuestProvisioningWebhook::test_commit_triggers_cv_invalidation_with_api_key (real notifier + httpx capture) | COMPLIANT |
| 10 | CV unreachable leaves the sale intact | pytest | TestGuestProvisioningWebhook::test_cv_unreachable_leaves_the_sale_intact | COMPLIANT |
| 11 | Replayed reference provisions nothing new | pytest | test_guest_replay_reference_is_idempotent + TestPendingConsumption::test_replayed_reference_provisions_nothing_new + concurrent unique-abort | COMPLIANT |
| 12 | Confirmation directs enrollment to the gym | vitest | guest-checkout.test.ts › directs enrollment to the gym [on branch]; built dist/ ships "Compra registrada" + "registro facial" | COMPLIANT |
| 13 | Non-approved payment shows no success | vitest | guest-checkout.test.ts › non-approved states show no success copy [on branch] | COMPLIANT |

### customer-portal-runtime delta (1 MODIFIED + 2 ADDED req / 8 scenarios)

| # | Scenario | Tag | Covering test (passed) | Status |
|---|---|---|---|---|
| 1 | Forged webhook is rejected | — | TestWebhookSignatureGate (2 tests) | COMPLIANT |
| 2 | Disallowed portal traffic is rejected | — | test_portal_security.py (base-capability suite, green in the 485) | COMPLIANT |
| 3 | Webhook without pending record is rejected | pytest | test_unknown_reference_provisions_nothing | COMPLIANT |
| 4 | Amount not matching the pending record is rejected | pytest | TestAmountGates::test_amount_not_matching_the_pending_record_is_rejected | COMPLIANT |
| 5 | Pending read with the internal key succeeds | pytest | test_pending_read_with_the_internal_key_succeeds | COMPLIANT |
| 6 | Pending read with only SECRET_KEY is denied | pytest | test_pending_read_with_only_secret_key_is_denied | COMPLIANT |
| 7 | Placeholders are present in .env.example | pytest | TestEnvExamplePlaceholders (7 keys, `change-me-*` values only — file inspected: no live secret) | COMPLIANT |
| 8 | Missing integrity secret fails closed | pytest | TestIntegritySecretFailClosed | COMPLIANT |

## 4. Design coherence

Design decisions checked against merged source (not just tests):

| Decision | Source evidence (inspected @ main 7d45ecb) | Status |
|---|---|---|
| D1 key-after-commit + unique wompi_reference | `api/portal.py`: `db.commit()` (585) → `r.delete(_pending_key(reference))` (624, "strictly AFTER the commit" comment) → `notify_cv_invalidation` (632); `models/sale.py:47` `wompi_reference String(100) unique=True` | COHERENT |
| D2 dedicated internal key, fail-closed | `core/config.py:49` `PORTAL_INTERNAL_API_KEY: str = ""`; GET auth via `hmac.compare_digest` (portal.py:798) | COHERENT |
| D6 CHECK + model parity | `models/membership.py:67` `CheckConstraint("price > 0", ...)`; migration `20260818_1000_8d7e6f5a4b3c_price_check_wompi_reference.py` present; dev DB at head | COHERENT |
| D5/D9 guest resolve + advisory lock | `_begin_guest_provisioning` (portal.py:264), lock release in `finally` (609), post-commit order documented in docstring (404) | COHERENT |
| D10 guest endpoint + rate limit | `GUEST_CHECKOUT_RATE_LIMIT: str = "10/minute"` (config.py:101); schema pattern + EmailStr verified via tests | COHERENT |
| D7/D8/D11 (Pages, on branch) | `signature.ts` facegymId ×4 gym plans + `facegymPlanId` response; `webhook.ts` FACEGYM_PORTAL_INTERNAL_KEY + amount/currency gate + amount_in_cents forward; renovar.astro 0 UUIDs (source AND built bundle); confirmacion "Compra registrada"/"registro facial" in dist | COHERENT |
| D12 spec boundary | design.md "Spec Boundary Addendum (D12)" section present with rationale + reopen condition | COHERENT |

No design deviations found.

## 5. Hallucination check — apply-progress claims vs reality

Every checkable artifact claim resolved. **Zero hallucinations.**

| Claim | Resolved |
|---|---|
| backend full suite 485 passed; lint trio clean; mypy 121 files | ✅ re-executed, exact match |
| `alembic current` → 8d7e6f5a4b3c (head) on dev DB | ✅ re-executed |
| per-file counts 29 (integrity) + 33 (guest) = 62 | ✅ re-executed + names collected |
| site 85 passed / 7 files; per-file 18/23/14/14/9/4/3 | ✅ re-executed (verbose reporter) |
| astro check 0 errors; build 24 pages incl /comprar | ✅ re-executed |
| Files: canonical_phone.py, .env.example (7 placeholders), deploy doc, migration, all 5 site sources + 5 test files | ✅ all exist |
| site commits `413285f`/`f317d14`/`4d3ab98`/`448f966` on `feat/portal-guest-checkout`, "13 files, +1273/−222" | ✅ exact (git log + diff --stat byte-exact) |
| renovar built bundle 0 UUIDs; confirmacion ships "Compra registrada" | ✅ grep on dist |
| secret grep clean both repos | ✅ diff grep dccb18b..7d45ecb and 11c04b6..448f966: only `INTEGRITY_SECRET = "test-integrity-secret"` test fixtures |
| PRs #82 (36a682b) + #83 (7d45ecb) merged to main | ✅ git log |
| E2E wrangler harness (guest pending → stored TTL 86400 → APPROVED → committed + key deleted; underpayment blocked) | ➖ apply-time runtime evidence, documented in apply-progress + engram #550; NOT re-executed at verify (accepted per orchestrator instruction; pytest integration equivalents re-ran green this session) |

## 6. Success criteria (proposal.md)

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | E2E guest purchase: APPROVED → Member+Membership+Sale atomic; kiosk-visible after CV invalidation | **PROVEN** | test_guest_payment_provisions_all_records + test_commit_triggers_cv_invalidation_with_api_key (runtime, this session) + apply-time wrangler E2E (documented). Live-kiosk confirmation is part of deploy verification. |
| 2 | Existing-phone dedup attaches, no duplicate | **PROVEN** | test_existing_phone_attaches_no_duplicate |
| 3 | Amount mismatch (Wompi < plan) → NO membership + staff alert | **PROVEN** | test_backend_underpayment_yields_no_membership (backend) + underpayment blocked + MailChannels alert (relay, on branch) |
| 4 | DB rejects $0 plans (CHECK price > 0) | **PROVEN** | TestPlanPriceConstraint 2/2 + migration tests 4/4 + `alembic current` = 8d7e6f5a4b3c on dev DB |
| 5 | Pending key consumed exactly once; replay idempotent | **PROVEN** | commits-and-consumes + replay idempotency + concurrent unique-abort tests |
| 6 | No secret leakage; PAT out of remote URL at deploy | **PROVEN (code)** / **OUTSTANDING (ops)** | response-secret tests both repos + diff grep clean; PAT removal + rotation is deploy-time ops (by design) |
| 7 | Backend pytest green; Pages vitest green | **PROVEN** | 485 + 85 re-executed this session |

## 7. Issues

**CRITICAL — none.**

**WARNING (2):**
- W1: All `[vitest]` scenario evidence and the Pages implementation live on the **unmerged** branch `feat/portal-guest-checkout` (PR #30). Verified green there, but site `main` does not carry the relay integrity gate until it merges. Hold is intentional (backend-first deploy order); backend PRs #82+#83 ARE merged, so the merge precondition is satisfied — PR #30 should merge as part of the coordinated deploy, not after.
- W2: Ops-dependent items outstanding-by-design (see §8) — secret provisioning, production migration, PAT removal/rotation. Code and docs are ready (fail-closed defaults, `docs/portal-secure-restore-deploy.md`); nothing further is implementable from this repo.

**SUGGESTION (2):**
- S1: The wrangler E2E harness is apply-time evidence only. When the deploy runbook executes, re-run the three harness steps against production-configured secrets as the post-deploy verification the runbook already prescribes.
- S2: `astro check` reports 16 pre-existing hints (0 errors) — all in pre-change code; a future non-blocking cleanup.

**Remediation performed: none.** Nothing flaky, nothing mis-claimed; no code was modified during verification.

## 8. Outstanding ops items (by design — proposal Dependencies)

1. Merge PR #30 (`feat/portal-guest-checkout` → site main) as part of the deploy window (backend-first order now satisfied).
2. Provision secrets: `PORTAL_INTERNAL_API_KEY` (backend `.env` on LXC 114) + `FACEGYM_PORTAL_INTERNAL_KEY` + `WOMPI_INTEGRITY_SECRET`/`WOMPI_PUBLIC_KEY` (Cloudflare Pages) — placeholders only in repo; dev `.env` has neither (harness used throwaway exports).
3. Run production migration via migrator role (trap 20): `set -a; . ./.env; . /etc/faceapp/migrate-db.env; set +a && alembic upgrade head && alembic current` → expect `8d7e6f5a4b3c`.
4. Deploy backend, then Pages (deploy-gap: old relay omits `amount_in_cents` → new backend 422s those renewals loudly; pending TTL ≤24h allows replay).
5. PAT removal from remote URL + rotation at deploy time.
6. cloudflared allowlist for the portal surface.

## 9. Verdict

**PASS WITH WARNINGS.** Implementation on both repos matches specs, design (incl. D12 boundary), and all 27 tasks. All 37 spec scenarios across the three specs are covered by tests that passed at runtime during this verification (backend on `main`; Pages on its held branch). No hallucinated claims. Remaining work is exclusively ops/deploy execution that was explicitly out of scope.

Recommended next phase: **archive-pending-ops** — Pages PR #30 held for deploy runbook + ops handoff outstanding.
