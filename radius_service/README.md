# radius_service

RADIUS ⇄ FaceAPP gateway for the pfSense captive portal (member WiFi).
Answers Access-Requests (PAP, cédula as user+password) on UDP 1812 and
Accounting-Requests on 1813; decisions come from
`POST /api/wifi/authorize` on the backend. Holds no membership logic.
**Fail closed**: backend unreachable → Access-Reject.

- Runbook (install, pfSense config, verification, rollback):
  [`docs/pfsense-captive-portal.md`](../docs/pfsense-captive-portal.md)
- SDD change: `openspec/changes/wifi-captive-portal/`
- Tests: `pytest tests/` (offline, no DB needed)
- Manual probe: `tools/radtest.py <cedula> <host> <secret> [port]`
