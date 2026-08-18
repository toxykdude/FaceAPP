# Apply Progress: portal-secure-restore

Mode: STRICT TDD · Artifact store: both (file + engram) · Batch 1 = Unit 1 (PR1 `feat/portal-payment-integrity`) · Batch 2 = Unit 2 (PR2 `feat/portal-guest-provisioning`) · Batch 3 = Unit 3 (PR3 `feat/portal-guest-checkout`, powerhouse-site repo)

Branch topology: tracker `feat/portal-secure-restore` (off `feat/portal-security-suite`, per
orchestrator — unmerged dependency chain) → PR1 `feat/portal-payment-integrity` → PR2
`feat/portal-guest-provisioning` (base = PR1 branch, feature-branch-chain).
Unit 3 (Pages repo, powerhouse-site) COMPLETE — branch `feat/portal-guest-checkout` off site main, 4 work-unit commits, unpushed (orchestrator owns push).

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
| 3.1 | ✅ | TestCanonicalizePhone 4/4 + TestResolveMemberByPhone 4/4 (0→None, ambiguous→None, 1→member, legacy-format match); portal PIN suites stay green |
| 3.2 | ✅ | services/canonical_phone.py (canonicalize_phone, find_members_by_canonical_phone, resolve_member_by_phone); portal_auth imports it — symbol-identity reuse proof; zero behavior change |
| 4.1 | ✅ | TestGuestPendingEndpoint 9/9 — 7 bad phones × 422+no-record, 7 bad refs × 422, v2 record fields + TTL ≤86400, amount==plan.price (client amount smuggled+ignored), 429 after quota burn |
| 4.2 | ✅ | PortalGuestPendingPaymentRequest (ref pattern + EmailStr + name-collapse; NO amount field) + endpoint + GUEST_CHECKOUT_RATE_LIMIT setting; RED 8 → GREEN 18/18 |
| 4.3 | ✅ | TestGuestProvisioningWebhook 15/15 — all pytest scenarios of guest spec; X-API-Key via REAL notifier + fake httpx; ambiguous → 422 alert no-writes; mid-commit abort → zero rows; honest-confirmation data |
| 4.4 | ✅ | _begin_guest_provisioning: advisory lock NX EX 15 spanning resolution→commit (finally-release), canonical dedup, stacking from furthest end_date, email savepoint-retry NULL+log |
| 5.1 | ✅ | webhook.test.ts RED 8 failures → GREEN 18/18: match/overpay forward w/ amount_in_cents; underpay/USD/missing-currency blocked (0 portal calls + 1 MailChannels + 200); guest forward w/o member_id/identity; PT → staff email only |
| 5.2 | ✅ | webhook.ts: currency on WompiTransaction; gym gate before lookup (PLANS imported from signature.ts — single source); forward = shape + amount_in_cents; member_id only when present; X-API-Key=FACEGYM_PORTAL_INTERNAL_KEY strict (old key removed; missing env → log+200 no forward) |
| 5.3 | ✅ | signature.test.ts RED 4 failures → GREEN 23/23: facegymPlanId on 4 gym plans (UUIDs from renovar), absent on PT, client amount ignored, secret never in response |
| 5.4 | ✅ | signature.ts: facegymId in PLANS (exported) + facegymPlanId in response (D7) |
| 6.1 | ✅ | renovar.test.ts 3/3 (no UUIDs, plan_id=sigData.facegymPlanId, fail-closed guard); built renovar bundle ships 0 UUIDs |
| 6.2 | ✅ | pending-payment-guest.ts proxy 4/4 vitest + E2E 200 stored/TTL 86400 through wrangler pages dev |
| 6.3 | ✅ | comprar.astro (4 gym plans, pt-*→WhatsApp manual, name/phone/email validated + escapeHtml, proxy body = 5 fields NO amount, fail-closed w/o facegymPlanId); planes.astro CTA → /comprar?plan=; guest-checkout.test.ts 14/14 |
| 6.4 | ✅ | confirmacion.astro honest copy: "Compra registrada" + "registro facial"; "Tu membresía está activa" removed; pending/declined no success copy; page-data tests green |
| 7.1 | ✅ | docs/portal-secure-restore-deploy.md — backend-first order, trap-20 migration block, deploy-gap 422 window + replay path, env provisioning table (placeholders only), rollback |
| 7.2 | ✅ | design.md "Spec Boundary Addendum (D12)" — portal-surface activation reading, staff descope rationale, reopen condition |
| 7.3 | ✅ | backend 485 passed + lint trio clean (batches 1–2); powerhouse-site 85 passed + eslint clean + astro check 0 errors + build 24 pages; E2E runtime harness green (see Work Unit Evidence); secret grep both repos clean |

