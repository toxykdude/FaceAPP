# RESUME.md — How to pick up where we left off

> An agent reads this when resuming work after a gap. Concrete and actionable;
> no philosophy. For state, see [STATUS.md](./STATUS.md).

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

**Current state**: `main` at `ae95e02` (121 commits, 15 PRs merged), CI green.
Test counts: backend 144, frontend 49, cv_service 12. Both SDD cycles archived
under `openspec/changes/archive/2026-07-28-*`; accepted specs in
`openspec/specs/`.

## Immediate next actions

1. **User configures the NAS target** — Settings → Backup tab → pick transport
   → fill fields → Test → Save. No code change needed; remote is currently
   `none`.
2. **Tracker-branches cleanup** — delete merged local/remote branches
   (`feat/remote-backup-config-ui`, `feature/admin-data-tools`,
   `fix/backup-database-url` and, if `git branch --merged main` agrees, the
   old local-only `feature/pr2-membership-expiration-access`,
   `fix/kiosk-recognition-state-regressions`, `feature/tracker`).
3. **Production LXC update** — build+deploy awaits explicit user approval.
   Flow: `git pull` in `/opt/faceapp` → `npm ci && npm run build` → rsync to
   `/opt/powerhouse-membership` excluding `.env*` (NOT `biometric*`) → restart
   services. Follow `docs/deployed-build-diagnosis.md`.
4. **Rotate the `gh.env` PAT** — its value was discussed in chat. GitHub web
   UI only (no API for PAT creation); update the file after regenerating.
5. **Adopt a dependency lockfile** — `uv lock` or `pip freeze >
   requirements.lock`; venv-vs-requirements drift caused most of the PR #4/#5
   pain.
6. **If starting new feature work**, open an SDD change in `openspec/changes/`
   before writing code (see [SKILL.md SDD workflow](./SKILL.md)).
7. **Update STATUS.md** after any merge lands — keep the snapshot honest.

## Open threads

- **NAS replication is intentionally NOT configured yet** — the user holds the
  NAS credentials and will fill them via the Backup tab. Until then each timer
  run logs "Remote replication disabled (BACKUP_REMOTE_TYPE=none)" — expected,
  not an error.
- **`remote-backup-config-ui` accepted W1** — the managed-override runtime-test
  gap and one cosmetic locale item were accepted as low-severity at archive;
  see `openspec/changes/archive/2026-07-28-remote-backup-config-ui/archive-report.md`.
- **`/root/faceapp/gh.env` fine-grained PAT** — required for `git push` (the
  default OAuth token lacks `workflow` scope). The PAT sits on a **bare line**;
  extract with `grep`, never `source`:
  ```bash
  TOKEN=$(grep '^github_pat_' gh.env)
  git push "https://x-access-token:${TOKEN}@github.com/toxykdude/FaceAPP.git" BRANCH:BRANCH
  export GH_TOKEN=$(grep '^github_pat_' gh.env)   # for gh CLI commands
  ```
  Discussed in chat → rotate.
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

# --- Git push (requires gh.env PAT, see Open threads) ---
TOKEN=$(grep '^github_pat_' gh.env)
git push "https://x-access-token:${TOKEN}@github.com/toxykdude/FaceAPP.git" BRANCH:BRANCH
export GH_TOKEN=$(grep '^github_pat_' gh.env)
gh pr create --title "<type>: <subject>" --body-file <file>
gh pr checks <PR> --watch                            # wait for CI
gh pr merge <PR> --merge                             # merge-commit style

# --- Deploy to dev LXC (canonical clone -> flat app copy) ---
ssh faceapp
cd /opt/faceapp && git pull
cd frontend && npm ci && npm run build
rsync -a --delete --exclude='.env*' /opt/faceapp/ /opt/powerhouse-membership/
sudo systemctl restart facegym-backend facegym-cv

# --- SDD / CodeGraph ---
codegraph status                            # check local code index
git log main..feature/tracker --oneline     # reconcile tracker branch
```

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
- **Commit history**: `git log --oneline` — Conventional Commits, 121 commits
  on main, 15 PRs merged (`#1`–`#15`).

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
tab, backup-config service, and remote transports, but the systemd timer and
scripts on the LXC keep running from the deployed copy — stop
`powerhouse-backup.timer` first if you truly want backups off:
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
