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

## Repository layout

| Path | Purpose | Key entry file |
|------|---------|----------------|
| `backend/` | FastAPI REST API, JWT auth, RBAC, payments, scheduler | `backend/main.py` |
| `backend/api/` | Route handlers (auth, members, memberships, sales, portal, etc.) | `backend/api/auth.py` |
| `backend/core/` | config, database, security (JWT/bcrypt), encryption (AES-GCM) | `backend/core/config.py` |
| `backend/services/` | Domain logic (dashboard aggregation, etc.) | `backend/services/dashboard_service.py` |
| `backend/alembic/` | DB migrations | `backend/alembic.ini` |
| `backend/tests/` | pytest suite (needs Postgres + Redis) | `backend/tests/` |
| `frontend/` | React 18 + TypeScript + Vite + MUI SPA | `frontend/src/main.tsx` |
| `frontend/src/pages/Kiosk/Kiosk.tsx` | Kiosk terminal (USB/MJPEG camera + WS recognition) | — |
| `frontend/src/i18n/translations.ts` | All ES/EN strings (`t.*.*`) | — |
| `frontend/src/contexts/` | Auth + Theme + Language providers | — |
| `cv_service/` | FastAPI + OpenCV + FaceNet; RTSP + WebSocket camera input | `cv_service/main.py` |
| `cv_service/recognition/` | FaceNet recognizer + template matcher | — |
| `cv_service/validation/` | Access policy (start/end date enforcement) | `cv_service/validation/access_validator.py` |
| `scripts/` | Ops: backup, restore, health monitor, nginx fix, migrations | `scripts/backup.sh` |
| `openspec/` | SDD artifacts (proposals, specs, designs, tasks) | `openspec/config.yaml` |
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
does. Default login after install: `admin` / `admin123` — change immediately.

For running a single service during development, see [Three services](#three-services).

## Three services

**Backend** — Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Redis. Exposes `/api`
on `:8000`. Owns auth (JWT HS256, Redis blacklist), RBAC, biometric AES-256-GCM
encryption, Wompi payment webhooks, and the APScheduler email-report job. Run
alone: `cd backend && uvicorn main:app --reload --port 8000`. Needs Postgres +
Redis up (use `docker-compose up db redis` if not running them system-wide).

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

CI (`.github/workflows/ci.yml`) runs three jobs. These are the exact commands:

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

Backend CI supplies Postgres + Redis as GitHub Actions services. Locally, run
`docker-compose up db redis` before `pytest`. Full CI config:
[ci.yml](./.github/workflows/ci.yml).

## Conventions

- **Commits**: Conventional Commits (`feat:`, `fix:`, `chore:`, `fix(kiosk):`,
  etc.). See `git log --oneline` for established prefixes.
- **Branches**: named `^(feat|fix|chore|docs|refactor|test)/[a-z0-9._-]+$`
  (e.g. `fix/kiosk-recognition-state-regressions`).
- **PRs**: merge commits use the GitHub `Merge pull request #N` format. No
  automated PR-validation workflow yet (see traps).
- **No `Co-Authored-By`** or AI attribution in commits or PRs.
- **i18n**: every user-visible string goes through `t.<section>.<key>` in
  `frontend/src/i18n/translations.ts`, with both `es` and `en` keys. No
  hardcoded Spanish/English in JSX. Enforced by convention only — no lint rule.
- **Secrets**: never hardcode. All secrets are env vars documented in
  [SECURITY.md §2](./SECURITY.md). Verify `.env` is gitignored before committing.
- **SDD**: changes follow Spec-Driven Development — artifacts live in
  `openspec/changes/<change-name>/`. See [SKILL.md SDD workflow](./SKILL.md#sdd-workflow).

## Critical traps

1. **`gh.env` is a fine-grained PAT** at `/root/faceapp/gh.env` (gitignored).
   Required for `git push` because the default OAuth token lacks the `workflow`
   scope needed to push the CI workflow file. Treat as a secret; rotate after
   any chat discussion. Source via `source gh.env && gh auth setup-git` or pass
   `GH_TOKEN` inline.
2. **CI was just added (PR #3, 2026-07-27).** PRs #1 and #2 merged with ZERO
   GitHub Actions validation — only local TDD evidence. Do not assume "CI passed"
   for any commit before `b476944`. The first real CI run happens on the NEXT
   push/PR to `main`.
3. **Backend tests require live Postgres + Redis.** They are not mocked. Run
   `docker-compose up -d db redis` (or system services) before `pytest`.
4. **Colombia timezone (UTC-5) is hardcoded in places.** Commits `f031ed1` and
   `b18cd3c` introduced `America/Bogota` for "today" date math; `85cf905` fixed
   a date-only-string UTC bug that was creating 29-day memberships. Always use
   the app timezone helpers, not naive `datetime.utcnow()`.
5. **WebSocket `onerror` → `onclose` ordering is a known race.** The USB error
   overlay in `Kiosk.tsx` must check BOTH states: see `connectionStatus ===
   'error' || connectionStatus === 'disconnected'` at
   `frontend/src/pages/Kiosk/Kiosk.tsx:807` and the guide-suppression guard at
   `:861`.
6. **`connectionStatus` defaults to `'disconnected'`** and is only set by the
   USB code path. The guide visibility check must be scoped `!usbMode ||
   (connectionStatus !== 'error' && connectionStatus !== 'disconnected')` —
   otherwise it permanently hides the guide in remote/MJPEG mode.
7. **`branch-pr` skill rules are NOT enforced by CI.** No PR-validation
   workflow exists. Issue-first checks and `type:*` labels are aspirational.
   Existing PRs #1/#2/#3 merged with no linked issues or labels.
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

## Where to look next

| Need | File |
|------|------|
| Current state, HEAD, open work | [STATUS.md](./STATUS.md) |
| How to resume the last session | [RESUME.md](./RESUME.md) |
| Domain knowledge, architecture, memorable bugs | [SKILL.md](./SKILL.md) |
| Threat model, secrets, biometrics, payments | [SECURITY.md](./SECURITY.md) |
| Feature list, user guide, API reference | [README.md](./README.md) |
| Active SDD change (reports + kiosk + portal) | [openspec/changes/membership-report-kiosk-tunnel/proposal.md](./openspec/changes/membership-report-kiosk-tunnel/proposal.md) |
| CI pipeline definition | [.github/workflows/ci.yml](./.github/workflows/ci.yml) |
