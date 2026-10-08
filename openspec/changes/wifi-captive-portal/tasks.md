# Tasks: WiFi Captive Portal

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | A ≈ 850 · B ≈ 700 · C ≈ 600 · total ≈ 2150 |
| 400-line budget risk | High per slice (under the 800-line/PR override) |
| Chained PRs recommended | Yes (pre-sliced A → B → C; B and C depend on A) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked: PR-A targets main, PR-B targets A, PR-C targets B |

Decision needed before apply: No

> Backend slices need live Postgres+Redis (already running on this host, with
> `backend/.env` exported). Slice B runs fully offline (pytest only).

---

## Slice A: Backend authorization + accounting (PR-A)

- [x] **A.1 RED — authorize tests**: `backend/tests/test_wifi_authorize.py` covering every denial reason, payment gate (pending vs partial), document normalization, device cap with stale/ended sessions, timeout bounds, bilingual messages, fail-closed auth (401/503). Run → fail (no route).
- [x] **A.2 GREEN — model + schemas + service**: `models/wifi_session.py`, `schemas/wifi.py`, `services/wifi_auth.py` (canonical predicate, timezone-aware timeout, device cap), `core/config.py` WIFI_* knobs, `models/__init__.py` export.
- [x] **A.3 GREEN — API**: `api/wifi.py` (`POST /wifi/authorize`, `POST /wifi/accounting`, `GET /wifi/sessions` staff-only) reusing `verify_internal_secret`; register in `main.py`.
- [x] **A.4 RED/GREEN — accounting tests**: `tests/test_wifi_accounting.py` — start/interim/stop lifecycle, idempotency, unknown-username row, staff-only listing.
- [x] **A.5 — migration**: alembic revision `a3f8c2d91e47` (table, indexes, unique constraint, RLS enable + guarded app-role policy). Upgrade dev DB, `alembic current` confirms head.
- [x] **A.6 — full suite + lint/type**: `flake8 .`, `black --check .`, `mypy .`, `pytest tests/` all green.

## Slice B: radius_service (PR-B)

- [x] **B.1 RED — server tests**: `radius_service/tests/test_server.py` — PAP extraction, accept attributes, reject Reply-Message, backend-error → reject, cooldown lockout, acct mapping. Run → fail.
- [x] **B.2 GREEN — service**: `config.py` (env), `backend_client.py` (httpx, X-Internal-Secret), `server.py` (pyrad Server subclass, fail-closed, cooldown), `main.py` entry, `tools/radtest.py`, `requirements.txt`.
- [x] **B.3 — backend-client tests**: `tests/test_backend_client.py` — header injection, URL join, error mapping.
- [x] **B.4 — CI job**: `.github/workflows/ci.yml` gains `radius_service` (mirror cv_service).
- [x] **B.5 — local run**: pytest green; live smoke via `tools/radtest.py` against backend.

## Slice C: Portal page + runbook + installer (PR-C)

- [x] **C.1 — portal page**: `deploy/pfsense/powerhouse-portal.html` (form contract `auth_user`/`auth_pass`, `$PORTAL_ACTION$`, `$PORTAL_REDIRURL$`, `$PORTAL_MESSAGE$`, `$PORTAL_ZONE$`, ES/EN toggle, no-JS fallback, Powerhouse branding).
- [x] **C.2 — systemd + installer**: `scripts/systemd/facegym-radius.service`; `install.sh` section 7 gains the unit + venv; `/etc/faceapp/radius.env` documented (0600).
- [x] **C.3 — runbook**: `docs/pfsense-captive-portal.md` — architecture, prerequisites (AP bridge mode, dedicated interface), backend deploy (trap-20 migrator + `alembic current`), radius install + firewall (UDP 1812/1813 from pfSense only), pfSense CP zone step-by-step, RADIUS + accounting config, verification checklist, rollback, troubleshooting.
- [x] **C.4 — docs sync**: `backend/.env.example` WIFI_* knobs; `radius_service/radius.env.example`; README feature bullet; AGENTS.md layout row + trap; SKILL.md domain entry; STATUS.md snapshot.
