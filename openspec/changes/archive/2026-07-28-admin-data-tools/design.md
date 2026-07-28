# Design: Admin Data Tools

## Technical Approach

Six admin features (#1 DB export, #2 remote backup, #3 timezone bugfix, #4 custom-range diagnosis, #5 CSV export, #6 membership accordion) delivered as one change, sliced into 3 chained PRs. The shared spine is **(a)** a cached DST-aware timezone service (#3, foundational — #5 depends on it), **(b)** reuse of the existing `build_report_window` half-open contract for #5, **(c)** reuse of `scripts/backup.sh` + `require_admin` + `log_action` for #1/#2, and **(d)** a pure presentational partition for #6. #4 needs no code in `main` — it ships a documented diagnosis + rebuild procedure plus a guard test.

## Architecture Decisions

| Decision | Options | Tradeoff | Choice |
|---|---|---|---|
| TZ cache location | new `services/timezone.py` vs `core/` | `services/` matches `report_window.py` sibling; pure DB+Redis | `backend/services/timezone.py` |
| TZ cache backing | Redis TTL vs in-process vs per-request | Spec mandates invalidate-on-write; Redis already wired, multi-worker safe | Redis key `app:tz`, TTL 300s, invalidated in settings write paths |
| TZ type | `timezone(timedelta)` vs `zoneinfo.ZoneInfo` | Fixed offset cannot do DST; spec requires DST-correct | `zoneinfo.ZoneInfo` everywhere |
| Frontend TZ display | server formats ISO+offset vs client `Intl.DateTimeFormat` w/ zone | Public-settings already carries display prefs; zero new deps | Add `timezone` to `/settings/public`; client `Intl.DateTimeFormat({timeZone})` |
| CSV export route | client-side CSV vs server `StreamingResponse` | Spec: "server-side CSV … same configured-timezone half-open window as on-screen" | `GET /sales/report/export`, `StreamingResponse`, reuse `_resolve_report_window` |
| CSV download trigger | `window.open` vs blob+anchor | Need `Authorization` header → window.open can't send it | axios `responseType:'blob'` + object URL + anchor click |
| DB export mechanism | sync `pg_dump -F c` streamed vs return latest `backup.sh` artifact | Spec: "fresh … on-demand" | `subprocess.Popen(["pg_dump",…,"-F","c"], stdout=PIPE)` → `StreamingResponse` |
| DB export auth | `require_admin` (existing) | Spec: 401 unauth + 403 non-admin; existing dep already enforces role | `Depends(require_admin)` |
| Remote push transport | smbclient vs mount vs rsync | One script, env-selected; no new mount deps at runtime | `BACKUP_REMOTE_TYPE=smb|nfs|rsync|none`, rsync preferred |
| Remote failure handling | exit non-zero vs warn-continue | Spec: local copy + retention MUST survive | Warn-and-log; only local dump failure exits non-zero |
| Backup cadence host | APScheduler job vs systemd timer | Ops-only, matches bare-metal/LXC prod model, survives app restarts | systemd `powerhouse-backup.timer` `OnCalendar=*:0/30` |
| Accordion structure | per-row accordion vs single accordion wrapping items 3-50 | Spec: "collapsed MUI Accordion by default"; one expander, less noise | Single `<Accordion>` around `sortedMemberships.slice(2)` |
| Custom-range #4 | re-implement vs diagnose+rebuild | Code is correct in `main`; only deployment is stale | Diagnose drift, rebuild frontend on LXC, guard test |

## Data Flow

```
#3 TZ:  Setting(key='timezone') ──► get_app_tz(db) ──► ZoneInfo ──┬─► build_report_window(start,end,tz)
                                                                  ├─► DashboardService._today_start_utc()
                                                                  └─► events.colombia_today()→ app_today(db)
            PUT /settings/{key}|/bulk ──► DEL redis "app:tz"  (invalidation)

#5 CSV:  Reports.tsx onClick ──► salesApi.exportReport(reportRange) ──► GET /sales/report/export
              └─► _resolve_report_window ──► build_report_window(tz=get_app_tz(db)) ──► StreamingResponse CSV

#1 DB:   Settings (System tab) ──► settingsApi.exportDatabase() ──► GET /system/db-export
              └─► require_admin ──► pg_dump -F c (Popen) ──► StreamingResponse ──► log_action("db_export")

#2 BU:   systemd timer (30m) ──► backup.sh ──► local pg_dump+tar (exit-on-fail)
              └─► remote_push (warn-on-fail) ──► local retention (always)

#6 UI:   sortedMemberships ──► [slice(0,2) visible] + [slice(2) in <Accordion>]
```

## Interfaces / Contracts

```python
# backend/services/timezone.py
from zoneinfo import ZoneInfo
DEFAULT_TZ = "America/Bogota"; CACHE_KEY = "app:tz"; TTL = 300
def get_app_tz(db) -> ZoneInfo: ...           # Redis-first, fall back to DB read, default DEFAULT_TZ
def invalidate_app_tz_cache() -> None: ...    # called by settings PUT/bulk when key=='timezone'
def utc_to_local(dt_naive_utc, tz) -> datetime: ...  # rendering helper, tz-aware

# build_report_window signature UNCHANGED (tz defaults to APP_TZ kept for pure-function tests);
# sales.py/_resolve_report_window pass tz=get_app_tz(db).
```

```python
# backend/api/system.py  (NEW router prefix=/system)
@router.get("/db-export")
def export_database(db=Depends(get_db), admin=Depends(require_admin), request=Request):
    # parse DATABASE_URL → host/port/user/pass/db; PGPASSWORD env; Popen pg_dump -F c
    # StreamingResponse(media_type="application/octet-stream",
    #   headers={"Content-Disposition":'attachment; filename="powerhouse_db_<ts>.dump"'})
    log_action(db, action="db_export", resource_type="system",
        user_id=str(admin.id), username=admin.username,
        details={"format":"pg_dump -F c"}, ip_address=request.client.host,
        user_agent=request.headers.get("user-agent")); db.commit()
```

```python
# backend/api/sales.py — added
@router.get("/report/export")
def export_sales_report(days=Query(30,ge=1,le=365), start_date:Optional[date]=None,
                        end_date:Optional[date]=None, db=Depends(get_db),
                        current_user=Depends(require_staff)):
    # resolved = _resolve_report_window(...) OR preset via datetime.utcnow()-days
    # query SalesTransaction filtered; tz=get_app_tz(db) for transaction_date rendering
    # StreamingResponse(generator yielding "\ufeff"+header+rows, media_type="text/csv",
    #   headers={Content-Disposition: filename=sales_report_<rng>.csv})
```

**.env keys** (documented in `.env.example`, never in settings table):
`BACKUP_REMOTE_TYPE=none|smb|nfs|rsync`, `BACKUP_REMOTE_TARGET=//host/share` or `user@host:/path`, `SMB_USER`, `SMB_PASS`, `RSYNC_USER`, `RSYNC_HOST`, `RSYNC_PATH`. `.env` stays `chmod 600`; no credential value is ever logged.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/services/timezone.py` | Create | `get_app_tz(db)`, `invalidate_app_tz_cache()`, `utc_to_local()` |
| `backend/services/report_window.py` | Modify | Keep `APP_TZ` default (pure tests stay green); docstring note that callers pass configured tz |
| `backend/services/dashboard_service.py` | Modify | `DashboardService.__init__` stores `self.tz=get_app_tz(db)`; replace `COLOMBIA_TZ` usages |
| `backend/api/events.py` | Modify | `colombia_today()`/`colombia_today_start_utc()` → accept `db`/`tz`; endpoints pass `get_app_tz(db)` |
| `backend/api/sales.py` | Modify | `_resolve_report_window` accepts `db` and passes `tz=get_app_tz(db)`; add `/report/export` |
| `backend/api/settings.py` | Modify | `update_setting` + `bulk_update_settings` call `invalidate_app_tz_cache()` when key=='timezone' |
| `backend/api/system.py` | Create | `GET /system/db-export` admin endpoint |
| `backend/api/__init__.py` | Modify | Register `system` |
| `backend/main.py` | Modify | `include_router(system.router)` |
| `backend/core/database.py` or new | Minor | expose redis client helper if not already (used by tz cache) |
| `scripts/backup.sh` | Modify | Add remote-push step (warn-on-fail); source `.env` remote keys |
| `scripts/remote_push.sh` | Create | Extracted helper invoked by backup.sh; independently testable with mocks |
| `scripts/systemd/powerhouse-backup.service` | Create | `Type=oneshot`, `ExecStart=.../backup.sh` |
| `scripts/systemd/powerhouse-backup.timer` | Create | `OnCalendar=*:0/30`, `Persistent=true` |
| `install.sh` | Modify | New step installs backup units, `systemctl enable --now powerhouse-backup.timer` |
| `.env.example` | Modify | Document `BACKUP_REMOTE_*` keys |
| `frontend/src/pages/Sales/SalesList.tsx` | Modify | Render `transaction_date` via `Intl.DateTimeFormat({timeZone})` date+time |
| `frontend/src/api/sales.ts` | Modify | Add `exportReport(params)` returning blob |
| `frontend/src/api/settings.ts` | Modify | Add `exportDatabase()` returning blob |
| `frontend/src/pages/Reports/Reports.tsx` | Modify | Wire Export Report `onClick`; consume `timezone` from public-settings for display |
| `frontend/src/pages/Settings/Settings.tsx` | Modify | Add System-tab "Export Database" button section |
| `frontend/src/pages/Members/MemberForm.tsx` | Modify | Partition `sortedMemberships`; wrap slice(2) in single `<Accordion>` |
| `frontend/src/i18n/translations.ts` | Modify | es+en: `settings.exportDb`, `settings.exportDbHelp`, `members.olderMemberships` (with `{count}`), `members.hideOlderMemberships`, `settings.backupRemoteStatus` |
| `docs/deployed-build-diagnosis.md` (or `openspec/changes/admin-data-tools/`) | Create | #4 diagnosis procedure |

## Testing Strategy (STRICT TDD ACTIVE — backend `pytest tests/`, frontend `vitest run`; backend needs `docker-compose up -d db redis`)

| Layer | File | RED tests |
|-------|------|-----------|
| Unit | `backend/tests/test_timezone_service.py` (NEW) | default zone; reads `timezone` setting; cache hit skips DB; invalidate → next call returns new zone |
| Unit | `backend/tests/test_report_window.py` (extend) | **DST**: `build_report_window(date(2026,9,6),date(2026,9,9), tz=ZoneInfo("America/Santiago"))` — each local midnight maps with the applicable offset for that date; half-open preserved |
| Integration | `backend/tests/test_sales_csv_export.py` (NEW) | custom-range CSV header+rows match `/report/summary` count; reversed→422; preset days works; filename convention |
| Integration | `backend/tests/test_db_export.py` (NEW) | **401 unauth**; **403 non-admin**; admin→200 `application/octet-stream`+body starts `PGDMP`; **audit row `action='db_export'` exists** |
| Integration | `backend/tests/test_remote_backup_isolation.py` (NEW, mock) | run `scripts/backup.sh` in tmp with mocked `pg_dump` and unreachable `BACKUP_REMOTE_TYPE=rsync` target → local `.dump`+`.tar.gz` present; checksums present; retention ran; exit code 0; "remote" warned to log |
| Unit | `frontend/src/test/SalesList.test.tsx` (NEW) | renders date+time in `America/Santiago` (mock public-settings `timezone`); not just `toLocaleDateString()` |
| Unit | `frontend/src/test/MembershipAccordion.test.tsx` (NEW) | 2 memberships → no accordion; **3 → 2 visible + accordion w/ 1**; **50 → 2 visible + accordion w/ 48 expandable**; admin edit/delete buttons render inside accordion |
| Unit | `frontend/src/test/ReportsExport.test.tsx` (NEW) | clicking Export triggers `salesApi.exportReport` with current `reportRange`; anchor click observed |
| Unit | `frontend/src/test/SettingsExportDb.test.tsx` (NEW) | admin-only Export DB button calls `settingsApi.exportDatabase` |
| Unit | `frontend/src/test/reportRange.test.ts` (extend) | regression guard documenting custom-range contract (covers #4 acceptance at unit level) |

## Threat Matrix (applicable — adds routes, subprocess, shell, process integration)

| Threat | Applicable? | Safe behavior | RED test |
|---|---|---|---|
| Subprocess arg injection (pg_dump) | **Yes** | `pg_dump` args built from parsed `DATABASE_URL`, never shell string; no user input in argv | unit: argv has no shell metachar; body starts `PGDMP` |
| Shell injection in `backup.sh` remote | **Yes** | All remote vars consumed quoted; never `eval`; creds only via env | unit: unreachable target never executes arbitrary `cmd` |
| Path traversal in dump filename | **Yes** | Filename built from fixed prefix + server timestamp; no user path input | unit: `Content-Disposition` filename matches `^powerhouse_db_\d+\.dump$` |
| Auth bypass on db-export | **Yes** | `require_admin` enforces 401/403 before `pg_dump` runs | 401 unauth, 403 staff tests |
| Biometric data exposure (Ley 1581) | **Yes** | admin-only, audit-logged, TLS via Nginx, NAS must be encrypted (ops note) | audit-row test + SECURITY.md §4 cross-ref |
| Secrets in logs | **Yes** | backup.sh never echoes `SMB_PASS`/`PGPASSWORD`; `.env` `chmod 600` | log-grep test (no credential token) |
| Remote failure takes down local backups | **Yes** | remote step warn-only; local retention always runs | isolation test |
| TZ regression on 29-day membership fix | **Yes** | keep `build_report_window` signature/contract; only thread tz | existing `test_report_window.py` stays green + new DST test |
| VCS/PR automation | N/A | no git/PR automation in this change | — |
| Executable-file classification | N/A | no new executable classification logic | — |

## Migration / Rollout

- **Backend:** no schema change. Deploy new router + tz service; restart `facegym-backend`. Cache cold-starts lazily.
- **Frontend (#4 remediation):** rebuild on the LXC (`cd frontend && npm ci && npm run build`), replace served `dist/`. **Diagnosis procedure** (docs/deployed-build-diagnosis.md): (1) diff deployed `dist/` mtime vs. last successful `npm run build`; (2) check served bundle contains the `custom` MenuItem + `buildReportRange` symbol (grep minified for `customRange`); (3) confirm Reports page exposes two `<input type="date">` when dropdown = `custom`; (4) acceptance = valid range returns results. If drift confirmed → rebuild; if not → escalate as real bug.
- **Systemd timer (#2):** `install.sh` new step writes the two units, `daemon-reload`, `enable --now`. Existing installs: documented manual `systemctl enable --now powerhouse-backup.timer`.
- **Rollback:** revert slices independently; `systemctl disable --now powerhouse-backup.timer`; remove `/system/db-export` + `/sales/report/export` routes and Settings buttons; UTC storage and local backups untouched.

## Open Questions

- [ ] Confirm `America/Santiago` 2026 DST transition date for the red test (tzdata version-dependent; pin `tzdata` in requirements).
- [ ] Confirm whether `membershipsApi.getMemberships` limit must rise above 50 for very long histories (currently out of scope per spec).
- [ ] Decide rsync vs SMB as the *primary* documented path in `.env.example` (recommend rsync; SMB as fallback).
