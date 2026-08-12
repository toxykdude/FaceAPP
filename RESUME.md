# RESUME.md — How to pick up where we left off

> An agent reads this when resuming work after a gap. Concrete and actionable;
> no philosophy. For state, see [STATUS.md](./STATUS.md).

## Production upgraded to `b3017c0` (2026-08-12, latest)

Production LXC 114 went from `0ca361d` to `b3017c0` — **15 commits**, covering
membership payment enforcement, RBAC page-permission capabilities, the
migration-role work, and the backup fixes (#71/#72).

**Database was preserved and proven so.** Pre-upgrade dump
`/var/backups/powerhouse-deploy/membership_db_PREUPGRADE_20260812T212611Z.dump`
(10,647,181 bytes, `pg_restore -f /dev/null` rc=0, 14 `TABLE DATA` entries,
sha256 recorded alongside it). Row census identical before and after:

```
members=1004 memberships=2862 biometric=540 sales=2887 users=3
```

Rollback tree: `/opt/deploy-rollbacks/0ca361d-20260812T212611Z` (1.8M — tracked
files plus the previous `dist`, deliberately excluding the 7.2G of venvs and
`node_modules`). It holds the old bundle `index-B2CpWa1v.js`.

What made this deploy low-risk, established before touching anything:
- **No dependency changes.** `backend/requirements.txt`, `cv_service/requirements.txt`,
  `frontend/package.json` and the lockfile are all byte-identical across the
  delta, so no pip/npm install was needed and `node_modules` stayed valid.
- **One migration**, `7c6d5e4f3a2b`, a single `CREATE INDEX` on
  `sales_transactions(membership_id)`. No data modified, and its
  `down_revision` matched the deployed revision exactly.
- **The clone's 3 "dirty" files were already upstream.** `/opt/faceapp` had
  local modifications to `backend/schemas/sale.py`,
  `frontend/src/utils/dateTime.ts` and `frontend/src/pages/Reports/Reports.tsx`
  — timezone hotfixes applied to the host and later committed. All three were
  verified **byte-identical to `main`** (md5) before `git reset --hard`, so the
  reset discarded nothing. **Always check this before resetting that clone.**

**Migrations ran as `membership`, NOT as `powerhouse_migrator`, on purpose.**
Prod's 14 tables are owned by `membership`, which is the role **cv_service**
connects as (`cv_service/.env`). Running `002_migration_role.sql` would have
reassigned every table away from it, and 002 re-grants DML to `backend_app` and
`backend_readonly` but **not** to `membership` — which would have broken
cv_service. So DDL was run as the existing owner via
`MIGRATE_DATABASE_URL=<cv_service DATABASE_URL>`; ownership is unchanged
(`membership owns 14`) and cv `/health` returned 200 afterwards.
**Consequence: prod still has no migrator role.** The next DDL migration needs
that decision made deliberately — either grant `membership` back its DML inside
a modified 002, or keep using the owner role.

Deploy mechanics (trap 14, followed exactly):
1. `rsync -a --delete /opt/faceapp/frontend/dist/ …/frontend/dist/` — scoped so
   the stale hashed asset is removed. Dry-run showed exactly one deletion.
2. `rsync -a --exclude '.env*' --exclude '.git' --exclude 'node_modules'
   --exclude 'venv' --exclude '__pycache__' /opt/faceapp/ /opt/powerhouse-membership/`
   — **no `--delete`**. Dry-run confirmed 0 deletions, no venv/`node_modules`/`.env`
   touched. `biometric*` is NOT excluded, deliberately.

Post-deploy verification: all five units active; `/api/health`, `/api/health/db`
and `/` all 200; `db-export` unauthenticated 401; the **served** HTML references
`index-CHo24Ijd.js` and that bundle contains `Saldo pendiente` /
`el miembro NO podrá entrar` which the old bundle did **not** (`new=1 old=0`) —
the staleness protocol in `docs/deployed-build-diagnosis.md`; `require_any_page`
present in `deps.py` and used by members/membership_plans/memberships/sales;
zero error-level journal lines; and a full backup run afterwards produced a
verified 10,647,656-byte dump plus 529 photos.

**`.env` is still unquoted on prod (trap 13/22).** `set -a; . ./.env` aborts on
line 17 (`usmm: command not found`). Alembic does not need it — pydantic-settings
parses the file itself; only `MIGRATE_DATABASE_URL` must be exported.

## Production backup provisioning (2026-08-12)

**Production LXC 114 now takes real, verified backups every 30 minutes.** It
never did before this date: no `powerhouse_backup` role, no
`powerhouse-backup.timer`, no `/etc/faceapp/`, no `/var/backups/powerhouse`.

This was a **targeted backup deployment, NOT a full application deploy.** Only
these were changed on the host — the application otherwise still runs the code
it ran before:

| Changed on LXC 114 | |
|---|---|
| `scripts/backup.sh`, `scripts/restore.sh`, `scripts/migrations/003_backup_role.sql` | copied from main |
| `backend/api/system.py` | copied from main (was byte-identical to the pre-change baseline, so a clean drop-in) |
| `/etc/systemd/system/powerhouse-backup.{service,timer}` | installed |
| `powerhouse-backup.service.d/override.conf` | `EnvironmentFile` → `backend/.env` (prod has no `/opt/powerhouse-membership/.env`) + `-/etc/faceapp/backup-db.env` |
| `facegym-backend.service.d/backup-db-env.conf` | `EnvironmentFile=-/etc/faceapp/backup-db.env` |
| Postgres | `powerhouse_backup` role created |
| `/etc/faceapp/backup-db.env` | written 0600 root:root |

**`/opt/faceapp` (the canonical clone) was NOT touched and is still stale/dirty
at `e43f243` with 3 modified files.** `.deployed-sha` still reads `0ca361d`,
which remains accurate for the application — do not treat this entry as an app
deploy.

Verified after deployment:
- backup role: `rolinherit=t`, `rolbypassrls=t`, `rolsuper=f`, member of
  `pg_read_all_data` with `inherit_option=true`;
- read-only proven live: `DELETE` / `INSERT` / `TRUNCATE` → permission denied,
  `DROP` and `ALTER TABLE ... DISABLE ROW LEVEL SECURITY` → must be owner;
- first scheduled run: dump **10,645,292 bytes**, `pg_restore -f /dev/null`
  rc=0, 14 `TABLE DATA` entries; face archive **529 photos**, matching the 529
  files on disk; `snapshots/` correctly excluded;
- timer enabled and armed; `facegym-backend` restarted, `/api/health` 200,
  `BACKUP_DATABASE_URL` present in the service process environment.

Pre-deploy safety artifacts on the host (`/var/backups/powerhouse-deploy/`,
0700 root): `membership_db_predeploy_20260812T204257Z.dump` (10,644,828 bytes,
read-through verified) plus `.bak` copies of the previous
`facegym-backend.service`, `backup.sh`, and `api/system.py`.

**Still unverified:** an authenticated round trip through
`/api/system/db-export`. Prod enforces session-bound tokens, so a synthetically
minted admin JWT is rejected with `Session has been revoked`, and no admin
password was used. The underlying mechanism is proven (the same role, same
binary, produces a complete 10.6 MB archive) and the env var is in the process,
but **click Export DB once in the UI to close the loop** — a successful export
now writes an `audit_logs` row with `action='db_export'`, so
`select * from audit_logs where action='db_export' order by created_at desc limit 1`
confirms it.

**Remote replication is OFF on prod** (`BACKUP_REMOTE_TYPE=none`): backups are
local-only, on the same host as the database. Configure a remote target in
Settings → Backup before treating this as disaster recovery.

Production is **15 commits behind `main`**, including RBAC page-permission and
membership-payment-enforcement work. That is a separate deployment decision and
was deliberately not taken here.

## Production deployment handoff (2026-07-30, earlier)

Production LXC 114 is running exact SHA
`946c605cf0ca1dcd2ec4b123a8043993a12345a5` (PRs #29+#30 — the remote-backup
fixes). Deployed from canonical clone `/opt/faceapp` to runtime copy
`/opt/powerhouse-membership`, marker `.deployed-sha` updated.

Verified: backend `/api/health` and `/api/health/db` 200, authenticated CV
`/health` 200, frontend HTTP 200, all services active, `nginx -t` valid, zero
error-level journal lines after restart, and the served `index.html` referencing
the new `index-CrN45nRN.js` **with the PR #29 strings actually present in it**.
Alembic was already at head `f0786144f6c0`; PR #29 adds no migration.

Rollback: `/opt/deploy-rollbacks/873e51b-20260730T181056Z` (tracked tree +
`dist`; venv/node_modules excluded deliberately — a full copy would have
exceeded the 4.5G free space). Pre-deploy dump:
`/var/backups/powerhouse-deploy/membership_db_predeploy_20260730T181056Z.dump`,
verified with `pg_restore -l` at 14 table-data entries. Note `pg_restore -l`
must run as root — `/var/backups/powerhouse-deploy` is `0700 root:root`, so the
`postgres` user cannot traverse it and reports a misleading permission error.

The native release gate returned `invalidated` / `allowed: false` /
`action: explicit-maintainer-action` (denial `receipt_unrelated`: the code was
already merged, so no terminal receipt governs the deployed candidate). NOT a
PASS. The maintainer authorized deployment explicitly after being shown the gate
requirement; the exception is scoped to this candidate and LXC 114 only.

**DEV (DEVFaceApp, LXC 124 — reach it as `ssh faceapp`; the address of record is
the STATUS.md host table) is also on `8651568`**, deployed
the same way and verified identically (health 200s, authenticated CV 200,
services active, zero error-level journal lines, new bundle served with the PR
#29 strings in it). Rollback `/opt/deploy-rollbacks/873e51b-20260730T182450Z`,
dump `.../membership_db_predeploy_20260730T182450Z.dump` (14 table-data
entries). DEV already had `sshpass`/`smbclient`, so its Backup-tab failure was
purely the PR #29 bugs, not missing tooling.

The `ssh faceapp` alias had vanished from `~/.ssh/config` and its address was
recorded nowhere; both hosts are now in the STATUS.md host table and the alias
is restored locally.

**DEV addressing is settled as of 2026-08-12.** A DHCP reservation pins
DEVFaceApp to `10.162.36.52`, ending the `.101`/`.105` churn that had this file
and STATUS.md contradicting each other. `~/.ssh/config` points `faceapp`,
`faceapp-dev` and the historical `faceapp-dev-105` at `.52`, all verified
answering `hostname` = `DEVFaceApp`. Prefer the alias over any literal IP in
these docs — earlier sections quote the address that was live when they were
written, and only the STATUS.md host table is maintained.

## Previous production deployment (2026-07-30, `873e51b`)

Production LXC 114 was running exact SHA
`873e51b54450cd13143f9deaa41e8f9d43522e8a`. The canonical clone is
`/opt/faceapp`; the Nginx/runtime copy is `/opt/powerhouse-membership`.
Verification passed for checksum parity, frontend and kiosk HTTP 200, backend
basic/DB/full health 200, authenticated CV health 200, active application and
data services, valid Nginx configuration, and zero fresh error-level journal
lines.

The native release gate returned `delivery-derivation/unavailable`, not PASS.
Deployment proceeded under the maintainer's explicit exception scoped only to
this candidate and production LXC 114. The later independent verification found
two missing tracked OpenSpec files; restoring those files and the later,
separately authorized tracked non-secret `.env.example` produced 258/258 tracked
paths with zero content/mode drift.

Rollback code/frontend/runtime files from
`/opt/deploy-rollbacks/preprod-20260730T014157Z`. The pre-deploy database dump
`/var/backups/powerhouse-deploy/membership_db_predeploy_20260730T014157Z.dump`
was verified with `pg_restore -l` and contains 14 table-data entries. No Alembic
migration was required; production was already at `f0786144f6c0` head.

Direct SSH uses local alias `faceapp-prod-114` and dedicated key
`/root/.ssh/faceapp-prod-lxc114_ed25519`. Production does not currently have the
shipped `powerhouse-backup.service` or `.timer` installed. Provision a safe
full-database backup role/config before installing and enabling those units;
do not point the timer at an RLS-restricted runtime role.

## Historical DEV handoff (2026-07-29)

The latest recorded DEVFaceApp deployment is PR #28 at exact SHA
`873e51b54450cd13143f9deaa41e8f9d43522e8a`, with rollback
`/opt/deploy-rollbacks/873e51b5445-20260729T225619Z`. The following PR #19
notes are retained as an earlier verified DEV milestone; its rollback is
`/opt/deploy-rollbacks/bb6a859-20260729T091230Z`.

Verification passed: frontend 200, backend health 200, authenticated CV health
200, and required services active. DEV Nginx exposes `/cv/stream/` and
`/cv/ws/` with WebSocket upgrade handling; a configured camera UUID returned
HTTP 200 `multipart/x-mixed-replace` and timed out at the bounded probe instead
of returning 404.

Remaining checks: the outer Nginx Proxy Manager could not be inspected, and the
kiosk still needs manual browser confirmation. The frontend build completed on
Node 18 with an npm engine warning; upgrade the DEV build runtime before that
warning becomes a hard toolchain requirement.

## Remote-backup session (2026-07-30)

Goal was narrow — "Test connection does nothing" — and it uncovered three
separate defects plus a provisioning gap. Sequence, because the order is the
lesson:

1. **The UI swallowed every error.** `SettingsBackupTab.tsx` gave both
   mutations an `onSuccess` and no `onError`, so a rejected request left
   `testResult` null and the button looked dead. The console 400 was the only
   evidence.
2. **The 400 was correct.** `POST /system/backup-config/test` sends no body and
   probes the **stored** config; nothing had been saved, so the transport was
   `none` → `nothing to probe`. Fixed by disabling **Test** while the form is
   dirty or the stored transport is unprobeable, and stating which. The saved
   baseline is adopted from the PUT **response** (the backend normalizes smb
   shares and default ports) — baselining the request would strand the form as
   permanently dirty. That trap is pinned by a regression test.
3. **Production had neither `sshpass` nor `smbclient`.** LXC 114 was
   provisioned by copying the tree, so `install.sh` never ran its dependency
   lines. Installed (client packages only, no samba daemon).
4. **SFTP had never worked, on any host.** `remote_push.sh` passed
   `-b "$batch"` *after* the `user@host` destination; `sftp` stops parsing
   options at the first non-option argument, so it exited with a usage error
   every time. The mocked `sshpass` in the test suite records argv without
   exec'ing a real `sftp`, which is exactly why it stayed invisible. Fixed and
   pinned by `TestSftpArgvOrder`.
5. **Added a controlled SSH reason vocabulary** (`_SSH_REASONS`) mirroring the
   existing `NT_STATUS_*` map, because the sanitized message scrubs the host and
   left "Host key verification failed" as an unactionable bare warning.

Verified: backend 150 passed (black/flake8/mypy clean), frontend 73 passed,
`bash -n` clean, and sandboxed SMB + SFTP probes run against real tooling on
LXC 114 without touching deployed backups.

Deliberately NOT done: `StrictHostKeyChecking` was not relaxed. These transfers
carry full database dumps, so an untrusted host key stays a failure — the
operator trusts the NAS once via `ssh-keyscan`.

## Last session summary

On **2026-07-28** we completed, merged, and went live with **two SDD cycles**
(PRs #7–#15), taking FaceAPP from "membership + kiosk platform" to "platform
with a full data-safety and reporting layer":

**Cycle 1 — `admin-data-tools`** (PRs #7/#8/#9 slices → #10 tracker→main at
`c8bc6d2`, fix in PR #15 at `ae95e02`):

1. Audited admin-only full-DB export — `GET /api/system/db-export`
   (`pg_dump -F c` streaming, argv-list no-shell, `PGPASSWORD` env-only, audit
   row), button in Settings → Backup tab.
2. Remote automatic backups — `scripts/backup.sh` + `scripts/remote_push.sh`
   (transports none/rsync/sftp/ftp/smb/nfs), `powerhouse-backup.timer` every
   30 min, 30-day retention, **warn-only remote failure** (local backup always
   preserved).
3. Configured-timezone sales reporting — `backend/services/timezone.py`
   (cached `get_app_tz(db)`, ZoneInfo, Redis TTL 300s + write-invalidation)
   replaced 3 hardcoded `America/Bogota` sites; SalesList shows date+time in
   the configured zone.
4. Custom date-range "bug" — reframed: code was already correct (PR #1);
   delivered regression contract tests + `docs/deployed-build-diagnosis.md`
   (staleness protocol). The deploy got rebuilt and the feature works.
5. Export-report button FIXED — it was decorative (no `onClick`); now streams
   `GET /api/sales/report/export` CSV reusing the same configured-TZ window.
6. Member panel — memberships 3+ collapse into an MUI Accordion (2 visible,
   actions preserved, i18n es+en).

**Cycle 2 — `remote-backup-config-ui`** (PRs #11/#12/#13 slices → #14
tracker→main at `62b7617`):

- Settings 6th "Backup" tab managing remote backup from the UI (6-transport
  dropdown, conditional fields, FTP cleartext warning, write-only password
  encrypted at rest via AES-256-GCM `encrypt_string`, masked GET
  `has_password`, keep-sentinel). Endpoints `GET/PUT /system/backup-config`,
  `POST /system/backup-config/test` (sanitized 20s probe). Backend materializes
  `/etc/faceapp/backup-remote.env` (0600 root:root, atomic), which `backup.sh`
  sources AFTER `.env` (managed config wins). Export DB button moved into the
  tab. `install.sh` now installs `samba-client`+`sshpass`. The "Environment-Only
  Remote Credentials" spec requirement was formally MODIFIED; specs synced into
  `openspec/specs/` (5 capability domains now).

**Ops/delivery the same day (dev LXC `ssh faceapp` / DEVFaceApp):**

- Frontend rebuilt+deployed twice (bundle now `index-Ctx_oAT7.js`) — custom
  range + Backup tab live; canonical clone at `/opt/faceapp`, flat app copy at
  `/opt/powerhouse-membership`.
- **RLS discovery**: DB has Row-Level Security on 9+ tables; the runtime role
  `backend_app` can NEVER `pg_dump`. Created dedicated `powerhouse_backup` role
  (`BYPASSRLS` + `pg_read_all_data`, creds in `/etc/faceapp/backup-db.env`
  0600) and shipped `BACKUP_DATABASE_URL` support (PR #15) honored by both
  `backup.sh` and the export endpoint.
- Backup timer ACTIVE — first real backup
  `db_backup_20260728_163851.dump` (9.3M, 14/14 tables) in
  `/var/backups/powerhouse`; volume expanded to 30G. Remote transport still
  `none` pending the user's NAS credentials.
- CI proved itself: the 3-job pipeline (main-gated) caught the env-sensitive
  `test_password_not_in_argv` assertion in the PR #15 chain.

**End-of-session state (2026-07-28)**: `main` at `ae95e02` (121 commits, 15 PRs
merged), CI green.
Test counts: backend 144, frontend 49, cv_service 12. Both SDD cycles archived
under `openspec/changes/archive/2026-07-28-*`; accepted specs in
`openspec/specs/`.

## Immediate next actions

1. **User configures the NAS target** — Settings → Backup tab → pick transport
   → fill fields → **Save**, then **Test** (that order: the probe reads the
   stored config, and Test stays disabled until the form is saved). For `sftp`
   or `rsync`, trust the NAS host key on the target host first:
   `ssh-keyscan -H <nas-host> >> /root/.ssh/known_hosts`. Remote is currently
   `none`; production still needs its backup role/config and timer provisioned.
   **The frontend fix needs a rebuild+deploy to be visible** — the running
   bundle on 114 predates it.
2. **Tracker-branches cleanup** — delete merged local/remote branches
   (`feat/remote-backup-config-ui`, `feature/admin-data-tools`,
   `fix/backup-database-url` and, if `git branch --merged main` agrees, the
   old local-only `feature/pr2-membership-expiration-access`,
   `fix/kiosk-recognition-state-regressions`, `feature/tracker`).
3. **Production backup provisioning** — the code is deployed, but production
   has no installed `powerhouse-backup.service` or `.timer`. Configure a
   full-database backup role before enabling the timer.
4. **Adopt a dependency lockfile** — `uv lock` or `pip freeze >
   requirements.lock`; venv-vs-requirements drift caused most of the PR #4/#5
   pain.
5. **If starting new feature work**, open an SDD change in `openspec/changes/`
   before writing code (see [SKILL.md SDD workflow](./SKILL.md)).
6. **Update STATUS.md** after any merge lands — keep the snapshot honest.

## Open threads

- **DEV NAS replication is intentionally NOT configured yet** — DEV's active
  timer logs "Remote replication disabled (BACKUP_REMOTE_TYPE=none)". Production
  has no backup timer installed, so this statement does not apply there.
- **`remote-backup-config-ui` accepted W1** — the managed-override runtime-test
  gap and one cosmetic locale item were accepted as low-severity at archive;
  see `openspec/changes/archive/2026-07-28-remote-backup-config-ui/archive-report.md`.
- **`/root/faceapp/gh.env` fine-grained PAT** — required for `git push` (the
  default OAuth token lacks `workflow` scope). The PAT sits on a **bare line**.
  It was rotated on 2026-07-29 after the prior exposure. Keep the file
  gitignored, never source it, and never embed the token in a Git URL because
  Git may print that URL on failure:
  ```bash
  export GH_TOKEN=$(grep '^github_pat_' gh.env)
  gh auth setup-git
  git push origin BRANCH:BRANCH
  ```
  `GH_TOKEN` authenticates `gh`; `gh auth setup-git` configures
  `gh auth git-credential` for Git without writing the PAT into `origin`.
- **`requirements.txt` drift is a real recurring hazard.** Local `.venv` is
  the de facto source of truth; CI installs whatever `requirements.txt` pins.
  PR #4 bumped lint tools, PR #5 bumped core app deps, but nothing prevents
  the next drift. Lockfile is the durable fix.
- **Dev DB masks CI bugs.** `backend/.env` sets `INTERNAL_API_SECRET`,
  `API_KEY`, `APP_ENV`, `ENVIRONMENT`, `DEBUG`; CI only sets the first one
  (PR #5). Local pytest is NOT a substitute for CI verification — the exact
  reason `test_password_not_in_argv` went red only in CI. When local and CI
  disagree, suspect ambient env first.
- **OpenSpec `membership-report-kiosk-tunnel` Phases 4–5** are unchecked
  (portal security + tunnel deployment). Explicitly out of scope so far;
  resume when portal work is prioritized. Start point: task 4.1 in
  [`openspec/changes/membership-report-kiosk-tunnel/tasks.md`](./openspec/changes/membership-report-kiosk-tunnel/tasks.md).
- **`WOMPI_INTEGRITY_SECRET`** is referenced in code but must be provisioned
  from the Wompi dashboard before production payments go live.
- **Optional tech-debt cleanup** (all documented as TODOs in their respective
  config files): re-enable 4 silenced ESLint rules after cleaning up
  `Kiosk.tsx:630` and the `any`/unused-vars warnings; migrate SQLAlchemy models
  to `Mapped[T]`/`mapped_column()` to drop mypy `disable_error_code` scopes;
  clean up the F401/E402/E722 flake8 categories.

## Key artifacts to read first

Ordered reading list for a fresh agent:

1. [README.md](./README.md) — features, architecture diagram, backup & user guide
2. [AGENTS.md](./AGENTS.md) — repo layout, run commands, traps, conventions
3. [STATUS.md](./STATUS.md) — current HEAD, branches, open work, live deploy state
4. [SECURITY.md](./SECURITY.md) — security contract (skim §1, §2, §4, §6 before
   touching auth/biometrics/payments)
5. [SKILL.md](./SKILL.md) — domain primer, backup subsystem, timezone model,
   kiosk state machine, memorable bugs
6. [openspec/specs/](./openspec/specs/) — 5 accepted capability specs
   (sales-reporting, membership-history, admin-database-export, remote-backup,
   backup-remote-config)
7. [openspec/changes/archive/2026-07-28-remote-backup-config-ui/archive-report.md](./openspec/changes/archive/2026-07-28-remote-backup-config-ui/archive-report.md)
   — terminal record of the Backup-tab cycle (merged via #11–#14)
8. [openspec/changes/archive/2026-07-28-admin-data-tools/archive-report.md](./openspec/changes/archive/2026-07-28-admin-data-tools/archive-report.md)
   — terminal record of the export/backup/timezone cycle (merged via #7–#10)
9. [openspec/changes/membership-report-kiosk-tunnel/proposal.md](./openspec/changes/membership-report-kiosk-tunnel/proposal.md)
   — in-flight SDD change (Phases 4–5 outstanding: portal security + tunnel)
10. [docs/deployed-build-diagnosis.md](./docs/deployed-build-diagnosis.md) —
    4-step staleness protocol before debugging any "missing feature" in prod

## Key commands

```bash
# --- Tests (per service) ---
docker-compose up -d db redis              # backend tests need Postgres + Redis
cd backend
set -a && . ./.env && set +a               # REQUIRED: conftest does NOT load .env
python init_db.py && pytest tests/         # backend suite (144 tests)
cd frontend && npm run test                # vitest run (49 tests)
cd cv_service && pytest tests/             # 12 tests

# --- Lint / type-check (exact CI mirrors, verified against PRs #7-#15) ---
cd backend && flake8 . && black --check . && mypy .
cd frontend && npm run lint && npm run type-check

# --- Dev servers ---
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev
cd cv_service && uvicorn main:app --port 8001

# --- Backups / admin ops ---
sudo systemctl list-timers powerhouse-backup.timer   # next run + last trigger
sudo tail -f /var/log/powerhouse-backup.log          # watch a run live
sudo /opt/powerhouse-membership/scripts/backup.sh    # manual run
ls -lh /var/backups/powerhouse/                      # artifacts + retention

# --- Git/GitHub auth (requires gh.env PAT, see Open threads) ---
export GH_TOKEN=$(grep '^github_pat_' gh.env)
gh auth setup-git
git push origin BRANCH:BRANCH
gh pr create --title "<type>: <subject>" --body-file <file>
gh pr checks <PR> --watch                            # wait for CI
gh pr merge <PR> --merge                             # merge-commit style

# --- Deploy (canonical clone -> flat app copy) ---
# prod: ssh faceapp-prod-114   |   dev: ssh faceapp  (DHCP-reserved .52 since 2026-08-12)
cd /opt/faceapp && git fetch --all && git merge --ff-only origin/main   # clone is detached HEAD
cd frontend && npm ci && npm run build
grep -o 'assets/index-[A-Za-z0-9_-]*\.js' dist/index.html               # note the new hash

# NEVER run a bare `rsync -a --delete /opt/faceapp/ /opt/powerhouse-membership/`.
# The runtime copy is ~7.2G of backend/venv (3.7G), cv_service/venv (3.3G) and
# frontend/node_modules (263M) that do NOT exist in the 271M canonical clone, so
# --delete without these excludes DESTROYS both venvs and takes production down.
# It would also delete `.deployed-sha` and the legacy `backup-20260422-020220/`.
# Deploy in two passes: scoped --delete for dist only, plain sync for the rest.
rsync -a --delete /opt/faceapp/frontend/dist/ /opt/powerhouse-membership/frontend/dist/
rsync -a --exclude='.env*' --exclude='venv/' --exclude='node_modules/' \
      --exclude='__pycache__/' --exclude='.git/' --exclude='frontend/dist/' \
      /opt/faceapp/ /opt/powerhouse-membership/
# Always dry-run with -i first: rsync prints '*deleting' (not 'deleting'), so a
# `grep '^deleting'` reports zero deletions even when it is about to delete.

git -C /opt/faceapp rev-parse HEAD > /opt/powerhouse-membership/.deployed-sha

# Migrations run as the OWNING role, never the runtime role (AGENTS.md trap 20).
# backend_app owns nothing by design, so without the env file below every DDL
# migration dies with `must be owner of ...`.
cd /opt/powerhouse-membership/backend
set -a; . ./.env; . /etc/faceapp/migrate-db.env; set +a
./venv/bin/alembic upgrade head
./venv/bin/alembic current   # MUST confirm the head moved — a failed upgrade
                             # does not stop the rest of this script

nginx -t && systemctl restart facegym-backend facegym-cv
# Verify on port 80 — nginx has no TLS listener, so https:// returns 000.
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/health

# --- SDD / CodeGraph ---
codegraph status                            # check local code index
git log main..feature/tracker --oneline     # reconcile tracker branch
```

## PR-to-DEV release boundary

Run the release gate only after CI/merge readiness and before publication or
deployment. A pre-PR receipt proves review state; it does not supply the five
independent release artifacts.

1. Generate or obtain the release configuration, evidence-freshness record,
   generated-artifact manifest, provenance record, and sealed publication
   boundary from their independent providers.
2. Validate all five together:

   ```bash
   gentle-ai review validate --gate release \
     --release-configuration <configuration-artifact> \
     --release-evidence-freshness <freshness-artifact> \
     --release-generated <generated-artifact-manifest> \
     --release-provenance <provenance-artifact> \
     --release-publication-boundary <publication-boundary-artifact>
   ```

3. Cross the deploy boundary only on a genuine PASS, then record the merged SHA,
   deployed SHA, and runtime verification in `STATUS.md`.

If this repository has no provider/tool for any required artifact, record the
typed gate result `delivery-derivation/unavailable`; do not fabricate evidence
or convert it to PASS. Stop and ask the maintainer to choose explicitly between
provisioning the missing provider/evidence or authorizing a documented release
exception. Record that decision before deployment so the next worker does not
mistake a pre-PR receipt or unavailable result for release approval.

## Contact points / decision log

- **Engram memory**: `mem_search query="faceapp"` (or `query="facegym"`) for
  past decisions, bug fixes, and session summaries across sessions. Topic keys
  of note: `ci-pipeline/bootstrap`, `ci-pipeline/baseline-config`,
  `ci-pipeline/pr5-test-failures`, `ci-pipeline/local-verification`,
  `project/handoff-docs`, plus the `sdd/*-report` keys for the two archived
  cycles.
- **SDD changes**: [`openspec/changes/`](./openspec/changes/) — each change has
  `proposal.md`, `design.md`, `tasks.md` recording the decision trail;
  accepted requirements land in [`openspec/specs/`](./openspec/specs/).
- **Security decisions**: [SECURITY.md](./SECURITY.md) is the authoritative
  security contract; updates there are the security decision log.
- **Commit history**: `git log --oneline` — Conventional Commits, 141 commits
  on main, 23 merged PR records through #28 (PR numbers contain gaps).

## Rollback / safety

**Roll back the last merge (PR #15):**
```bash
git revert -m 1 ae95e02
```
Effect: `BACKUP_DATABASE_URL` stops being honored; backups/exports fall back
to the RLS-restricted runtime role and produce incomplete dumps. Only revert
under a specific new failure — NOT to "fix" small dumps (the fix is the
reverse: keep PR #15 and ensure `BACKUP_DATABASE_URL` is set).

**Roll back the backup platform (PRs #10/#14):** reverting removes the Backup
tab, backup-config service, and remote transports. In environments where the
systemd timer is installed (currently DEV), scripts keep running from the
deployed copy, so stop `powerhouse-backup.timer` first. Production LXC 114 has
no installed backup timer:
```bash
sudo systemctl stop powerhouse-backup.timer
sudo systemctl disable powerhouse-backup.timer
```

**Roll back PR #5 / #4 / #3** — see the previous RESUME notes: PR #5 reverted
→ 8 pytest failures return; PR #4 reverted → lint configs and docs vanish;
PR #3 reverted → CI disappears entirely. Prefer forward-fixes.

**Roll back PR #2 or PR #1** — higher risk; these touched production code
(kiosk + reports + admin UI). Use `git revert -m 1 <merge-sha>` and re-run the
full test suite locally before pushing. Do NOT revert individual commits from
inside a merge — revert the merge commit with `-m 1`.

**Disable a misbehaving service in prod** (from
[SECURITY.md §9](./SECURITY.md)):
```bash
systemctl stop powerhouse-cv                # or powerhouse-backend
```

**Disable the Cloudflare Tunnel** (if portal is misbehaving): stop `cloudflared`
on the host; the tunnel allowlist is the portal's public boundary.
