# WiFi Captive Portal — pfSense + FaceAPP membership auth

Member WiFi at the gym is gated on an **active FaceAPP membership**. Clients
that join the member SSID get a captive-portal page, enter their cédula, and
may browse only if FaceAPP resolves that document to a member with a
date-valid, paid membership. Denial reasons and semantics are the same ones
the kiosk uses at the door.

```
[Member phone] ─WiFi─ [AP (bridge mode)] ─ [pfSense CP zone: MEMBER_WIFI]
                                                  │ RADIUS PAP  (UDP/1812)
                                                  │ RADIUS Acct (UDP/1813)
                                                  ▼
                                 radius_service (facegym-radius, app host)
                                                  │ HTTP + X-Internal-Secret
                                                  ▼
                          backend POST /api/wifi/authorize | /wifi/accounting
```

Components in this repo:

| Piece | Where |
|---|---|
| Authorization logic (source of truth) | `backend/services/wifi_auth.py`, `backend/api/wifi.py` |
| Session audit table | `wifi_sessions` (migration `a3f8c2d91e47`) |
| RADIUS gateway | `radius_service/` (pyrad), systemd `facegym-radius` |
| Portal page | `deploy/pfsense/powerhouse-portal.html` |
| Test client | `radius_service/tools/radtest.py` |

## 0. Rules the system enforces

- Member record `active`, membership `active`, `start_date <= today <=
  end_date` in the **configured app timezone**, and at least partial payment
  (`payment_status != "pending"`). Same order and reasons as the kiosk.
- `access_rules` (day/time/location) are NOT applied to WiFi — they govern
  facility entry, not network use (recorded decision, `openspec/changes/
  wifi-captive-portal/design.md` Decision 3).
- `Session-Timeout = min(4 h cap, time until local midnight after end_date)`
  — a membership lapse is enforced at the NEXT re-auth, never later than the
  cap. `Idle-Timeout` 30 min drops idle devices.
- Max 3 concurrent devices per member (`WIFI_MAX_DEVICES_PER_MEMBER`);
  sessions silent for 24 h stop counting (lost Acct-Stop).
- **Fail closed**: backend down / secret mismatch → Access-Reject.
- 5 consecutive rejects for one cédula → 60 s lockout (brute-force damper).
- Documents are normalized (punctuation/space/case-insensitive) on lookup.

## 1. Prerequisites

1. **A dedicated pfSense interface or VLAN for member WiFi.** Never enable
   the captive portal on the admin LAN — it would captive-portal the kiosk
   and staff PCs.
2. **The AP in bridge/AP mode** on that interface/VLAN, DHCP off (pfSense
   serves DHCP). Any brand works — UniLink/UniFi, TP-Link, MikroTik… If the
   AP currently routes/NATs (its own DHCP handing 192.168.x.x), switch it to
   bridge/AP mode first, or the portal will never trigger.
3. **UDP reachability pfSense → app host on 1812/1813.** If pfSense and the
   app host are on different subnets, allow it end-to-end.
4. Backend deployed at migration head **including `a3f8c2d91e47`** (see §2).

## 2. Backend deploy (the trap-20 dance)

```bash
cd /opt/powerhouse-membership/backend
set -a; . ./.env; . /etc/faceapp/migrate-db.env; set +a
./venv/bin/alembic upgrade head
./venv/bin/alembic current      # MUST print a3f8c2d91e47 (head)
sudo systemctl restart facegym-backend
```

- On hosts without `powerhouse_migrator` (like current prod LXC 114), use
  the owner role connection as documented in AGENTS.md trap 20 — a
  `must be owner of ...` error means the env file was not sourced.
- The migration creates `wifi_sessions` + RLS. It is safe on dev (the RLS
  policy is created only when the `backend_app` role exists).
- Optional knobs in `backend/.env` (defaults shown): `WIFI_SESSION_TIMEOUT_CAP_SECONDS=14400`,
  `WIFI_IDLE_TIMEOUT_SECONDS=1800`, `WIFI_MAX_DEVICES_PER_MEMBER=3`,
  `WIFI_STALE_SESSION_HOURS=24`, `WIFI_ACCT_INTERIM_INTERVAL_SECONDS=600`.

## 3. Install the RADIUS gateway on the app host

```bash
cd /opt/powerhouse-membership/radius_service
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# secrets (0600, root-only):
sudo install -m 600 radius.env.example /etc/faceapp/radius.env
sudo nano /etc/faceapp/radius.env   # set RADIUS_SHARED_SECRET + INTERNAL_API_SECRET

sudo cp ../scripts/systemd/facegym-radius.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now facegym-radius
journalctl -u facegym-radius -f     # should log "RADIUS gateway starting"
```

## 4. Firewall — allow RADIUS from pfSense ONLY

The gateway accepts any source IP that proves the shared secret; the network
layer must do the scoping. On the app host (adjust iface/chain to yours):

