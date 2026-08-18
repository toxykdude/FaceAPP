# Delta for Customer Portal Runtime

> Base: `openspec/changes/membership-report-kiosk-tunnel/specs/customer-portal-runtime/spec.md` (capability introduced by that in-flight change; not yet in `openspec/specs/`). Scenario tags: `[pytest]` backend, `[vitest]` portal repo (powerhouse-site).

## MODIFIED Requirements

### Requirement: Webhook and Runtime Controls

The runtime MUST verify webhooks before state changes, enforce origin and rate controls, and MUST NOT disclose secrets. Webhook reconciliation MUST consume and verify the Redis pending record: look up by Wompi reference, verify the event amount against the pending record and the DB plan price, and consume the pending key atomically with the provisioning commit.

(Previously: Webhook verification covered signature, origin, and rate controls only, with no pending-record consumption or amount reconciliation contract.)

#### Scenario: Forged webhook is rejected

- GIVEN a webhook has missing or invalid authenticity proof
- WHEN it reaches the portal runtime
- THEN it MUST be rejected without changing state

#### Scenario: Disallowed portal traffic is rejected

- GIVEN a request has a disallowed origin or exceeds its rate
- WHEN the request reaches the runtime
- THEN it MUST be rejected without exposing secrets

#### Scenario: Webhook without pending record is rejected [pytest]

- GIVEN a signed webhook whose reference has no pending record in Redis
- WHEN reconciliation runs
- THEN it is rejected without provisioning and without disclosing secret material

#### Scenario: Amount not matching the pending record is rejected [pytest]

- GIVEN a signed webhook whose amount differs from the pending record or the DB plan price
- WHEN reconciliation runs
- THEN no membership is created and the pending key is not consumed

## ADDED Requirements

### Requirement: Internal-Key Authentication on Pending Reads

`GET /portal/pending-payment/{reference}` SHALL authenticate with a dedicated internal key (WS-1) shared only between the portal relay and the backend; the global `SECRET_KEY` MUST NOT be accepted, and denials MUST NOT disclose whether the reference exists.

#### Scenario: Pending read with the internal key succeeds [pytest]

- GIVEN the dedicated internal key is configured
- WHEN the relay reads a pending payment with that key
- THEN the pending record is returned

#### Scenario: Pending read with only SECRET_KEY is denied [pytest]

- GIVEN a request authenticates with the global SECRET_KEY
- WHEN it reads a pending payment
- THEN it is denied identically to an unauthenticated request

### Requirement: Documented Portal Environment Placeholders

`backend/.env.example` SHALL document `MEMBER_PORTAL_DATABASE_URL`, `WOMPI_*` (integrity and public keys), and `EVOLUTION_*` placeholders, and required secrets MUST fail closed when unset.

#### Scenario: Placeholders are present in .env.example [pytest]

- GIVEN the backend environment template is inspected
- WHEN placeholders are checked
- THEN `MEMBER_PORTAL_DATABASE_URL`, the `WOMPI_*` keys, and the `EVOLUTION_*` keys are all documented with no real secret values

#### Scenario: Missing integrity secret fails closed [pytest]

- GIVEN `WOMPI` integrity material is unset
- WHEN webhook reconciliation runs
- THEN it rejects the event rather than processing it unverified
