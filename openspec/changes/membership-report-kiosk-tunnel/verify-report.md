```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:ce9110e1280a726bfedd71b7885139db8c397cd69d6299c0878ecde6947cf690
verdict: pass
blockers: 0
critical_findings: 0
requirements: 3/3
scenarios: 4/4
test_command: cd /root/faceapp/backend && set -a && . ./.env && set +a && /root/faceapp/.venv/bin/python -m pytest tests/ -q
test_exit_code: 0
test_output_hash: sha256:c816c92fe2ca2c7f33249449d2586f7cfdd729a36c10e697638c884c9a0c5fc8
build_command: cd /root/faceapp/backend && /root/faceapp/.venv/bin/flake8 . && /root/faceapp/.venv/bin/black --check . && /root/faceapp/.venv/bin/mypy .
build_exit_code: 0
build_output_hash: sha256:b39b416b6a50caf469886620f805b4063148e41924c7c36597b225f5bb57c97f
```

# Verification Report

**Change**: membership-report-kiosk-tunnel (Phase 4: Portal Security, tasks 4.1–4.7)
**Version**: N/A (change-level spec delta)
**Mode**: Strict TDD
**Scope**: branch `feat/portal-security-suite`, commits `99659b5..184849c` (3 work-unit commits + 1 docs commit). Tasks 5.1–5.3 are ops-time and deliberately out of scope — recorded below as outstanding ops items, not failures.

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total (Phase 4 scope) | 7 |
| Tasks complete | 7 |
| Tasks incomplete | 0 |
| Change-wide tasks | 27 (24 complete; 5.1–5.3 ops-time outstanding) |

### Build & Tests Execution

**Build (backend quality gate)**: ✅ Passed
```text
flake8 .            → exit 0, no findings
black --check .     → exit 0, 130 files would be left unchanged
mypy .              → exit 0, Success: no issues found in 118 source files
```

**Tests**: ✅ 423 passed / 0 failed / 0 skipped — run twice, deterministic
```text
cd /root/faceapp/backend && set -a && . ./.env && set +a \
  && /root/faceapp/.venv/bin/python -m pytest tests/ -q
→ 423 passed, 280 warnings in 25.11s   (exit 0)
Focused: python -m pytest tests/test_portal_security.py tests/test_tunnel_allowlist.py -q
→ 51 passed (16 portal-security + 35 tunnel-allowlist)   (exit 0)
```
423 = 372 pre-change baseline (apply-session safety net) + 51 new. Zero regressions. Zero skips — meaning the 6 RLS tests genuinely executed against the provisioned `member_portal` role (bootstrap succeeded via its documented `su postgres` fallback), and the CORS positive control ran.

**Coverage**: ➖ Not available — no coverage tool installed in the venv (no `pytest-cov`/`coverage`); CI runs pytest without coverage. Not a failure.

### Spec Compliance Matrix