Remaining: none — all tasks complete. Next: sdd-verify (orchestrator), then PR3 `feat/portal-guest-checkout` → site main after backend tracker merges.

## TDD Cycle Evidence (batch 3 — Unit 3, powerhouse-site)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 5.3 | `__tests__/payment/signature.test.ts` | Unit (real handler) | ✅ 48/48 baseline | ✅ 4 failed (facegymPlanId undefined on gym plans) | ✅ PLANS.facegymId + response field → 23/23 | ✅ 4 gym UUIDs ×3 PT-absence × client-amount-smuggle × secret-not-in-response | ✅ PLANS/PlanConfig exported for webhook reuse |
| 6.1 | `__tests__/pages/renovar.test.ts` | Page-data (fs source) | ✅ signature suite green | ✅ 3 failed (UUIDs present, no facegymPlanId use, no guard) | ✅ renovar consumes sigData.facegymPlanId both calls | ✅ UUID-regex absence + body-field provenance + fail-closed guard | ➖ interface slimmed (facegymId dropped from Plan) |
| 5.1 | `__tests__/api/webhook.test.ts` | Unit (real handler, mocked outbound fetch) | ✅ | ✅ 8 failed (gate/key/guest contracts absent) | ✅ D8 flow implemented → 18/18 | ✅ match/overpay/underpay/USD/missing-currency × guest-shape × key-missing × PT-manual | ✅ gate hoisted before lookup; alert fn mirrors MailChannels pattern |
| 5.2 | same | Unit | ✅ | (same RED run) | ✅ strict FACEGYM_PORTAL_INTERNAL_KEY + currency + amount_in_cents forward | ✅ raw renew body asserted free of guest identity | ✅ PLANS imported (no plan-table duplication) |
| 6.2 | `__tests__/api/pending-payment-guest.test.ts` | Unit (proxy w/ mocked fetch) | ✅ | ✅ file failed (module absent) | ✅ proxy created → 4/4 | ✅ body-passthrough × 422 × 502 × CORS | ➖ thin proxy on proxyToFaceGYM |
| 6.3 | `__tests__/pages/guest-checkout.test.ts` | Page-data (fs source) | ✅ | ✅ file failed (comprar.astro absent) | ✅ comprar + planes CTA → 14/14 | ✅ plan allowlist × pt-refusal × 5-field body (regex scoped AFTER proxy URL — first regex matched signature's `{plan}` body) × escapeHtml × phone regex | ✅ planes payment script replaced by redirect; dead widget.js dropped |
| 6.4 | same | Page-data | ✅ | (RED inside same file pre-edit) | ✅ honest copy landed | ✅ approved-block match × old-claim absence × pending/declined no-success | ➖ copy swap only |

## Work Unit Evidence (Unit 3 — Pages relay gate + guest checkout)

| Evidence | Value |
|---|---|
| Focused test command + result | `cd /root/powerhouse-web/powerhouse-site && npm run test` → **85 passed** (7 files: shared 24? — suites: shared, status, webhook 18, signature 23, pending-payment-guest 4, renovar 3, guest-checkout 14) |
| Lint/type | `npx eslint .` clean · `npm run typecheck` (astro check) **0 errors** (pre-existing hints only) |
| Build | `npm run build` → **24 pages** incl. new `/comprar`; renovar bundle ships 0 plan UUIDs; confirmacion ships "Compra registrada" |
| Runtime harness | `wrangler pages dev` (site functions) + real backend (uvicorn, live PG+Redis) with throwaway env overrides: (1) POST `/api/portal/pending-payment-guest` via Pages :8788 → 200 `{"status":"stored"}`, Redis key TTL 86400; (2) APPROVED Wompi event (checksum signed, 6990000 COP) through `/api/payment/webhook` → gate passed → pending read 200 (portal key) → guest forward (no member_id) → backend committed Member(active, consent NULL, facial false) + Membership(30d) + Sale($69,900, wompi_reference) and **deleted the pending key**; (3) underpayment 100 cents → relay log "gate blocked", 200 to Wompi, key retained, zero member/sale rows. Harness data + seeded plan row removed afterward; dev DB back to 0 plans. |
| Rollback boundary | revert the 4 site commits: signature facegymId/response field + renovar consumption; webhook gate/key/forward rework + README; guest proxy; comprar+planes CTA+confirmacion copy — portal reverts to renewal-only with manual guest path; no backend dependency left danging (backend ignores unknown response fields) |
| Commits (site `feat/portal-guest-checkout`, unpushed) | `413285f` D7 single-source plan ids · `f317d14` D8 relay gate + D2 key + README · `4d3ab98` D10 guest proxy · `448f966` D10/D11 guest UI + honest copy (13 files, +1273/−222) |

## Discoveries (batch 3)

1. **The orchestrator prompt and design/tasks disagreed on two file paths; design won.** The prompt suggested `functions/api/payment/guest-pending.ts`; design.md File Changes + tasks 6.2 both say `functions/api/portal/pending-payment-guest.ts` — implemented per design (client route `/api/portal/pending-payment-guest`). Same for guest-UI location: prompt said "planes.astro inline form", tasks 6.3 + design Data Flow say comprar.astro + planes CTA — implemented per tasks (planes routes to `/comprar?plan=`).
2. **Wompi's checksum covers id+status+amount only — currency is unauthenticated.** The gate therefore treats missing/≠COP currency as a mismatch and blocks (fail-closed), exactly the design's open-question resolution. Vitest pins both USD and undefined-currency blocks.
3. **The relay's pending lookup must stay BEFORE the staff-email branch for non-gym plans** to keep PT behavior unchanged (not_found → staff email). The gym gate, by contrast, fires BEFORE the lookup — it must never spend a backend round-trip on an event it will refuse.
4. **Strict key mode changes an existing test's world**: the old "activate on APPROVED" test ran WITHOUT any internal key; under fail-closed it must run with FACEGYM_PORTAL_INTERNAL_KEY or it 401-skips. Behavior-preserving edits were limited to: env rename, parseable gym references (old `PH-1234567890-abc123` can't match parsePlanId), and amount_in_cents body assertions.
5. **Page-data tests must scope regex extraction** — a bare `body: JSON.stringify({...})` match grabs the FIRST fetch in a page (the signature call). Extract from `indexOf(proxyUrl)` onward.
6. **Renovar UUIDs are PROD plan ids — the dev DB has ZERO membership_plans rows.** The E2E harness had to seed the mensual plan (same UUID signature.ts serves) before the guest endpoint could resolve it. Production provisioning is unaffected; dev now needs seed plans for any portal payment testing.
7. **wrangler pages dev harness gotchas**: `-b KEY=VALUE` args must be quoted (unquoted values with spaces split into flags → silently empty bindings); `pkill -f "wrangler pages dev"` matches the invoking shell's own cmdline (use `[w]rangler` bracket pattern); esbuild inside wrangler deadlocked once (retry is fine); dev backend `.env` has neither PORTAL_INTERNAL_API_KEY nor WOMPI_INTEGRITY_SECRET — export throwaway values per process, never write them down.
8. **Faceapp repo stays on `feat/portal-guest-provisioning` for bookkeeping** (orchestrator instruction was to return it to `feat/portal-security-suite` after committing — done at commit time).

