# STATUS.md — Current project state

> Time-stamped snapshot of where FaceAPP is RIGHT NOW. Update this file as work
> progresses. For narrative, read [RESUME.md](./RESUME.md).

## Snapshot

| Field | Value |
|-------|-------|
| **Last updated** | 2026-07-30 (PR #29+#30 merged and SHA `946c605` deployed + runtime-verified on production LXC 114) |
| **Current HEAD** | `465c9a6` — Merge PR #29 `fix/backup-remote-test-connection` |
| **Commits on main** | 145 |
| **PRs merged to date** | 24 merged PR records through #29 (numbers contain gaps) |
| **CI workflow** | `.github/workflows/ci.yml` — PR #29 passed backend, frontend, and cv_service before merge. Triggers ONLY on PRs/pushes to `main`. |

`git rev-parse HEAD` → `465c9a68e397b87f46e2b1b5972ad4c1bb2bf168` (main).
Remote is clean and in sync.

✅ **Production is in sync with `main`.** LXC 114 was deployed to `946c605` on
2026-07-30 and runtime-verified (see below). The `sshpass`/`smbclient` packages
were installed directly on the host earlier the same day.

✅ **DEV is in sync with `main` too.** DEVFaceApp was deployed to `8651568` on
2026-07-30 and runtime-verified.

📌 **Host addresses** (the `ssh faceapp` alias had gone missing from
`~/.ssh/config`; recorded here so it can be rebuilt):

| Env | Host | IP | SSH alias | Key |
|-----|------|----|-----------|-----|
| Production | `FaceAPP` (LXC 114) | `10.162.36.16` | `faceapp-prod-114` | `~/.ssh/faceapp-prod-lxc114_ed25519` |
| DEV | `DEVFaceApp` (LXC 124) | `10.162.36.101` | `faceapp`, `faceapp-dev-105` | `~/.ssh/faceapp` |

⚠️ **The DEV IP in this table was wrong until 2026-08-05.** It read
`10.162.36.105`, which has **no route to host**. The correct address is
`10.162.36.101` — verified by SSH (`hostname` → `DEVFaceApp`) and consistent
with `~/.ssh/config`, which had it right all along. The `faceapp` /
`faceapp-dev-105` aliases both resolve correctly, so prefer the alias over a
literal IP. (RESUME.md's note that the `faceapp` alias "does NOT resolve" is
also stale — it resolves.)

`known_hosts` uses `HashKnownHosts`, so hostnames cannot be read back out of it
— this table is the only record.

## Active branches

```
* main                                        # 873e51b (PR #28 merge) — synced with origin
```

Merged-and-deletable local branches (remotes already gone or pending cleanup):

| Branch | State |
|--------|-------|
| `feat/remote-backup-config-ui` | merged via PR #14 — delete after verifying `git branch --merged main` |
| `feature/admin-data-tools` | merged via PR #10 — delete after verifying |
| `fix/backup-database-url` | merged via PR #15 — delete after verifying |
| `feature/pr2-membership-expiration-access` | merged via PR #1 (local-only) — delete after verifying |
| `fix/kiosk-recognition-state-regressions` | merged via PR #2 (local-only) — delete after verifying |
| `feature/tracker` | SDD tracker for `membership-report-kiosk-tunnel`; reconcile vs `main` (`git log main..feature/tracker`) — likely redundant post-PR-#1 |

## Recent merges

| PR | Merge SHA | Title |
|----|-----------|-------|
| #29 | `465c9a6` | fix(backup): make remote backup Test connection actually work |
| #28 | `873e51b` | feat(kiosk): redesign premium camera-first terminal |
| #26 | `0481a21` | feat(kiosk): automate camera and show access feedback |
| #25 | `6d745a3` | fix(cv): keep websocket recognition stream alive |
| #23 | `989c38c` | fix(backup): target SMB share root when path is empty |
| #21 | `cef2f23` | docs(ops): document safe release workflow |
| #19 | `bb6a859` | fix(kiosk): reconcile configured camera streams |
| #15 | `ae95e02` | fix(backup): honor BACKUP_DATABASE_URL for pg_dump |
| #14 | `62b7617` | Merge `feat/remote-backup-config-ui` tracker → main |
| #13 | `ad69b02` | remote-backup-config-ui slice S3 (install.sh deps + docs) |
| #12 | `6dd9b5e` | remote-backup-config-ui slice S2 (admin Backup tab + Export DB move + i18n) |
| #11 | `8cf40df` | remote-backup-config-ui slice S1 (backup_config service + system.py + sftp/ftp/smb transports + managed env override) |
| #10 | `c8bc6d2` | Merge `feature/admin-data-tools` tracker → main |
| #7–#9 | (into tracker) | admin-data-tools slices A/B/C (timezone + CSV + diagnosis; membership accordion; DB export + remote backup) |
| #5 | `1acf916` | fix(backend): resolve 8 hidden pytest failures surfaced by CI |
| #4 | `7745610` | chore(ci): green CI baseline + project handoff docs (AGENTS/SKILL/STATUS/RESUME) |
| #3 | `b476944` | chore(ci): add CI workflow, GitHub templates, and OpenSpec artifact trail |
| #2 | `2213bee` | fix(kiosk): stuck-verifying, camera-restart freeze, denial masking + retry overlay, start race, name leak |
| #1 | `114d0ee` | feat(kiosk): premium redesign + display/access split + 3-path CV invalidation + custom date-range reports |

## Last recorded DEV state (`ssh faceapp` / DEVFaceApp, `10.162.36.101`)

- **Latest DEV deployment (current)**: exact SHA
  `b41954ff43f10f59772c8fcc97782330d25c1aa8` — branch
  `feat/membership-payment-enforcement` (membership payment balance +
  unpaid-entry gate), deployed 2026-08-05. **Deployed from a BRANCH, not
  `main`** — this SHA is not on `main` and CI has not run on it; it carries the
  three payment commits on top of `8dc2b0a`, and also brought DEV forward past
  the 6 commits it was missing (liveness fix, portal ambiguous-phone auth,
  duplicate contact phones).
  Verified: `/api/health` 200, `/api/health/db` 200, frontend 200, all five
  services active (`facegym-backend`, `facegym-cv`, `nginx`, `postgresql`,
  `redis-server`), `nginx -t` valid, zero error-level journal lines, served
  `index.html` referencing `index-DagbKDRJ.js`, and the internal CV access
  payload confirmed carrying the new `payment_status` / `amount_due` fields.
  Alembic advanced `5a4b3c2d1e0f` → `7c6d5e4f3a2b` (see the migration-privilege
  blocker below). Rollback code SHA
  `95666d0ba7eba38fb9d3f0c96b518aa7bb9e4238`; verified 14-table-data-entry dump
  `/var/backups/powerhouse-deploy/membership_db_predeploy_20260805T170941Z.dump`.
  `powerhouse-backup.timer` was stopped for the deploy and restarted after.
- 🚨 **Migration-privilege blocker (affects PRODUCTION too, unresolved).** All
  14 public tables are owned by `postgres`, but migrations run as `backend_app`,
  which owns nothing — so **no DDL migration can succeed via the documented
  `alembic upgrade head` step**. On this deploy `6b5c4d3e2f1a` failed with
  `must be owner of index ix_members_phone_unique`, which also blocked the
  follow-on `7c6d5e4f3a2b`. Worked around on DEV by running Alembic as the
  owning role over the local socket:
  `sudo -u postgres env DATABASE_URL="postgresql://postgres@/membership_db?host=/var/run/postgresql" ./venv/bin/alembic upgrade head`.
  This is a workaround, not a fix — production will hit the identical failure
  the first time it deploys a schema change. Decide deliberately between
  granting `backend_app` ownership of the tables it migrates, or making the
  owning-role invocation the documented deploy step.
- **DEV payment-state census after deploy** (2735 memberships): 2712 `paid`,
  2 `partial`, 21 `pending`. **Zero** currently-active memberships would be
  denied by the new unpaid gate — every active membership has payment linked.
  All 23 unsettled memberships are already inactive, so no live traffic
  exercises the amber or red payment paths on DEV today.
- **Previous DEV deployment**: exact SHA
  `8651568cbf6c3999c9b22e9343f66f13bd12acaa` (PRs #29–#31), deployed
  2026-07-30. Verified: `/api/health` 200, `/api/health/db` 200, authenticated
  CV `/health` 200, frontend 200, all five services active, `nginx -t` valid,
  zero error-level journal lines, and the served `index.html` referencing
  `index-CrN45nRN.js` with the PR #29 strings present. Alembic already at head
  `f0786144f6c0`. Rollback `/opt/deploy-rollbacks/873e51b-20260730T182450Z`;
  verified 14-table-data-entry dump
  `/var/backups/powerhouse-deploy/membership_db_predeploy_20260730T182450Z.dump`.
  `.deployed-sha` did not exist on DEV before this deploy — it does now.
- **DEV already had `sshpass` + `smbclient`** — unlike production. Transport
  tooling was never DEV's blocker; the Backup tab's dead Test button was the
  swallowed-error bug plus the save-before-test contract (PR #29).
- **DEV carries a 3.7G `backend.bak-20260728-162127/`** in the runtime copy on
  top of the two venvs, so the deploy `--delete` excludes matter even more here
  (see [AGENTS.md](./AGENTS.md) trap 14).
- **Previous DEV deployment**: PR #28 at exact SHA
  `873e51b54450cd13143f9deaa41e8f9d43522e8a`; rollback snapshot at
  `/opt/deploy-rollbacks/873e51b5445-20260729T225619Z`. The earlier PR #19
  rollback remains `/opt/deploy-rollbacks/bb6a859-20260729T091230Z`.
- **Runtime checks passed**: frontend 200, backend health 200, authenticated CV
  health 200, and required services active.
- **Camera proxy verified on the DEV LXC**: Nginx has `/cv/stream/` and
  `/cv/ws/` routes with WebSocket upgrade handling. A configured camera UUID
  returned HTTP 200 `multipart/x-mixed-replace` and reached the bounded timeout
  as expected instead of returning 404.
- **Remaining boundary checks**: the outer Nginx Proxy Manager could not be
  inspected, and manual browser confirmation of the kiosk flow remains.
- **Build caveat**: Node 18 emitted an npm engine warning during the frontend
  build; the build completed, but the DEV build runtime should be upgraded
  before a future toolchain release makes that warning fatal.

- **Unified backup platform**: Settings → Backup tab (6 transports, sanitized
  connection test, write-only encrypted password), Export Database button moved
  into the same tab.
- **Backup timer ACTIVE**: `powerhouse-backup.timer` fires every 30 min. First
  real backup `db_backup_20260728_163851.dump` (9.3M, 14/14 tables) in
  `/var/backups/powerhouse`. Remote transport still `none` — user will point it
  at a NAS from the UI.
- **DEV RLS workaround**: dedicated `powerhouse_backup` role
  (`BYPASSRLS` + `pg_read_all_data`), credentials in `/etc/faceapp/backup-db.env`
  (0600), consumed via `BACKUP_DATABASE_URL` by both `backup.sh` and
  `/api/system/db-export` (PR #15).
- **Custom-range reporting visible again**: frontend rebuilt+deployed twice from
  the canonical clone; bundle now `index-Ctx_oAT7.js`. The "bug" was a
  3-month-stale static bundle (see `docs/deployed-build-diagnosis.md`).
- **Deploy layout**: canonical git clone at `/opt/faceapp` (pull→build→rsync),
  flat app copy at `/opt/powerhouse-membership` (no `.git`; Nginx serves its
  `frontend/dist`). Backup volume expanded to 30G by the user.
- **Production LXC 114 deployed (current)**: exact SHA
  `946c605cf0ca1dcd2ec4b123a8043993a12345a5` (PRs #29+#30), deployed
  2026-07-30. `.deployed-sha` in the runtime copy records it. Verified: backend
  `/api/health` 200, `/api/health/db` 200, authenticated CV `/health` 200,
  frontend HTTP 200 (nginx listens on **port 80 only** — an `https://`
  healthcheck returns `000` and is a test error, not an outage), all of
  `facegym-backend`/`facegym-cv`/`nginx`/`postgresql`/`redis-server` active,
  `nginx -t` valid, and zero error-level journal lines after restart. The served
  `index.html` references the new `index-CrN45nRN.js`, which contains the PR #29
  strings — checked deliberately, because the last incident here was a stale
  bundle. Alembic was already at head `f0786144f6c0`; PR #29 adds no migration.
  Rollback (tracked tree + `dist`, venv/node_modules excluded) is
  `/opt/deploy-rollbacks/873e51b-20260730T181056Z`; verified
  14-table-data-entry DB dump is
  `/var/backups/powerhouse-deploy/membership_db_predeploy_20260730T181056Z.dump`.
- **Previous production SHA**: `873e51b54450cd13143f9deaa41e8f9d43522e8a`,
  rollback `/opt/deploy-rollbacks/preprod-20260730T014157Z`, DB dump
  `/var/backups/powerhouse-deploy/membership_db_predeploy_20260730T014157Z.dump`.
- **Approval state (both deploys)**: NOT a gate PASS. For `946c605` the native
  gate returned `result: invalidated`, `allowed: false`,
  `action: explicit-maintainer-action`, denial `receipt-discovery/receipt_unrelated`
  ("terminal review receipts exist only for unrelated targets" — the code was
  already merged, so no receipt governs the deployed candidate). The maintainer
  explicitly authorized deployment after being shown the gate requirement; the
  exception is scoped only to this candidate and LXC 114. The earlier `873e51b`
  deploy proceeded the same way on a `delivery-derivation/unavailable` result.
- **Production backup warning**: LXC 114 has no installed
  `powerhouse-backup.service` or `powerhouse-backup.timer`. The pre-deploy DB
  dump above is valid, but recurring production backups require explicit unit
  and backup-role/config provisioning before the timer can be enabled safely.

## Test counts (post-merge, main)

| Suite | Result | Command |
|-------|--------|---------|
| Backend | **150 passed** | `cd backend && set -a && . ./.env && set +a && python init_db.py && pytest tests/` |
| Frontend | **73 passed** | `cd frontend && npm run test` |
| cv_service | 12 passed | `cd cv_service && pytest tests/` |

⚠️ Backend `conftest.py` does NOT load `backend/.env` — export it into the
shell first or auth tests 401.

⚠️ Backend deps do NOT install on Python 3.13 (Debian 13 default): `numpy`
1.26.3, `psycopg2-binary` 2.9.9, and `bcrypt` 3.2.0 all predate it and fail to
build. Production LXC 114 runs 3.12, and CI pins its own interpreter. To run the
backend suite on a 3.13 workstation, relax exactly those three pins in a local
throwaway venv — do NOT edit `requirements.txt` (see priority 4, lockfile).

## Open work

1. **DEV NAS replication** — configure it via Settings → Backup. DEV's remote
   transport is currently `none`; production has no backup timer installed.
   Transport tooling is no longer a blocker on production (see below).
2. **Optional follow-ups from the archived cycles**: W1 — the
   managed-override runtime test gap accepted in `remote-backup-config-ui`
   (see its archive report); a cosmetic locale item in the same cycle.
3. **Production backup provisioning** — install/configure the shipped backup
   units with a full-database backup role, then enable and verify the timer.
4. **Tracker-branches cleanup** — delete the merged local/remote branches
   listed above after `git branch --merged main` confirms them.

Separately, the `membership-report-kiosk-tunnel` OpenSpec change has
Phases 4–5 outstanding (portal security + tunnel deployment) — explicitly not
started and not blocking.

## Known issues / tech debt

From `openspec/changes/membership-report-kiosk-tunnel/tasks.md` (Phases 4–5,
unchecked — explicitly NOT started):

- Portal security: forged/missing HMAC-SHA256 webhook rejection (task 4.1)
- CORS rejection of disallowed origins on portal routes (4.2)
- Cross-member `/portal/me` RLS denial test (4.3)
- Rate limiting on the three `/api/auth/member-*` routes (4.4–4.5)
- Cloudflare Tunnel allowlist enforcement (4.6–4.7)
- Deployment prerequisites: cloudflared, RLS verification, dep confirmation (5.1–5.3)

From [SECURITY.md](./SECURITY.md) (open items, pre-existing):

- `WOMPI_INTEGRITY_SECRET` webhook verification is implemented in code but the
  secret must be provisioned from the Wompi dashboard before going live.
- HTTP→HTTPS redirect on port 80 is marked PENDIENTE.
- Habeas Data: SIC registration, public privacy policy, and designated data
  officer are all unchecked compliance items.

From PR #4 / PR #5 (documented as TODOs inside config files — not silently
ignored):

- **Lint baseline**: `backend/.flake8` ignores `F401/F811/F841/E402/E712/E722/E741`
  as documented historical debt. `E712` (`== True`) is a legitimate SQLAlchemy
  ORM pattern. The rest should be cleaned up incrementally.
- **Type-check baseline**: `backend/mypy.ini` has scoped `disable_error_code`
  for legacy SQLAlchemy `Column[T]` drift in `api/core/models/schemas/services/main`.
  TODO: migrate models to `Mapped[T]`/`mapped_column()` and remove the disables.
- **Frontend lint baseline**: `frontend/.eslintrc.cjs` silences 4 noisy rules
  (`no-explicit-any`, `no-unused-vars`, `react-hooks/exhaustive-deps`,
  `react-refresh/only-export-components`) to `'off'`. The lint script also
  dropped `--report-unused-disable-directives` because of a stale directive
  in `Kiosk.tsx:630`. Re-enable after source cleanup.
- **`requirements.txt` drift**: PR #4 bumped lint tools, PR #5 bumped core deps.
  The local `.venv` is the de facto source of truth. Recommend `uv lock` or
  `pip freeze > requirements.lock` to prevent silent recurrence.
- **Dev DB masks CI bugs**: `backend/.env` provisions `INTERNAL_API_SECRET`,
  `API_KEY`, `APP_ENV`, `ENVIRONMENT`, `DEBUG` — CI only sets the first one
  (PR #5). Local pytest is NOT a substitute for CI.

## CI status

.github/workflows/ci.yml was **green for PR #28 before merge to `873e51b`**.
Three jobs, triggered
only on PRs/pushes targeting `main` (feature-branch pushes and inter-feature
PRs run no checks — verified during the #7–#15 chain).

- `backend` (~1m) — flake8, black --check, mypy, `python init_db.py`, pytest
  with Postgres+Redis GitHub Actions services.
- `frontend` (~45s) — npm ci, lint, type-check, vitest run.
- `cv_service` (~1m15s) — pip install, pytest.

CI already earned its keep: it caught the env-sensitive
`test_password_not_in_argv` assertion in the PR #15 chain (passed locally,
failed in CI because the local `.env` masked it).

CI env vars for the backend job: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`,
`JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`,
`INTERNAL_API_SECRET`. All non-secret values are in the workflow file;
secret-looking values are CI-only placeholders (`ci-...`).

## Pipeline state (production)

Expected running services in a healthy prod deployment:

| Service | Port | Notes |
|---------|------|-------|
| Backend (FastAPI / uvicorn) | 8000 (internal) | Behind Nginx |
| Frontend (static build via Nginx) | 80/443 | Served by Nginx |
| cv_service (FastAPI / uvicorn) | 8001 (localhost only) | Nginx denies `/api/cv/` externally |
| PostgreSQL | 5432 | Local socket |
| Redis | 6379 | Local socket |
| Nginx | 80/443 | TLS termination, rate limits, `/api/cv/` ACL |
| APScheduler email reports | (in backend) | Fires every 2h |
| `powerhouse-backup.timer` | — | Shipped in source but not installed on production LXC 114 |

### Remote-backup transport tooling (production LXC 114)

Installed 2026-07-30 — LXC 114 was provisioned by copying the tree, so
`install.sh`'s dependency lines never ran and both packages were absent:

| Transport | Tool | Status on 114 |
|-----------|------|---------------|
| `rsync` | `rsync` | present |
| `sftp` | `sshpass` + `sftp` | **`sshpass 1.09` installed** |
| `ftp` | `curl` (not `lftp`/`ftp`) | present |
| `smb` | `smbclient` | **`smbclient 4.19.5` installed** |
| `nfs` | none — `cp` into a pre-mounted dir | n/a |

Client packages only: no `smbd`/`nmbd` unit was installed or enabled, so no new
listening service. Verified end-to-end on 114 in a sandboxed probe: SMB now
reaches the network (`NT_STATUS_IO_TIMEOUT` against an unreachable host, mapped
to "connection timed out") instead of skipping warn-only, and SFTP attempts a
real connection instead of exiting on a usage error.

**Still outstanding before a NAS target will succeed:** the remote host key must
be trusted for SSH-based transports —
`ssh-keyscan -H <nas-host> >> /root/.ssh/known_hosts` on 114.

Actual production units are `facegym-backend` and `facegym-cv`; the backup
timer units ship in `scripts/systemd/` but are not installed on LXC 114. Health
checks: `GET /api/health` (basic),
`/api/health/db` (internal), `/cv/health`.

## Upcoming priorities

1. **Point the remote backup at the NAS from Settings → Backup tab.** The UI is
   shipped and, as of 2026-07-30, actually usable: **Save first, then Test** —
   the probe reads the stored config, not the form. Two real defects were found
   and fixed while verifying this (the Backup tab silently swallowed every error
   response; SFTP had never worked because of a bad `sftp` argv order), so the
   earlier note that "no code was needed" was wrong. Production still needs its
   backup role/config and timer provisioned, plus the NAS host key trusted for
   SSH-based transports.
2. **Production backup provisioning** — configure a full-database backup role,
   install the shipped units, then enable and verify the timer.
3. **Tracker-branches cleanup** (see Active branches).
4. **Adopt a lockfile** (`uv lock` or `pip freeze > requirements.lock`) — the
   silent drift between local venv and `requirements.txt` caused 3 PR iterations
   in PR #4 and 2 in PR #5. Locking prevents recurrence.
5. **OpenSpec Phase 4 (portal security)** when the portal tunnel work resumes —
   start with task 4.1 (HMAC-SHA256 webhook RED test) in `openspec/changes/membership-report-kiosk-tunnel/tasks.md`.
6. **Provision `WOMPI_INTEGRITY_SECRET`** from the Wompi dashboard before any
   production payment flow goes live.
7. **Optional cleanup**: re-enable silenced ESLint rules after fixing the 89
   `any`/unused-vars warnings; migrate models to `Mapped[T]` to drop the mypy
   `disable_error_code` scopes; remove `# type: ignore` shims.