Spec: `openspec/changes/membership-report-kiosk-tunnel/specs/customer-portal-runtime/spec.md` — 3 requirements, 4 scenarios.

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Restricted Tunnel Availability | Portal health succeeds through tunnel | `test_tunnel_allowlist.py::TestAllowedRoutes::test_basic_health_reachable` (+ `test_member_auth_routes_reachable`[3], `test_portal_routes_reachable`[5]) — asserts decision routes to `http://127.0.0.1:8000` under first-match ingress semantics | ✅ COMPLIANT (config-level; live-tunnel curl proof is ops task 5.3 via `docs/portal-tunnel-allowlist.md`) |
| Restricted Tunnel Availability | Tunnel exposure is restricted | `TestDeniedRoutes` (23 param cases: `/cv/*`, `/api/cv/*`, `/api/health/{db,full,redis}`, admin API, static, 7 near-misses) + `TestIngressStructure::test_final_rule_is_catch_all_404` — all fall through to `http_status:404` catch-all | ✅ COMPLIANT |
| Authenticated Member Isolation | Cross-member access is denied | `test_portal_security.py::TestPortalRlsIsolation` — 2 API-level (`/portal/me` from A's and B's JWT; forbidden identifiers absent from full JSON, own rows present as positive control) + 4 DB-level (unfiltered portal-role scan sees only self; targeted read of B's membership → 0 rows; no-context session → 0 rows; INSERT → `permission denied`) | ✅ COMPLIANT |
| Webhook and Runtime Controls | Forged webhook is rejected | `TestWebhookSignatureEnforcement` — missing header / wrong-secret signature / valid-signature-over-tampered-body → 401 with Membership+SalesTransaction row counts unchanged; positive control (valid signature → 200, exactly +1 membership, +1 transaction) | ✅ COMPLIANT |
| Webhook and Runtime Controls | Disallowed portal traffic is rejected | `TestCorsOriginRejection` (disallowed origin: no ACAO on simple request, preflight 400; allowed origin echoed — positive control; reads the app's actual `app.user_middleware` kwargs) + `TestMemberAuthRateLimits` (11th request → 429 `"Rate limit exceeded"` on all three `/api/auth/member-*`; app-level cooldown/lockout keys purged per request so responses 1–10 prove the 429 is slowapi's) | ✅ COMPLIANT |

**Compliance summary**: 4/4 scenarios compliant (3/3 requirements).

### Correctness (Static Evidence)

| Area | Status | Notes |
|------|--------|-------|
| 4.1 webhook HMAC rejection | ✅ Implemented | `verify_wompi_signature` (api/portal.py:184, pre-existing since `9b41569`) checked before any write; rejection tests assert no state change via row counts |
| 4.2 CORS rejection | ✅ Implemented | `CORSMiddleware` in main.py:222 (since initial commit `8549eef`); disallowed origin → no ACAO + preflight 400 (starlette "Disallowed CORS origin") |
| 4.3 RLS isolation | ✅ Implemented | `member_portal` role NOINHERIT LOGIN, SELECT-only grants on 5 tables, 5 `portal_*` policies scoped to `current_setting('app.member_id', true)` — bootstrap applies `001_rls_setup.sql` §7 (lines 147–171) **verbatim** (cross-checked line-by-line) |
| 4.4/4.5 rate limits | ✅ Implemented | `@limiter.limit(settings.MEMBER_AUTH_RATE_LIMIT)` on all three routes (portal_auth.py:165, 209, 265); `MEMBER_AUTH_RATE_LIMIT: str = "10/minute"` (core/config.py:87); `request: Request` param + body param renamed to `body` on member-verify |
| 4.6/4.7 allowlist | ✅ Implemented | `scripts/cloudflared/config.yml`: anchored regexes (`^/api/health/?$`, `^/api/auth/member-(login\|verify\|resend)/?$`, `^/api/portal/.*`), single loopback origin `http://127.0.0.1:8000`, RFC 2606 placeholder hostname, final `http_status:404` catch-all; `docs/portal-tunnel-allowlist.md` consistent (exposure table, near-miss curl checks, provisioning, rollback) |
| conftest wiring | ✅ Implemented | `ensure_member_portal_env()` called before `from main import app` (conftest.py:12 vs :20); autouse `fresh_rate_limits` fixture resets process-global slowapi storage around every test |
| Hallucination check | ✅ Clean | Every file/test named in apply-progress.md exists and contains the named test classes: `tests/test_portal_security.py` (4 classes, 16 tests), `tests/portal_rls_bootstrap.py` (236 lines), `tests/test_tunnel_allowlist.py` (35 tests), `scripts/cloudflared/config.yml`, `docs/portal-tunnel-allowlist.md`, `backend/mypy.ini` yaml ignore. Commit stats match the claim exactly: 3 commits, 9 files, +1212/−19 (372+5−, 487+14−, 353+0−); `184849c` is docs-only (apply-progress.md + tasks.md) |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Tunnel exposure = exact allowlist (design.md:15, :39, :78) | ✅ Yes | config.yml rules match the design exposure set exactly: `GET /api/health` + 3 `/api/auth/member-*` + `/api/portal/*` allowed; `/cv/*`, `/api/cv/*`, `/api/health/{db,full,redis}`, admin API, static denied via catch-all 404. Method-level (GET vs POST) control documented as app-enforced (cloudflared ingress is path-level) — consistent across config comment, test docstring, and docs runbook |
| `member_portal` RLS role stays SELECT-only (design.md:22) | ✅ Yes | GRANT SELECT only; INSERT denied at flush (`permission denied`) proven by test; no policy weakening — policies verbatim from 001 §7 |
| Rate limits on the three `/auth/member-*` (design.md:50) | ✅ Yes (documented deviation) | `core/rate_limiter.py` NOT modified — the shared limiter already existed; the change is `MEMBER_AUTH_RATE_LIMIT` in `core/config.py` consumed by the route decorators. Design intent (per-route slowapi limits) fully met; deviation recorded in apply-progress before this verification |
| Webhook verified before state change (design.md:29) | ✅ Yes | HMAC checked before Membership/SalesTransaction inserts; row-count assertions prove no partial writes on rejection |
| RLS provisioning = 001 subset, not whole script | ✅ Yes (documented deviation) | Whole 001 would create backend_app/backend_readonly and FORCE audit_logs RLS (affects even owner locally); bootstrap applies the member_portal-relevant §7 subset verbatim — recorded in apply-progress |
| docs ↔ config ↔ tests consistency | ✅ Yes | docs/portal-tunnel-allowlist.md allowlist table = config.yml rules = test allow/deny sets, including the near-miss class and the bare `/api/portal` denial |

### TDD Compliance (Strict TDD)

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | apply-progress.md "Genuine forward RED→GREEN evidence" table, per-task rows with exact RED failure text (e.g. 4.4: `AssertionError: (401, '{"detail":"Código incorrecto o expirado"}')`; 4.6: `FileNotFoundError`) |
| All tasks have tests | ✅ | 7/7 tasks have named test files, all exist on disk |
| RED confirmed (tests exist) | ✅ | 7/7 test files/classes verified present; test counts match claims (16 + 35 = 51) |
| GREEN confirmed (tests pass) | ✅ | 51/51 focused pass; full suite 423 passed (2 runs, 0 skips, 0 flaky) |
| Triangulation adequate | ✅ | Webhook: 3 negative + 1 positive control; CORS: 2 negative + 1 positive; RLS: API-level both directions + 4 DB-level; rate: one per route with pre-429 status ladder asserted; allowlist: structure + allowed + denied + 7 near-misses |
| Safety Net for modified files | ✅ | Full-suite baseline 372 passed recorded before, 423 after (apply session); this verification re-confirms 423 with zero regressions |

**TDD Compliance**: 6/6 checks passed. Two process caveats graded as WARNINGs below (approval tests 4.1/4.2; non-replayable 4.3 RED harness).

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 35 | 1 (`test_tunnel_allowlist.py`) | pytest + pyyaml — replays cloudflared first-match ingress semantics (path = unanchored regex ≈ Go RE2 `MatchString`) against the shipped config |
| Integration | 16 | 1 (`test_portal_security.py`) | FastAPI TestClient + real Postgres + real Redis + real `member_portal` TCP login (RLS policies exercised in-database, not mocked) |
| E2E | 0 | 0 | live-tunnel runtime checks are ops task 5.3 (curl runbook in docs) |
| **Total** | **51** | **2** | |

No tools outside cached capabilities are used (pytest/TestClient/redis/pyyaml all pre-existing).

### Changed File Coverage

Coverage analysis skipped — no coverage tool detected (`pytest-cov`/`coverage` not installed; CI runs plain pytest). Informational only, not a failure.

### Assertion Quality

| File | Line | Assertion | Issue | Severity |
|------|------|-----------|-------|----------|
| — | — | — | No trivial, tautological, ghost-loop, or smoke-only assertions found; every negative test has a positive control proving non-vacuity (webhook valid-signature writes; CORS allowed-origin echo; RLS own-rows visible; rate ladder `[200]*10`/`[401]*10` before the 429) | — |

**Assertion quality**: ✅ All assertions verify real behavior (0 CRITICAL, 0 WARNING).

Notable assertion hygiene: `TestCorsOriginRejection` asserts its own premise (`origin not in allow`) before the negative check; `test_portal_role_cannot_read_other_members_membership` asserts empty with an inline pointer to its non-empty companion; forbidden-identifier checks scan the FULL JSON dump, not just top-level keys.

### Quality Metrics

**Linter (flake8)**: ✅ No errors (exit 0)
**Formatter (black --check)**: ✅ 130 files unchanged (exit 0)
**Type Checker (mypy)**: ✅ Success, no issues in 118 source files (exit 0)

### Issues Found

**CRITICAL**: None

**WARNING**:
1. **Task 4.3 RED harness is not replayable from the repo.** The RLS RED proof ran with RLS disabled post-provisioning via an uncommitted `/tmp` pytest plugin (`portal_red_plugin`, deliberately not committed). The failure transcript is recorded in apply-progress (3 DB-level tests failed with RLS weakened), and the GREEN state + policy text are independently verified here — but a future auditor cannot re-run the RED step from the branch alone. Documented honestly; evidence limitation, not a product defect.
2. **Tasks 4.1/4.2 are approval tests, not RED-first.** The webhook verification and CORS middleware pre-existed this change (verified: `verify_wompi_signature` since `9b41569`; `CORSMiddleware` since the initial commit `8549eef`), so no genuine RED was possible without deleting production code. This was declared at planning time in tasks.md ("Approval tests") and the tests are spec-locking regressions guards — a justified Strict-TDD deviation, transparently recorded.

**SUGGESTION**:
1. Install `pytest-cov` and add changed-file coverage reporting to enable the coverage dimension of future verifications (informational today).

### Outstanding Ops Items (Phase 5 — deliberately out of scope, NOT failures)

- **5.1** Tunnel prerequisites (no secrets): provision cloudflared on LXC 114 + Cloudflare Pages — placeholder `<TUNNEL_ID>`/`portal.example.com` in `scripts/cloudflared/config.yml` must be replaced per `docs/portal-tunnel-allowlist.md`.
- **5.2** Verify `001_rls_setup.sql` is APPLIED on production (member_portal SELECT-only, `MEMBER_PORTAL_DATABASE_URL` set for the backend unit) BEFORE the tunnel opens.
- **5.3** Confirm external deps (Redis, Evolution, Wompi, cloudflared), then run the live curl verification from `docs/portal-tunnel-allowlist.md` (allowed routes 200; `/cv/*`, deep health, admin, near-misses all 404) and open.

### Remediation Performed

None required. All commands green on first execution; all artifact claims verified true (files, test counts, commit stats, policy text, config semantics). No flaky tests observed (full suite run twice, identical results). No artifact corrections needed.

### Verdict

**PASS WITH WARNINGS**

Phase 4 (tasks 4.1–4.7) is fully implemented, tested (423 passed, 0 failed, 0 skipped), lint/type-clean, and spec-compliant (4/4 scenarios, 3/3 requirements); the 2 warnings are documented Strict-TDD process-evidence caveats (non-replayable 4.3 RED harness; approval tests for pre-existing 4.1/4.2 behavior), not product defects. Phase 5 ops items (5.1–5.3) remain outstanding by design.
