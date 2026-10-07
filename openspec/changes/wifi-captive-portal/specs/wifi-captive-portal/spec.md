# wifi-captive-portal Specification

## ADDED Requirements

### Requirement: Membership-gated WiFi authorization

The backend SHALL expose `POST /api/wifi/authorize` (X-Internal-Secret
protected) deciding whether a document number may use the member WiFi.

#### Scenario: active paid member is allowed

- **WHEN** the document matches an active member with a membership whose
  `start_date <= today <= end_date` (configured timezone) and at least partial
  payment recorded
- **THEN** the response is `allowed: true` with a `session_timeout_seconds`
  between 60 and `WIFI_SESSION_TIMEOUT_CAP_SECONDS`, plus member display info

#### Scenario: unknown document

- **WHEN** no member matches the normalized document
- **THEN** `allowed: false`, `reason: member_not_found`

#### Scenario: member record inactive

- **WHEN** the only matching members are `inactive`/`suspended`
- **THEN** `allowed: false`, `reason: member_inactive`

#### Scenario: no membership at all

- **WHEN** the member has no membership rows
- **THEN** `allowed: false`, `reason: no_active_membership`

#### Scenario: lapsed membership

- **WHEN** the newest membership ended before today
- **THEN** `allowed: false`, `reason: expired_membership`

#### Scenario: suspended membership

- **WHEN** a date-valid membership has `status: suspended`
- **THEN** `allowed: false`, `reason: suspended_membership`

#### Scenario: not-yet-started membership

- **WHEN** the membership starts after today
- **THEN** `allowed: false`, `reason: membership_not_started`

#### Scenario: unpaid membership

- **WHEN** the date-valid membership has no payments recorded
- **THEN** `allowed: false`, `reason: unpaid_membership` (partial payment allows)

#### Scenario: document normalization

- **WHEN** the portal submits `1.234.567` and the member is stored as `1234567`
- **THEN** the lookup still matches (punctuation/whitespace/case-insensitive)

#### Scenario: device limit

- **WHEN** the member already has `WIFI_MAX_DEVICES_PER_MEMBER` sessions that
  are open and freshly updated
- **THEN** `allowed: false`, `reason: device_limit`; sessions stale beyond
  `WIFI_STALE_SESSION_HOURS` or ended do not count

#### Scenario: bilingual denial messages

- **WHEN** any decision is returned
- **THEN** the payload carries `message_es` and `message_en` for the portal

#### Scenario: service auth fails closed

- **WHEN** `INTERNAL_API_SECRET` is unset → 503; header missing/wrong → 401
- **THEN** no decision is ever produced without the shared secret

### Requirement: WiFi session accounting

The backend SHALL expose `POST /api/wifi/accounting` (X-Internal-Secret
protected) persisting RADIUS accounting events into `wifi_sessions`,
idempotently, keyed on `(nas_ip, acct_session_id)`.

#### Scenario: start creates a session row

- **WHEN** an Acct-Start arrives for document D from NAS N
- **THEN** a row exists with `member_id` resolved from D (nullable when
  unknown), `ended_at` NULL, `started_at` set

#### Scenario: interim updates counters

- **WHEN** an Interim-Update arrives with cumulative octets
- **THEN** `last_update_at`, `acct_input_octets`, `acct_output_octets`,
  `acct_session_time` are updated (counters never decrease)

#### Scenario: stop closes the session

- **WHEN** an Acct-Stop arrives with a terminate cause
- **THEN** `ended_at` and `terminate_cause` are set; a repeated Stop changes
  nothing

#### Scenario: duplicate start is idempotent

- **WHEN** two Starts arrive for the same `(nas_ip, acct_session_id)`
- **THEN** only one row exists and it stays open

#### Scenario: staff-only session listing

- **WHEN** `GET /api/wifi/sessions` is called without a staff JWT
- **THEN** 401; with staff/admin JWT it lists sessions and supports
  `active_only` and `member_id` filters

### Requirement: RADIUS translation service

A `radius_service` SHALL answer Access-Requests (PAP) and Accounting-Requests
on UDP 1812/1813, forwarding decisions to the backend.

#### Scenario: accept path

- **WHEN** the backend allows the document
- **THEN** Access-Accept carries `Session-Timeout`, `Idle-Timeout`,
  `Acct-Interim-Interval`, `Reply-Message`

#### Scenario: reject path

- **WHEN** the backend denies the document
- **THEN** Access-Reject carries the bilingual `Reply-Message`

#### Scenario: backend outage fails closed

- **WHEN** the backend is unreachable or errors
- **THEN** Access-Reject with a service-unavailable message; never Accept

#### Scenario: brute-force cooldown

- **WHEN** 5 consecutive rejects occur for the same document
- **THEN** subsequent requests for it are rejected immediately for 60 s
  without a backend call

#### Scenario: accounting forwarding

- **WHEN** a valid Accounting-Request (Start/Interim/Stop) arrives
- **THEN** it is mapped and POSTed to `/api/wifi/accounting`; mapping failures
  are logged and dropped (no crash)

### Requirement: Portal page and network enforcement

The deliverable SHALL include a pfSense-ready portal page and a runbook.

#### Scenario: portal form contract

- **WHEN** the captive portal renders
- **THEN** the form posts `auth_user` and `auth_pass` (same cédula value) to
  `$PORTAL_ACTION$` with `redirurl`; a no-JS fallback still submits both fields

#### Scenario: bilingual UI

- **WHEN** the page loads
- **THEN** ES is default with an EN toggle, and `$PORTAL_MESSAGE$` renders
  pfSense error text

#### Scenario: rollback

- **WHEN** the CP zone is disabled on pfSense
- **THEN** the member WiFi passes traffic without a portal (documented in the
  runbook with exact steps)
