# Archive Report: admin-data-tools

**Change**: `admin-data-tools`
**Archived**: 2026-07-28
**Archive mode**: `hybrid` (per `openspec/config.yaml`)
**Verdict**: PASS — SDD cycle complete. All 6 features delivered, 12/12 requirements met, 18/18 scenarios compliant, 0 critical findings.

> **Final-state authority**: This report reflects the FINAL state of the change at close,
> per the SDD archive hierarchy. Where the intermediate `verify-report` and `apply-progress`
> snapshots (rank 4) disagree with the orchestrator's authoritative launch facts (rank 3),
> the launch facts win and the snapshot claim is not echoed as current. The single such
> case — W-1 black regression — is documented under "Warnings" below.

## Engram Traceability

| Artifact | Topic key | Observation |
|----------|-----------|-------------|
| Apply progress | `sdd/admin-data-tools/apply-progress` | **#72** |
| Verify report | `sdd/admin-data-tools/verify-report` | **#75** |
| Archive report | `sdd/admin-data-tools/archive-report` | (this document, persisted at close) |

On-disk artifacts (this folder): `proposal.md`, `design.md`, `exploration.md`, `tasks.md`, `verify-report.md`, `specs/{4 domains}/spec.md`.

## Delivered vs Proposed Scope

| # | Feature (proposed) | Delivered as | Slice | Status |
|---|--------------------|--------------|-------|--------|
| 1 | Admin-only audited DB export | `GET /system/db-export` (argv-list `pg_dump -F c`, `PGPASSWORD` env-only, `require_admin`, `log_action("db_export")` on success), Settings System-tab button | C | ✅ Met |
| 2 | 30-minute remote backup (warn-only) | `scripts/remote_push.sh` (smb/nfs/rsync env-selected), `scripts/backup.sh` rewrite (warn-only remote + unconditional local retention), `powerhouse-backup.{service,timer}` (`OnCalendar=*:0/30`, `Persistent=true`), `install.sh` enable step, `.env.example` docs | C | ✅ Met |
| 3 | Configured timezone reporting | `backend/services/timezone.py` (cached `get_app_tz`, Redis key `app:tz` TTL 300, `invalidate_app_tz_cache` on both settings write paths, `utc_to_local`); `ZoneInfo` threaded through `dashboard_service`, `events`, `sales`; 3 hardcoded `timedelta(hours=-5)` sites replaced; `SalesList` date+time via `Intl.DateTimeFormat({timeZone})` | A | ✅ Met |
| 4 | Custom-range "not visible" remediation | **Reframed mid-flight**: code was already correct in `main` (PR #1). Delivered as **regression contract** (`reportRange.test.ts` 12 cases) + **deployed-build diagnosis protocol** (`docs/deployed-build-diagnosis.md`, 4-step: diff dist mtime → grep minified for `customRange`/`buildReportRange` → confirm 2 date inputs at `custom` → rebuild on LXC if drift). User-facing fix is rebuild+redeploy, not code. | A | ✅ Met (as reframed) |
| 5 | Server CSV export | `GET /sales/report/export` (`require_staff`, reuses `_resolve_report_window` + `build_report_window(tz=get_app_tz(db))`, `StreamingResponse` `text/csv` + BOM + `Content-Disposition`), Reports.tsx Export button (axios blob + object URL + anchor) | A | ✅ Met |
| 6 | Membership accordion | `MemberForm.tsx`: sort by `end_date` desc, `slice(0,2)` visible, `slice(2,50)` in single MUI `<Accordion>` (collapsed by default), shared `renderMembershipRow` preserves edit/renew/delete + admin gate; i18n `olderMemberships` (with `{count}`) + `hideOlderMemberships` es+en | B | ✅ Met |

### Scope decisions / reframes
- **Feature #4** is the only reframe. Per orchestrator (rank 3, authoritative): "code existed in main (PR #1); delivered as regression contract + deployed-build diagnosis protocol. The user-facing 'not visible' issue is a stale deployed build on the LXC — remediation is rebuild+redeploy (documented), NOT code." The verify-report snapshot (rank 4) treated #4 as fully compliant via the regression contract + diagnosis protocol — consistent with the reframe.

## Branch state at archive

Feature-branch chain (all **LOCAL ONLY — NO push**, per orchestrator/user decision):

| Branch | Tip | Contents |
|--------|-----|----------|
| `feature/admin-data-tools` | tracker | at main, chain root |
| `feat/admin-data-tools-slice-a` | `3a6b54c` | #3 timezone + #5 CSV + #4 diagnosis (final commit `3a6b54c` = black remediation) |
| `feat/admin-data-tools-slice-b` | `8704e75` | #6 membership accordion (rebased onto slice-a) |
| `feat/admin-data-tools-slice-c` | `b3193c7` | #1 DB export + #2 remote backup + Settings button (rebased onto slice-b) |

Push / PR opening is **pending user decision** — see Outstanding.

## Final Evidence (post-remediation, orchestrator-run)

> These numbers supersede the `verify-report` snapshot. The snapshot was taken at slice-c
> `a6cc21c` BEFORE the W-1 black fix landed; the orchestrator re-ran the full suite after
> remediation and the numbers below are the final authoritative counts.

| Gate | Result |
|------|--------|
| Backend pytest | **98 / 98 pass** (exit 0) |
| Frontend vitest | **42 / 42 pass** (exit 0) |
| `black --check .` | **99 files clean** (W-1 REMEDIATED in `3a6b54c` + rebase; all 3 slice tips black-clean) |
| `tsc --noEmit` | clean |
| `eslint --max-warnings 0` | clean |
| `flake8 .` | clean (exit 0, empty) |
| `mypy .` | clean (exit 0) |
| Requirements compliant | **12 / 12** |
| Scenarios compliant | **18 / 18** |
| Critical findings | **0** |

Slice-c tip at archive: `b3193c7` (cumulative chain A→B→C).

## Warnings (accepted, non-blocking)

- **W-1 — black formatter regression: REMEDIATED.** The `verify-report` snapshot (slice-c `a6cc21c`) flagged `backend/api/sales.py` + `backend/api/settings.py` as would-be-reformatted and predicted CI `black --check .` failure. **Final state** (rank 3): fix landed in slice-a commit `3a6b54c` (`style(sales,settings): black formatting for CI compliance`), slices B and C were rebased onto the fixed slice-a, and the orchestrator re-ran `black --check .` post-remediation → **99 files clean across all three slice tips**. CI will not fail on black for any of the three slices. The snapshot's "must be fixed before merge" status is satisfied.
- **W-2 — SMB password visibility in process list (inherent).** `remote_push.sh push_smb` uses `smbclient -U "${user}%${pass}"`, visible via `ps` to other users. Inherent to smbclient's `-U` syntax. No secret reaches the log (output redirected; log-grep test passes). Design recommends rsync-first; SMB is fallback. Non-blocking.
- **W-3 — pre-existing i18n debt in `Reports.tsx` (out of scope).** Hardcoded Spanish fragments (`"acumulado"`, `"activas / total"`) exist in pre-existing metrics labels. The export button added by this change uses `t.reports.exportReport` correctly. Pre-existing; surfaced because we touched the file. Accepted as non-blocking hygiene debt.

## Suggestions (documented, non-blocking)

- **S-1 — legacy `COLOMBIA_TZ` constants retained** in `events.py`, `dashboard_service.py`, `report_window.py` as documented backward-compat fallbacks. Design explicitly keeps them; all production callers now pass `db` → `get_app_tz`. Could be removed later.
- **S-2 — `backup.sh` config-tar naming inconsistency.** Still references `powerhouse-backend.service` (prod path) with `|| true`; pre-existing naming inconsistency with the new `powerhouse-backup.*` units and `install.sh`'s `facegym-*` naming. Out of scope; noted.

## Size / review budget

- Slice C diff vs chain parent: **~1060 changed lines** (1023 insertions / 37 deletions) — above the 800-line per-slice ceiling. Driven by thorough threat-matrix test suite (493 ln tests) + `backup.sh` near-total rewrite.
- **User-accepted `size:exception`** for slice C (documented).
- Cumulative chain: 3206 ins / 200 del across 47 files.

## Deviations from design (both match spec text)

1. **Audit-in-generator-`finally`** (DB export): audit fires only on `returncode == 0` after full stream, in the generator's `finally`. Spec says "for every successful download" — consistent.
2. **Per-transport env keys** (remote backup): spec says creds "sourced from `.env`"; per-transport vars (`RSYNC_*`/`SMB_*`/`NFS_MOUNT`) are env-only. Consistent.

## Gates passed before archive

- **Task Completion Gate**: 17 / 17 tasks `[x]` in `tasks.md` (A.1–A.9, B.1–B.2, C.1–C.6). No stale unchecked implementation tasks.
- **Critical Findings Gate**: 0 critical findings in `verify-report.md`.
- **Action Context Guard**: no `workspace-planning` constraint; archive operations stayed inside `openspec/`.

> **Native Review Receipt Gate**: not applicable for this change — no native review
> (`review/{transaction,ledger,receipt,gate-context}`) was created for `admin-data-tools`;
> the project's SDD workflow for this change did not exercise the native review pipeline.
> The orchestrator's authoritative launch facts ("Attempt ledger: complete", "all
> implementation and verification COMPLETE") stand as the terminal delivery receipt.

## Outstanding (post-archive)

1. **Push / PR decision — pending with user.** Three local-only feature-branch-chain slices (`-slice-a` / `-slice-b` / `-slice-c`) plus the `feature/admin-data-tools` tracker have NOT been pushed. PR opening and push timing are the user's call. CI has not yet run on any of these commits.
2. **Feature #4 — stale LXC build remediation.** The user-facing "custom range not visible" symptom is a stale deployed build on the LXC, not a code defect. The rebuild+redeploy procedure is documented in `docs/deployed-build-diagnosis.md`. Until the LXC is rebuilt, the deployed instance will still show the symptom despite the code being correct in the chain.
3. **`rsync` not installed on this container.** Slice C #2 manual verification of the remote-failure path was triggered by rsync-missing rather than unreachable-host; the SAME warn code path was exercised as the unit test (mock rsync exit 23). On prod, install rsync (or use smb/nfs).

## Pre-existing issues (out of scope, surfaced during this work)

- **Backend pytest requires exporting `backend/.env`.** `conftest.py` lacks dotenv loading; `pytest tests/` from the backend dir fails on missing env unless `set -a && . ./.env && set +a` is run first. Documented in the `verify-report` test_command; pre-existing, not introduced by this change.
- **`backup.sh` config-tar naming inconsistency** (see S-2 above).
- **Pre-existing hardcoded ES strings in `Reports.tsx`** (see W-3 above).

## Specs synced to source of truth

| Domain | Action | Details |
|--------|--------|---------|
| `sales-reporting` | Created `openspec/specs/sales-reporting/spec.md` | 4 requirements (2 from delta ADDED, 2 from delta MODIFIED — collapsed into single `## Requirements` section; "(Previously: …)" notes preserved as historical context) |
| `membership-history` | Created `openspec/specs/membership-history/spec.md` | 2 requirements (delta ADDED) |
| `admin-database-export` | Created `openspec/specs/admin-database-export/spec.md` | 3 requirements (delta ADDED) |
| `remote-backup` | Created `openspec/specs/remote-backup/spec.md` | 3 requirements (delta ADDED) |

Main specs tree was empty prior to this archive; all 4 domains are brand-new source-of-truth specs. Delta `ADDED Requirements` / `MODIFIED Requirements` wrappers were normalized to a single `## Requirements` heading in each main spec; requirement blocks and scenarios are verbatim from the deltas.

## SDD Cycle

Complete. Change has been planned (`proposal`, `exploration`, `spec`, `design`), broken down (`tasks`), implemented (`apply-progress` #72), independently verified (`verify-report` #75 + on-disk `verify-report.md`), and archived (this document). Ready for the next change.
