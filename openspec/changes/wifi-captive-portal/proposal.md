# Proposal: WiFi Captive Portal (pfSense + RADIUS)

## Summary

Members-only WiFi at the gym: every client that associates to the member AP is
redirected to a pfSense captive portal, enters their cédula, and may surf only
if FaceAPP knows that document number with a currently-valid, paid membership.

## Motivation and Scope

| # | Problem → outcome |
|---|---|
| 1 | Open member WiFi → access gated on active FaceAPP membership (same rules the kiosk enforces at the door). |
| 2 | No per-user WiFi audit trail → RADIUS accounting rows (`wifi_sessions`) with member, MAC, IP, bytes, session times. |
| 3 | Membership can lapse mid-session → bounded `Session-Timeout` (min of cap and time left on the membership) forces re-auth, after which the lapsed member is rejected. |
| 4 | Cédula sharing → per-member concurrent-device cap (default 3). |

### Goals

- pfSense captive portal on the member WiFi interface, authenticating against
  FaceAPP through a small RADIUS service we own.
- Denial reasons and membership semantics identical to the kiosk vocabulary
  (`no_active_membership`, `unpaid_membership`, …) so staff learn one language.
- Bilingual (ES/EN) portal page and denial messages; Powerhouse branding.
- Full runbook: pfSense UI steps, AP bridging, secrets, firewall, rollback.

### Non-Goals

- Face/selfie verification at the portal (natural phase 2 via cv_service).
- Bandwidth quotas per plan, WISPr attributes, per-voucher flows.
- Admin UI for WiFi sessions (API-only this change; Settings tab is a follow-up).
- Portal-page HTTPS (the credential is a public document number; noted as
  optional hardening in the runbook).

## Capabilities

### New Capabilities

- `wifi-captive-portal`: membership-gated WiFi access + session accounting.

### Modified Capabilities

None.

## Approach

| # | Decision |
|---|---|
| 1 | pfSense captive portal zone on the member WiFi interface/VLAN (never the admin LAN), auth method RADIUS — the officially supported external-auth path, with accounting and Session-Timeout semantics for free. |
| 2 | New `radius_service` (Python, pyrad) on the app host, UDP 1812/1813, shared secret in root-only `/etc/faceapp/radius.env`; translates RADIUS ⇄ backend HTTP. No third-party RADIUS dependency, no custom PHP on the firewall. |
| 3 | Backend is the single source of truth: `POST /api/wifi/authorize` reuses `verify_internal_secret` (X-Internal-Secret, fail-closed) and the canonical active-membership predicate (status + date window in the configured timezone + payment gate). |
| 4 | `Session-Timeout = min(cap, seconds until local midnight after the membership end_date)`; `Idle-Timeout`; interim accounting every 10 min. |
| 5 | Access rules (day/time/location) are deliberately NOT applied to WiFi — they govern facility entry, not network use; recorded here so the decision is intentional. |
| 6 | `wifi_sessions` table records accounting events; RLS enabled with a policy for the app role (guarded — the role does not exist in dev). |

## Risks

| Risk | Mitigation |
|---|---|
| Backend down → members lose WiFi | Fail closed by design (matches door behavior); runbook documents it; Session-Timeout bounds blast radius of a stale grant. |
| pfSense on the wrong interface locks out staff | Runbook insists on a dedicated interface/VLAN for member WiFi; rollback = disable the CP zone. |
| Brute-force cédula guessing | Per-document cooldown in radius_service (5 fails → 60 s), plus the document is low-value (grants WiFi only, not door access). |
| Duplicate `id_number` rows | Authorization grants if ANY member matching the normalized document qualifies; usernames snapshotted per session. |
| Secrets sprawl | Reuse `INTERNAL_API_SECRET` for backend⇄radius (same trust domain as CV); RADIUS shared secret in its own 0600 env file. |

> **What this proposal explicitly does NOT decide:** which physical AP hardware is
> in use — the runbook covers any AP that can bridge to a pfSense interface.
