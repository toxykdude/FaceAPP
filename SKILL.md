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
and Wompi online payment integration via a customer portal. Target region is
**Colombia (UTC-5)**, which drives both timezone handling and the Habeas Data
legal regime (Ley 1581/2012) for biometric data — see
[SECURITY.md §4](./SECURITY.md).

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
  biometric encryption, Wompi webhook handling, APScheduler email reports.
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

The currently tracked change is
[`membership-report-kiosk-tunnel`](./openspec/changes/membership-report-kiosk-tunnel/):
custom date-range reports, display-vs-access membership split with 3-path CV
cache invalidation, and a portal security + Cloudflare Tunnel allowlist.
Phases 1–3 are implemented (PRs #1 and #2); Phases 4–5 (portal security,
deployment prereqs) remain — see
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
- **Colombia timezone** (`b18cd3c`, `f031ed1`, `85cf905`) — naive UTC math
  produced wrong "today" boundaries and 29-day memberships. Use
  `America/Bogota` (UTC-5) consistently for date logic.
- **CV API key propagation** (`32a30db`) — after enrollment the backend
  notified cv_service without the `X-API-Key` header; the notification silently
  failed. Any change to the enrollment → CV notification path must keep the
  header (see `notify_cv_invalidation`).
- **Display vs access predicate** (SDD design, PR #2) — using a single shared
  query for "show latest expiration" and "grant access" caused early entry
  before `start_date`. These MUST stay split (see
  [design.md](./openspec/changes/membership-report-kiosk-tunnel/design.md)).
