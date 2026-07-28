# Proposal: Admin Data Tools

## Summary

Secure exports, recovery, reporting.

## Motivation and Scope

| # | Problem → outcome |
|---|---|
| 1 | No full DB export → fresh, audited, admin-only custom-format dump. |
| 2 | Manual local backups → 30-minute remote SMB/NFS/rsync replication. |
| 3 | Saved timezone is ignored → configured IANA-zone report windows and sales timestamps. |
| 4 | Custom range exists in `main` but is unavailable to users → diagnosed, remediated deployed flow. |
| 5 | Export button is inert → full-range server CSV download. |
| 6 | Memberships form a long flat list → two visible, older actionable rows collapsed. |

### Goals
- Secure operations and consistent timezone/range behavior without losing actions.

### Non-Goals
- Stored remote secrets, UTC schema changes, backup rewrite, new filters, pagination, or picker redesign.

## Capabilities

### New Capabilities
- `admin-database-export`: audited dumps.
- `remote-backup`: scheduled replication.
- `sales-reporting`: timezone, ranges, CSV.
- `membership-history`: collapsible records.

### Modified Capabilities
None.

## Approach

| # | Decision |
|---|---|
| 1 | Stream request-time `pg_dump -F c`; enforce admin; audit; add Settings action. |
| 2 | Extend `scripts/backup.sh`; preserve retention; source `.env`; install systemd timer. |
| 3 | Add cached `get_app_tz(db)` with `ZoneInfo`; replace fixed offsets; format UI timestamps. |
| 4 | Compare deployment with `main`; inspect query flow; rebuild if stale. |
| 5 | Reuse `build_report_window` and frontend `reportRange`; wire button download. |
| 6 | Partition existing sort into two rows plus MUI Accordion; preserve actions and bilingual i18n. |

## Risks

| Risk | Mitigation |
|---|---|
| DST arithmetic | Test `America/Santiago` half-open windows. |
| Biometric dumps | Admin-only, audit, TLS, secured NAS. |
| LXC I/O | Preserve retention; monitor IOPS. |
| Settings N+1 | TTL cache with invalidation. |
| #5 depends on #3 | Land together; share window logic. |
| Stale build for #4 | Diagnose before coding; verify deployment. |

## Rollback Plan

Revert slices independently; disable remote timer; remove routes/actions; retain UTC storage and local backups.

## Success Criteria

- [ ] #1 Fresh dump restores; non-admin fails; audit exists.
- [ ] #2 Remote timer succeeds; secrets stay in `.env`; retention works.
- [ ] #3 Backend/UI honor configured zones and DST.
- [ ] #4 Dropdown → dates → query → results works after proven remediation.
- [ ] #5 CSV matches displayed range and timezone.
- [ ] #6 Two newest stay visible; older rows retain actions.

## PR Slicing

- **A:** #3 timezone, #4 diagnosis/fix, #5 CSV.
- **B:** #6 accordion.
- **C:** #1 DB export, #2 backup/systemd; security-focused review.
