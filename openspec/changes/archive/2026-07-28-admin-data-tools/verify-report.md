```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:3ed5247d82cb3e53702146dfede0a71805d9d7417ea5ea8f0e77fd93a5e5409a
verdict: pass-with-warnings
blockers: 0
critical_findings: 0
requirements: 12/12
scenarios: 18/18
test_command: "backend: cd backend && set -a && . ./.env && set +a && /root/faceapp/.venv/bin/python -m pytest tests/ -q  |  frontend: cd frontend && npm run test"
test_exit_code: 0
test_output_hash: sha256:edecb736028ae1ce3b003d695cc92c8a85d4a9e130bc32ae23298fee3b007389 (backend, 98 passed) + sha256:7fdea16aefa84c550f5bb2027ef8b0ff544f89733c52141d36d1b63e667b0b8f (frontend, 42 passed)
build_command: "cd frontend && npm run type-check  |  cd backend && flake8 .  |  cd backend && mypy ."
build_exit_code: 0
build_output_hash: sha256:df222effe2e49e734fc4f89580b73fa35a8b358e8e942e40e3ff2b1e5ba67aa0 (tsc) + sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 (flake8, empty) + sha256:164f61786e9457a079d508a59fe50bfc066a3dd4065912f345854cf8907be5ab (mypy)
```

## Verification Report

**Change**: admin-data-tools
**Version**: N/A (delta specs, no versioned capability)
**Mode**: Strict TDD (active per `openspec/config.yaml` `strict_tdd: true`)
**Branch verified**: `feat/admin-data-tools-slice-c` @ `a6cc21c` (chain tip; cumulative A→B→C)
**Verifier**: independent (sdd-verify executor; did NOT author the code)

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 17 (A.1–A.9, B.1–B.2, C.1–C.6) |
| Tasks complete | 17 |
| Tasks incomplete | 0 |

All 17 task checkboxes are `[x]` in `tasks.md`. Slice bookkeeping commit `9047cdc` is present on slice-a.

### Build & Tests Execution

**Build / type-check / quality**: tsc ✅ · flake8 `.` ✅ (exit 0, empty) · mypy ✅ — **black `--check .` ❌** (see WARNING W-1)

**Tests**: ✅ 98 passed (backend, 0 failed) / ✅ 42 passed (frontend, 0 failed)
```text
backend: 98 passed, 81 warnings in 4.19s   (hash edecb736…, exit 0)
frontend: Test Files 11 passed (11) | Tests 42 passed (42)   (hash 7fdea16…, exit 0)
focused backend (tz+window+csv+db_export+remote_backup): 35 passed
focused frontend (SalesList+Accordion+ReportsExport+ReportsWiring+SettingsExportDb+reportRange+dateTime): 28 passed
```

**Coverage**: ➖ Not available (project `coverage.configured: false`).

### Spec Compliance Matrix

