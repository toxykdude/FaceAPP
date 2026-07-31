# FaceAPP Security Remediation Master Plan

> **Audience:** the implementing agent. This document tells you **only how to fix** every finding from the Codex Security scan (108 findings: 3 critical, 13 high, 56 medium, 36 low). It is organized so you can execute workstream-by-workstream with concrete recipes, exact files/symbols, tests to add, and acceptance criteria.
>
> **Scan of record:** `~/codex-security/reports/faceapp/` → `report.md`, `findings.json`, `exports/results.sarif`, `coverage.json`. Revision scanned: `e43f2436`. Coverage was **partial** — fix the listed items, then re-run a full scan.
>
> **Scope scanned:** `backend/core`, `backend/api`, `cv_service`. Other paths (frontend, scripts, alembic, services outside those dirs) were NOT scanned — do not assume they are clean.

---

## 0. Global execution rules (read first — apply to every fix)

These are non-negotiable repo invariants. Violating them breaks CI or production.

1. **Fail closed, always.** Every "secret not configured" branch must **reject**, never allow. The scan's #1 root cause is fail-open secret checks. This single principle closes most criticals.
2. **No secrets in code, ever.** Secrets are env vars (see `SECURITY.md §2`). Reject weak/placeholder/default values **at startup**, not at use time.
3. **Server-side authority.** Never trust client-supplied prices, roles, permissions, payment proof, or consent. Derive from the plan / provider / DB.
4. **RBAC granularity.** Use `require_page("<page>")` (see `backend/api/deps.py:222`), not bare `require_staff`, for any route tied to a UI page. Admins bypass; staff need explicit page grant.
5. **Timezone:** ALL date/window/day authorization math MUST go through `backend/services/timezone.py` → `get_app_tz(db)`. Never `datetime.utcnow()`, never hardcoded `America/Bogota`. The CV service must read the same configured TZ, not the host clock.
6. **i18n:** every new/changed user-visible string goes through `t.<section>.<key>` in `frontend/src/i18n/translations.ts` with both `es` and `en`. No hardcoded JSX strings.
7. **CV API key propagation:** any change to the enrollment → CV notification path must keep the `X-API-Key` header (`notify_cv_invalidation` in `backend/api/members.py`).
8. **Backups/exports** need `BACKUP_DATABASE_URL` (the `powerhouse_backup` BYPASSRLS role), never `DATABASE_URL` (RLS blocks the runtime role).
9. **Conventions:** Conventional Commits (`fix(security): …`), branch `fix/security-<area>`, PRs target `main`, **no** `Co-Authored-By`/AI attribution.
10. **Test gate (per `AGENTS.md`):**
    ```bash
    cd backend && set -a && . ./.env && set +a && docker-compose up -d db redis
    python init_db.py && pytest tests/            # currently 144 passing — must stay green
    cd ../cv_service && pytest tests/             # 12 passing
    cd ../frontend && npm run lint && npm run type-check && npm run test
    flake8 . && black --check . && mypy .          # in backend/
    ```
    Every fix adds **at least one negative test** (lower-privileged caller / malformed input is rejected) and a **positive regression test** (intended path still works) — this is the scan's universal `remediationTests` contract.
11. **Negative tests are mandatory for every authz/authn change.** The scan explicitly requires "deny-by-default tests for lower-privileged callers." Add a staff-without-page fixture and an unauthenticated client fixture to `backend/tests/conftest.py`.
12. **Atomicity for audit:** protected mutation + audit row must commit in the **same transaction**. See WS-8.

---

## Workstream map

| WS | Title | Findings | Priority |
|----|-------|----------|----------|
| **S** | Shared Security Control Library (do first) | unblocks ~40 findings | P0 |
| **1** | Secrets & startup hardening | C×2, M×1, L×1 | P0 |
| **2** | Internal service auth (fail-closed) | C×1, H×2, M×6 | P0 |
| **3** | RBAC / page permissions | H×21, M×6, L×1 | P0/P1 |
| **4** | Payment integrity | H×1, M×2 | P0/P1 |
| **5** | Biometric data protection | M×5, L×4 | P1 |
| **6** | Cameras & RTSP | H×2, M×5, L×5 | P1 |
| **7** | CV liveness & access validation | M×8 | P1 |
| **8** | Sync data integrity & audit | H×2, M×4, L×5 | P1 |
| **9** | Authn hardening (enum/timing/revocation/throttle) | M×2, L×7 | P2 |
| **10** | Input/transport hardening | M×4, L×8 | P2 |

**Execution order:** S → 1 → 2 → 3 → 4 → (5,6,7,8 parallel) → 9 → 10. Then re-scan (full repo) and close residual findings.

---

## Workstream S — Shared Security Control Library (BUILD FIRST)

These are the centralized controls referenced by dozens of findings. Build them once in a feature branch `fix/security-shared-controls`, merge, then every downstream WS reuses them.

