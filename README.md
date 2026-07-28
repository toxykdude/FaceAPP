# FaceGYM — AI-Powered Membership Management Platform

> Facial-recognition gym membership platform: real-time kiosk access control,
> payment tracking, timezone-aware reporting, and automated local + remote
> backups. Backend (FastAPI) + CV service (OpenCV/FaceNet) + React admin SPA.

**TL;DR to run it:** `cp .env.example .env` → edit secrets → `docker-compose up
--build` (dev) or `sudo ./install.sh` on a bare-metal/LXC host (prod-like).
Default login `admin` / `admin123` — change it immediately.

## 🏋️ Features

### Core
- **Facial Recognition Access Control** — FaceNet recognition with configurable confidence thresholds; enrollment = 1 photo → 6 averaged embeddings, stored AES-256-GCM encrypted
- **Member Management** — Full CRUD with biometric enrollment (photo upload or webcam capture); membership history with older records collapsed in an accordion
- **Membership Plans** — Flexible plans with auto-calculated expiration dates; renewals start the day after the previous end date
- **Payment Tracking** — Cash/transfer payments with partial payment support; Wompi online payments via the member portal
- **Multi-Camera Support** — RTSP cameras + USB webcams via browser WebSocket streaming

### Sales & Reporting
- **Configurable-timezone reporting** — all report windows, bucketing, and sales timestamps use the IANA timezone saved in Settings (DST-aware, cached)
- **Custom date ranges** — reports accept arbitrary start/end dates on top of the preset 7d/30d/90d/year ranges
- **CSV export** — server-side `GET /api/sales/report/export` matching exactly what the on-screen report shows
- **Dashboard Analytics** — revenue trends, member growth, peak hours, check-in tracking
- **Automated Email Reports** — every 2 hours: sales, new members, and expired-access alerts (`POST /api/reports-email/send-now` to trigger manually)

### Backups & Data Safety
- **Automated backups every 30 minutes** — systemd timer, `pg_dump -F c` + biometric data + config + manifest + checksums, 30-day local retention
- **Remote replication to your storage** — NAS (rsync/SFTP) / FTP / SMB / NFS; remote failures are warn-only and never lose the local copy
- **Managed from the UI** — Settings → Backup tab: pick a transport, fill its fields, run a sanitized connection test, save. Passwords are write-only and AES-256-GCM encrypted at rest
- **Audited full-DB export** — admin-only `GET /api/system/db-export` streaming download, audit-logged; RLS-safe via a dedicated backup role
- **Restore tooling** — `scripts/restore.sh` + per-backup manifest

### Kiosk Terminal
- Full-screen welcome screen with live camera feed
- Green glow (access granted) / Red glow (access denied) recognition feedback
- Auto-reset after 3 seconds, ready for next member

### Administration
- **Role-Based Access Control (RBAC)** — Per-page permissions for staff users
- **Spanish/English i18n** — Full translation with language toggle
- **Dark/Light Theme** — Toggle in sidebar and settings
- **Custom Branding** — Upload your logo and set your organization name

## 🏗️ Architecture

Three services behind Nginx on one Proxmox LXC container:

```
┌─────────────────────────────────────────────────────────┐
│                    Proxmox LXC Container                 │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ Nginx    │  │ Backend  │  │ CV Service           │  │
│  │ :80/:443 │  │ :8000    │  │ :8001 (localhost)    │  │
│  │ SSL/WS   │──│ FastAPI  │──│ OpenCV + FaceNet     │  │
│  └──────────┘  │ SQLAlchemy│  │ RTSP + WebSocket     │  │
│                └────┬─────┘  └──────────┬───────────┘  │
│                ┌────▼─────┐ ┌────────┐   │              │
│                │PostgreSQL│ │ Redis  │   │              │
│                │ :5432    │ │ :6379  │───┘              │
│                └──────────┘ └────────┘                  │
└─────────────────────────────────────────────────────────┘
                          │
   ┌──────────────────────┼────────────────────┐
   │                      │                    │
 ┌─▼────────────────┐  ┌──▼───────────────┐  ┌─▼─────────────┐
 │ RTSP Camera      │  │ Kiosk PCs (LAN)  │  │ Backup target │
 │ (Reception Door) │  │ USB cam → Browser│  │ NAS/SFTP/FTP/ │
 │ Direct stream    │  │ WebSocket → CV   │  │ SMB/NFS       │
 └──────────────────┘  └──────────────────┘  └───────────────┘
```

### Tech Stack
| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Redis, APScheduler |
| CV Service | Python 3.11, OpenCV, FaceNet (InsightFace), FastAPI |
| Frontend | React 18, TypeScript, Vite, MUI 6, TanStack Query |
| Database | PostgreSQL 14+ (Row-Level Security enabled for portal isolation) |
| Reverse Proxy | Nginx with SSL, WebSocket proxy, rate limiting |
| Container | Proxmox LXC (Ubuntu 22.04), Cloudflare in front |

