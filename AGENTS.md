# AGENTS.md — Orientation for any agent landing in FaceAPP

> Read this FIRST. It answers: what is this, where is everything, how do I run it, where are the traps.
> For depth, follow the links in [Where to look next](#where-to-look-next).

## Project at a glance

FaceAPP (repo name `FaceGYM`, package `powerhouse-frontend`) is a biometric
access-control and membership platform for gyms/clubs. A member steps in front
of a kiosk camera, is recognized by face, and is granted or denied entry based
on membership status. Three services cooperate: a **backend** (FastAPI +
Postgres + Redis) owning the public `/api` surface, a **frontend** (React/Vite
SPA) for admin UI and the kiosk terminal, and a **cv_service** (FastAPI +
OpenCV + FaceNet) doing face recognition on RTSP and browser camera streams.
Target deployment is a Proxmox LXC container behind Nginx, with Cloudflare in
front. See [README.md](./README.md) for the feature list and user flows.

As of 2026-07-28 the platform also ships a **backup/reporting layer**: 30-min
automated local backups with optional remote replication (NAS/SFTP/FTP/SMB/NFS,
configurable from the admin UI), an audited admin-only full-DB export, and
configured-timezone sales reporting with CSV export.

## Repository layout

| Path | Purpose | Key entry file |
|------|---------|----------------|
| `backend/` | FastAPI REST API, JWT auth, RBAC, payments, scheduler | `backend/main.py` |
| `backend/api/` | Route handlers (auth, members, memberships, sales, portal, etc.) | `backend/api/auth.py` |
| `backend/api/system.py` | Admin system endpoints: `/system/db-export`, `/system/backup-config*` | — |
| `backend/core/` | config, database, security (JWT/bcrypt), encryption (AES-GCM) | `backend/core/config.py` |
| `backend/services/` | Domain logic (dashboard, timezone, backup-config, report windows) | `backend/services/timezone.py` |
| `backend/alembic/` | DB migrations | `backend/alembic.ini` |
| `backend/tests/` | pytest suite (needs Postgres + Redis + `backend/.env` exported) | `backend/tests/` |
| `frontend/` | React 18 + TypeScript + Vite + MUI SPA | `frontend/src/main.tsx` |
| `frontend/src/pages/Kiosk/Kiosk.tsx` | Kiosk terminal (USB/MJPEG camera + WS recognition) | — |
| `frontend/src/pages/Settings/Settings.tsx` | Settings shell (6 tabs; Backup is tab 6) | — |
| `frontend/src/components/settings/SettingsBackupTab.tsx` | Remote-backup UI (transports, test button) + Export DB | — |
| `frontend/src/i18n/translations.ts` | All ES/EN strings (`t.*.*`) | — |
| `frontend/src/contexts/` | Auth + Theme + Language providers | — |
| `cv_service/` | FastAPI + OpenCV + FaceNet; RTSP + WebSocket camera input | `cv_service/main.py` |
| `cv_service/recognition/` | FaceNet recognizer + template matcher | — |
| `cv_service/validation/` | Access policy (start/end date enforcement) | `cv_service/validation/access_validator.py` |
| `scripts/backup.sh` + `scripts/remote_push.sh` | Local backup + warn-only remote replication | `scripts/backup.sh` |
| `scripts/systemd/` | `powerhouse-backup.{service,timer}` — 30-min schedule | `scripts/systemd/powerhouse-backup.timer` |
| `scripts/` | Ops: restore, health monitor, nginx fix, migrations | `scripts/restore.sh` |
| `openspec/specs/` | Accepted capability specs (5 domains: sales-reporting, membership-history, admin-database-export, remote-backup, backup-remote-config) | — |
| `openspec/changes/` | Active + archived SDD artifacts | `openspec/config.yaml` |
| `docs/` | Operational runbooks (deployed-build diagnosis, etc.) | `docs/deployed-build-diagnosis.md` |
| `.github/workflows/ci.yml` | CI pipeline (3 jobs: backend, frontend, cv_service) | — |
| `install.sh` | One-click bare-metal installer (systemd + Nginx + Postgres) | — |
| `docker-compose.yml` | Dev orchestration of db/redis/backend/cv/frontend | — |
| `SECURITY.md` | Security contract (read before touching auth/biometrics/payments) | — |

## Quick start

Two supported local paths. Pick one.

**Docker (fastest, isolated):**
```bash
cp .env.example .env           # then edit secrets to non-default values
docker-compose up --build      # frontend on :3000, backend internal :8000, cv :8001
```

**Bare metal / LXC (matches prod):**
```bash
sudo ./install.sh              # installs deps, builds frontend, systemd services, Nginx
```
See [README.md Quick Install](./README.md#quick-install) for what the installer
does (including `samba-client` + `sshpass` for the SMB/SFTP backup transports).
Default login after install: `admin` / `admin123` — change immediately.

For running a single service during development, see [Three services](#three-services).

## Three services

**Backend** — Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Redis. Exposes `/api`
on `:8000`. Owns auth (JWT HS256, Redis blacklist), RBAC, biometric AES-256-GCM
encryption, Wompi payment webhooks, configured-timezone reporting
(`services/timezone.py`), the backup-config service (`services/backup_config.py`),
and the APScheduler email-report job. Run alone: `cd backend && uvicorn main:app
--reload --port 8000`. Needs Postgres + Redis up (use `docker-compose up db redis`).

**Frontend** — React 18 + TypeScript + Vite + MUI 6 + TanStack Query. Dev server
on `:5173` (Vite default) or built and served by Nginx on `:3000`/`:80`. Two
roles in one SPA: the admin dashboard and the `/kiosk` terminal. Run alone:
`cd frontend && npm install && npm run dev`.

**cv_service** — Python 3.11, FastAPI, OpenCV, FaceNet (InsightFace). Listens on
`:8001`, never exposed to the internet (Nginx denies `/api/cv/` from exterior).
Consumes RTSP streams and browser WebSocket frames, runs recognition, posts
access events back to the backend. Run alone: `cd cv_service && uvicorn main:app
--port 8001`. Requires `API_KEY` env to enable control-endpoint auth.

## Test commands

CI (`.github/workflows/ci.yml`) runs three jobs **only on PRs and pushes to
`main`**. These are the exact commands — they were run locally to green and
verified against the CI runs of PRs #7–#15, so a local green means a CI green
(with the env caveat below):

| Job | Command | Working dir |
|-----|---------|-------------|
| Backend lint | `flake8 .` | `backend/` |
| Backend format check | `black --check .` | `backend/` |
| Backend type check | `mypy .` | `backend/` |
| Backend tests | `python init_db.py && pytest tests/` | `backend/` |
| Frontend lint | `npm run lint` | `frontend/` |
| Frontend type check | `npm run type-check` | `frontend/` |
| Frontend tests | `npm run test` (=`vitest run`) | `frontend/` |
| CV service tests | `pytest tests/` | `cv_service/` |

Current test counts: backend **144 passed**, frontend **49 passed**, cv_service 12.

**Env-export caveat (critical):** the backend `conftest.py` does NOT load
`backend/.env`, and it supplies no auth secrets of its own. Run pytest like
this or auth-dependent tests fail with 401s:

```bash
cd backend
set -a && . ./.env && set +a          # export backend/.env into the shell
python init_db.py && pytest tests/
```

Backend CI supplies Postgres + Redis as GitHub Actions services plus
CI-placeholder env vars (see the workflow file). Locally, run
`docker-compose up db redis` before `pytest`. Full CI config:
[ci.yml](./.github/workflows/ci.yml).

## Conventions

- **Commits**: Conventional Commits (`feat:`, `fix:`, `chore:`, `fix(kiosk):`,
  etc.). See `git log --oneline` for established prefixes.
- **Branches**: named `^(feat|fix|chore|docs|refactor|test)/[a-z0-9._-]+$`
  (e.g. `fix/backup-database-url`).
- **PRs**: target `main` (a PR targeting another branch runs **no CI checks**).
  Merges use the GitHub `Merge pull request #N` format. All PRs #7–#15 followed
  this and were CI-gated — the convention is now real practice, not aspirational.
- **No `Co-Authored-By`** or AI attribution in commits or PRs.
- **i18n**: every user-visible string goes through `t.<section>.<key>` in
  `frontend/src/i18n/translations.ts`, with both `es` and `en` keys. No
  hardcoded Spanish/English in JSX. Enforced by convention only — no lint rule.
- **Timezone**: all report/date bucketing goes through
  `backend/services/timezone.py` (`get_app_tz(db)`, Redis-cached, invalidated
  on settings save). Never hardcode `America/Bogota` or `timedelta(hours=-5)`.
- **Secrets**: never hardcode. All secrets are env vars documented in
  [SECURITY.md §2](./SECURITY.md). Verify `.env` is gitignored before committing.
- **Backup remote config**: admins manage it from Settings → Backup tab; the
  backend materializes `/etc/faceapp/backup-remote.env` (0600) which
  `backup.sh` sources AFTER `.env`. `.env` is the headless fallback.
- **SDD**: changes follow Spec-Driven Development — artifacts live in
  `openspec/changes/<change-name>/`, accepted requirements land in
  `openspec/specs/`. See [SKILL.md SDD workflow](./SKILL.md#sdd-workflow).

## Critical traps

1. **`gh.env` is a fine-grained PAT** at `/root/faceapp/gh.env` (gitignored).
   Required for `git push` because the default OAuth token lacks the `workflow`
   scope needed to push the CI workflow file. **The PAT sits on a bare line.**
   Never source the file and never put the token in a push URL: Git may print a
   failing credential-bearing URL. Export it for GitHub CLI, configure `gh` as
   Git's credential helper, and push through the token-free `origin` URL:
   ```bash
   export GH_TOKEN=$(grep '^github_pat_' gh.env)
   gh auth setup-git
   git push origin BRANCH:BRANCH
   ```
   `gh auth setup-git` installs the `gh auth git-credential` helper; it does not
   put the PAT in the remote URL. The previously exposed PAT was rotated on
   2026-07-29. Keep `gh.env` gitignored and rotate again after any new exposure.
2. ~~**CI was just added**~~ — **RESOLVED (2026-07-28).** CI is real and
   enforced: 3 jobs gate every PR to `main`, and PRs #7–#15 all merged through
   it. It already caught real issues (env-sensitive argv test in PR #15's
   chain). Residual gotcha: CI triggers **only** on PRs/pushes to `main` —
   feature branches and PRs between them run zero checks until they target main.
3. **Backend tests require live Postgres + Redis AND exported env.** They are
   not mocked, and `conftest.py` does not read `backend/.env` — export it first
   or auth tests 401 (see Test commands). `docker-compose up -d db redis` first.
4. **App timezone is now a service, not a hardcode.** The old
   `America/Bogota` / `timedelta(hours=-5)` hardcodes (commits `f031ed1`,
   `b18cd3c`, `85cf905`) were replaced by `backend/services/timezone.py`:
   cached `get_app_tz(db)` (ZoneInfo, Redis TTL 300s, write-invalidated on
   settings save). Any new date math MUST use it — and never naive
   `datetime.utcnow()` for "today".
5. **WebSocket `onerror` → `onclose` ordering is a known race.** The USB error
   overlay in `Kiosk.tsx` must check BOTH states: see `connectionStatus ===
   'error' || connectionStatus === 'disconnected'` at
   `frontend/src/pages/Kiosk/Kiosk.tsx:807` and the guide-suppression guard at
   `:861`.
6. **`connectionStatus` defaults to `'disconnected'`** and is only set by the
   USB code path. The guide visibility check must be scoped `!usbMode ||
   (connectionStatus !== 'error' && connectionStatus !== 'disconnected')` —
   otherwise it permanently hides the guide in remote/MJPEG mode.
7. ~~**`branch-pr` skill rules are NOT enforced by CI**~~ — **RESOLVED in
   practice (2026-07-28).** There is still no dedicated PR-validation workflow,
   but the main-gated 3-job CI plus the real PR chain (#7–#15, conventional
   branches + commits) make the convention enforceable. Remaining gap: PRs that
   target a non-main branch run no checks.
8. **CV API key must propagate on enrollment.** Commit `32a30db` fixed the CV
   service not receiving its API key when notified after enrollment. Any change
   to the enrollment → CV notification path must keep the `X-API-Key` header
   (see `notify_cv_invalidation` in `backend/api/members.py`).
9. **i18n regressions have happened.** Commit `b26c45c` (among others) fixed
   hardcoded strings. No automated check exists; review manually.
10. **CodeGraph index is local-only** at `.codegraph/`. Never commit it. Each
    checkout must re-initialize its own index.
11. **Biometric data is legally sensitive** (Colombia Ley 1581/2012). Read
    [SECURITY.md §4](./SECURITY.md) before touching anything in the enrollment,
    template, or biometric-data path.
12. **Row-Level Security blocks `pg_dump` for the runtime role.**
    `backend_app` (the app DB role) can NEVER produce a full dump — RLS on 9+
    tables silently filters rows (portal security). Backups and the admin
    `/api/system/db-export` endpoint need `BACKUP_DATABASE_URL` pointing at the
    dedicated `powerhouse_backup` role (`BYPASSRLS` + `pg_read_all_data`;
    credentials root-only at `/etc/faceapp/backup-db.env` 0600). Both
    `scripts/backup.sh` and the export endpoint prefer `BACKUP_DATABASE_URL`
    over `DATABASE_URL` (PR #15).
13. **`backup.sh` chokes on `.env` values with unquoted spaces.**
    `backup.sh` sources `.env` via `set -a; . file; set +a` — a bare
    `KEY=value with spaces` line aborts sourcing (or shifts parsing). Always
    quote values with spaces in `.env` and in `/etc/faceapp/backup-remote.env`.
14. **rsync deploy excludes: `.env*` yes, `biometric*` no.** Deploying from the
    canonical clone (`/opt/faceapp`) to the flat app copy requires excluding
    `.env*` (prod secrets live on the target) but MUST NOT exclude
    `biometric*` — biometric reference data under the repo tree must deploy.
    Inverting either half corrupts the deployment.
    **`--delete` MUST also exclude `venv/` and `node_modules/`.** The runtime
    copy is ~7.2G — `backend/venv` 3.7G, `cv_service/venv` 3.3G,
    `frontend/node_modules` 263M — none of which exist in the 271M canonical
    clone. A bare `rsync -a --delete /opt/faceapp/ /opt/powerhouse-membership/`
    (as this runbook used to print) deletes both venvs and takes production
    down, plus `.deployed-sha` and the legacy `backup-20260422-020220/`. Deploy
    in two passes: scoped `--delete` for `frontend/dist/` only (stale hashed
    assets must go), then a plain non-deleting sync for everything else. Also
    note rsync prints `*deleting` with `-i`, so a `grep '^deleting'` dry-run
    check reports zero deletions even when it is about to delete — grep
    `deleting` unanchored.
15. **SMB/SFTP transports need extra packages.** `smb` requires `smbclient`
    (package `samba-client`), `sftp` requires `sshpass`. `install.sh` provides
    both on fresh installs; on an existing LXC run
    `apt-get install samba-client sshpass`. Without them, remote replication
    degrades to the documented warn-only skip (local backup still succeeds).
    **Production LXC 114 was missing BOTH** until 2026-07-30 — it was
    provisioned by copying the tree rather than running `install.sh`, so the
    dependency lines never executed. Installed there now (`sshpass 1.09`,
    `smbclient 4.19.5`; client only, no `smbd`/`nmbd` daemon). On Debian/Ubuntu
    the concrete package is `smbclient`, which *provides* the virtual
    `samba-client` — verified as the only provider, so either name resolves.
    After provisioning a host, verify rather than assume:
    `for t in rsync sftp sshpass smbclient curl; do command -v $t; done`.
16. **The release gate needs independent release evidence, not only a pre-PR
    receipt.** Before crossing the release/deploy boundary, prepare all five
    artifacts required by `gentle-ai review validate --gate release` and pass
    them with `--release-configuration`, `--release-evidence-freshness`,
    `--release-generated`, `--release-provenance`, and
    `--release-publication-boundary`. If no project provider/tool can generate
    them, record the typed `delivery-derivation/unavailable` outcome and stop.
    A maintainer must explicitly choose either to provision the missing evidence
    or authorize a documented exception for that deployment. Never invent an
    artifact or report PASS; a pre-PR receipt alone is insufficient. The
    executable sequence is in [RESUME.md](./RESUME.md#pr-to-dev-release-boundary).
17. **`sftp` argv order is load-bearing, and the test mocks hide it.** `sftp`
    stops parsing options at the first non-option argument, so every flag MUST
    precede the `user@host` destination and the destination MUST come last.
    `remote_push.sh` shipped `sshpass -e sftp -P "$port" "$user@$host" -b
    "$batch"` — the trailing `-b` made `sftp` exit with a *usage error*, so the
    SFTP transport never connected once. It went unnoticed because the mocked
    `sshpass` in `test_remote_backup_isolation.py` records argv and returns
    without ever exec'ing a real `sftp`. Fixed 2026-07-30 and pinned by
    `TestSftpArgvOrder`. When you touch any transport's argv, assert the ORDER,
    not just that secrets stay out of it.
18. **SSH transports fail closed on unknown host keys.** `sftp`/`rsync` run
    non-interactively, so a target whose key is not in the backup user's
    `known_hosts` fails with `Host key verification failed`. This is
    intentional — `StrictHostKeyChecking` is NOT relaxed, because these
    transfers carry full database dumps. Trust the target once with
    `ssh-keyscan -H <host> >> /root/.ssh/known_hosts` as the user the backend
    runs as. The probe maps this to the controlled reason *"remote host key is
    not trusted"* (`_SSH_REASONS` in `backend/services/backup_config.py`).
19. **The connection probe tests the SAVED config, never the form.**
    `POST /system/backup-config/test` takes no body: `run_probe` reads the
    `backup_remote` settings row and 400s (`nothing to probe for transport
    'none'`) when nothing valid is stored. The Backup tab therefore disables
    **Test** while the form is dirty. Its saved baseline is adopted from the
    PUT *response*, not the submitted form — the backend normalizes values (smb
    share → `//server/share`, default ports), so baselining the request leaves
    the form permanently dirty and **Test** unclickable forever.
20. **Migrations run as a DEDICATED role, never as the app role.** The runtime
    role (`backend_app`) owns nothing on purpose, so `alembic upgrade head` with
    the runtime `DATABASE_URL` fails every DDL migration with
    `must be owner of ...`. **The fix is not to grant `backend_app` ownership** —
    a table owner can `DROP TABLE`, and can
    `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`, and **bypasses RLS on every
    table that does not set FORCE ROW LEVEL SECURITY** (only `audit_logs` does;
    the other 12, including both biometric tables, do not). That would be a
    permanent privilege escalation on the most internet-exposed credential.
    Instead, `powerhouse_migrator` owns the tables (non-superuser,
    `NOBYPASSRLS`), provisioned by
    [`scripts/migrations/002_migration_role.sql`](./scripts/migrations/002_migration_role.sql),
    with credentials root-only in `/etc/faceapp/migrate-db.env` (0600) — the same
    pattern as `backup-db.env` (trap 12). Deploys run:
    ```bash
    cd /opt/powerhouse-membership/backend
    set -a; . ./.env; . /etc/faceapp/migrate-db.env; set +a
    ./venv/bin/alembic upgrade head
    ./venv/bin/alembic current        # ALWAYS confirm the head actually moved
    ```
    `alembic/env.py` prefers `MIGRATE_DATABASE_URL` over `DATABASE_URL`
    (`core/config.py::resolve_migration_database_url`), falling back so local dev
    and CI — where the connecting role already owns the schema — need no extra
    config. **Always run `alembic current` after an upgrade**: the failure is loud
    in the log, but a deploy script will happily continue past it and leave new
    code running against an unmigrated database, which is exactly what happened
    on 2026-08-05 before this was fixed. If you see `must be owner of ...`, the
    env file was not sourced — do NOT reach for `sudo -u postgres` as a shortcut.
    Two follow-ons are deliberately left undone: the three views stay owned by
    `postgres` (reassigning them would silently change which rows portal users
    see through them), and **new tables do not get RLS automatically** — default
    privileges cover grants, not row security, so any migration adding
    member-scoped data must `ENABLE ROW LEVEL SECURITY` and add policies itself.
21. **DEV's `.env` has unquoted values containing spaces.** Sourcing it emits
    `usmm: command not found` / `Gym: command not found` (lines 17 and 24) —
    trap 13 live on DEV: anything after a bad line may never get set. Quote
    those values before trusting any script that sources `.env`.

## Where to look next

| Need | File |
|------|------|
| Current state, HEAD, open work | [STATUS.md](./STATUS.md) |
| How to resume the last session | [RESUME.md](./RESUME.md) |
| Domain knowledge, architecture, memorable bugs | [SKILL.md](./SKILL.md) |
| Threat model, secrets, biometrics, payments | [SECURITY.md](./SECURITY.md) |
| Feature list, user guide, API reference | [README.md](./README.md) |
| Deployed-build staleness protocol | [docs/deployed-build-diagnosis.md](./docs/deployed-build-diagnosis.md) |
| Accepted capability specs (5 domains) | [openspec/specs/](./openspec/specs/) |
| Archived SDD cycle: admin-data-tools | [openspec/changes/archive/2026-07-28-admin-data-tools/](./openspec/changes/archive/2026-07-28-admin-data-tools/) |
| Archived SDD cycle: remote-backup-config-ui | [openspec/changes/archive/2026-07-28-remote-backup-config-ui/](./openspec/changes/archive/2026-07-28-remote-backup-config-ui/) |
| Active SDD change (portal security Phases 4–5) | [openspec/changes/membership-report-kiosk-tunnel/proposal.md](./openspec/changes/membership-report-kiosk-tunnel/proposal.md) |
| CI pipeline definition | [.github/workflows/ci.yml](./.github/workflows/ci.yml) |
