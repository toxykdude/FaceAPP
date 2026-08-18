# Deploy runbook: portal-secure-restore (guest purchase + payment integrity)

Ordered deployment protocol for the portal-secure-restore change chain
(PRs: payment integrity → guest provisioning → Pages guest checkout). Read
[SECURITY.md §2](../SECURITY.md) first: no real secret value ever lands in
this repo — Cloudflare and LXC 114 provisioning is orchestrator/ops-owned.

## Deploy order — backend FIRST, Pages second

The backend must be live before the Pages relay changes:

1. **Backend (LXC 114)** — migration + new code.
2. **Pages (powerhouse-site)** — relay amount gate + guest checkout UI,
   deployed minutes later in the same window.

The order is load-bearing in both directions:

- The relay's new `amount_in_cents` field requires the new backend to accept
  it (old backend rejects unknown-shape renewals silently differently).
- The new backend REQUIRES `amount_in_cents` (schema v2). An old relay that
  still omits it gets a loud **422** from `/api/portal/webhook-renew` — see
  the deploy-gap window below.

## Backend deploy (LXC 114)

```bash
cd /opt/powerhouse-membership/backend
set -a; . ./.env; . /etc/faceapp/migrate-db.env; set +a
./venv/bin/alembic upgrade head
./venv/bin/alembic current   # ALWAYS confirm the head moved (trap 20)
systemctl restart powerhouse-backend
```

Migration `8d7e6f5a4b3c` (price CHECK + `wompi_reference` UNIQUE/backfill)
runs as the dedicated `powerhouse_migrator` role via
`MIGRATE_DATABASE_URL` — see AGENTS.md trap 20. If you see
`must be owner of ...`, the env file was not sourced; do NOT reach for
`sudo -u postgres`.

## The deploy-gap renewal 422 window

Between the backend deploy and the Pages deploy, an OLD relay forwarding
renewal webhooks without `amount_in_cents` receives **422 Invalid webhook
payload** from the new backend. This is deliberate (deploy-gap contract,
design D4): provisioning an unverified amount is never acceptable.

Behavior during the gap:

- The backend changes NO state (422 fires before any lookup/write).
- The relay logs the rejection; Wompi still receives its 200 from the relay
  event endpoint.
- Affected members' renewals are NOT provisioned during the gap. The pending
  Redis record survives ≤24 h (TTL 86400); once Pages is deployed, Wompi
  event replays (or a re-forwarded event) provisions them through the
  normal webhook path. If a payment's TTL expires, reconcile manually — the
  webhook logs `no pending record and no prior sale` alerts for exactly
  this case.

Minimize the window: deploy Pages immediately after the backend restart.

## Environment provisioning (placeholders only — never commit values)

The repo ships `backend/.env.example` with placeholder keys. Real values are
provisioned at deploy time on the target hosts only:

| Variable | Where | Notes |
|---|---|---|
| `PORTAL_INTERNAL_API_KEY` | backend `.env` (LXC 114) | Authenticates `GET /api/portal/pending-payment/{ref}` (relay-only). Generate ≥32 random bytes. Unset/empty → deny-all 401 (fail closed). |
| `FACEGYM_PORTAL_INTERNAL_KEY` | Cloudflare Pages env (dashboard or wrangler) | The same value, relay side. A Pages leak must not expose CV auth — hence a dedicated key, not `INTERNAL_API_SECRET`. |
| `WOMPI_INTEGRITY_SECRET` | backend `.env` | Already provisioned (webhook HMAC). |
| `GUEST_CHECKOUT_RATE_LIMIT` | backend `.env` (optional) | slowapi limit for `POST /api/portal/pending-payment/guest`; defaults to `10/minute`. |

Rotate the internal key by updating both sides in the same window; denials
are uniform 401s, so a mismatch fails closed without information leakage.

## Guest provisioning behavior to verify post-deploy

- `POST /api/portal/pending-payment/guest` stores a v2 record (TTL 86400)
  only for signature-format references and phones normalizable to 57+10.
- An APPROVED guest webhook provisions Member + Membership + Sale in one
  commit; duplicate canonical phones attach instead of duplicating; the
  provisioning advisory lock is `member-provision:{phone}` (EX 15) in Redis.
- New members are created with `consent_given_at NULL` and
  `facial_data_enrolled false` — face enrollment happens at the gym, never
  implied by a purchase.

## Rollback

Revert the PR commits; `alembic downgrade` drops the CHECK/index only
(column + backfilled data retained). Un-consumed pending Redis keys expire
within 24 h. See the design doc's Migration/Rollout section for detail.
