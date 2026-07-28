# SKILL.md — FaceAPP domain knowledge

> Project-specific expertise an agent needs to do good work here. Not a clone
> of the global skill system; this is the domain layer for FaceAPP itself.
> Start with [AGENTS.md](./AGENTS.md) for orientation.

## Domain primer

FaceAPP solves physical access control for membership businesses (gyms, clubs).
The deployment model is a **front-desk kiosk**: a dedicated PC with a camera
points at the entrance. A member walks up, the camera recognizes their face,
and the system grants entry (green glow, 3s auto-reset) or denies it (red glow)
based on current membership status. Staff use a separate admin dashboard for
member CRUD, membership plans, payment tracking, sales reports, and camera
setup.

The system handles: biometric enrollment (1 photo → 6 averaged FaceNet
embeddings, stored AES-256-GCM encrypted), membership plans with auto-expiring
dates, partial cash/transfer payments, automated email reports every 2 hours,
and Wompi online payment integration via a customer portal. Since 2026-07-28 it
also handles its own **data safety**: 30-minute automated backups with optional
remote replication, an audited admin full-DB export, and timezone-correct sales
reporting with server-side CSV export. Target region is **Colombia (UTC-5)**,
which drives both timezone handling and the Habeas Data legal regime (Ley
1581/2012) for biometric data — see [SECURITY.md §4](./SECURITY.md).

## Architecture

Three services behind Nginx, on a Proxmox LXC container:

```
Browser (Admin SPA / Kiosk) ──HTTPS──▶ Nginx ──┬──▶ Backend :8000 (FastAPI)
                                               │       ├── PostgreSQL :5432
                                               │       └── Redis :6379
                                               └──▶ cv_service :8001 (FastAPI + OpenCV + FaceNet)
                                                       └── RTSP cameras (LAN)
```

- **Backend** owns the public `/api` surface. FastAPI + SQLAlchemy 2 + Alembic
  + Redis. JWT auth (HS256, Redis blacklist), per-page RBAC, AES-256-GCM
  biometric encryption, Wompi webhook handling, APScheduler email reports,
  admin system endpoints (`/api/system/*`) for DB export and backup-config.
- **Frontend** is a single React/Vite SPA serving two roles: the admin
  dashboard and the `/kiosk` terminal. Talks to backend over REST (TanStack
  Query) and to cv_service over WebSocket (kiosk USB-camera frames).
- **cv_service** runs face recognition. Consumes RTSP streams (direct) or
  browser WebSocket frames (USB camera relayed via the kiosk), runs MTCNN
  detection + FaceNet recognition, posts access events to the backend, and
  serves an MJPEG stream for the admin camera monitor. Never exposed to the
  internet — Nginx denies `/api/cv/` externally (see
  [SECURITY.md §6](./SECURITY.md)).

Communication: **REST** for all admin/auth/config, **WebSocket** for the kiosk
real-time frame stream (`/cv/ws/camera/{id}`), **MJPEG over HTTP** for the
camera monitor view.

## Backup subsystem

Added 2026-07-28 (SDD cycles `admin-data-tools` + `remote-backup-config-ui`).
Design model: **local-first, warn-only remote**.

```
powerhouse-backup.timer (every 30 min, Persistent)
        │
        ▼
powerhouse-backup.service (root, EnvironmentFile=/opt/powerhouse-membership/.env)
        │
        ▼
scripts/backup.sh ── 1. source .env (set -a)
                     2. source /etc/faceapp/backup-remote.env  ← WINS over .env
                     3. pg_dump -F c  (BACKUP_DATABASE_URL ?? DATABASE_URL)
                     4. tar biometric_data + config, checksums, manifest
                     5. bash remote_push.sh   ← WARN-ONLY; exit ignored
                     6. local retention ALWAYS runs (30 days)
```

- **Two-layer config**: `.env` is the headless fallback; the admin UI writes
  `/etc/faceapp/backup-remote.env` (0600, root:root, atomic temp+`os.replace`)
  via `backend/services/backup_config.py`. Managed file wins because
  `backup.sh` sources it second.
- **Remote push is never fatal**: `remote_push.sh` returns non-zero on failure;
  `backup.sh` logs one sanitized line and continues. Local backup + retention
  always succeed. Transports: `none|rsync|sftp|ftp|smb|nfs`.
- **No credential ever touches argv, logs, or stdout**: SFTP uses
  `sshpass -e` + a temp batch file; FTP uses a temp 0600 `--netrc-file`;
  SMB interpolates the password only into `-U user%pass`. FTP is documented
  as cleartext.
- **UI path**: Settings → Backup tab (`SettingsBackupTab.tsx`) →
  `GET/PUT /api/system/backup-config` + `POST /api/system/backup-config/test`.
  Password is write-only (AES-256-GCM in DB, masked GET via `has_password`,
  keep-sentinel on empty input); the test probes with a real 1-byte file
  through `remote_push.sh` in a 20s timeout and returns a sanitized message.