### S1. Fail-closed `verify_internal_secret` — `backend/api/cv_internal.py:33`
**Current (fail-open):**
```python
async def verify_internal_secret(x_internal_secret: str = Header(None, alias="X-Internal-Secret")):
    if not settings.INTERNAL_API_SECRET:
        return None  # ❌ Development mode
    if x_internal_secret != settings.INTERNAL_API_SECRET:
        raise HTTPException(401, ...)
```
**Fix:** reject when unset; use `hmac.compare_digest`.
```python
import hmac
async def verify_internal_secret(x_internal_secret: str = Header(None, alias="X-Internal-Secret")):
    secret = settings.INTERNAL_API_SECRET
    if not secret:                                  # fail CLOSED
        raise HTTPException(503, "INTERNAL_API_SECRET not configured")
    if not x_internal_secret or not hmac.compare_digest(x_internal_secret, secret):
        raise HTTPException(401, "Invalid internal service credentials")
    return x_internal_secret
```
**Closes:** all `missing-authentication.missing-auth` on `cv_internal.py` + `events.py` (WS-2). **Tests:** `test_internal_secret_required` (no header → 503/401), `test_internal_secret_wrong` → 401, `test_internal_secret_correct` → 200.

### S2. Fail-closed `verify_api_key` — `cv_service/main.py:97`
Same pattern as S1. `if not settings.API_KEY:` → `raise HTTPException(503, "API_KEY not configured")`; use `hmac.compare_digest`.
**Closes:** CV `/invalidate`, `/reload`, `/cameras/start|stop`, `/health`, `/stream`, `/ws/camera` unauth surfaces (WS-2, WS-6).