```bash
# example for an nftables/iptables host — UDP 1812+1813 from pfSense only
iptables -I INPUT -p udp -s <PFSENSE_IP> --dport 1812 -j ACCEPT
iptables -I INPUT -p udp -s <PFSENSE_IP> --dport 1813 -j ACCEPT
iptables -A INPUT -p udp --dport 1812 -j DROP
iptables -A INPUT -p udp --dport 1813 -j DROP
```

## 5. pfSense configuration (step by step)

1. **Services → Captive Portal → Add zone** — name it `MEMBER_WIFI`,
   interface = the member WiFi interface/VLAN.
2. **Authentication** → Authentication Method = **RADIUS**.
   - Primary authentication server: *Add new*
     - Protocol: RADIUS
     - Hostname: app host IP (NOT localhost — pfSense resolves literally)
     - Authentication port: `1812`, Accounting port: `1813`
     - Shared secret: the `RADIUS_SHARED_SECRET` from `/etc/faceapp/radius.env`
     - Authentication timeout: 5 s
     - RADIUS protocol: PAP (the CP uses PAP; the page contract sends the
       cédula as both user and password)
3. Enable **RADIUS Accounting** (session start/stop/interim → `wifi_sessions`).
4. **Session controls** (backstops on top of the RADIUS attributes):
   - Idle timeout: 30 min · Hard timeout: 4 h · Concurrent logins: allowed
     (our per-member device cap lives in the backend)
5. **Portal page contents** → *HTML* → upload
   `deploy/pfsense/powerhouse-portal.html`.
6. Leave "Logout popup window" on default (off is fine).
7. Apply. Interception starts immediately for NEW associations.

## 6. Verification checklist (in order)

```bash
# On the app host — proves gateway+backend+DB without any WiFi client:
cd /opt/powerhouse-membership/radius_service
set -a; . /etc/faceapp/radius.env; set +a
./venv/bin/python tools/radtest.py <CEDULA_OF_ACTIVE_MEMBER> 127.0.0.1 "$RADIUS_SHARED_SECRET"
# expect: reply code: Access-Accept + Session-Timeout/Idle-Timeout lines
./venv/bin/python tools/radtest.py 000000000 127.0.0.1 "$RADIUS_SHARED_SECRET"
# expect: reply code: Access-Reject + bilingual "Cédula no encontrada"
```

Then on a phone:

- [ ] Join the member SSID → portal appears with PowerHouse branding (ES).
- [ ] Active member's cédula → redirected onward / browsing works.
- [ ] Unknown cédula → red message, still captive.
- [ ] Expired/unpaid member → the matching bilingual denial.
- [ ] After ≤ 4 h (or 30 min idle) → portal re-appears (bounded staleness).
- [ ] `GET /api/wifi/sessions?active_only=true` (staff JWT) shows the phone
      with MAC/IP; after disconnect + a few minutes, `ended_at` fills in.

## 7. Rollback

1. pfSense: Services → Captive Portal → zone → **Enable = unchecked** →
   Apply. WiFi passes traffic with no portal (open) immediately.
2. App host: `sudo systemctl disable --now facegym-radius`.
3. Backend: nothing to undo — `/api/wifi/*` is inert without the gateway.
   The `wifi_sessions` table can stay (harmless, audited history) or be
   dropped via `alembic downgrade a3f8c2d91e47 -1`… run
   `alembic downgrade -1` from the backend dir as the migrator role.

## 8. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| pfSense log: `Authentication error: ... timeout` | Gateway down or firewall blocks UDP 1812. `systemctl status facegym-radius`, check §4. |
| Portal loads but every login fails with "Solicitud inválida" | Shared secret mismatch (password fails decryption → the user≠password guard trips). Re-check BOTH sides. |
| Gateway log: `backend rejected internal credentials (HTTP 401)` | `INTERNAL_API_SECRET` in `/etc/faceapp/radius.env` differs from backend `.env`. |
| Gateway log: `backend rejected ... (HTTP 503)` | Backend has NO `INTERNAL_API_SECRET` configured at all. |
| Member with active plan rejected `unpaid_membership` | Correct behavior: zero payments on the membership. Record the payment (reception) — partial is enough. |
| Rejected `device_limit` | 3 open sessions already; wait for idle/hard timeout, or close from the session list (`ended_at` …) — an admin DELETE endpoint is future work. |
| Session outlives a revoked membership | By design until the next re-auth (≤ 4 h). Lower `WIFI_SESSION_TIMEOUT_CAP_SECONDS` to tighten. |
| `must be owner of ...` during migration | Trap 20 — see §2. |
| Two members share one cédula | Grant wins if ANY matching member qualifies; consider cleaning the duplicate in Members. |

## 9. Privacy notes (Ley 1581)

- The portal stores no personal data client-side; only the cédula transits
  (equivalent to typing it at reception).
- `wifi_sessions` stores document snapshot + MAC/IP + usage counters —
  operational data, admin-only (staff JWT + RLS; the portal role has no
  policy and is denied).
- Failed attempts are NOT persisted (gateway journal only).
