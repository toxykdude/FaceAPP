# Portal Tunnel Allowlist — Verification Runbook

Runtime verification for the Cloudflare Tunnel exposure of the member portal
backend on **LXC 114**, per `openspec/changes/membership-report-kiosk-tunnel/design.md`
(threat matrix: public allowlist, exact).

All names below are **placeholders** — substitute the real values at deploy
time. No secrets belong in this document or in the config artifact.

## Exposure model (who may reach what)

```
Internet → Cloudflare Pages (portal frontend, external)
              └─ /api/* proxied by Pages Functions → Cloudflare Tunnel
Internet → nginx (admin SPA + kiosk, LAN/proxied as today; /api/cv/ denied from exterior)
Cloudflare Tunnel (cloudflared on LXC 114) → http://127.0.0.1:8000 (backend ONLY)
cv_service (:8001) — never reachable through the tunnel; nginx keeps /api/cv/ interior-only
```

The tunnel is the ONLY new exposure. The allowlist is enforced at the
cloudflared ingress (`scripts/cloudflared/config.yml`); authentication
(member JWT, webhook HMAC) and method handling (405) are enforced by the
application behind it.

## Allowlist (exact)

| Decision | Route | Notes |
|---|---|---|
| ALLOW | `GET /api/health` | basic liveness only |
| ALLOW | `POST /api/auth/member-login` | 10/minute per IP (slowapi) |
| ALLOW | `POST /api/auth/member-verify` | 10/minute per IP + PIN lockout |
| ALLOW | `POST /api/auth/member-resend` | 10/minute per IP + cooldown |
| ALLOW | `/api/portal/*` | member JWT (or HMAC for webhook-renew) |
| DENY | everything else | incl. `/cv/*`, `/api/cv/*`, `/api/health/db`, `/api/health/full`, `/api/health/redis`, all admin API, static assets |

Route decisions are pinned by unit test:
`cd backend && python -m pytest tests/test_tunnel_allowlist.py -q`.

## Provisioning (once, on LXC 114 — placeholders)

```bash
# 1. Install and authenticate cloudflared (browser login, no secrets stored here)
cloudflared tunnel login

# 2. Create the tunnel (note the printed UUID = <TUNNEL_ID>)
cloudflared tunnel create powerhouse-portal

# 3. Route DNS for the portal hostname (must already be in your CF zone)
cloudflared tunnel route dns powerhouse-portal portal.example.com

# 4. Install the config (replace <TUNNEL_ID> and portal.example.com)
sudo mkdir -p /etc/cloudflared
sudo cp scripts/cloudflared/config.yml /etc/cloudflared/config.yml
sudo cp <TUNNEL_ID>.json /etc/cloudflared/<TUNNEL_ID>.json
sudo chmod 600 /etc/cloudflared/<TUNNEL_ID>.json

# 5. Run as a service
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

## Runtime verification (exact checks — run AFTER opening)

Replace `portal.example.com` with the real hostname. Every command shows the
expected result; anything else means STOP and close the tunnel.

```bash
BASE=https://portal.example.com

# Reachable
curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/health"
# → 200

curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BASE/api/auth/member-login" \
  -H 'Content-Type: application/json' -d '{"phone":"3000000000"}'
# → 200 (generic response even for unknown numbers) — reachable + rate-limited path

curl -s -o /dev/null -w '%{http_code}\n' "$BASE/api/portal/plans"
# → 200

# Denied by the ingress catch-all (cloudflared http_status:404)
for PATH_TO_CHECK in \
    /cv/templates \
    /api/cv/templates \
    /api/health/db \
    /api/health/full \
    /api/health/redis \
    /api/members \
    /api/users \
    /api/system/db-export \
    /docs; do
  printf '%-28s %s\n' "$PATH_TO_CHECK" \
    "$(curl -s -o /dev/null -w '%{http_code}' "$BASE$PATH_TO_CHECK")"
done
# → every line must be 404
```

Also verify the near-miss class (anchored regexes must not widen):

```bash
for PATH_TO_CHECK in /api/healthx /api/auth/member-loginX /api/portalx/me; do
  printf '%-28s %s\n' "$PATH_TO_CHECK" \
    "$(curl -s -o /dev/null -w '%{http_code}' "$BASE$PATH_TO_CHECK")"
done
# → every line must be 404
```

## Cloudflare dashboard steps (Zero Trust UI)

1. **Zero Trust → Networks → Tunnels**: the `powerhouse-portal` tunnel shows
   connector status **HEALTHY** (LXC 114, uptime counter increasing).
2. Open the tunnel's **Public Hostname** table: it must contain exactly the
   three allow rules (health, member-auth, portal) with the paths from
   `scripts/cloudflared/config.yml`, plus nothing else — the catch-all is not
   represented in this table; verify it with the curl checks above.
3. **DNS → Records**: `portal` CNAME → `<TUNNEL_ID>.cfargotunnel.com`
   (proxied) — auto-created by `tunnel route dns`; no other new records.
4. Optional belt-and-braces: **Security → WAF** a firewall rule blocking
   requests to the portal hostname whose URI Path does not match
   `^/api/(health/?|auth/member-(login|verify|resend)/?|portal/.*)`.

## Rollback

```bash
sudo systemctl disable --now cloudflared
cloudflared tunnel delete powerhouse-portal   # after cleanup, on LXC 114
```

The portal goes offline; admin/kiosk traffic (nginx) is untouched. RLS stays
enabled regardless — rollback never weakens the database.
