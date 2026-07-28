# STATUS.md — Current project state

> Time-stamped snapshot of where FaceAPP is RIGHT NOW. Update this file as work
> progresses. For narrative, read [RESUME.md](./RESUME.md).

## Snapshot

| Field | Value |
|-------|-------|
| **Last updated** | 2026-07-28 (admin-data-tools SDD cycle archived) |
| **Current HEAD** | `6fcab85` — Merge PR #6 `chore/refresh-status-resume` |
| **Commits on main** | 88 |
| **PRs merged to date** | 6 (#1 feature, #2 fix, #3 chore, #4 chore+docs, #5 fix, #6 chore+docs) |
| **CI workflow** | `.github/workflows/ci.yml` — green at last `main` run (PR #6). **admin-data-tools slices NOT yet pushed — no CI run on them.** |

`git rev-parse HEAD` → `6fcab850e02141eeb49bb7cd201960f07e7540d6` (main)

## Active branches

```
* main                                        # 6fcab85 (PR #6 merge)
  feature/admin-data-tools                    # LOCAL ONLY — admin-data-tools tracker (at main; no commits beyond main)
  feat/admin-data-tools-slice-a               # LOCAL ONLY — slice A: #3 timezone + #5 CSV + #4 diagnosis (tip 3a6b54c, black-clean)
  feat/admin-data-tools-slice-b               # LOCAL ONLY — slice B: #6 membership accordion (tip 8704e75, rebased onto slice-a)
  feat/admin-data-tools-slice-c               # LOCAL ONLY — slice C: #1 DB export + #2 remote backup (tip b3193c7, rebased onto slice-b)
  feature/pr2-membership-expiration-access    # local only, merged via PR #1
  feature/tracker                             # local only, SDD work for membership-report-kiosk-tunnel OpenSpec change
  fix/kiosk-recognition-state-regressions     # local only, merged via PR #2
```

Remote (`origin`) is clean: only `refs/heads/main` exists. The three
`feat/admin-data-tools-slice-*` branches plus `feature/admin-data-tools`
form the **`admin-data-tools` feature-branch chain** — the SDD cycle is
COMPLETE and ARCHIVED but **NONE of these branches have been pushed**.
Push / PR opening is pending a user decision (see Open work). The other
three local-only branches were merged via their respective PRs and can be
deleted once you confirm no unmerged work remains
(`git log main..<branch> --oneline`).

## Recent merges

| PR | Merge SHA | Title |
|----|-----------|-------|
| #5 | `1acf916` | fix(backend): resolve 8 hidden pytest failures surfaced by CI |
| #4 | `7745610` | chore(ci): green CI baseline + project handoff docs (AGENTS/SKILL/STATUS/RESUME) |
| #3 | `b476944` | chore(ci): add CI workflow, GitHub templates, and OpenSpec artifact trail |
| #2 | `2213bee` | fix(kiosk): resolve stuck-verifying, camera-restart freeze, denial masking + vanishing retry overlay, concurrent camera-start race, check-in name leak |
| #1 | `114d0ee` | feat(kiosk): premium dark redesign + split membership display from access + 3-path CV invalidation + custom date-range reports |

PR #5 landed 6 commits across 4 root-cause categories. PR #4 landed 8 commits
across 3 work units (docs, baseline configs, black reformat) plus 3 follow-up
fixes for cross-version tool divergence.

## Open work

**`main` itself is clean**, but the **`admin-data-tools` SDD change is
COMPLETE + ARCHIVED yet UNPUSHED** — this is the active decision point:

- SDD cycle done: 6 features delivered, 12/12 requirements, 18/18 scenarios,
  0 critical findings. Delta specs synced into `openspec/specs/` (4 new
  domain specs); change folder moved to
  `openspec/changes/archive/2026-07-28-admin-data-tools/`.
- The four feature-branch-chain branches (`feature/admin-data-tools` tracker +
  `feat/admin-data-tools-slice-{a,b,c}`) are **LOCAL ONLY**. Final
  post-remediation evidence: backend 98/98 pytest, frontend 42/42 vitest,
  `black --check .` 99 files clean, tsc/eslint/flake8/mypy clean.
- **CI has NOT run on any admin-data-tools commit** — first real CI run
  happens on the next push/PR.
- The archive filesystem move (delta-spec sync + folder relocation) is
  currently an **uncommitted change on `feat/admin-data-tools-slice-c`** —
  decide whether to commit it on slice-c, move it to a separate `chore/`
  branch, or land it on the tracker before pushing.
- Feature #4 (custom-range "not visible") is reframed: code is correct in
  `main`; user-facing symptom is a stale LXC build. Remediation =
  rebuild+redeploy per `docs/deployed-build-diagnosis.md`, NOT code.

Separately, the `membership-report-kiosk-tunnel` OpenSpec change has
Phases 4–5 outstanding on its task list (see below) — explicitly not started
and not blocking.

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

Introduced or surfaced by PR #4 / PR #5 (documented as TODOs inside config
files — not silently ignored):

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
- **`requirements.txt` drift**: PR #4 (#4648ac9) bumped lint tools (black 24→26,
  flake8 7.0→7.3, mypy 1.8→2.3); PR #5 (#22843b9) bumped core deps (fastapi
  0.109→0.139, pydantic 2.5→2.13, pydantic-settings 2.1→2.14, sqlalchemy
  2.0.25→2.0.51). The local `.venv` is the de facto source of truth. Recommend
  `uv lock` or `pip freeze > requirements.lock` to prevent silent recurrence.