| # | Requirement | Spec | Scenario(s) | Covering test | Result |
|---|-------------|------|-------------|---------------|--------|
| 1 | Timezone Cache Consistency | sales-reporting ADDED | Timezone changes during an active session | `test_timezone_service.py::TestGetAppTzCache::test_invalidate_forces_reread_of_new_zone`, `test_cache_hit_skips_db_read` | ✅ COMPLIANT |
| 2 | Server-Side CSV Report Export | sales-reporting ADDED | Custom-range CSV matches the screen | `test_sales_csv_export.py` (7 cases: matches-summary, reversed→422, partial→422, preset days, filename) | ✅ COMPLIANT |
| 3 | Configured-Timezone Reporting & Sales Timestamps | sales-reporting MODIFIED | Report crosses an America/Santiago DST boundary | `test_report_window.py::TestBuildReportWindowDSTAware` (2 cases) + `test_timezone_service::test_dst_correct_conversion_for_santiago` + `SalesList.test.tsx` | ✅ COMPLIANT |
| 4 | Deployed Custom Date Range Flow | sales-reporting MODIFIED | Valid custom range returns results; Reversed custom dates remain rejected | `reportRange.test.ts` (12 cases) + `ReportsWiring.test.tsx` + `docs/deployed-build-diagnosis.md` (4-step protocol) | ✅ COMPLIANT |
| 5 | Membership History Visibility Threshold | membership-history ADDED | exactly two / exactly three / fifty | `MembershipAccordion.test.tsx` (5 cases: 2→none, 3→2+1, 50→2+48) | ✅ COMPLIANT |
| 6 | Actionable and Localized Older Memberships | membership-history ADDED | admin acts; non-admin views | `MembershipAccordion.test.tsx` (admin edit/delete inside accordion; non-admin hides) + i18n es/en | ✅ COMPLIANT |
| 7 | Fresh Custom-Format Database Download | admin-database-export ADDED | Administrator downloads a fresh dump | `test_db_export.py::TestDbExportFlow` + `test_real_pg_dump_produces_genuine_custom_format` (body[:5]==PGDMP) | ✅ COMPLIANT |
| 8 | Export Authorization | admin-database-export ADDED | Unauthenticated 401; non-admin 403 | `TestDbExportAuthorization::test_unauthenticated_returns_401`, `test_non_admin_returns_403` | ✅ COMPLIANT |
| 9 | Export Audit Record | admin-database-export ADDED | Successful export is audited | `TestDbExportFlow::test_successful_export_is_audited` (before/after count, action='db_export') | ✅ COMPLIANT |
| 10 | Scheduled Remote Replication | remote-backup ADDED | Scheduled replication succeeds | systemd `powerhouse-backup.timer` OnCalendar=*:0/30 + remote_push.sh smb/nfs/rsync + install.sh enable | ✅ COMPLIANT |
| 11 | Local Backup and Retention Preservation | remote-backup ADDED | Remote unreachable; retention runs | `test_remote_backup_isolation.py` (local .dump+.tar.gz+checksums survive, exit 0, remote warned) + backup.sh retention step | ✅ COMPLIANT |
| 12 | Environment-Only Remote Credentials | remote-backup ADDED | Remote credentials are configured | `test_remote_backup_isolation` (no SMB_PASS/PGPASSWORD token in log) + .env.example docs + grep: no literal secret/eval | ✅ COMPLIANT |

**Compliance summary**: 18/18 scenarios compliant.

