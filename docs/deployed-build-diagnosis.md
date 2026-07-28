# Deployed-build diagnosis: custom date-range reports

The custom date-range report feature (dropdown option **Rango personalizado**
with *from/to* date pickers) is implemented and tested in `main`
(commit `a4613d9`, PR #1). If users cannot see or use it in a deployed
environment, the deployed frontend bundle almost certainly predates that merge.
This document is the ordered protocol to confirm drift and remediate it.
Only escalate to a code bug after every step below checks out.

## Step 1 — Compare the deployed bundle against main

On the LXC serving the frontend (Nginx serves the Vite build output):

```bash
# Where Nginx serves the SPA (check root in /etc/nginx/sites-enabled/*):
ls -l --time-style=full-iso /var/www/faceapp/dist/assets/ | head
```

Vite emits hashed bundle names (`index-<hash>.js`). A bundle `mtime` older
than the PR #1 merge date (2026-07-27) proves staleness immediately.

## Step 2 — Prove the feature is absent from the served bundle

```bash
grep -l "customRange" /var/www/faceapp/dist/assets/*.js
grep -l "buildReportRange" /var/www/faceapp/dist/assets/*.js  # may be minified away; absence of customRange is the decisive signal
```

If `customRange` does not appear in any served asset, the deployed build does
not contain the feature — this is a deployment issue, not a code bug.

## Step 3 — Confirm the runtime renders the pickers when the build is current

With a current build (local `npm run build && npm run preview`, or a
redeployed LXC):

1. Open **Reportes**, open the time-range dropdown.
2. Select **Rango personalizado** — two date inputs (*Inicio* / *Fin*) must appear.
3. Pick a valid range — the dashboard and summary must refetch with
   `start_date`/`end_date` query params (visible in the browser Network tab).
4. Pick a reversed range — an inline error appears and no request fires.

## Step 4 — Remediate drift (rebuild + redeploy)

```bash
cd /opt/faceapp/frontend          # repo checkout on the LXC
git fetch origin && git checkout main && git pull
npm ci && npm run build
sudo rsync -a --delete dist/ /var/www/faceapp/dist/
sudo systemctl reload nginx
```

Then re-run Step 2: `customRange` must now be present in the served bundle.

## Escalation

If — and only if — the served bundle contains `customRange`, the pickers
render, and requests still fail: capture the failing request/response from the
Network tab and open a bug issue. Suspects at that point are the backend
window resolution (`_resolve_report_window` in `backend/api/sales.py`) or a
timezone-setting mismatch (see `backend/services/timezone.py`).
