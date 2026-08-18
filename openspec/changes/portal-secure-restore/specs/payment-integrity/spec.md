# Payment Integrity Specification

## Purpose

Make payment amounts server-authoritative end to end: the client never chooses an amount, relay and backend independently verify the Wompi amount against the plan, activation requires a persisted qualifying sale, and zero-price plans are impossible at the database level. Scenario tags: `[pytest]` backend, `[vitest]` portal repo (powerhouse-site).

## Requirements

### Requirement: Server-Originated Amounts

The ONLY authoritative amount sources SHALL be the Pages plan table (relay side) and the backend's persisted `membership_plans` price. A client-submitted amount MUST NOT influence any price, pending record, or checkout outcome.

#### Scenario: Client-sent amount is ignored [vitest]

- GIVEN a checkout request carries a client-chosen amount
- WHEN the relay builds the pending payment
- THEN the amount is derived from the plan table and the client value is discarded

#### Scenario: Pending amount equals plan price [pytest]

- GIVEN a pending record exists for a plan
- WHEN it is read back
- THEN its amount equals the backend plan price in cents

### Requirement: Relay Amount and Currency Verification

Before signing and forwarding to `webhook-renew`, the relay SHALL verify the Wompi `amount_in_cents` and currency against the plan. A mismatch MUST NOT be forwarded.

#### Scenario: Matching amount is forwarded [vitest]

- GIVEN Wompi reports APPROVED with amount_in_cents ≥ plan price and the expected currency
- WHEN the relay processes the event
- THEN it signs and forwards the webhook

#### Scenario: Underpayment is blocked before forwarding [vitest]

- GIVEN Wompi reports an amount_in_cents below the plan price
- WHEN the relay processes the event
- THEN no webhook is forwarded and a staff alert is emitted

#### Scenario: Currency mismatch is blocked [vitest]

- GIVEN the Wompi transaction currency differs from the plan's expected currency
- WHEN the relay processes the event
- THEN the event is rejected without forwarding

### Requirement: Webhook Re-Verification and Atomic Pending Consumption

Implementing SECURITY.md:498-504, the backend webhook SHALL: verify the HMAC signature; locate the pending record by reference; verify the Wompi amount against the DB plan price; create Membership + SalesTransaction; enforce reference idempotency; and consume the Redis pending key. Pending-key consumption SHALL be atomic with provisioning — the key MUST NOT be consumed unless the provisioning transaction commits.

#### Scenario: Approved webhook commits and consumes the key [pytest]

- GIVEN a valid signed APPROVED webhook with a matching pending record
- WHEN reconciliation runs
- THEN Membership and SalesTransaction commit and the pending key is consumed

#### Scenario: Unknown reference provisions nothing [pytest]

- GIVEN no pending record exists for the webhook reference
- WHEN reconciliation runs
- THEN no membership or sale is created

#### Scenario: Forged signature changes no state [pytest]

- GIVEN a webhook with a missing or invalid signature
- WHEN it reaches the backend
- THEN it is rejected before any lookup or provisioning

#### Scenario: Failed commit retains the pending key [pytest]

- GIVEN provisioning fails before commit
- WHEN the transaction rolls back
- THEN the pending key remains available for retry

### Requirement: Sale-Gated Activation

A Membership SHALL become active only when the same atomic commit persists a SalesTransaction whose amount is greater than or equal to the plan price.

#### Scenario: No membership activates without a qualifying sale [pytest]

- GIVEN any code path attempts to create an active membership
- WHEN no SalesTransaction with amount ≥ plan price is persisted in the same commit
- THEN the membership is not activated

### Requirement: Positive-Price Plan Constraint

`membership_plans.price` SHALL carry a `CHECK (price > 0)` database constraint, applied by a migration run under the dedicated migrator role.

#### Scenario: Zero-price plan insert is rejected [pytest]

- GIVEN an operator or migration inserts a plan with price 0
- WHEN the statement executes
- THEN the database rejects it

#### Scenario: Negative-price update is rejected [pytest]

- GIVEN an existing plan is updated to a negative price
- WHEN the statement executes
- THEN the database rejects it

### Requirement: Mismatch Handling and Staff Alert

Any amount mismatch reaching the backend MUST result in no Membership and an emitted staff alert.

#### Scenario: Backend underpayment yields no membership [pytest]

- GIVEN a signed webhook whose Wompi amount is below the DB plan price
- WHEN reconciliation runs
- THEN no membership or sale is created and a staff alert is emitted

### Requirement: Secret Isolation and Internal Pending Key

Integrity, events, and internal keys MUST NOT be visible to any client. `GET /portal/pending-payment/{reference}` SHALL authenticate with a dedicated internal key (WS-1); the global `SECRET_KEY` MUST NOT be accepted for it.

#### Scenario: Pending read requires the internal key [pytest]

- GIVEN a request to read a pending payment
- WHEN it presents the dedicated internal key
- THEN the read succeeds; with a missing or wrong key it is denied without disclosing whether the reference exists

#### Scenario: SECRET_KEY no longer authorizes pending reads [pytest]

- GIVEN a pending-payment read signed only with the global SECRET_KEY
- WHEN it reaches the backend
- THEN it is denied

#### Scenario: No secret reaches a client response [pytest+vitest]

- GIVEN integrity, events, or internal key values are configured
- WHEN any client-visible response is inspected
- THEN none of those values appears