### Correctness (Static Evidence)

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| 1 | TZ cache | ✅ Implemented | `get_app_tz` Redis-first (key `app:tz`, TTL 300); `invalidate_app_tz_cache` called on BOTH write paths (`settings.py:182` key=='timezone', `:142` bulk). |
| 2 | CSV export | ✅ Implemented | `GET /sales/report/export` `require_staff`, reuses `_resolve_report_window`, StreamingResponse text/csv + BOM `\ufeff` + Content-Disposition. |
| 3 | Configured-TZ reporting | ✅ Implemented | `build_report_window(tz=ZoneInfo)`; `_resolve_report_window`→`get_app_tz(db)`; `DashboardService.__init__ self.tz=get_app_tz(db)`; events.py 3 callers pass `db`. No remaining hardcoded `timedelta(hours=-5)` in production logic (only documented legacy-default constants; callers pass configured zone). |
| 4 | Custom-range flow | ✅ Implemented | `buildReportRange` validates reversed/incomplete; Reports.tsx pickers gated by `customReady`; diagnosis doc has the ordered 4-step protocol. |
| 5 | Accordion threshold | ✅ Implemented | `visibleMemberships=slice(0,2)`, `olderMemberships=slice(2,50)`, query capped `getMemberships(0,50,memberId)`, sorted by `end_date` desc. |
| 6 | Actionable+localized | ✅ Implemented | Shared `renderMembershipRow` (identical edit/renew/delete + `isAdmin` gate); i18n `olderMemberships`/`hideOlderMemberships` in BOTH es+en. |
| 7 | DB download | ✅ Implemented | `system.py` Popen argv list, `-F c`, StreamingResponse octet-stream, filename `powerhouse_db_<ts>.dump`. |
| 8 | Export auth | ✅ Implemented | `Depends(require_admin)` runs before Popen (401/403 enforced server-side, not UI-only). |
| 9 | Audit | ✅ Implemented | `log_action("db_export")` + commit in generator `finally`, guarded by `returncode == 0`. |
| 10 | Scheduled replication | ✅ Implemented | `OnCalendar=*:0/30`, `Persistent=true`, `Type=oneshot`; `install.sh` daemon-reload + `enable --now`. |
| 11 | Local retention | ✅ Implemented | remote push invoked as `if ! bash remote_push.sh; then WARN`; retention `find -mtime +RETENTION -delete` runs unconditionally afterwards. |
| 12 | Env-only creds | ✅ Implemented | `.env` sourced; no literal secret in any script; no `eval`; `.env.example` documents all keys; nothing written to settings table. |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| TZ service in `services/timezone.py` (Redis key `app:tz`, TTL 300) | ✅ Yes | Exactly as designed. |
| ZoneInfo everywhere (DST-correct) | ✅ Yes | `utc_to_local`, `build_report_window(tz)` both ZoneInfo. |
| `build_report_window` signature UNCHANGED | ✅ Yes | `tz` defaults to legacy `APP_TZ`; contract + pure tests preserved. |
| CSV `GET /sales/report/export` reuses `_resolve_report_window` | ✅ Yes | Same half-open window as `/report/summary`. |
| Blob+anchor download (Authorization header constraint) | ✅ Yes | axios `responseType:'blob'` + object URL. |
| DB export `subprocess.Popen` argv list, PGPASSWORD env-only | ✅ Yes | No shell=True; no secret in argv. |
| Remote failure warn-and-continue | ✅ Yes | `set -uo pipefail` (no `set -e` in remote_push); `if !` in backup.sh. |
| systemd timer (not APScheduler) | ✅ Yes | Ops-only, survives app restarts. |
| Single `<Accordion>` wrapping slice(2) | ✅ Yes | One expander, `olderExpanded` default false. |
| **Deviation 1**: audit-in-generator-finally | ✅ Matches spec | Spec says "for every successful download"; audit fires only on `returncode==0` after full stream. Consistent. |
| **Deviation 2**: per-transport env keys | ✅ Matches spec | Spec says creds "sourced from `.env`"; per-transport vars (RSYNC_*/SMB_*/NFS_MOUNT) are env-only. Consistent. |

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | Found in apply-progress memory #72 (TDD Cycle Evidence table per slice). |
| All tasks have tests | ✅ | 17/17 tasks have covering test files. |
| RED confirmed (tests exist) | ✅ | All listed test files exist on disk (backend 5 new/extended, frontend 5 new/extended). |
| GREEN confirmed (tests pass) | ✅ | Re-ran independently: 98 backend + 42 frontend, all green. |
| Triangulation adequate | ✅ | DST (winter≠summer offset), real-vs-mock pg_dump, admin/non-admin, 2/3/50 memberships, reachable/unreachable remote. |
| Safety Net for modified files | ✅ | New files N/A; modified files had 40/40 frontend + 87 backend baselines recorded. |

**TDD Compliance**: 6/6 checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit (backend) | ~12 | test_timezone_service.py, test_report_window.py | pytest |
| Integration (backend) | ~23 | test_sales_csv_export.py, test_db_export.py, test_remote_backup_isolation.py | pytest + FastAPI TestClient + live PG/Redis |
| Unit (frontend) | ~28 | SalesList, MembershipAccordion, ReportsExport, ReportsWiring, SettingsExportDb, reportRange, dateTime | vitest + RTL/jsdom |
| E2E | 0 | — | not configured |
| **Total run** | **140** (98+42) | 16 files | |

### Assertion Quality

All new/extended test files scanned against tautology / ghost-loop / smoke-only / mock-heavy patterns.

**Assertion quality**: ✅ All assertions verify real behavior.
- `test_db_export.py`: argv-list safety, password-absent-from-argv, PGDMP magic, audit before/after count — behavioral, no tautologies.
- `test_timezone_service.py`: cache-hit-skips-DB (deletes row then asserts cached value still served — genuine cache proof), invalidate→reread, DST offsets differ — high quality.
- Frontend tests assert rendered date+time text, accordion presence/absence by membership count, blob-download invocation — behavioral.

