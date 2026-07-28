# Exploration: admin-data-tools

> Six user-requested admin features investigated against real code in `main`
> (HEAD `1acf916`). Two are confirmed bugs, one is already done, one is a pure
> UI refactor, and two are net-new ops/security-sensitive surfaces. No product
> code was modified.

## Quick verdict

| # | Feature | Type | Verdict | Primary surface |
|---|---|---|---|---|
| 1 | Export DB button (dump download) | Net-new | No dump endpoint exists; `/members/export` is CSV-only | `backend/api/`, `Settings.tsx` |
| 2 | Remote backup server (NAS/SMB/NFS, 30 min) | Infra + net-new | `scripts/backup.sh` does local dump only; no remote push, no cadence | `scripts/`, `backend/main.py` scheduler |
| 3 | Sales timestamp with **configured** timezone | **Confirmed bug** | Settings UI exposes a TZ dropdown but backend hardcodes `America/Bogota` in 3 places; the setting is silently ignored | `dashboard_service.py`, `events.py`, `report_window.py`, `SalesList.tsx` |
| 4 | Custom date range in reports dropdown | **Already shipped** | Done in `main` by commit `a4613d9` (PR #1). No work needed | `Reports.tsx`, `reportRange.ts` |
| 5 | Fix "Export Report" button (exports nothing) | **Confirmed bug** | The `<Button>` has NO `onClick` handler — purely decorative | `Reports.tsx:376-382` |
| 6 | Group membership history (3rd onward) into accordion | UI refactor | `MemberForm` `MembershipSection` renders a flat list; no collapsing | `MemberForm.tsx:577-708` |

## Current State (per feature)

### Feature 1 — Export DB button
- **Today:** No full-database dump endpoint anywhere. `backend/api/import_export.py:82`
  exposes `GET /members/export` but it returns a **CSV of member rows only** (first_name,
  last_name, email, phone, status, facial_data_enrolled, created_at) — it does NOT include
  sales, memberships, access events, settings, or a binary dump.
- The existing `scripts/backup.sh` already produces a real `pg_dump -F c` (custom format)
  to `/var/backups/powerhouse/db_backup_<ts>.dump` plus a biometric tarball and a config
  tarball, with 30-day retention. This is the correct artifact to expose/download.
- **Gap:** An admin-only endpoint (e.g. `GET /api/system/db-export`) that runs `pg_dump`
  (or returns the latest dump produced by `backup.sh`) as a streaming download, plus a
  "Export Database" button in `Settings.tsx` (System tab).
- **Integration points:** new router under `backend/api/` (admin-gated via `require_admin`);
  `Settings.tsx` System tab; i18n keys `t.settings.exportDb` + `t.settings.exportDbHelp`
  (es+en in `translations.ts`).
- **Risks/traps:**
  - **Trap #11 (biometric data, Ley 1581/2012):** a full dump contains encrypted biometric
    templates. The download MUST be admin-only, logged via `core/audit.log_action`, and
    ideally TLS-only. Do NOT expose to staff role.
  - `pg_dump` shells out — the DB creds come from `DATABASE_URL`; reuse the parsing in
    `backup.sh` rather than reinventing.
  - Large dumps can time out uvicorn workers; prefer streaming (`StreamingResponse`) or
    returning the last `backup.sh` artifact instead of dumping synchronously on click.
  - `INTERNAL_API_SECRET` / CI env divergence (STATUS.md) — do not hardcode.

### Feature 2 — Remote backup server (NAS/SMB/NFS, every 30 min)
- **Today:** `scripts/backup.sh` runs only when invoked manually (no cron/systemd timer
  ships in the repo). It writes locally only. No remote-mount config exists anywhere.
  No settings keys for `backup_*` exist in `Settings.tsx` `DEFAULT_SETTINGS`.
- The APScheduler pattern exists in `backend/main.py:52-63` (`BackgroundScheduler`,
  `add_job(send_scheduled_report, "interval", hours=2, args=[SessionLocal], id=...)`).
- **Gap:** (a) a 30-minute cadence for `backup.sh`, and (b) a remote-target config
  (SMB share / NFS mount / rsync target) plus a push step after the local dump.
- **Integration points:** two realistic options:
  1. **Systemd timer** `powerhouse-backup.timer` (OnCalendar=`*:0/30`) wrapping
     `backup.sh` — ops-only, matches the bare-metal/LXC prod model (AGENTS.md).
  2. **In-app scheduler job** mirroring the email-report job, pushing the latest dump to
     the remote target. Requires remote config in the Settings table.
  Either way: extend `backup.sh` with an optional `REMOTE_TARGET`/`SMB_SHARE` env-driven
  `rsync`/`smbclient` step; add `backup_remote_target`, `backup_interval_minutes` settings;
  expose them under the System tab.
- **Risks/traps:**
  - **Credentials in `.env`:** SMB/NFS creds must NOT be stored in the Settings table
    (which is plain DB rows). Keep secrets in `.env` (SECURITY.md §2); store only the
    non-secret target host/share in settings.
  - Biometric tarball is sensitive at rest on the NAS — ensure the target is encrypted
    or access-restricted (trap #11).
  - 30-minute `pg_dump` cadence on a small DB is fine, but watch disk + IOPS on the LXC.
  - `backup.sh` uses `set -euo pipefail` and already has retention + checksums — extend,
    don't rewrite.

### Feature 3 — Sales timestamp with the configured timezone  ⚠️ CONFIRMED BUG
- **Today (the bug):** The Settings UI DOES expose a timezone selector
  (`Settings.tsx:52` default `America/Bogota`; full dropdown at `:154-178` with 11 IANA
  zones), and the value is persisted to the `settings` table. **But the backend NEVER
  reads it.** Three independent places hardcode Colombia:
  - `backend/api/events.py:27` — `COLOMBIA_TZ = timezone(timedelta(hours=-5))`
  - `backend/services/dashboard_service.py:11` — same constant; drives `get_new_signups`,
    `get_checkins_today`, `get_checkins_week`, `get_revenue_change_pct`, and the
    custom-window revenue trend bucketing.
  - `backend/services/report_window.py` — `APP_TZ = timezone(timedelta(hours=-5))`,
    drives the half-open `[start 00:00, (end+1) 00:00)` window for both
    `/sales/dashboard` and `/sales/report/summary`.
  - **No code path reads `Setting.key == 'timezone'`** (grep confirms zero consumers).
  - **Result:** selecting e.g. `America/Mexico_City` in Settings changes NOTHING. Report
    boundaries and "today"/"this week" are always America/Bogota. The user's explicit
    "verify timezone works per selection" request FAILS — this is a real, reproducible bug.
- **Sales timestamp display:** `SalesList.tsx:131` renders
  `new Date(tx.transaction_date).toLocaleDateString()` — this shows **date only, no time,
  in the browser's local zone**, NOT the configured one. The exact sale time is stored
  (model default `datetime.now(timezone.utc)` in `models/sale.py:39`) but never displayed.
- **Gap:** (a) centralize TZ resolution into one helper that reads the `timezone` setting
  (cached — see below); replace the 3 hardcoded constants; (b) make `SalesList.tsx` show
  full date+time converted to the configured TZ.
- **Integration points:**
  - New `backend/services/timezone.py` (or extend `core/`) with `get_app_tz(db) -> ZoneInfo`
    using `zoneinfo.ZoneInfo` (stdlib, not the legacy `timezone(timedelta(hours=-5))` which
    can't represent DST zones like `America/Santiago` or `Europe/Madrid`).
  - **Caching:** there is NO settings cache today (`settings.py` reads the DB ad-hoc). A
    per-request DB hit inside `DashboardService` hot loops is wasteful; add a small TTL
    cache (Redis is already available) or read once per request and thread it through.
  - Replace `COLOMBIA_TZ`/`APP_TZ` usages in `dashboard_service.py`, `events.py`,
    `report_window.py`.
  - Frontend: add a TZ-aware formatter (date-fns `formatInTimeZone` or pass the configured
    TZ from public settings) and use it in `SalesList.tsx` + the recent-sales panel in
    `Reports.tsx:516`.
- **Risks/traps:**
  - **Trap #4 (Colombia TZ hardcoded):** this feature is literally the fix for that trap.
    Commits `f031ed1`/`b18cd3c`/`85cf905` already touched this area — re-read them before
    editing to avoid regressing the 29-day-membership fix.
  - `timezone(timedelta(hours=-5))` is a fixed offset; switching to `ZoneInfo` changes
    behavior for DST zones. Tests must cover a DST zone (e.g. `America/Santiago`) crossing
    a DST boundary.
  - DB columns are **naive UTC** (see `report_window.py` docstring). Do not change column
    types; only change how bounds are computed and how values are rendered.
  - Half-open window contract (`build_report_window`) is covered by existing tests
    (`test_sales_date_range.py`, `test_report_window.py`); keep them green.

### Feature 4 — Custom date range in reports dropdown  ✅ ALREADY SHIPPED
- **Today:** Fully implemented in `main` by commit `a4613d9` ("feat(reports): custom
  date-range reports"), shipped to `main` via PR #1 (per STATUS.md line 41). Verified:
  - `frontend/src/api/reportRange.ts` exists with `buildReportRange(timeRange, start, end)`
    returning `{ days }` for presets and `{ start_date, end_date }` for `custom`, throwing
    on reversed/incomplete ranges.
  - `frontend/src/pages/Reports/Reports.tsx:338-366` renders two `<TextField type="date">`
    pickers (from/to) when `timeRange === 'custom'`, plus an inline reversed-range error.
  - Backend `GET /sales/dashboard` (`backend/api/sales.py:189`) and `/sales/report/summary`
    (`:220`) both accept optional `start_date`/`end_date` and apply the same half-open
    window.
  - Tests exist: `frontend/src/test/reportRange.test.ts` (custom + reversed + incomplete),
    `backend/tests/test_sales_date_range.py`, `backend/tests/test_report_window.py`.
  - `git log main..feature/tracker --oneline` is **empty** — no unmerged work; nothing
    pending for this feature.
- **Gap:** None. The only minor enhancement is swapping the native `<TextField type="date">`
  for MUI `<DatePicker>` (requires `@mui/x-date-pickers`), but that is cosmetic and not
  requested.
- **Recommendation:** Close this item as already-done; confirm with the user before
  dropping it from the change scope. Do NOT duplicate.

### Feature 5 — Fix "Export Report" button  ⚠️ CONFIRMED BUG
- **Today (the bug):** `Reports.tsx:376-382`:
  ```tsx
  <Button variant="contained" startIcon={<DownloadIcon />}
     sx={{ bgcolor: '#2e7d32', '&:hover': { bgcolor: '#1b5e20' } }}>
     {isMobile ? '' : t.reports.exportReport}
  </Button>
  ```
  **There is no `onClick` handler.** The button is purely decorative — clicking it does
  nothing. That is exactly why "it exports nothing."
- **Gap:** Wire the button to actually export the currently-loaded report data. Two
  reasonable scopes:
  1. **Minimal:** export the in-memory `reportData` + `salesReport` + recent transactions
     to CSV/Excel client-side (no new endpoint). Depends on the selected range/custom
     window so it respects feature #4.
  2. **Server-side:** add `GET /sales/report/export?start_date=&end_date=&days=` returning
     a CSV/XLSX `StreamingResponse`. More consistent with feature #1 and gives a single
     source of truth.
- **Integration points:** `Reports.tsx` (add `onClick`); `salesApi` (add
  `exportReport(params)` if server-side); i18n key already exists (`t.reports.exportReport`
  in both es/en at `translations.ts:254`/`:693`).
- **Risks/traps:** The export MUST respect the same date window the user selected
  (feature #4 + #3) — otherwise it re-introduces the old "summary ignores range" bug the
  previous change fixed. If server-side, the TZ window (feature #3) applies, so #5 depends
  on #3 being correct.

### Feature 6 — Membership history dropdown/accordion
- **Today:** `MemberForm.tsx` `MembershipSection` (defined at `:339`) fetches up to 50
  memberships (`membershipsApi.getMemberships(0, 50, memberId)`, `:360`) and renders them
  as a **flat list** of `<Paper>` rows (`sortedMemberships.map(...)` at `:577-708`). There
  is no grouping, folding, or "show more." A long-term member with many renewals produces
  an arbitrarily long scroll.
- **Gap:** Keep the first 2 (most recent by `end_date desc`, which is the existing sort)
  visible; collapse items 3+ into an MUI `<Accordion>` (or a "Show N older" expander).
  History must remain consultable (expand-on-click).
- **Integration points:** `MemberForm.tsx:577-708` only (pure presentational change);
  i18n keys for the toggle, e.g. `t.members.showOlderMemberships` / `t.members.hideOlderMemberships`
  (es+en).
- **Risks/traps:** Minimal. Preserve the existing edit/renew/delete actions per row. The
  `getMemberships` limit of 50 is already a soft cap; consider whether very long histories
  should paginate, but that is out of scope for this request. Admin-only actions (`isAdmin`)
  must remain scoped inside the collapsed rows.

## Affected Areas (consolidated)

- `backend/services/dashboard_service.py` — drop hardcoded `COLOMBIA_TZ`, thread configured TZ (#3).
- `backend/services/report_window.py` — drop hardcoded `APP_TZ`, accept configured TZ (#3).
- `backend/api/events.py` — same `COLOMBIA_TZ` removal (#3).
- `backend/services/timezone.py` (NEW) — `get_app_tz` helper reading the `timezone` setting, cached (#3).
- `backend/api/sales.py` — optional `/report/export` endpoint (#5, if server-side).
- `backend/api/system.py` (NEW) — admin `GET /system/db-export` endpoint (#1).
- `backend/main.py` — optional backup scheduler job (#2, alternative to systemd timer).
- `scripts/backup.sh` — add optional remote push step (#2).
- `frontend/src/pages/Settings/Settings.tsx` — Export DB button + backup config fields (#1, #2).
- `frontend/src/pages/Reports/Reports.tsx` — wire Export Report `onClick` (#5).
- `frontend/src/pages/Sales/SalesList.tsx` — TZ-aware date+time display (#3).
- `frontend/src/pages/Members/MemberForm.tsx` — accordion for history item 3+ (#6).
- `frontend/src/i18n/translations.ts` — new es+en keys for all new UI strings (#1,#2,#3,#5,#6).
- `install.sh` / systemd units — optional `powerhouse-backup.timer` (#2).

## Approaches

### Grouping the work
1. **Single change `admin-data-tools`, phased/chained PRs (recommended)** — one proposal,
   three chained PRs under the 800-line budget:
   - **PR1 — bugfixes (#3 TZ + #5 export):** the export respects the TZ window, so they
     must land together. Central TZ helper + wire the button. ~Medium.
   - **PR2 — UI polish (#6 accordion):** pure presentational, low risk, ~Small.
   - **PR3 — DB export + remote backup (#1 + #2):** security-sensitive, ops-heavy,
     isolated for review focus. ~Medium-Large.
   - #4 closed as already-shipped (verify with user).
   - Pros: one coherent narrative ("admin data tooling"), shared i18n/settings touches
     batched, respects the 800-line budget, matches the repo's chained-PR convention.
   - Cons: the change spans backend+frontend+ops; strict TDD across all three PRs is work.
2. **Split into two changes** — `admin-data-fixes` (#3, #5, #6) + `admin-backup-tools`
   (#1, #2). Cleaner separation between bug-fixes and net-new infra, but doubles OpenSpec
   ceremony for loosely-related admin asks.
   - Pros: security review isolates the dump/backup work.
   - Cons: more overhead; #5 depends on #3 either way.

**Recommendation:** Approach 1 — one `admin-data-tools` change, three chained PRs,
explicitly dropping #4 (already shipped). Confirm the #4 drop with the user before proposal.

## Risks

- **TZ switch breaks DST zones** — moving from `timezone(timedelta(hours=-5))` to
  `ZoneInfo` is correct but changes arithmetic for DST zones; add a red test crossing a
  `America/Santiago` DST boundary before refactoring (#3).
- **Feature #5 silently regresses the range fix** — if the export does not reuse
  `buildReportRange`/`build_report_window`, it can re-introduce the "summary ignores
  range" bug fixed in PR #1. Reuse the existing helpers.
- **Biometric data exposure (#1, #2)** — a full DB dump and the biometric tarball contain
  sensitive data (Ley 1581/2012, trap #11, SECURITY.md §4). Enforce admin-only access,
  audit-log every download, keep NAS target encrypted, never put SMB creds in the settings
  table.
- **Backup cadence I/O (#2)** — a 30-minute `pg_dump` on the LXC is fine for small DBs
  but watch disk/retention; reuse `backup.sh` retention rather than disabling it.
- **Trap #4 (Colombia TZ)** — this change is the fix; re-read commits `f031ed1`/`b18cd3c`/
  `85cf905` before editing date math to avoid regressing the 29-day-membership fix.
- **Settings cache does not exist** — reading the TZ setting per request in dashboard hot
  loops needs a small Redis TTL cache or a per-request read passed through, otherwise it is
  a new N+1.
- **`gh.env` PAT / secrets hygiene (trap #1)** — none of these features should touch
  secrets in code; keep all in `.env`.

## Dependencies between features

- **#5 depends on #3** (export must use the configured TZ window).
- **#1 and #2 share** the dump artifact (`pg_dump` output) and the biometric-sensitivity
  concerns; build #1 on top of `backup.sh` and #2 extends the same script.
- **#3 is foundational** for trustworthy reports; ideally lands first.
- **#4 is independent and already done** — no dependency.
- **#6 is independent** — pure UI.

## Uncertainties (to confirm with user before proposal)

1. **Feature #4 drop:** confirm the user agrees the custom date-range is already shipped
   (it is in `main` since PR #1). The dropdown they want already exists.
2. **Export Report scope (#5):** client-side CSV from in-memory data (fast, no endpoint)
   vs. server-side `/sales/report/export` (consistent with #1, larger). Which do they want?
3. **Export DB (#1):** synchronous dump-on-click vs. download the latest `backup.sh`
   artifact? The latter is safer and faster but at most 30 min stale.
4. **Backup remote target (#2):** SMB, NFS, or rsync-over-SSH? And is systemd-timer
   acceptable, or must it be the in-app scheduler?
5. **History accordion threshold (#6):** "from the 3rd onward" — confirm exactly 2 visible,
  rest collapsed.

## Ready for Proposal

**Yes — for #1, #2, #3, #5, #6.** #4 should be dropped (already shipped) pending user
confirmation. Before the proposal the orchestrator should resolve the 5 uncertainties
above, especially the #4 drop and the #5 export scope.
