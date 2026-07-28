# Tasks: Admin Data Tools

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | A ≈ 780 · B ≈ 176 · C ≈ 632 · total ≈ 1588 |
| 400-line budget risk | High (per-slice ceiling; under 800-line review budget) |
| Chained PRs recommended | Yes (pre-sliced A/B/C) |
| Suggested split | PR-A → PR-B, PR-C (B and C independent of each other; both land after A) |
| Delivery strategy | auto-chain |
| Chain strategy | pending (orchestrator asks user; tasks are strategy-agnostic) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

> Threshold this run honors: **800 changed lines / PR** (orchestrator override). Slice A sits near the ceiling; if it overruns during apply, split A.9 (#4 diagnosis doc + guard test, zero production code) into its own PR — it is the cleanest break point.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| A | TZ service + CSV export + #4 diagnosis | PR-A | `cd backend && pytest tests/test_timezone_service.py tests/test_report_window.py tests/test_sales_csv_export.py` ; `cd frontend && npm run test -- SalesList ReportsExport reportRange` | `docker-compose up -d db redis` then pytest; `cd frontend && npm run dev` | `backend/services/timezone.py`, `sales.py /report/export`, frontend SalesList/Reports — revert keeps UTC storage & local backups intact |
| B | Membership accordion | PR-B | `cd frontend && npm run test -- MembershipAccordion` | `cd frontend && npm run dev` → open a member with ≥3 memberships | `frontend/src/pages/Members/MemberForm.tsx` accordion partition + 3 i18n keys |
| C | DB export + remote backup/systemd | PR-C | `cd backend && pytest tests/test_db_export.py tests/test_remote_backup_isolation.py` | `sudo systemctl start powerhouse-backup.service` (manual; shell/systemd has no unit runner) | `backend/api/system.py` + router reg, `scripts/remote_push.sh`, `scripts/systemd/powerhouse-backup.{service,timer}`, Settings System-tab button |

**TDD contract**: every code task is RED (failing test first) → GREEN → REFACTOR. Backend needs live Postgres+Redis (`docker-compose up -d db redis`). Slice C #2 (shell/systemd) has no unit-test runner → manual verification steps only, called out explicitly.

---

## Slice A: Timezone + CSV Export + Custom-Range Diagnosis (PR-A)

- [x] **A.1 RED — timezone service**: add `backend/tests/test_timezone_service.py`: assert `get_app_tz(db)` returns `America/Bogota` default; reads `timezone` setting; Redis cache hit skips DB; `invalidate_app_tz_cache()` → next call returns new zone. Run: `cd backend && pytest tests/test_timezone_service.py` → **fail (module missing)**. Deps: none.
- [x] **A.2 GREEN+REFACTOR — timezone service**: create `backend/services/timezone.py` (`DEFAULT_TZ`, `CACHE_KEY="app:tz"`, `TTL=300`, `get_app_tz(db)`, `invalidate_app_tz_cache()`, `utc_to_local()`); expose redis helper in `backend/core/database.py` if missing. Modify `backend/api/settings.py`: `update_setting` + `bulk_update_settings` call `invalidate_app_tz_cache()` when key==`timezone`. Verify: `pytest tests/test_timezone_service.py` → green. Deps: A.1.
- [x] **A.3 RED — DST window**: extend `backend/tests/test_report_window.py`: `build_report_window(date(2026,9,6),date(2026,9,9), tz=ZoneInfo("America/Santiago"))` — each local midnight uses its date's offset; half-open preserved. Run → **fail (fixed offset)**. Deps: none.
- [x] **A.4 GREEN — thread tz**: modify `backend/services/dashboard_service.py` (`__init__` stores `self.tz=get_app_tz(db)`, replace `COLOMBIA_TZ`); `backend/api/events.py` (`colombia_today*` accept db/tz, callers pass `get_app_tz(db)`); `backend/api/sales.py` (`_resolve_report_window` accepts db, passes `tz=get_app_tz(db)`); docstring note in `report_window.py` (signature unchanged). Verify: full `pytest tests/`. Deps: A.2, A.3.
- [x] **A.5 RED — CSV export**: add `backend/tests/test_sales_csv_export.py`: custom-range CSV header+rows match `/report/summary` count; reversed→422; preset `days` works; filename `^sales_report_.+\.csv$`. Run → **fail (no route)**. Deps: A.4.
- [x] **A.6 GREEN — CSV route**: add `GET /sales/report/export` to `backend/api/sales.py` (`require_staff`, reuse `_resolve_report_window`, `StreamingResponse` `text/csv` with BOM `\ufeff` + `Content-Disposition`). Verify: `pytest tests/test_sales_csv_export.py` → green. Deps: A.5.
- [x] **A.7 RED — SalesList date+time**: add `frontend/src/test/SalesList.test.tsx`: renders date+time in mocked `America/Santiago` `timezone` (not bare `toLocaleDateString()`). Run: `cd frontend && npm run test -- SalesList` → **fail**. Deps: none.
- [x] **A.8 GREEN — frontend display + export wiring**: modify `frontend/src/pages/Sales/SalesList.tsx` (`Intl.DateTimeFormat({timeZone})` date+time); `frontend/src/api/sales.ts` (`exportReport(params)` → blob, axios `responseType:'blob'`); `frontend/src/pages/Reports/Reports.tsx` (Export button onClick → anchor+object-URL download with current `reportRange`; consume `timezone` from public-settings); i18n keys in `frontend/src/i18n/translations.ts`. Verify: `npm run test -- SalesList ReportsExport`. Deps: A.6, A.7.
- [x] **A.9 RED+GREEN — #4 diagnosis + guard**: extend `frontend/src/test/reportRange.test.ts` with custom-range regression contract (valid→results, reversed→rejected). Create `docs/deployed-build-diagnosis.md` (4-step procedure: diff dist mtime; grep minified for `customRange`/`buildReportRange`; confirm 2 date inputs at `custom`; rebuild on LXC if drift). Verify: `npm run test -- reportRange`. Deps: none.

**Commit plan (PR-A work units)**: (1) `feat(sales): cached DST-aware timezone service with invalidation` — A.1+A.2; (2) `feat(sales): thread configured timezone through report/dashboard/events` — A.3+A.4; (3) `feat(sales): server-side CSV report export` — A.5+A.6; (4) `feat(sales): show local date+time and wire export download` — A.7+A.8+i18n; (5) `docs(sales): custom-range deployment diagnosis and regression guard` — A.9.
**Rollback**: revert `backend/services/timezone.py`, `sales.py /report/export`, `settings.py` invalidation calls, `SalesList.tsx`/`Reports.tsx` display. UTC storage and local backups untouched.
**Acceptance**: `Timezone Cache Consistency` (A.1/A.2); `Configured-Timezone Reporting…` + DST scenario (A.3/A.4); `Server-Side CSV Report Export` + custom-range-matches-screen (A.5/A.6); `Deployed Custom Date Range Flow` + reversed-rejected (A.9).

---

## Slice B: Membership Accordion (PR-B)

- [x] **B.1 RED — accordion behavior**: add `frontend/src/test/MembershipAccordion.test.tsx`: 2 memberships → no accordion; 3 → 2 visible + accordion with 1; 50 → 2 visible + accordion with 48; admin edit/delete/renew buttons render inside accordion; non-admin hides admin actions. Run: `npm run test -- MembershipAccordion` → **fail**. Deps: none.
- [x] **B.2 GREEN+REFACTOR — partition + i18n**: modify `frontend/src/pages/Members/MemberForm.tsx` (sort by most-recent end date; `slice(0,2)` visible; `slice(2,50)` in single MUI `<Accordion>` collapsed by default; preserve edit/renew/delete + auth rules). Add i18n keys `members.olderMemberships` (with `{count}`), `members.hideOlderMemberships` (es+en) in `frontend/src/i18n/translations.ts`. Verify: `npm run test -- MembershipAccordion` → green; manual: open member with ≥3 memberships. Deps: B.1.

**Commit plan (PR-B)**: `feat(members): collapse older membership history into accordion` — B.1+B.2 (test+code+i18n together).
**Rollback**: revert `MemberForm.tsx` partition + 3 i18n keys; flat list returns.
**Acceptance**: `Membership History Visibility Threshold` (2/3/50 scenarios); `Actionable and Localized Older Memberships` (admin actions preserved, non-admin gated, bilingual labels).

---

## Slice C: DB Export + Remote Backup (PR-C)

- [x] **C.1 RED — db export + threat tests**: add `backend/tests/test_db_export.py`: 401 unauth, 403 non-admin, admin→200 `application/octet-stream` + body starts `PGDMP`, audit row `action='db_export'` exists; `Content-Disposition` matches `^powerhouse_db_\d+\.dump$`; argv has no shell metachar. Run: `pytest tests/test_db_export.py` → **fail (no route)**. Deps: none.
- [x] **C.2 GREEN — system router**: create `backend/api/system.py` (`GET /system/db-export`, `Depends(require_admin)`, parse `DATABASE_URL` → `subprocess.Popen(["pg_dump",...,"-F","c"], stdout=PIPE)` with `PGPASSWORD` env, `StreamingResponse`, `log_action("db_export")`+commit). Register in `backend/api/__init__.py` and `backend/main.py` (`include_router`). Verify: `pytest tests/test_db_export.py` → green. Deps: C.1.
- [x] **C.3 RED — remote backup isolation (mock)**: add `backend/tests/test_remote_backup_isolation.py`: run `scripts/backup.sh` in tmp with mocked `pg_dump` + unreachable `BACKUP_REMOTE_TYPE=rsync` → local `.dump`+`.tar.gz` present, checksums present, retention ran, exit 0, remote warned to log; log-grep asserts no `SMB_PASS`/`PGPASSWORD` token. Run: `pytest tests/test_remote_backup_isolation.py` → **fail (no remote step / no remote_push.sh)**. Deps: none.
- [x] **C.4 GREEN — remote push + systemd + install + env (NO unit runner → manual verify)**: create `scripts/remote_push.sh` (`BACKUP_REMOTE_TYPE=none|smb|nfs|rsync`, env-selected, creds only via env, quoted, warn-on-fail never `eval`); modify `scripts/backup.sh` (source `.env`, call `remote_push.sh` warn-only, local retention always); create `scripts/systemd/powerhouse-backup.service` (`Type=oneshot`) + `powerhouse-backup.timer` (`OnCalendar=*:0/30`, `Persistent=true`); modify `install.sh` (write units, `daemon-reload`, `enable --now`); modify `.env.example` (document `BACKUP_REMOTE_TYPE/TARGET`, `SMB_USER/PASS`, `RSYNC_*`). Verify: `pytest tests/test_remote_backup_isolation.py` → green; **manual**: `sudo systemctl start powerhouse-backup.service && journalctl -u powerhouse-backup.service` shows local+retention OK, remote warn if unreachable. Deps: C.3.
- [ ] **C.5 RED — Settings export button**: add `frontend/src/test/SettingsExportDb.test.tsx`: admin-only Export DB button calls `settingsApi.exportDatabase()`. Run: `npm run test -- SettingsExportDb` → **fail**. Deps: none.
- [ ] **C.6 GREEN — Settings UI + i18n**: modify `frontend/src/api/settings.ts` (`exportDatabase()` → blob); `frontend/src/pages/Settings/Settings.tsx` (System-tab "Export Database" button, admin-gated, triggers download); i18n `settings.exportDb`, `settings.exportDbHelp`, `settings.backupRemoteStatus` (es+en). Verify: `npm run test -- SettingsExportDb` → green. Deps: C.2, C.5.

**Commit plan (PR-C work units)**: (1) `feat(system): audited admin database export endpoint` — C.1+C.2; (2) `feat(ops): scheduled remote backup with local-retention isolation` — C.3+C.4 (test+scripts+systemd+install+.env together); (3) `feat(settings): admin database-export button` — C.5+C.6+i18n.
**Rollback**: delete `backend/api/system.py` + router reg, `scripts/remote_push.sh`, systemd units; `sudo systemctl disable --now powerhouse-backup.timer`; remove Settings button. Local backup, retention, and UTC storage untouched.
**Acceptance**: `Fresh Custom-Format Database Download` + `Export Authorization` (401/403) + `Export Audit Record` (C.1/C.2); `Scheduled Remote Replication` + `Local Backup and Retention Preservation` (unreachable-target + retention scenarios) + `Environment-Only Remote Credentials` (C.3/C.4).

---

## Cross-slice notes

- **Order**: A first (shared tz service + i18n spine); B and C can be authored in parallel but both land after A.
- **Chain strategy** (stacked-to-main vs feature-branch-chain) is the orchestrator's user question; tasks above are boundary-clean for either. For feature-branch-chain: PR-A base = tracker branch, PR-B/PR-C base = PR-A branch; retarget if a child diff shows sibling-slice changes.
- **Threat matrix coverage**: subprocess arg-injection (A.6/C.2), shell-injection (C.4), path-traversal filename (C.1/C.2), auth-bypass (C.1/C.2), biometric exposure (audit test + SECURITY.md §4), secrets-in-logs (C.3/C.4), remote-failure isolation (C.3/C.4), tz-29-day regression (A.3 keeps `build_report_window` contract).