- **Dev DB masks CI bugs**: `backend/.env` provisions `INTERNAL_API_SECRET`,
  `API_KEY`, `APP_ENV`, `ENVIRONMENT`, `DEBUG` — none of which CI sets by
  default. CI was extended in PR #5 (`a468e73`) to set `INTERNAL_API_SECRET`.
  Other env vars may still diverge. Local pytest is NOT a substitute for CI.

## CI status

`.github/workflows/ci.yml` is **green at the last `main` run** (PR #6, `6fcab85`).
Three jobs, all passing. **Note:** the `admin-data-tools` slice chain has NOT
been pushed — these counts reflect `main` only, not the archived SDD change.

- `backend` (~1m) — flake8, black --check, mypy, pytest with Postgres+Redis
  services. Backend pytest: **69 passed, 0 failed**.
- `frontend` (~45s) — npm ci, lint, type-check, vitest run. **24 tests pass.**
- `cv_service` (~1m15s) — pip install, pytest. **12 tests pass.**

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

Systemd units created by `install.sh`: `powerhouse-backend`, `powerhouse-cv`
(referenced in [SECURITY.md §9](./SECURITY.md)). Health checks: `GET /api/health`
(basic), `/api/health/db` (internal), `/cv/health`.

## Dev LXC deployment (discovered 2026-07-28)

The dev LXC (`ssh faceapp`, hostname `DEVFaceApp`) runs the app stack
(`facegym-backend`, `facegym-cv`, `nginx`). Key paths:

- Canonical repo checkout: `/opt/faceapp` (fresh clone of `main`, created
  2026-07-28; future deploys: `git pull && npm ci && npm run build && rsync`).
- Nginx served dir: `/opt/powerhouse-membership/frontend/dist` (app lives as
  a flat copy at `/opt/powerhouse-membership`, NO `.git`).
- Previous dist backup: `/opt/powerhouse-membership/frontend/dist.bak-20260728-112656`.
- Frontend rebuilt and redeployed 2026-07-28 from `main` 6fcab85: bundle
  `index-DvYf6lga.js`, `customRange` verified present (feature #4 now live).
- rsync 3.2.7 present; smbclient NOT installed (needed if BACKUP_REMOTE_TYPE=smb).

## Upcoming priorities

1. **Merge the `admin-data-tools` PR chain** — PRs #7 (slice-a→tracker),
   #8 (slice-b→slice-a), #9 (slice-c→slice-b) are OPEN on GitHub. Merge in
   order #7 → #8 → #9, then open the tracker → `main` PR (which triggers CI
   for the first time; the workflow only fires on `main`).
2. ~~Rebuild the LXC frontend~~ — DONE 2026-07-28 (see Dev LXC deployment above).
3. **Rotate the `gh.env` fine-grained PAT** — its value was discussed in chat;
   it is gitignored but should be rotated as hygiene. Note: PAT creation
   requires the GitHub web UI (no API); after regenerating, update
   `/root/faceapp/gh.env` and re-run `gh auth setup-git`.
4. **Adopt a lockfile** (`uv lock` or `pip freeze > requirements.lock`) — the
   silent drift between local venv and `requirements.txt` caused 3 PR iterations
   in PR #4 and 2 in PR #5. Locking prevents recurrence.
5. **OpenSpec Phase 4 (portal security)** when the portal tunnel work resumes —
   start with task 4.1 (HMAC-SHA256 webhook RED test) in `openspec/changes/membership-report-kiosk-tunnel/tasks.md`.
6. **Provision `WOMPI_INTEGRITY_SECRET`** from the Wompi dashboard before any
   production payment flow goes live.
7. **Reconcile `feature/tracker`** with `main` — decide whether remaining
   commits are redundant post-PR-#1 or carry value; delete if the former.
8. **Optional cleanup**: re-enable silenced ESLint rules after fixing the 89
   `any`/unused-vars warnings; migrate models to `Mapped[T]` to drop the mypy
   `disable_error_code` scopes; remove `# type: ignore` shims.
