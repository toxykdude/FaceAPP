# Guest Purchase Provisioning Specification

## Purpose

Let unauthenticated guests buy the four gym plans online so a Wompi APPROVED payment provisions Member + Membership + SalesTransaction atomically, with canonical-phone dedup and no implied biometric consent. Scenario tags name the verifying suite: `[pytest]` backend, `[vitest]` portal repo (powerhouse-site).

## Requirements

### Requirement: Guest Checkout Scope and Identity Capture

Guest checkout SHALL be offered only for the four gym plans. `pt-*` plans MUST NOT be guest-purchasable. Checkout SHALL capture full name, email, and phone, and the system SHALL normalize the phone to canonical form: country code `57` followed by exactly 10 digits.

#### Scenario: Guest identity captured for a gym plan [vitest+pytest]

- GIVEN a guest selects one of the four gym plans
- WHEN the guest submits name, email, and a valid Colombian phone
- THEN checkout proceeds with the phone normalized to 57+10 digits
- AND no member account or login is required

#### Scenario: PT plan is not guest-purchasable [vitest]

- GIVEN a guest selects a `pt-*` plan
- WHEN guest checkout is attempted
- THEN the purchase is refused with direction to the manual staff path

#### Scenario: Non-canonical phone is rejected [pytest]

- GIVEN a guest submits a phone that cannot normalize to 57+10 digits
- WHEN the pending guest record is created
- THEN the request is rejected and no pending record is stored

### Requirement: Pending Guest Record Without Member Binding

The system SHALL store the guest pending record in Redis keyed by Wompi reference with a TTL not exceeding 24 hours, carrying guest identity and plan but no member_id.

#### Scenario: Pending record carries identity, not a member [pytest]

- GIVEN a guest completes checkout and initiates payment
- WHEN the pending record is persisted
- THEN it contains name, canonical phone, email, and plan
- AND it contains no member_id and expires within 24 hours

### Requirement: Atomic Provisioning on Approved Payment

On a Wompi APPROVED event, the backend SHALL create a Member (status active, `consent_given_at=NULL`, `facial_data_enrolled=false`), a Membership, and a SalesTransaction in a single atomic transaction — either all three persist or none.

#### Scenario: Approved payment provisions all records [pytest]

- GIVEN a pending guest record and an APPROVED, amount-verified Wompi event
- WHEN the webhook provisions the purchase
- THEN Member, Membership, and SalesTransaction are all committed together
- AND the new member has status active with NULL consent and no facial data enrolled

#### Scenario: Failure mid-commit leaves no partial records [pytest]

- GIVEN provisioning fails after the Member insert but before the sale
- WHEN the transaction aborts
- THEN no Member, Membership, or SalesTransaction row persists

### Requirement: Canonical-Phone Deduplication

Before inserting a Member, the backend SHALL look up the submitted canonical phone; an existing member MUST receive the new Membership rather than a duplicate Member row.

#### Scenario: Existing phone attaches to the existing member [pytest]

- GIVEN a member already exists with the same canonical 57+10 phone
- WHEN an approved guest purchase provisions
- THEN the Membership and sale attach to the existing member
- AND no duplicate Member row is created

#### Scenario: New phone creates a new member [pytest]

- GIVEN no member exists with the canonical phone
- WHEN provisioning runs
- THEN exactly one new Member row is created

### Requirement: Post-Commit CV Invalidation

After the provisioning transaction commits, the backend SHALL notify the CV service (including its `X-API-Key` header) so the member becomes kiosk-visible. Notification failure MUST NOT roll back committed records and MUST be logged.

#### Scenario: Commit triggers CV invalidation with API key [pytest]

- GIVEN guest provisioning committed
- WHEN the CV notification is sent
- THEN it carries the CV API key header

#### Scenario: CV unreachable leaves the sale intact [pytest]

- GIVEN the CV service is unreachable after commit
- WHEN notification fails
- THEN the Member/Membership/Sale rows remain committed
- AND the failure is logged for retry

### Requirement: Idempotent Replay

A replayed Wompi reference or transaction id SHALL produce exactly one Membership and one SalesTransaction; the idempotency check MUST reject a reference that already exists in the database.

#### Scenario: Replayed reference provisions nothing new [pytest]

- GIVEN a reference was already consumed and provisioned
- WHEN the same webhook is replayed
- THEN no second Membership or SalesTransaction is created

### Requirement: Honest Confirmation Messaging

The `/pago/confirmacion` page MUST NOT claim biometric enrollment or immediate kiosk access; it SHALL state that face enrollment happens at the gym, and MUST NOT show success for non-approved payments.

#### Scenario: Confirmation directs enrollment to the gym [vitest]

- GIVEN an approved guest purchase completed
- WHEN the confirmation page renders
- THEN it reports the purchase recorded and enrollment pending at the gym
- AND it does not claim face enrollment or immediate access

#### Scenario: Non-approved payment shows no success [vitest]

- GIVEN a DECLINED or PENDING payment
- WHEN the confirmation page renders
- THEN it does not present a success state