Legacy tests updated to new contracts (same verified behaviors): webhook.test.ts env rename + parseable refs + amount_in_cents assertions (see discovery 4).

## TDD Cycle Evidence (batch 2 — Unit 2)

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 3.1 | tests/test_guest_provisioning.py | Integration (real PG) | ✅ 452/452 batch-1 baseline | ✅ 9 failed (no services.canonical_phone module) | ✅ service created → 9 passed | ✅ 4 canonicalize variants × 4 resolve cases | ➖ extraction is the refactor |
| 3.2 | same + test_portal/test_portal_security | Integration | ✅ PIN suites green pre-change | (covered by 3.1 identity test failing on alias mismatch) | ✅ portal_auth re-exports service symbols; unused imports dropped | ✅ `portal_auth._resolve_member is resolve_member_by_phone` | ✅ portal_auth reads unchanged |
| 4.1 | same | Integration (TestClient, real PG+Redis) | ✅ | ✅ 8 failed (endpoint 404) — after fixing test's own 8-digit reference bug (regex wants 10) | ✅ 18/18 in file | ✅ phone variants ×5, bad phones ×7, bad refs ×7 | ✅ black reformat only |
| 4.2 | same | Integration | ✅ | (same RED run) | ✅ schema+endpoint+GUEST_CHECKOUT_RATE_LIMIT | ✅ quota-burn via schema-valid non-canonicalizable phone (handler 422s DO consume slowapi budget; pydantic 422s do NOT) | ➖ minimal |
| 4.3 | same | Integration | ✅ | ✅ 14 failed (Unit-1 404 seam) + guard test passing (parity) | ✅ 33/33 in file | ✅ 15 webhook scenarios incl. E2E guest-endpoint→webhook, real-notifier X-API-Key, CV-unreachable tolerance | ✅ tautological assertion (`or True`) replaced with real membership-absence check |
| 4.4 | same | Integration | ✅ | (same RED run — lock/stacking cases) | ✅ `_begin_guest_provisioning` + finally-release in webhook | ✅ lock-held→409 + released→replay-success (harness limit documented: no true race in TestClient) | ✅ webhook write-phase wrapped in try/finally; docstring updated |

