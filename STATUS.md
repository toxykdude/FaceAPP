# STATUS.md — Current project state

> Time-stamped snapshot of where FaceAPP is RIGHT NOW. Update this file as work
> progresses. For narrative, read [RESUME.md](./RESUME.md).

## Snapshot

| Field | Value |
|-------|-------|
| **Last updated** | 2026-07-27 |
| **Current HEAD** | `b476944` — Merge PR #3 `chore/add-ci-openspec-artifacts` |
| **Commits on main** | 71 |
| **PRs merged to date** | 3 (#1 feature, #2 fix, #3 chore) |
| **CI workflow** | exists at `.github/workflows/ci.yml`, NOT yet triggered on real code |

`git rev-parse HEAD` → `b4769449460adaf1861579c155dc32606ea8198e`

## Active branches

```
* main                                    # b476944 (PR #3 merge)
  feature/pr2-membership-expiration-access
  feature/tracker                         # SDD work branch (PR1 commits a4613d9, 5e9fec2, d83793b)
  fix/kiosk-recognition-state-regressions # PR #2 branch
  remotes/origin/main
  remotes/origin/feature/pr2-membership-expiration-access
  remotes/origin/fix/kiosk-recognition-state-regressions
```

Local-only: `feature/tracker` and `feature/pr2-membership-expiration-access`
carry the in-progress SDD work for `membership-report-kiosk-tunnel`. They are
ahead of `main` on the reports + display/access work; PR #1 already merged the
expiration/access slice. Confirm with `git log main..feature/tracker --oneline`
before deleting.

## Recent merges

| PR | Merge SHA | Title |
|----|-----------|-------|
| #3 | `b476944` | chore(ci): add CI workflow, GitHub templates, and OpenSpec artifact trail |
| #2 | `2213bee` | fix(kiosk): resolve stuck-verifying, camera-restart freeze, denial masking + vanishing retry overlay, concurrent camera-start race, check-in name leak |
| #1 | `114d0ee` | feat(kiosk): premium dark redesign + split membership display from access + 3-path CV invalidation + custom date-range reports |

`#2` landed in two commits (`96bb59f`, `b26c45c`) representing the two TDD
review rounds. `#1` landed three feature commits (`a4613d9`, `5e9fec2`,
`d83793b`) from `feature/tracker`.

## Open work

**None on `main`.** PR #3 just merged. The OpenSpec change
`membership-report-kiosk-tunnel` has Phases 4–5 outstanding on its task list
(see below) but those are explicitly not started and not blocking.

## Known issues / tech debt

From `openspec/changes/membership-report-kiosk-tunnel/tasks.md` (Phases 4–5,
unchecked — explicitly NOT started, out of this session's scope):

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

Local-to-this-checkout (not repo debt):

- `feature/tracker` and `feature/pr2-membership-expiration-access` branches are
  unmerged to `main` beyond what PR #1 already carried. Reconcile or delete.

## CI status

The CI workflow at `.github/workflows/ci.yml` was added in PR #3 (commit
`60152b5`) and **has not yet run on real code**. It defines three jobs:

- `backend` — flake8, black --check, mypy, pytest (with Postgres + Redis
  services)
- `frontend` — npm ci, lint, type-check, vitest run
- `cv_service` — pip install, pytest

The **next push or PR to `main`** will be the first real CI run. Treat the
historical PRs as "locally tested only".

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

## Upcoming priorities

1. **Watch the first CI run** on the next PR to `main`. If flake8/mypy/black
   surface issues on pre-merge code, fix forward and consider tightening gates.
2. **Rotate the `gh.env` fine-grained PAT** — its use was discussed in chat; it
   is gitignored but should be rotated as hygiene.
3. **Reconcile `feature/tracker`** with `main` — decide whether remaining
   commits are redundant post-PR-#1 or carry value; delete if the former.
4. **OpenSpec Phase 4 (portal security)** when the portal tunnel work resumes —
   start with task 4.1 (HMAC-SHA256 webhook RED test).
5. **Provision `WOMPI_INTEGRITY_SECRET`** from the Wompi dashboard before any
   production payment flow goes live.