### Port map
| Service | Port | Exposure |
|---------|------|----------|
| Backend `/api` | 8000 | internal, via Nginx |
| Frontend (built SPA) | 80/443 | public via Nginx (3000 in docker dev) |
| cv_service | 8001 | **localhost only** — Nginx denies `/api/cv/` from outside |
| PostgreSQL / Redis | 5432 / 6379 | localhost |
| Vite dev server | 5173 | local development |

## 🚀 Quick Start

### A. Docker (development)

```bash
git clone https://github.com/toxykdude/FaceGYM.git
cd FaceGYM
cp .env.example .env        # then EDIT: replace every change-me secret
docker-compose up --build
```
Frontend on `:3000`, backend on `:8000` (internal), cv_service on `:8001`.

### B. Bare metal / LXC (production-like)

Prerequisites: Ubuntu 22.04+, Python 3.11+, Node.js 18+, PostgreSQL 14+, Nginx, 2GB RAM, 30GB disk.

```bash
git clone https://github.com/toxykdude/FaceGYM.git
cd FaceGYM
chmod +x install.sh
sudo ./install.sh
```

The installer will:
1. Install system dependencies (Python, Node.js, PostgreSQL, Nginx, `samba-client`, `sshpass`)
2. Create the database and user
3. Install Python dependencies (backend + CV service)
4. Build the React frontend
5. Configure Nginx with SSL (self-signed by default)
6. Create systemd services for auto-start (backend, cv service, backup timer)
7. Generate a `.env` file with random secrets

**Post-install:**
1. Access the app at `http://your-server-ip`
2. Default login: `admin` / `admin123` — **change this immediately!**
3. Settings → General: set organization name, upload your logo, set your timezone
4. Cameras: add your RTSP camera(s)
5. Open `/kiosk` on a kiosk PC with a USB camera for facial check-in
6. Settings → Backup tab: pick your remote backup target (optional)

## 💾 Backups & Restore

Backups run **every 30 minutes** via `powerhouse-backup.timer` →
`scripts/backup.sh`. Each run writes a `pg_dump` (custom format), a biometric
tarball, a config tarball, SHA-256 checksums, and a manifest under `BACKUP_DIR`
(default `/var/backups/powerhouse`), with **30-day local retention**.

### Configure it (two paths)

**Primary — admin UI (recommended):** Settings → **Backup** tab (admin only).
Choose a transport, fill the conditional fields, hit **Test** (a sanitized
1-byte probe), and Save. The password is encrypted at rest and materialized to
a root-only file (`/etc/faceapp/backup-remote.env`, 0600) that `backup.sh`
sources **after** `.env` — so UI-managed values always win.

**Advanced / fallback — `.env`:** edit `.env` directly (full reference in
`.env.example`). Used for headless installs or when the managed file is
absent. Delete `/etc/faceapp/backup-remote.env` to fall back to `.env`.

| Transport | Tool | Notes |
|-----------|------|-------|
| `none` | — | Local backup only (default) |
| `rsync` | `rsync` over SSH | Preferred. SSH key or `RSYNC_PASSWORD` |
| `sftp` | `sshpass -e sftp -b` | Requires the `sshpass` package |
| `ftp` | `curl --netrc-file` (0600) | ⚠️ **Cleartext** — prefer SFTP/rsync |
| `smb` | `smbclient` (SMB3) | Requires the `samba-client` package |
| `nfs` | `cp` into pre-mounted dir | Mount via `/etc/fstab` first |

Remote replication is **warn-only**: a failed/unreachable target logs one
sanitized line; the local backup and retention still succeed. No password ever
appears in logs.

### Row-Level Security: use a dedicated backup role

The app DB enforces RLS on portal-facing tables, so the **runtime role cannot
produce a complete dump** (rows are silently filtered). Create a dedicated role
(`BYPASSRLS` + `pg_read_all_data`, e.g. `powerhouse_backup`) and export its
connection string as `BACKUP_DATABASE_URL`. Both `backup.sh` and the admin
export endpoint prefer it over `DATABASE_URL`. If backups suddenly shrink,
check which URL is in effect first.

### Restore

```bash
scripts/restore.sh <TIMESTAMP>    # from the backup manifest
# or directly:
pg_restore -h localhost -U membership -d membership_db db_backup_<TIMESTAMP>.dump
```

### On-demand full export

Admin UI: Settings → Backup tab → **Export Database** — streams a fresh
`pg_dump -F c` to the browser (`GET /api/system/db-export`, admin-only,
audit-logged in DB).

