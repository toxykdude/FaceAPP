# Apply Progress: portal-secure-restore

Mode: STRICT TDD · Artifact store: both (file + engram) · Batch 1 = Unit 1 (PR1 `feat/portal-payment-integrity`)

Branch topology: tracker `feat/portal-secure-restore` (off `feat/portal-security-suite`, per
orchestrator — unmerged dependency chain) → work branch `feat/portal-payment-integrity`.
Units 2 (guest provisioning) and 3 (Pages repo) NOT started — later batches own them.

## Cumulative task status

| Task | Status | Evidence (one line) |
|------|--------|---------------------|
| 1.1 | ✅ | TestPlanPriceConstraint 2/2 — zero insert + negative update IntegrityError on create_all scratch DB |
| 1.2 | ✅ | Migration 8d7e6f5a4b3c: 4/4 migration tests; dev DB `alembic upgrade head` + `current` → 8d7e6f5a4b3c (head); test_member_phone_migrations HEAD_REVISION bumped |
| 1.3 | ✅ | config PORTAL_INTERNAL_API_KEY + backend/.env.example (7 placeholder keys, no live values) — 2/2 tests |
| 1.4 | ✅ | Approval: unset WOMPI_INTEGRITY_SECRET → verify_wompi_signature False; migration docstring asserts MIGRATE_DATABASE_URL + "alembic current" |
| 2.1 | ✅ | 401 pre-lookup no-state (approval-kept) + 422 for missing amount_in_cents/tx_id/empty reference |
| 2.2 | ✅ | Replay → already_processed; unknown ref → 404 + reference in ERROR caplog, zero rows |
| 2.3 | ✅ | Tampered pending amount → 400; underpayment (−1 peso) → 400 + alert + key retained; overpayment accepted |
| 2.4 | ✅ | Simulated commit failure → key retained, 0 rows; SAVEPOINT-scoped race loser → already_processed, 1 sale; no secret in responses |
| 2.5 | ✅ | D9 order implemented; Redis member_id authoritative (body ignored, proven); pending plan authoritative; key deleted strictly post-commit; CV notify failure-tolerant |
| 2.6 | ✅ | Internal-key matrix 6/6: correct → 200; wrong/SECRET_KEY/unset → uniform 401; denial bodies identical for existing vs missing ref |

Remaining: 3.1–4.4 (Unit 2, PR2), 5.1–6.4 (Unit 3, Pages PR3), 7.1–7.3 (docs + verify).

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | tests/test_portal_webhook_integrity.py | Integration (scratch PG, create_all) | ✅ 423/423 baseline | ✅ 2 failed (commits succeeded) | ✅ CheckConstraint added → 2 passed | ✅ insert + update paths | ✅ none needed |
| 1.2 | same + test_member_phone_migrations.py | Integration (alembic on scratch PG) | ✅ 3/3 phone-migration suite pre-change | ✅ 4 failed (no revision) | ✅ migration written → pass; idempotent re-upgrade fixed via ADD COLUMN IF NOT EXISTS | ✅ backfill + duplicate + CHECK + downgrade + fail-loud | ✅ kept op.* style, IF-NOT-EXISTS precedent cited |
| 1.3 | same | Unit + file | ✅ (new file; 423 baseline) | ✅ 2 failed (attr/file missing) | ✅ config field + .env.example | ✅ keys + live-secret absence | ➖ static artifact |
| 1.4 | same | Unit | ✅ behavior pre-exists | approval (passes by design) | ✅ passed first run | ➖ single scenario | ➖ none needed |
| 2.1 | same | Integration (TestClient, real PG+Redis) | ✅ | ✅ 422 case failed (500→422 gap) | ✅ schema v2 + ValidationError catch | ✅ 3 missing-field variants | ✅ min_length=1 hardening |
| 2.2 | same | Integration | ✅ | ✅ replay/404/alert failed (200 created rows) | ✅ Redis load + DB idempotency | ✅ already_processed vs 404+alert | ✅ helpers `_load_pending_payment`/`_already_processed` |
| 2.3 | same | Integration | ✅ | ✅ both rejections returned 200 | ✅ D4 gates | ✅ tampered-pending + underpay + overpay-accept | ✅ single Decimal gate expression |
| 2.4 | same | Integration | ✅ | ✅ race test failed (rollback nuked outer tx) | ✅ SAVEPOINT-scoped abort | ✅ commit-fail + race + no-secret | ✅ savepoint moved before pending state |
| 2.5 | same | Integration | ✅ | ✅ member/plan authority tests failed (404/200-for-wrong-member) | ✅ D9 order implemented | ✅ 7 scenarios | ✅ docstring D9 map; json import hoisted |
| 2.6 | same | Integration | ✅ | ✅ SECRET_KEY still authorized (200) | ✅ compare_digest + fail-closed | ✅ 6-case matrix + disclosure probe | ➖ minimal already |

Legacy tests updated to new transport contract (same verified behaviors):
test_portal.py ×2, test_portal_security.py ×1 (+ key-consumption assertion added).

## Work Unit Evidence (Unit 1 — payment integrity)

| Evidence | Value |
|---|---|
| Focused test command + result | `cd backend && set -a && . ./.env && set +a && /root/faceapp/.venv/bin/python -m pytest tests/test_portal_webhook_integrity.py -q` → **29 passed** |
| Full suite | `pytest tests/ -q` → **452 passed** (423 baseline + 29 new), 0 failed |
| Lint trio | `flake8 .` clean · `black --check .` 132 unchanged · `mypy .` Success (119 files) |
| Runtime harness | `alembic stamp 7c6d5e4f3a2b && alembic upgrade head && alembic current` on dev DB → `8d7e6f5a4b3c (head)` (dev DB was create_all-built, no alembic_version — stamped-dev-path precedent); webhook flows exercised through real Postgres + Redis via TestClient |
| Rollback boundary | revert migration+model (drops CHECK/index only, data retained) + core/config.py PORTAL_INTERNAL_API_KEY + backend/.env.example + portal.py webhook/schema/internal-key + test file; un-consumed Redis keys expire ≤24h; downgrade verified in-test |

## Discoveries (batch 1)

1. **Dev DB had no `alembic_version`** — it was created by `init_db.py` `create_all`. `alembic upgrade head` tried to run from revision 001 → DuplicateTable. Fix: `stamp 7c6d5e4f3a2b` then `upgrade head` (the repo's own "stamped dev path" pattern). Pre-checked for violating plans (none) and Wompi-notes sales (none) first.
2. **`begin_nested()` autoflushes pending INSERTs** — opening the savepoint after `db.add(sale)` emitted the duplicate INSERT inside `begin_nested()` itself, escaping the try-block. The savepoint must be opened while the session is clean.
3. **A plain `db.rollback()` in the race-loser path is wrong in nested-session harnesses** and subtly dangerous generally — savepoint-scoped rollback (`nested.rollback()`) discards only the loser's rows.
4. **`PortalWebhookRenewRequest` was shared by POST /portal/pending-payment** — the deployed relay sends `{plan_id, member_id:'', wompi_transaction_id:'', amount}` there, so requiring `amount_in_cents` on the shared schema would have broken pending creation during the deploy gap. Split into `PortalPendingPaymentRequest` (old-compatible) vs v2 webhook schema (loud 422 on old relay — by design, D4).
5. **Empty-string reference passed pydantic validation** — `min_length=1` added to the three required webhook fields so `""` is a 422, not a Redis lookup miss.
6. Migration test seeding must supply `created_at`/`updated_at` — migration-built tables have NOT NULL timestamps with no server defaults (defaults are client-side).
