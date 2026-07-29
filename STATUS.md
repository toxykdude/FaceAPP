# STATUS.md — Current project state

> Time-stamped snapshot of where FaceAPP is RIGHT NOW. Update this file as work
> progresses. For narrative, read [RESUME.md](./RESUME.md).

## Snapshot

| Field | Value |
|-------|-------|
| **Last updated** | 2026-07-29 (PR #19 deployed and runtime-verified on DEVFaceApp) |
| **Current HEAD** | `bb6a859` — Merge PR #19 `fix/kiosk-camera-domain-portability` |
| **Commits on main** | 131 |
| **PRs merged to date** | 19 (#1–#19; all CI-gated since #3) |
| **CI workflow** | `.github/workflows/ci.yml` — PR #19 passed all three jobs before merge. Triggers ONLY on PRs/pushes to `main`. |

`git rev-parse HEAD` → `bb6a859f7cd6daf637adadad4009df9f3161c72d` (main).
Remote is clean and in sync.

## Active branches

```
* main                                        # bb6a859 (PR #19 merge) — synced with origin
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

## What's live on the dev LXC (`ssh faceapp` / DEVFaceApp)

- **PR #19 deployed**: exact SHA
  `bb6a859f7cd6daf637adadad4009df9f3161c72d`; rollback snapshot at
  `/opt/deploy-rollbacks/bb6a859-20260729T091230Z`.
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
- **RLS workaround in production use**: dedicated `powerhouse_backup` role
  (`BYPASSRLS` + `pg_read_all_data`), credentials in `/etc/faceapp/backup-db.env`
  (0600), consumed via `BACKUP_DATABASE_URL` by both `backup.sh` and
  `/api/system/db-export` (PR #15).
- **Custom-range reporting visible again**: frontend rebuilt+deployed twice from
  the canonical clone; bundle now `index-Ctx_oAT7.js`. The "bug" was a
  3-month-stale static bundle (see `docs/deployed-build-diagnosis.md`).
- **Deploy layout**: canonical git clone at `/opt/faceapp` (pull→build→rsync),
  flat app copy at `/opt/powerhouse-membership` (no `.git`; Nginx serves its
  `frontend/dist`). Backup volume expanded to 30G by the user.
- **Production LXC untouched** — this wave of changes is live on DEV only;
  prod update awaits explicit user approval.

## Test counts (post-merge, main)

| Suite | Result | Command |
|-------|--------|---------|
| Backend | **144 passed** | `cd backend && set -a && . ./.env && set +a && python init_db.py && pytest tests/` |
| Frontend | **49 passed** | `cd frontend && npm run test` |
| cv_service | 12 passed | `cd cv_service && pytest tests/` |

⚠️ Backend `conftest.py` does NOT load `backend/.env` — export it into the
shell first or auth tests 401.

## Open work

1. **User configures NAS replication via the UI** (Settings → Backup tab).
   All transports are shipped and tested; remote is currently `none`.
2. **Optional follow-ups from the archived cycles**: W1 — the
   managed-override runtime test gap accepted in `remote-backup-config-ui`
   (see its archive report); a cosmetic locale item in the same cycle.
3. **Production LXC update** — build+deploy awaits explicit user approval.
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

`.github/workflows/ci.yml` was **green for PR #19 before merge to `bb6a859`**.
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
| `powerhouse-backup.timer` | — | Every 30 min → `scripts/backup.sh` |

Systemd units created by `install.sh`: `powerhouse-backend`, `powerhouse-cv`
(referenced in [SECURITY.md §9](./SECURITY.md)); the backup timer's units ship
in `scripts/systemd/`. Health checks: `GET /api/health` (basic),
`/api/health/db` (internal), `/cv/health`.

## Upcoming priorities

1. **Point the remote backup at the NAS from Settings → Backup tab** (user
   task — UI is shipped; no code needed).
2. **Production LXC update** when approved (rebuild + rsync per
   `docs/deployed-build-diagnosis.md`; canonical clone → flat app copy).
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
