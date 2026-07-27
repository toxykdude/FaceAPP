# Customer Portal Runtime Specification

## Purpose

Define secure runtime availability for the external portal.

## Requirements

### Requirement: Restricted Tunnel Availability

The runtime MUST tunnel approved portal backend routes only. CV and unintended internal routes MUST NOT be exposed. The portal frontend MUST remain external.

#### Scenario: Portal health succeeds through tunnel

- GIVEN the tunnel and portal runtime are healthy
- WHEN the external portal calls an approved endpoint
- THEN the request MUST reach the authenticated portal backend

#### Scenario: Tunnel exposure is restricted

- GIVEN a tunnel request targets a CV or unintended internal route
- WHEN the request is made
- THEN the route MUST NOT be publicly reachable

### Requirement: Authenticated Member Isolation

The runtime MUST authenticate requests and restrict members to their own records, including cached data.

#### Scenario: Cross-member access is denied

- GIVEN a member requests another member's record
- WHEN authorization runs
- THEN the request MUST be denied without disclosing that record

### Requirement: Webhook and Runtime Controls

The runtime MUST verify webhooks before state changes, enforce origin and rate controls, and MUST NOT disclose secrets.

#### Scenario: Forged webhook is rejected

- GIVEN a webhook has missing or invalid authenticity proof
- WHEN it reaches the portal runtime
- THEN it MUST be rejected without changing state

#### Scenario: Disallowed portal traffic is rejected

- GIVEN a request has a disallowed origin or exceeds its rate
- WHEN the request reaches the runtime
- THEN it MUST be rejected without exposing secrets