## 🧪 Testing & CI

Every suite is CI-gated. The local commands below **exactly mirror the CI
jobs** (verified against the CI runs of PRs #7–#15):

| Suite | Command (working dir) | Count |
|-------|-----------------------|-------|
| Backend lint+format+types | `flake8 . && black --check . && mypy .` (`backend/`) | — |
| Backend tests | `python init_db.py && pytest tests/` (`backend/`) | 144 |
| Frontend lint+types | `npm run lint && npm run type-check` (`frontend/`) | — |
| Frontend tests | `npm run test` (`frontend/`) | 49 |
| CV service tests | `pytest tests/` (`cv_service/`) | 12 |

> ⚠️ Backend tests need **live Postgres + Redis** (`docker-compose up -d db
> redis`) AND the env exported — `conftest.py` does NOT read `backend/.env`:
> ```bash
> cd backend && set -a && . ./.env && set +a && python init_db.py && pytest tests/
> ```
> Skip the export and auth-dependent tests fail with 401s.

**CI:** `.github/workflows/ci.yml` — three jobs (backend with Postgres/Redis
services, frontend, cv_service), triggered **only on pushes and PRs targeting
`main`**. Docs-and-chore PRs run the full pipeline too.

## 🔒 Security

The full security contract (threat model, incident response, Habeas Data
compliance) lives in [SECURITY.md](./SECURITY.md). Headline rules:

- AES-256-GCM for biometric templates, RTSP URLs, and stored backup passwords
- JWT auth with Redis-blacklisted revocation; per-page RBAC; admin-only export/backup-config endpoints
- Full audit trail on sensitive operations (exports, enrollment, payments)
- Row-Level Security in Postgres isolates member-portal data
- cv_service is never internet-exposed (Nginx ACL); control endpoints need an API key
- Wompi webhooks verified with HMAC-SHA256 (provision `WOMPI_INTEGRITY_SECRET` before go-live)
- Remote backup credentials never touch argv, logs, or ps output

**Biometric data is legally sensitive** (Colombia, Ley 1581/2012 — Habeas
Data). Read [SECURITY.md §4](./SECURITY.md) before touching the enrollment or
template path.

## 🏭 Deployment

Production layout on the LXC (dev instance `DEVFaceApp` as the reference):

| Path | Role |
|------|------|
| `/opt/faceapp` | **Canonical git clone** — deploys start here (`git pull`) |
| `/opt/powerhouse-membership` | Flat app copy served by Nginx (no `.git`); rsync target |
| `/var/backups/powerhouse` | Local backup artifacts (30-day retention) |
| `/etc/faceapp/backup-remote.env` | UI-managed backup config (0600, root-only) |
| `/etc/faceapp/backup-db.env` | `BACKUP_DATABASE_URL` for the RLS-bypass role (0600, root-only) |

Deploy flow: `git pull` in `/opt/faceapp` → `cd frontend && npm ci && npm run
build` → `rsync -a --delete --exclude='.env*' /opt/faceapp/
/opt/powerhouse-membership/` → `systemctl restart facegym-backend facegym-cv`.
Never exclude `biometric*` from that rsync.

Systemd units: `powerhouse-backend`, `powerhouse-cv` (installed by
`install.sh`) and `powerhouse-backup.service` + `powerhouse-backup.timer`
(shipped in `scripts/systemd/`).

When a feature "doesn't work" on a deployed instance, suspect a **stale static
bundle before the code** — follow the 4-step protocol in
[`docs/deployed-build-diagnosis.md`](./docs/deployed-build-diagnosis.md).

## 🤝 Contributing

- **Branches**: `^(feat|fix|chore|docs|refactor|test)/[a-z0-9._-]+$`
- **Commits**: Conventional Commits (`feat:`, `fix:`, `chore:`, …)
- **PRs target `main`**; CI gates every merge. A PR to any other branch runs no checks.
- **No AI attribution**: no `Co-Authored-By` lines in commits or PRs.
- **i18n**: all user-visible strings go through `t.*.*` keys in
  `frontend/src/i18n/translations.ts` (both `es` and `en`).
- **Timezones**: use `get_app_tz(db)` (`backend/services/timezone.py`) — never hardcode offsets.
- **Specs**: major changes follow the SDD flow — see `openspec/changes/` and the
  accepted specs in `openspec/specs/`.
- Agent/developer onboarding docs: [AGENTS.md](./AGENTS.md),
  [SKILL.md](./SKILL.md), [STATUS.md](./STATUS.md), [RESUME.md](./RESUME.md).

## 📱 Usage Guide

### Adding Members
1. Navigate to **Members** → **New Member**
2. Fill in name, ID (cédula), and contact info
3. Click **Create Member**
4. Assign a membership plan (auto-calculates end date)
5. Enroll face via webcam or photo upload (minimum quality score: 0.9)

### Kiosk Setup
1. Open `http://your-server/kiosk` on a dedicated PC
2. Select camera → toggle **USB Camera** mode
3. Browser will request camera permission — approve
4. The kiosk shows live feed with recognition overlay
5. Members see green glow (granted) or red glow (expired)

### Managing Memberships
1. Go to a member's page → **Membership History**
2. Click **Renew** to extend with same plan (start = last end date + 1 day)
3. Or click **+ New Membership** to assign a different plan
4. Set payment method (cash/transfer) and amount
5. Partial payments supported — shows remaining balance
6. More than 2 memberships: older ones collapse into an "older" accordion

### Reports
1. **Sales / Reports** page: preset ranges (7d/30d/90d/year) or a custom
   start/end — all windows are computed in the configured timezone
2. Click **Export** for a server-side CSV of exactly what's on screen
3. Automated email reports land every 2 hours; manual trigger:
   `POST /api/reports-email/send-now`

### User Roles & Permissions
- **Admin**: Full access to all features
- **Staff**: Configurable per-page access (Settings → Users → Edit → toggle
  Dashboard, Members, Memberships, Cameras, Sales, Reports)

## 🔧 API Reference

The backend exposes a REST API at `/api/`. Full docs:
- Swagger UI: `http://your-server/docs`
- ReDoc: `http://your-server/redoc`

### Key Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Authenticate and get JWT |
| `/api/members` | GET/POST | List/create members |
| `/api/members/{id}/photo` | GET | Get member face photo |
| `/api/members/{id}/enroll` | POST | Enroll face biometric |
| `/api/memberships` | GET/POST | List/create memberships |
| `/api/membership-plans` | GET/POST | Manage plans |
| `/api/sales` | GET/POST | Sales transactions |
| `/api/sales/dashboard` | GET | Aggregated report data |
| `/api/sales/report/export` | GET | CSV export of the current report window |
| `/api/events` | GET | Access events log |
| `/api/events/today-recognized` | GET | Today's recognized members |
| `/api/cameras` | GET/POST | Camera management |
| `/api/settings` | GET/PUT | System settings |
| `/api/settings/upload-logo` | POST | Upload custom logo |
| `/api/reports-email/send-now` | POST | Trigger email report |
| `/api/system/db-export` | GET | Full DB dump download (admin, audited) |
| `/api/system/backup-config` | GET/PUT | Remote-backup configuration (admin, masked) |
| `/api/system/backup-config/test` | POST | Sanitized connection probe (admin) |
| `/cv/health` | GET | CV service health |
| `/cv/stream/{id}` | GET | MJPEG camera stream |
| `/cv/ws/camera/{id}` | WS | WebSocket for browser camera |

## 📁 Project Structure

```
FaceGYM/
├── backend/                  # FastAPI backend
│   ├── api/                  # API endpoints (incl. system.py: db-export + backup-config)
│   ├── core/                 # config, database, security, AES-GCM encryption, email
│   ├── services/             # timezone, backup_config, report_window, dashboard logic
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── alembic/              # DB migrations
│   ├── tests/                # pytest suite (needs Postgres + Redis)
│   ├── main.py               # FastAPI app entry
│   └── requirements.txt
├── cv_service/               # Computer vision service
│   ├── main.py               # FastAPI app + WebSocket handler
│   ├── stream/               # RTSP + V4L2 stream processor
│   ├── detection/            # Face detection + quality + liveness
│   ├── recognition/          # FaceNet recognizer + template matcher
│   └── api/                  # Backend client
├── frontend/                 # React frontend
│   ├── src/
│   │   ├── api/              # API clients
│   │   ├── components/       # Shared components (+ settings/SettingsBackupTab.tsx)
│   │   ├── contexts/         # Auth + Theme + Language contexts
│   │   ├── i18n/             # Translations (ES/EN)
│   │   ├── pages/            # Page components (Kiosk, Settings, Reports, ...)
│   │   └── main.tsx          # Entry point
│   └── package.json
├── scripts/                  # Ops: backup.sh, remote_push.sh, restore.sh, systemd/
├── openspec/                 # SDD: specs/ (accepted) + changes/ (active/archive)
├── docs/                     # Runbooks (deployed-build diagnosis)
├── .github/workflows/        # CI (3 jobs, main-gated)
├── install.sh                # One-click installer
├── docker-compose.yml        # Dev orchestration
├── .env.example              # Environment template (incl. backup remote config)
└── README.md                 # This file
```

## 📄 License

MIT License — feel free to use, modify, and deploy for your own gym or business.