No `expect(true).toBe(true)`, no ghost loops over possibly-empty collections, no render-only smoke tests.

### Changed File Coverage

| File | Rating | Note |
|------|--------|------|
| `backend/services/timezone.py` (new) | ✅ | fully covered by test_timezone_service.py |
| `backend/api/system.py` (new) | ✅ | fully covered by test_db_export.py (9 cases) |
| `backend/api/sales.py` (export added) | ✅ | covered by test_sales_csv_export.py |
| `scripts/remote_push.sh` / `backup.sh` | ✅ | covered by test_remote_backup_isolation.py (subprocess-driven) |
| frontend pages | ✅ | covered by the 5 frontend suites |

Coverage tool not configured (per capabilities) — ratings are qualitative from test-to-code mapping.

### Quality Metrics
**Linter (flake8 `.`)**: ✅ No errors (exit 0, empty; project `.flake8` max-line 88, E501 disabled).
**Type Checker (mypy)**: ✅ No errors (exit 0).
**Formatter (black `--check .`)**: ❌ 2 files would be reformatted — **WARNING W-1**.

### Issues Found

**CRITICAL**: None.

**WARNING**:
- **W-1 — black formatter regression (blocks CI green).** `black --check .` fails on `backend/api/sales.py` and `backend/api/settings.py`. Verified this change **introduced** it: main `6fcab85` is 93/93 black-clean (checked via isolated worktree); slice-c tips 2 dirty. The offending lines are in the CSV-export `_row` helper (multi-line ternary black collapses to one line). The apply agent's "black/flake8/mypy clean" claim was scoped to *new* files (system.py, timezone.py) and is false for these two *modified* files. **CI backend job `black --check .` will fail on push.** Fix: `black backend/api/sales.py backend/api/settings.py` (one command, ~2-line diff). Severity WARNING (quality/style gate; all behavior + tests + type-check correct), but it must be fixed before merge.
- **W-2 — SMB password visibility in process list.** `remote_push.sh` `push_smb` passes the password via `smbclient -U "${user}%${pass}"`, which is visible to other users via `ps`. This is inherent to smbclient's `-U` syntax; the design already states "rsync preferred; SMB as fallback". No secret reaches the log (output redirected, log-grep test passes). Recommend documenting the rsync-first guidance in `.env.example` (already present). Non-blocking.
- **W-3 — pre-existing i18n debt in a touched file.** `Reports.tsx` contains hardcoded Spanish fragments in the (pre-existing) metrics labels (`"acumulado"`, `"activas / total"`). Not introduced by this change (the export button itself uses `t.reports.exportReport` correctly), but surfaces in a file this change modified. Out of change scope; noted for hygiene.

**SUGGESTION**:
- **S-1 — legacy `COLOMBIA_TZ` constants retained** in `events.py`, `dashboard_service.py`, `report_window.py` as documented backward-compat fallbacks. Design explicitly keeps them; all production callers now pass `db`→`get_app_tz`. Could be removed later, non-blocking.
- **S-2 — backup.sh config-tar** still references `powerhouse-backend.service` (prod path) with `|| true`; pre-existing naming inconsistency with the new `powerhouse-backup.*` units, out of scope (noted by apply agent).

### Size
Slice C = **1023 insertions / 37 deletions (~1060 changed)** vs slice-b — above the 800-line per-slice ceiling. User-accepted **size:exception** (documented). Driven by threat-matrix test suite + backup.sh rewrite. Cumulative chain = 3206 ins / 200 del across 47 files.

### Verdict
**PASS WITH WARNINGS** — All 12 requirements and 18 scenarios are met; all tests pass (98 backend + 42 frontend); type-check/flake8/mypy clean; threat matrix covered; both documented deviations match spec text. One WARNING (W-1) is a black-formatting regression that will fail the CI `black --check .` step and must be fixed before merge (one-command fix, no behavior change). No critical findings.