### S3. Startup secret validation — new `backend/core/startup_checks.py` + call from `backend/main.py` startup
Validate at boot, **fail fast** (raise → container won't start) on weak/placeholder/default secrets:
```python
# backend/core/startup_checks.py
from core.config import settings
_PLACEHOLDERS = {"", "changeme", "secret", "admin123", "dev-jwt-secret-change-in-production",
                 "UJrZ7tMU93YaNX", "your-secret-key", "replace-me"}

def assert_production_secrets():
    for name in ("JWT_SECRET", "ENCRYPTION_KEY", "INTERNAL_API_SECRET"):
        val = getattr(settings, name, "")
        if not val or val in _PLACEHOLDERS or len(val) < 32:
            raise RuntimeError(f"{name} missing/weak/placeholder — refusing to start")
    if settings.ADMIN_PASSWORD in _PLACEHOLDERS or len(settings.ADMIN_PASSWORD) < 10:
        raise RuntimeError("ADMIN_PASSWORD is default/weak — refusing to start")
    if settings.API_KEY and len(settings.API_KEY) < 24:
        raise RuntimeError("API_KEY too short")
```
- Gate with an env flag `REQUIRE_PROD_SECRETS=1` (set in `docker-compose.yml` prod profile + `install.sh`) so dev isn't blocked, but **prod fails closed**.
- Update `docker-compose.yml:29-30` (`ENCRYPTION_KEY`, `JWT_SECRET`) to non-placeholder values generated at install (write to `/etc/faceapp/app.env`, gitignored) — and document in `SECURITY.md §2`.
**Closes:** `weak-cryptography.jwt_signing_secret` (C), `weak-password-policy.default_admin_password` (C), `weak-cryptography.biometric_rtsp_encryption_key` (M). **Tests:** `test_startup_rejects_placeholder_jwt`, `test_startup_rejects_admin123`.

### S4. Strong-key `get_encryption_key` — `backend/core/encryption.py:14`
**Current (weak-key fallback):** `return key.encode("utf-8")[:32].ljust(32, b"\0")` silently pads/truncates → weak AES key.
**Fix:** require exactly 32 bytes after base64/hex/raw decode; else `raise ValueError("ENCRYPTION_KEY must decode to 32 bytes")`. Remove the zero-pad fallback. **Test:** `test_encryption_key_rejects_short`.

### S5. Sync table→page authorization map — new helper in `backend/api/sync.py`
Replace the bare `require_staff` on `sync_pull`/`sync_push` with per-table authorization. Create:
```python
SYNC_TABLE_PAGE = {           # table -> page permission required to read/write
    "members": "members", "memberships": "memberships", "membership_plans": "memberships",
    "sales_transactions": "sales", "users": None,   # None = admin-only
    "cameras": None, "audit_log": None,
}
def assert_table_allowed(current_user: User, table: str, write: bool):
    page = SYNC_TABLE_PAGE.get(table, None)
    if current_user.role == UserRole.ADMIN: return
    if page is None:                      # users/cameras/audit_log → admin only
        raise HTTPException(403, f"{table} requires admin")
    # reuse deps.require_page logic
    perms = current_user.permissions or {}
    pages = perms.get("pages", [])
    if "all" not in pages and page not in pages:
        raise HTTPException(403, f"Access denied to {page}")
```
Call it for every requested table in `sync_pull` (`sync.py:105`) and every op table in `sync_push` (`sync.py:153/230/301`). **Remove `users`, `cameras`, `audit_log`** from any staff-accessible map (they must be admin-only). **Closes:** `sensitive-pull`, `page-authz` (sync), camera authz (WS-3/6/8).

### S6. Credential versioning for session revocation — `backend/core/security.py` + `deps.py`
Add a `token_version` to JWT payload and a `users.token_version` column (Alembic migration). `create_access_token` stamps current version; `get_current_user` rejects if `payload["ver"] != user.token_version`. Bump `user.token_version` on password change (WS-9) and admin password reset. Blacklist-on-change no longer needed for forward revocation. **Closes:** both `session-revocation.*` (WS-9). **Migration required.**

### S7. CSV formula sanitizer — new `backend/core/csv_safety.py`
```python
def sanitize_csv_cell(v: str) -> str:
    if v and v[0] in "=+-@\t\r":
        return "'" + v          # prefix neutralizes formula
    return v
```
Apply to **every** exported column in `import_export.py:145` and `sales.py:286`. **Closes:** `spreadsheet-formula-injection.csv-formula` (×2). **Test:** `test_csv_export_neutralizes_formula`.

### S8. SSRF resolver — new `backend/core/net_guard.py` (+ mirror in `cv_service`)
Resolve host, block private/loopback/link-local/reserved **after DNS resolution**, restrict schemes (`http`,`https` for snapshot; `rtsp` only for camera streams), revalidate on redirect, reject if any resolved IP is private.
```python
import ipaddress, socket
_BLOCKED = lambda ip: ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
def assert_safe_url(url: str, schemes=("http","https")):
    p = urlparse(url)
    if p.scheme not in schemes: raise ValueError("scheme not allowed")
    for fam,*_ in socket.getaddrinfo(p.hostname, None):
        ip = ipaddress.ip_address(_[4][0])
        if _BLOCKED(ip): raise ValueError("private/loopback host blocked")
```
Use in `cv_service/main.py` camera-start (`:446`) **and** `backend/api/cameras.py` snapshot/test (`:57/191/290`) **and** backup probes `system.py:208`. **Closes:** all `server-side-request-forgery.*` (WS-6, WS-10). **Critical:** the current filter "swallows its own rejection" — the bug is the filter logs/returns instead of raising. Make it raise and abort the op.

### S9. Audit durability helper — `backend/core/audit.py`
The bug (8 findings): `log_action` only **flushes**; the protected mutation commits first, audit row never commits. **Fix:** make `log_action` commit within the caller's transaction, OR add `log_action_and_commit(db, ...)` that writes the audit row then `db.commit()` in the same call so mutation+audit are atomic. Update every call site that currently does `db.commit()` then `log_action(...)`. **Closes:** all `audit-integrity.*` (WS-8). **Test:** `test_mutation_and_audit_atomic` (force rollback mid-flow → neither persists).

### S10. Rate-limit key — `backend/api/auth.py:26`
`@limiter.limit("5/minute")` keys on a value that collapses all clients behind the proxy. Use the real client IP from `X-Forwarded-For` (last hop) or Cloudflare `CF-Connecting-IP`. Configure `limiter` `key_func` accordingly. **Closes:** `proxy-rate-key`, supports WS-9 throttles.

---

## Workstream 1 — Secrets & startup hardening (P0)

| # | Rule | Sev | CWE | Location | Fix |
|---|------|-----|-----|----------|-----|
| 1 | `weak-cryptography.jwt_signing_secret` | **C** | 321/798 | `docker-compose.yml:30`, `backend/core/config.py:33`, `backend/core/security.py:47,65` | S3 (reject placeholder at boot). Also: `create_access_token`/`decode_access_token` already use `settings.JWT_SECRET` — no code change beyond the startup gate. Rotate any issued tokens after deploying a real secret. |
| 2 | `weak-password-policy.default_admin_password` | **C** | 521/798 | `backend/api/auth.py:26`, `init_db.py` | S3 (reject `admin123`). In `init_db.py`, if `ADMIN_PASSWORD` unset/default → raise instead of seeding `admin123`. Force password change on first login (add `must_change_password` flag). |
| 3 | `weak-cryptography.biometric_rtsp_encryption_key` | M | 321 | `docker-compose.yml:29`, `encryption.py:14` | S3 + S4. |
| 4 | `hardcoded-credential.pending_payment_lookup` | L | 798 | `backend/api/portal.py:416` | The pending-payment lookup is "protected" only by the public shipped `SECRET_KEY`. Replace with a per-operation signed token bound to `member_id`+`reference` and verified server-side, or require the member JWT. Remove reliance on `SECRET_KEY` as a shared secret for member-facing lookups. |

**Acceptance:** app refuses to start with any placeholder secret (negative boot test); no default credential can authenticate; pending-payment lookup rejects forged tokens.

---

## Workstream 2 — Internal service auth, fail-closed (P0)

**Root cause (all):** `verify_internal_secret` / `verify_api_key` allow-all when secret unset. Fixed centrally by S1 + S2 + S3.

| # | Rule | Sev | Loc | Extra |
|---|------|-----|-----|-------|
| 1 | `missing-authentication.missing-auth` (templates) | **C** | `cv_internal.py:52` | S1. This exports **all decrypted facial embeddings** — highest biometric impact. |
| 2 | `missing-authentication.missing-auth` (enabled cameras) | **H** | `cv_internal.py:219` | S1. Discloses decrypted RTSP URLs+creds. |
| 3 | `missing-authentication.missing-auth` (cv `/invalidate`) | **H** | `cv_service/main.py:755` | S2. Allows deleting facial templates. |
| 4 | `missing-authentication.missing-auth` (cv `/reload`) | M | `cv_service/main.py:748` | S2. Resource-heavy, remotely triggerable. |
| 5–9 | `missing-authentication.missing-auth` (cv start/stop/health, backend_client, events) | M/H | `cv_service/main.py:446/457`, `cv_service/api/backend_client.py:34/47/59/79/101`, `backend/api/events.py:128` | S1/S2. `backend_client.py` must **send** the header and **fail** if the backend 401s (currently omits header when secret empty). `events.py` access-event writer must fail-closed (also WS-8 audit forgery). |

**Acceptance:** with no/empty secret configured, every `/cv/*` and CV control endpoint returns 401/503; backend_client aborts on missing header. Negative tests for each.

---

## Workstream 3 — RBAC / page permissions (P0/P1)

**Root cause:** dozens of mutating/read routes use bare `require_staff`, bypassing `require_page`. Plus the `sync` pull/push endpoint (`sync.py:105/153`) is a single role-only API that exposes every table.

### 3a. The sync bypass (highest leverage) — `backend/api/sync.py`
Apply **S5** (`assert_table_allowed`) to:
- `sync_pull` (`:105`) — per requested table
- `sync_push` INSERT (`:153`), UPDATE (`:230`), DELETE (`:301`) — per op table
Remove `users`, `cameras`, `audit_log` from staff reach (admin-only). **Closes:** `sensitive-pull` (H), `page-authz` on sync (H), camera-insert/update/delete authz (H/M), membership-delete-authz (M).

### 3b. Membership endpoints — `backend/api/memberships.py`
Swap `require_staff` → `require_page("memberships")` on:
- `POST ""` create (`:96`), `PUT /{id}` update (`:161`), `POST /{id}/renew` (`:216`), delete, and every read-by-id.
**Closes:** the 6 membership `page-authz` highs. **Test:** staff without `memberships` page → 403 on each.

### 3c. Plans — `backend/api/membership_plans.py`
`require_page("memberships")` on create/update/delete/price/duration/status. **Closes:** `page-authz` plan mediums.

### 3d. Sales — `backend/api/sales.py`
`require_page("sales")` on read-by-id and the CSV export (`:286`). Also apply **S7** to the export. **Closes:** sales read + sales CSV `page-authz`.

### 3e. Reports — `backend/api/reports_email.py`, dashboard
`require_page("reports")` on manual report send (`:285`) and aggregated dashboard read. **Closes:** report/dashboard `page-authz`.

### 3f. Import/export — `backend/api/import_export.py`
`require_page("reports")` (or "members") on the members CSV export (`:145`); apply **S7**. **Closes:** import/export `page-authz` + audit-persistence (WS-8).

### 3g. Default staff all-pages — `backend/api/users.py:42`
`UserCreate` defaults `permissions` such that an unset object grants everything. **Fix:** deny-by-default — explicit empty `permissions={"pages": []}`; admin must explicitly grant. **Closes:** `privilege-management.default-staff-all-pages`. **Test:** create staff with no perms → no page access.

**Acceptance:** a staff user without page X gets 403 on every route of page X (full negative-test matrix); admin still works; sync respects per-table map.

---

## Workstream 4 — Payment integrity (P0/P1)

### 4a. Wompi payment-proof bypass — `backend/api/portal.py:104` (`client-side-enforcement.payment-proof`, H, CWE-602/840)
`POST /api/portal/renew` trusts client `plan_id` + `amount` and activates membership **without proving Wompi paid**.
**Fix:** activation must happen **only** in the verified Wompi webhook (`/portal/webhook-renew`):
1. `verify_wompi_signature` MUST run first (HMAC-SHA256 with `WOMPI_INTEGRITY_SECRET`) — if the secret is unset, **403** (fail-closed), never process.
2. Look up the Redis pending payment by `reference`; verify `amount_in_cents` and `currency` match server-stored values.
3. Idempotency: reject already-processed `reference`.
4. Server derives `plan_id`, price, duration from the plan — never from the client.
Remove direct activation from `POST /portal/renew`; that route may only **create** a pending payment (store `member_id`, `plan_id`, server-computed `amount`, `reference` in Redis TTL 24h) and return the Wompi reference. **Tests:** forged webhook → 403; amount mismatch → 400; valid → membership created exactly once.

### 4b. Membership price derivation — `backend/api/memberships.py:96/161` (`client-side-enforcement.business-price`, M×2)
`MembershipCreate`/`MembershipUpdate` trust caller `price`/entitlement. **Fix:** ignore client price; compute from `plan_id` server-side (`plan.price`); reject negative; derive `end_date`/`type` from plan. **Closes:** both business-price mediums + supports `input-validation.sales-insert-validation`.

**Acceptance:** a member cannot activate paid time without a verified Wompi event; membership price always equals the plan's price.

---

## Workstream 5 — Biometric data protection (P1)

| # | Rule | Sev | Loc | Fix |
|---|------|-----|-----|-----|
| 1 | `missing-authorization.biometric-consent` (×2) | M | `enrollment.py:311` (upload), `:521` (camera) | Before storing a template: assert `member.consent_given and member.consent_given_at is not None`; else **403** "consent required" (Ley 1581 Art. 9). Capture consent timestamp if not set. **Test:** enroll member w/o consent → 403. |
| 2 | `audit-integrity.biometric-audit` (×3) | L | `enrollment.py:311/396/521` | Apply **S9** — audit row commits atomically with enrollment/deletion. |
| 3 | `cleartext-sensitive-data.plaintext_biometric_redis_cache` | M | `cv_service/main.py:184` | The Redis template cache stores **decrypted** embeddings in cleartext. Encrypt-at-rest in Redis using the same deployment key (AES-GCM), or store only encrypted blobs and decrypt on match. Document the cache key TTL + invalidation. |
| 4 | `cleartext-transport.cleartext-biometric-transport` | M | `cv_service/api/backend_client.py:17` | The CV→backend template payload + internal secret travel over cleartext. Force `https://` backend URL in prod; reject `http://` when `REQUIRE_PROD_SECRETS`. Send `INTERNAL_API_SECRET` only over TLS. |
| 5 | `race-condition.template_revocation_reload_race` | L | `enrollment.py:396` | Concurrent `/reload` (CV) + enrollment delete can reinsert a revoked template. **Fix:** serialize with a Redis lock `SET nx px` around delete+invalidate, or a DB row lock / generation check on `biometric_templates`. **Test:** concurrent delete+reload → revoked template never reappears. |
| 6 | WebSocket recognition unauth | H | `cv_service/main.py:665` | S2 (fail-closed `verify_api_key`). Additionally bind the WS to the authenticated kiosk device, not any caller. |

**Acceptance:** no template stored without consent; no decrypted embedding in Redis or transit; revoked templates cannot be resurrected.

---

## Workstream 6 — Cameras & RTSP (P1)

| # | Rule | Sev | Loc | Fix |
|---|------|-----|-----|-----|
| 1 | `cleartext-sensitive-data.camera-insert-authz-encryption` | H | `sync.py:153` | S5 (cameras admin-only) + `encrypt_string(rtsp_url)` on every camera INSERT. Reject plaintext RTSP in DB. |
| 2 | `cleartext-sensitive-data.camera-update-authz-encryption` | H | `sync.py:230` | Same for UPDATE — re-encrypt on write; never persist plaintext. |
| 3 | `incorrect-authorization.camera-delete-authz` | M | `sync.py:301` | S5 (cameras admin-only). |
| 4 | `sensitive-data-exposure.rtsp_failure_url_health_exposure` | H | `cv_service/main.py:766` | On stream failure, store only a sanitized error (no URL/creds) in health state. Strip `user:pass@` before logging. **Test:** failed stream → health JSON has no `rtsp://user:pass`. |
| 5 | `resource-exhaustion` (camera start) | M | `cv_service/main.py:446` | Bound `camera_id` (allowlist/UUID), cap concurrent cameras + FPS; reject >N. |
| 6 | `ssrf_*` (camera-start private-IP) | M×3 | `cv_service/main.py:446` | **S8.** The filter currently swallows its rejection — make `assert_safe_rtsp` **raise** and abort `start_camera`. Block private/loopback post-DNS. |
| 7 | `server-side-request-forgery.http-ssrf` / `media-url-injection` / `camera-test-ssrf` | L×5 | `backend/api/cameras.py:57/191/290` | **S8** on snapshot URL + test op. Restrict schemes; block private hosts. |

**Acceptance:** camera RTSP creds only ever stored encrypted; health endpoint leaks no creds; camera-start refuses private/internal URLs.

---

## Workstream 7 — CV liveness & access validation (P1)

All in `cv_service/stream/rtsp_processor.py:264` (liveness) and `cv_service/validation/access_validator.py` (policy).

### 7a. Liveness fail-open (×4 mediums + 1 cross-stream)
`check_liveness` accepts when: baseline not yet established (first frames), EAR computation fails, <2 eyes, or continuously-open eyes (no blink). **Fix (make mandatory, fail closed):**
- Require **positive** liveness evidence (a detected blink / motion) before any match — never accept on missing/error.
- On `EAR` computation error or `<2 eyes` → `is_live=False`.
- Expire per-stream liveness state per-subject; don't share across cameras/subjects (`liveness_cross_stream_state_reuse`).
- Add a max "grace frames" of 0 during the spoofing gate.
**Tests:** static photo → never recognized; EAR failure → rejected; cross-camera state not reused.

### 7b. Access policy (`access_validator.py`)
| # | Rule | Sev | Loc | Fix |
|---|------|-----|-----|-----|
| 1 | `incorrect-authorization.incorrect-location-authz` | M | `:19` | Compares location **labels** against **IDs** → never matches → fail-open grants. Compare like-for-like (`location_id == location_id`) and **fail closed** on mismatch. |
| 2 | `incorrect-authorization.wrong-timezone-date-authz` | M | `:85` | Uses host date. Use `get_app_tz`-equivalent (CV must read the configured business TZ from backend settings, not `datetime.now()`). |
| 3 | `incorrect-authorization.wrong-timezone-day-authz` | M | `backend/schemas/membership.py:13` | Allowed-day uses host weekday. Compute weekday in configured TZ. |
| 4 | `incorrect-authorization.wrong-timezone-window-authz` | M | `backend/schemas/membership.py:13` | Access window uses host clock. Compute in configured TZ. |

**Acceptance:** spoofed photo/photo rejected; location/date/day/window evaluated in the configured business timezone; location check fails closed.

---

## Workstream 8 — Sync data integrity & audit (P1)

| # | Rule | Sev | Loc | Fix |
|---|------|-----|-----|-----|
| 1 | `sensitive-pull` (users table) | H | `sync.py:105` | **S5** — remove `users` from staff-accessible tables (admin-only). Never expose password hashes via sync. |
| 2 | `stale-resource.member-delete-audit-invalidation` | H | `sync.py:301` | Member DELETE via sync must: write audit (S9) **and** call CV invalidation (`notify_cv_invalidation` with `X-API-Key`). No silent cascade. |
| 3 | `business-logic.sales-delete-integrity` | M | `sync.py:39` | Remove `DELETE` from sales sync mode (financial records must be immutable; use refunds/voids). |
| 4 | `business-logic.sales-update-integrity` | M | `sync.py:230` | Remove `UPDATE` from sales sync mode. |
| 5 | `input-validation.sales-insert-validation` | M | `sync.py:39` | INSERT must run the same validation as the normal API (server invoice number, validated schema, server-derived totals). |
| 6 | `audit-integrity.audit-persistence` (×4) | L | `members.py:163/336/395`, `import_export.py:69` | **S9** — mutation + audit atomic. |
| 7 | `audit-integrity.biometric-audit` (×3) | L | `enrollment.py:311/396/521` | **S9** (with WS-5). |
| 8 | `audit-integrity.login` | L | `backend/core/audit.py:38` | **S9** — login audit row must commit, not just flush. |
| 9 | `incorrect-authorization.membership-delete-authz` | M | `sync.py:301` | **S5** (memberships require page; admin for delete). |

**Acceptance:** staff cannot read `users`/password hashes; financial records immutable via sync; every protected mutation has a durable, committed audit row in the same transaction.

---

## Workstream 9 — Authn hardening: enumeration / timing / revocation / throttle (P2)

| # | Rule | Sev | Loc | Fix |
|---|------|-----|-----|-----|
| 1 | `session-revocation.admin-password-change-session-persistence` | M | `users.py:188` | **S6** — bump `token_version` on admin password change; all prior JWTs invalid instantly. |
| 2 | `session-revocation.reset-session-persistence` | M | `password_reset.py:135` | **S6** — bump `token_version` on successful reset. |
| 3 | `observable-discrepancy.username-timing` | L | `auth.py:26` | For unknown username, still run a dummy bcrypt `verify` against a fixed hash so timing matches the known-user path. Constant-time message. |
| 4 | `observable-discrepancy.member-login-enumeration` / `member-resend-enumeration` | L×2 | `portal_auth.py:151/237` | Return the same generic "if the phone is registered, a PIN was sent" regardless of existence; same response shape + timing. |
| 5 | `authentication-bypass.duplicate-phone-identity` | L | `portal_auth.py:151` | Add a `UNIQUE` constraint (Alembic migration) on `Member.phone` (nullable allowed, duplicates rejected); on duplicate, fail registration, don't ambiguous-auth. |
| 6 | `resource-exhaustion.proxy-rate-key` | L | `auth.py:26` | **S10** — real client IP key. |
| 7 | `resource-exhaustion.member-login-throttle` | L | `portal_auth.py:151` | Apply the 60s cooldown to **login** too (currently only resend); per-phone + per-IP throttle. |
| 8 | `resource-exhaustion.forgot-email-abuse` | L | `password_reset.py:32` | Throttle forgot-password per-IP (e.g. 3/hour); don't send if SMTP would flood. |
| 9 | `resource-exhaustion.report-spam-resource` | L | `reports_email.py:285` | Throttle manual report per-user (e.g. 2/hour). |

**Acceptance:** password change/reset invalidates existing sessions immediately; no user/phone enumeration via response or timing; all public endpoints throttled by real client IP.

---

## Workstream 10 — Input / transport hardening (P2)

### 10a. SMTP TLS — `backend/core/email.py:51/56` (`certificate-validation.smtp_ssl/smtp_starttls`, M×2)
`SMTP_SSL`/`starttls` use no `SSLContext` → MITM. **Fix:** build a verified `ssl.create_default_context()` with hostname validation; pass to `SMTP_SSL(..., context=ctx)` and `server.starttls(context=ctx)`. Allow insecure only behind an explicit `SMTP_INSECURE=1` non-prod flag. **Test:** self-signed cert → connection rejected.

### 10b. Backup transport hardening — `backend/api/system.py:208` + `scripts/remote_push.sh`
| # | Rule | Sev | Fix |
|---|------|-----|-----|
| 1 | `cleartext-transport.ftp-cleartext` | M | FTP sends DB dump + creds in cleartext. Deprecate FTP; prefer SFTP/rsync/SMB. If kept, warn loudly + document risk. |
| 2 | `command-injection.command-injection-sftp-path` | M | SFTP path injected into batch file. **Sanitize/quote** the path; build the batch from an allowlisted charset; never interpolate raw user path into shell. |
| 3 | `command-injection.argument-injection-sftp-user` | M | Crafted username parsed as OpenSSH option (e.g. `-o ProxyCommand=...`). **Validate** username against `^[A-Za-z0-9._-]{1,64}$`; reject anything else before passing to ssh/sftp. |
| 4 | `ssrf-sftp/rsync/smb/ftp` (backup probes) | L×4 | **S8** on probe host: block private/loopback destinations; restrict to configured transports only. |
- Keep the load-bearing **sftp argv order** (`sshpass -e sftp -P "$port" -b "$batch" "$user@$host"`, destination LAST) pinned by `TestSftpArgvOrder` (`test_remote_backup_isolation.py`). Touching transport argv → assert the ORDER.

### 10c. CSV formula injection — `import_export.py:145`, `sales.py:286` (`spreadsheet-formula-injection.csv-formula`, L×2)
**S7.** Apply `sanitize_csv_cell` to every exported column; prefix `=+-@\t\r`-leading cells with `'`. **Test:** export a member named `=CMD|...` → cell neutralized.

### 10d. Stored XSS in admin email — `backend/api/reports_email.py:240` (`cross-site-scripting.stored-html`, L×2)
Member identity strings are inserted into HTML email unescaped. **Fix:** HTML-escape (`html.escape`) every stored value before interpolation, or render email via a templating engine with autoescaping. **Test:** member name `<script>` → escaped in generated HTML.

### 10e. Exception disclosure — `enrollment.py:393/518/610`, `sync.py:333` (from candidate ledger)
Raw exceptions returned in `HTTPException(detail=str(e))`. **Fix:** log full exception server-side; return generic `"Internal error"` (or a sanitized message) to the client. SECURITY.md §11 forbids returning DB/internal errors.

**Acceptance:** SMTP cert validated; no shell/argument injection via backup fields; CSV/XSS neutralized; no internal exception text reaches clients.

---

## Verification matrix (prove every WS closed)

For each workstream, the implementing agent must produce evidence:

1. **Unit/integration tests** added and green (`pytest tests/` backend + cv_service, `npm run test` frontend if UI touched). Current baselines: backend 144, cv_service 12, frontend 49 — must not regress.
2. **Negative authz test matrix:** for every route changed in WS-3, assert 403 for staff-without-page and 401 for unauthenticated.
3. **Static gates:** `flake8 . && black --check . && mypy .` (backend) green; `npm run lint && npm run type-check` (frontend) green.
4. **Migration correctness:** any Alembic migration (S6 token_version, WS-9 phone unique) runs up/down cleanly.
5. **Re-scan:** after all WS merged, run a **full-repo** unbounded Codex Security scan and confirm the previously reported `ruleId`s no longer appear:
    ```bash
    cd ~/codex-security && npx @openai/codex-security scan /root/faceapp --output-dir reports/faceapp-rescan
    npx @openai/codex-security scans compare <OLD_SCAN_ID> <NEW_SCAN_ID>
    ```
   Target: the 108 finding fingerprints show `resolved`; no new `critical`/`high` introduced.

---

## Appendix A — Finding → Workstream index (all 108)

Format: `[SEV] ruleId (CWE) — primary location → WS`. Locations are `file:startLine` from `findings.json`.

### Critical (3)
- `[C] weak-cryptography.jwt_signing_secret (321/798) — docker-compose.yml:30` → WS-1
- `[C] weak-password-policy.default_admin_password (521/798) — backend/api/auth.py:26` → WS-1
- `[C] missing-authentication.missing-auth (306) — backend/api/cv_internal.py:52 (template-sync)` → WS-2

### High (13)
- `[H] sensitive-data-exposure.rtsp_failure_url_health_exposure (200) — cv_service/main.py:766` → WS-6
- `[H] cleartext-sensitive-data.camera-insert-authz-encryption (312/863) — backend/api/sync.py:153` → WS-6
- `[H] cleartext-sensitive-data.camera-update-authz-encryption (312/863) — backend/api/sync.py:230` → WS-6
- `[H] incorrect-authorization.page-authz (863) — memberships.py:96/161/216, sync.py:105, sales.py, import_export.py, membership_plans.py, reports_email.py (×21)` → WS-3
- `[H] sensitive-data-exposure.missing-auth (200/306) — cv_service/main.py:465/665 (×2)` → WS-2/WS-6
- `[H] sensitive-data-exposure.sensitive-pull (200/862) — backend/api/sync.py:105` → WS-3/WS-8
- `[H] client-side-enforcement.payment-proof (602/840) — backend/api/portal.py:104` → WS-4
- `[H] stale-resource.member-delete-audit-invalidation (672/778) — backend/api/sync.py:301` → WS-8
- `[H] missing-authentication.missing-auth (306) — cv_internal.py:219 (enabled cameras), cv_service/main.py:755 (/invalidate)` → WS-2

### Medium (56)
- `[M] weak-cryptography.biometric_rtsp_encryption_key (321) — docker-compose.yml:29` → WS-1
- `[M] missing-authentication.missing-auth (306) — cv_service/main.py:446/457/748, backend_client.py ×5, events.py:128` → WS-2
- `[M] client-side-enforcement.business-price (602/840) — memberships.py:96/161 (×2)` → WS-4
- `[M] incorrect-authorization.page-authz (863) — plans/dashboard/sales-read (×6)` → WS-3
- `[M] missing-authorization.biometric-consent (862) — enrollment.py:311/521 (×2)` → WS-5
- `[M] privilege-management.default-staff-all-pages (269) — users.py:42` → WS-3
- `[M] resource-exhaustion.resource-exhaustion (400) — cv_internal.py:52, cv_service/main.py:446/665 (×3)` → WS-2/WS-6
- `[M] incorrect-authorization.incorrect-location-authz (863) — cv_service/validation/access_validator.py:19` → WS-7
- `[M] incorrect-authorization.wrong-timezone-{date,day,window}-authz (863) — access_validator.py:85, schemas/membership.py:13 (×3)` → WS-7
- `[M] biometric-liveness-bypass.liveness_cross_stream_state_reuse — cv_service/stream/rtsp_processor.py:38` → WS-7
- `[M] security-control-bypass.liveness_{baseline,ear_failure,insufficient_eyes,open_eyes}_fail_open (693) — rtsp_processor.py:264 (×4)` → WS-7
- `[M] server-side-request-forgery.ssrf{,-http,-rtsp,_direct_start_private_ip_filter} (918) — cv_service/main.py:446 (×3)` → WS-6
- `[M] certificate-validation.smtp_{ssl,starttls} (295) — backend/core/email.py:51/56 (×2)` → WS-10
- `[M] cleartext-sensitive-data.plaintext_biometric_redis_cache (312) — cv_service/main.py:184` → WS-5
- `[M] cleartext-transport.cleartext-biometric-transport (319) — cv_service/api/backend_client.py:17` → WS-5
- `[M] cleartext-transport.ftp-cleartext (319) — backend/api/system.py:208` → WS-10
- `[M] command-injection.command-injection-sftp-path (78) — backend/api/system.py:208` → WS-10
- `[M] command-injection.argument-injection-sftp-user (88) — backend/api/system.py:208` → WS-10
- `[M] business-logic.sales-{delete,update}-integrity (840/862) — sync.py:39/230 (×2)` → WS-8
- `[M] input-validation.sales-insert-validation (20/840) — sync.py:39` → WS-8
- `[M] incorrect-authorization.camera-delete-authz / membership-delete-authz (863) — sync.py:301 (×2)` → WS-8
- `[M] session-revocation.admin-password-change-session-persistence (613) — users.py:188` → WS-9
- `[M] session-revocation.reset-session-persistence (613) — password_reset.py:135` → WS-9

### Low (36)
- `[L] audit-integrity.audit-persistence (778) — members.py:163/336/395, import_export.py:69 (×4)` → WS-8
- `[L] audit-integrity.biometric-audit (778) — enrollment.py:311/396/521 (×3)` → WS-5/WS-8
- `[L] audit-integrity.login (778) — backend/core/audit.py:38` → WS-8
- `[L] authentication-bypass.duplicate-phone-identity (287) — portal_auth.py:151` → WS-9
- `[L] cross-site-scripting.stored-html (79) — reports_email.py:240 (×2)` → WS-10
- `[L] hardcoded-credential.pending_payment_lookup (798) — portal.py:416` → WS-1
- `[L] missing-authentication.missing-kiosk-auth (306) — enrollment_requests.py:175/201 (×2)` → WS-3 (add kiosk device auth dependency)
- `[L] observable-discrepancy.{member-login,member-resend}-enumeration (204) — portal_auth.py:151/237 (×2)` → WS-9
- `[L] observable-discrepancy.username-timing (208) — auth.py:26` → WS-9
- `[L] race-condition.template_revocation_reload_race (367) — enrollment.py:396` → WS-5
- `[L] resource-exhaustion.{forgot-email-abuse,member-login-throttle,proxy-rate-key,report-spam-resource} (400/799) — password_reset.py:32, portal_auth.py:151, auth.py:26, reports_email.py:285 (×4)` → WS-9
- `[L] server-side-request-forgery.{camera-test-ssrf,http-ssrf,media-url-injection} (918) — cameras.py:57/191/290 (×5)` → WS-6
- `[L] server-side-request-forgery.ssrf-{ftp,rsync,sftp,smb} (918) — system.py:208 (×4)` → WS-10
- `[L] spreadsheet-formula-injection.csv-formula (1236) — import_export.py:145, sales.py:286 (×2)` → WS-10

> **Note on WS-3 kiosk auth (`missing-kiosk-auth`):** `enrollment_requests.py:175/201` start/complete ops have only a data-existence check, no device auth. Add a kiosk-device authentication dependency (device token / mTLS / shared kiosk secret distinct from `INTERNAL_API_SECRET`) and gate both ops. Negative test: unauthenticated device → 401.

---

## Appendix B — Suggested branch / PR slicing

To stay under the ~400-line review budget and keep CI gating (PRs to `main`):

1. `fix/security-shared-controls` — WS-S (S1–S10). Largest, highest-leverage; review carefully.
2. `fix/security-startup-secrets` — WS-1 (depends on S3/S4).
3. `fix/security-internal-auth-failclosed` — WS-2 (depends on S1/S2).
4. `fix/security-rbac-page-perms` — WS-3 (depends on S5).
5. `fix/security-payments` — WS-4.
6. `fix/security-biometric` — WS-5.
7. `fix/security-cameras-rtsp` — WS-6 (depends on S8).
8. `fix/security-cv-liveness-tz` — WS-7.
9. `fix/security-sync-audit` — WS-8 (depends on S5/S9).
10. `fix/security-authn-hardening` — WS-9 (depends on S6/S10; includes migrations).
11. `fix/security-input-transport` — WS-10.

Each PR: conventional commits, targets `main`, passes the 3-job CI (`backend` flake8/black/mypy/pytest, `frontend` lint/type-check/vitest, `cv_service` pytest). After all merge: full-repo re-scan + `scans compare`.

---

*Plan generated from Codex Security scan of revision `e43f2436` (`~/codex-security/reports/faceapp/findings.json`). Cross-reference every fix against `SECURITY.md` (the security contract) and `AGENTS.md` §"Critical traps" before merging.*