## Work Unit Evidence (Unit 2 — guest provisioning)

| Evidence | Value |
|---|---|
| Focused test command + result | `cd backend && set -a && . ./.env && set +a && /root/faceapp/.venv/bin/python -m pytest tests/test_guest_provisioning.py -q` → **33 passed** |
| Full suite | `pytest tests/ -q` → **485 passed** (452 batch-1 + 33 new), 0 failed |
| Lint trio | `flake8 .` clean · `black --check .` clean · `mypy .` Success (121 files) |
| Runtime harness | TestClient against live Postgres + Redis for every scenario: guest POST → `SETEX pending-payment:{ref}` v2 TTL 86400 (verified via `redis-cli` client in-test incl. TTL bounds); webhook E2E → Member+Membership+Sale committed in one commit, key DELeted, advisory lock `member-provision:{phone}` set/released, CV invalidation POSTed with X-API-Key (fake httpx capture at the real notifier boundary) |
| Rollback boundary | revert `services/canonical_phone.py` + portal_auth import swap + guest endpoint/schema + `GUEST_CHECKOUT_RATE_LIMIT` + webhook guest branch + test file + 2 docs; member renewal path (Unit 1) fully intact without any of it; no migration in this unit |

## Discoveries (batch 2)

1. **The D10 reference regex takes a 10-digit timestamp** — `%Y%m%d` produces 8 digits and fails `^PH-[a-z0-9-]+-\d{10}-[a-f0-9]{6}$`. First RED run exposed it as wrong-reason greens (pydantic 422 on the "valid" fixture). Lesson re-learned: a 422-expecting test passes for free when the fixture itself is invalid — the happy-path test is what pins the fixture.
2. **slowapi quota is consumed only when the endpoint body runs** — pydantic-level 422s never engage the limiter (validation precedes the decorated handler). To prove a 429 you must burn budget with requests that pass schema validation and fail inside the handler (schema-valid, non-canonicalizable phone).
3. **Test DB connection is ASCII** — non-ASCII test data (María/Pérez) raises UnicodeEncodeError at bind time. Fixture names must stay ASCII even when the domain is Spanish.
4. **`_resolve_member` returns None for BOTH "no match" and "ambiguous"** — the guest branch needs the distinction (0 → create, >1 → 422), so the service exposes `find_members_by_canonical_phone` (list) alongside `resolve_member_by_phone` (specced None-on-ambiguous semantics kept for portal_auth).
5. **The advisory lock must span resolution → commit, not just creation** — releasing after the member flush would still let a second webhook miss the uncommitted row (phone is non-unique). Implemented as helper-returns-lock + webhook `finally` release; EX 15 is only the crash net.
6. **notify_cv_invalidation swallows its own failures** — the webhook's except+log path is only reachable when notify raises; the CV-unreachable test must mock at the portal module boundary to exercise the webhook's tolerance contract (the real-notifier test covers the header contract separately).

Legacy tests updated to new transport contract (same verified behaviors):
test_portal.py ×2, test_portal_security.py ×1 (+ key-consumption assertion added). (batch 1 — no legacy updates needed in batch 2.)

## TDD Cycle Evidence (batch 1 — Unit 1)

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