- **Admin export**: `GET /api/system/db-export` streams `pg_dump -F c`
  (argv-list, `PGPASSWORD` env-only, `require_admin`, audit-logged) and ALSO
  prefers `BACKUP_DATABASE_URL` (PR #15).

### RLS vs pg_dump — the dedicated-role pattern

The DB has **Row-Level Security on 9+ tables** (portal security). The runtime
role (`backend_app`) is therefore structurally unable to `pg_dump` a complete
database — RLS silently filters rows. Fix pattern:

1. Dedicated role `powerhouse_backup` with `BYPASSRLS` + `pg_read_all_data`.
2. Credentials root-only in `/etc/faceapp/backup-db.env` (0600), exported as
   `BACKUP_DATABASE_URL`.
3. Every dump path (timer backup AND admin UI export) prefers
   `BACKUP_DATABASE_URL` over `DATABASE_URL`.

If a backup or export ever comes out suspiciously small/empty, check which URL
was used before assuming code bugs.

## Timezone service model

Reports previously hardcoded `America/Bogota` / `timedelta(hours=-5)` at three
sites (commits `f031ed1`, `b18cd3c`, `85cf905`). That was replaced by
`backend/services/timezone.py`:

- `get_app_tz(db)` returns a DST-aware `ZoneInfo` for the configured IANA
  timezone. Cached in Redis (key `app:tz`, TTL 300s); write paths on settings
  save call `invalidate_app_tz_cache()`, so a timezone change takes effect
  without a restart.
- `services/report_window.py` builds the report window —
  `[start 00:00, end+1 00:00)` in the app timezone, converted to UTC for the
  query. Persistence stays UTC; DST rules are handled by ZoneInfo.
- Consumers: dashboard service, events bucketing, sales report window, CSV
  export (same window as the on-screen report), and `SalesList` which renders
  date+time via `Intl.DateTimeFormat({timeZone})` with the configured zone.

Rule: **any new date/reporting logic uses `get_app_tz(db)`** — never a fixed
offset and never naive `datetime.utcnow()` for "today".

## Kiosk state machine

The kiosk (`frontend/src/pages/Kiosk/Kiosk.tsx`) is the highest-risk surface in
the repo. It has two camera modes:

- **USB mode** — the browser captures frames from a local webcam and relays
  them to cv_service over WebSocket. Drives `connectionStatus` state.
- **Remote/MJPEG mode** — cv_service pulls an RTSP stream directly; the browser
  just watches the MJPEG output. `connectionStatus` is NOT touched in this mode.

Recognition lifecycle:

```
camera connect → frame → recognition event → granted | denied → 3s auto-dismiss → idle
```

State that an agent editing this file MUST understand:

- `connectionStatus` defaults to `'disconnected'` and is only mutated by the USB
  code path. Any UI guard keyed on it must be scoped with `!usbMode || (...)`
  or it will hide the guide permanently in MJPEG mode.
- The USB error overlay must trigger on BOTH `connectionStatus === 'error'` AND
  `connectionStatus === 'disconnected'` because `onerror` and `onclose`
  ordering is not guaranteed (`Kiosk.tsx:807`).
- The guide-suppression guard (`Kiosk.tsx:861`) combines the two checks above.
- Recognition has its own `recognitionState` (`idle | verifying | granted |
  denied`) separate from connection state. Do not conflate them.

The retry-overlay, concurrent camera-start race, and check-in name leak were
all fixed in PR #2 (commit `b26c45c`). See
[Memorable bugs](#memorable-bugs) and the [review discipline](#review-discipline)
section.

## i18n model

All user-visible strings live in `frontend/src/i18n/translations.ts` as a
nested object under `es` and `en`. Access pattern: `t.<section>.<key>`, e.g.
`t.kiosk.connected`, `t.nav.members`. The active language is controlled by
`LanguageContext.tsx`.

Rules:
- **No hardcoded strings** in JSX for anything user-visible — not even a single
  word. Always go through `t.*.*`.
- When you add a key, add it under BOTH `es` and `en`. An incomplete key will
  render as `undefined`.
- No automated check enforces this. Regressions have shipped before (fixed in
  commit `b26c45c`). Review i18n coverage manually in every PR that touches UI.

## SDD workflow

This project uses **Spec-Driven Development**. Config:
[`openspec/config.yaml`](./openspec/config.yaml). The change lifecycle:

```
explore → proposal → specs → design → tasks → apply → verify → archive
```

Artifacts for each change live in `openspec/changes/<change-name>/`:
`proposal.md` (intent, scope, risks, rollback), `design.md` (architecture
decisions, data flow, threat matrix), `tasks.md` (phased, TDD RED/GREEN/REFACTOR
checklist with PR-forecast workload). Strict TDD is enabled (`config.yaml`):
write failing tests first, then implement, then refactor. Review budget is 800
changed lines per PR; chained PRs are auto-forecast when a change exceeds it.

Cycle state:

- **Archived 2026-07-28**: `admin-data-tools` (12/12 reqs, PRs #7–#10) and
  `remote-backup-config-ui` (11/11 reqs, 1 requirement formally MODIFIED —
  "Environment-Only Remote Credentials" now permits DB-encrypted passwords —
  PRs #11–#14). Their accepted requirements live as 5 capability specs in
  [`openspec/specs/`](./openspec/specs/) (sales-reporting, membership-history,
  admin-database-export, remote-backup, backup-remote-config). Terminal
  records: each archive folder's `archive-report.md`.
- **Still active**:
  [`membership-report-kiosk-tunnel`](./openspec/changes/membership-report-kiosk-tunnel/)
  — Phases 1–3 implemented (PRs #1 and #2); Phases 4–5 (portal security,
  deployment prereqs) remain —
  [tasks.md](./openspec/changes/membership-report-kiosk-tunnel/tasks.md).

## Review discipline

FaceAPP has been through adversarial 4-lens review (risk / reliability /
resilience / readability). The canonical case study for why this matters:

- **PR #1** shipped the membership-display/kiosk feature with NO review
  (`114d0ee`). Post-hoc review found **3 CRITICAL + 1 WARNING** issues.
- **PR #2** (`2213bee`, commits `96bb59f` + `b26c45c`) fixed them in two TDD
  rounds (RED → GREEN), then a 4-lens pass surfaced **2 more CRITICAL**
  regressions that the focused fix rounds missed.
- Lesson: focused TDD fixes one layer of bugs; adversarial review catches the
  ones that span layers. Do not skip either.

Before merging kiosk, security, payment, or biometric changes, run the matching
tests (see [AGENTS.md Test commands](./AGENTS.md#test-commands)) AND read the
relevant section of [SECURITY.md](./SECURITY.md).

## Memorable bugs

These are the non-obvious gotchas. Each has bitten the project once; do not
re-introduce them.

- **WebSocket onerror/onclose ordering** (`b26c45c`) — the USB error overlay
  vanished intermittently because the handler only checked `error`. Fix: check
  both `error` and `disconnected` states. See `Kiosk.tsx:807,861`.
- **Concurrent camera-start race** (`b26c45c`) — starting the camera while a
  previous start was in-flight froze the kiosk. Guard with an in-flight flag.
- **Check-in name leak** (`b26c45c`) — denied/unknown members' names were
  leaking into the recognized-member surface. Access-denial paths must not emit
  identity.
- **Fixed-offset timezone hardcodes** (`f031ed1`, `b18cd3c`, `85cf905`) —
  naive UTC math and `timedelta(hours=-5)` produced wrong "today" boundaries
  and 29-day memberships. Root fix was a service, not another site patch: see
  [Timezone service model](#timezone-service-model).
- **CV API key propagation** (`32a30db`) — after enrollment the backend
  notified cv_service without the `X-API-Key` header; the notification silently
  failed. Any change to the enrollment → CV notification path must keep the
  header (see `notify_cv_invalidation`).
- **Display vs access predicate** (SDD design, PR #2) — using a single shared
  query for "show latest expiration" and "grant access" caused early entry
  before `start_date`. These MUST stay split (see
  [design.md](./openspec/changes/membership-report-kiosk-tunnel/design.md)).
- **The decorative export button** (2026-07-28, PR #7 chain) — the Reports
  "Export" button rendered but had **no `onClick` handler at all**. Looked
  fine, did nothing. Now wired to `GET /api/sales/report/export` (CSV blob →
  object URL → anchor). Lesson: a UI control is not a feature until the
  request round-trips.
- **The 3-month-stale bundle "bug that wasn't code"** (2026-07-28) — custom
  date-range reporting "didn't work" on the dev LXC, but the code had been
  correct since PR #1: the deployed static bundle was three months old. Never
  debug the source for symptoms on a deployed build — run the 4-step staleness
  protocol in `docs/deployed-build-diagnosis.md` (diff dist mtime → grep the
  minified bundle for a feature marker → verify count → rebuild+redeploy).
- **env-sensitive argv assertion** (PR #15 chain) —
  `test_password_not_in_argv` passed locally and failed in CI because the
  assertion effectively depended on ambient environment (a password value that
  only exists when the local `.env` is loaded). Tests touching process argv or
  env must be hermetic: inject the value explicitly, don't read the real
  shell environment.
- **smbclient preflight ordering** (2026-07-28, `remote_push.sh`) — on a
  fresh install without `samba-client`, the SMB transport would emit an opaque
  `command not found` AFTER building the `-U user%pass` argv — risking the
  password-bearing argument landing in the log. The preflight
  `command -v smbclient` check runs FIRST and the warning names the exact
  package to install. Keep that ordering when touching the SMB path.
- **RLS swallowed the first backup attempt** (2026-07-28, PR #15) — the very
  first real timer run produced an unusable/empty dump because pg_dump ran as
  the RLS-restricted runtime role. Root fix: dedicated `BYPASSRLS` role +
  `BACKUP_DATABASE_URL` (see [RLS vs pg_dump](#rls-vs-pg_dump--the-dedicated-role-pattern)).
  Symptom signature: dump succeeds but has almost no rows.
