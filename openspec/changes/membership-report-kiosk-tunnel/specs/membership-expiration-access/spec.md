# Membership Expiration Access Specification

## Purpose

Separate expiration display from access eligibility.

## Requirements

### Requirement: Furthest Paid Expiration Display

The system MUST immediately display a member's furthest paid expiration, even when that membership has not started.

#### Scenario: Future paid renewal is displayed

- GIVEN a member has paid memberships with different expirations
- WHEN kiosk details load
- THEN the furthest paid expiration MUST be displayed immediately

#### Scenario: Renewal invalidates stale data

- GIVEN cached data predates a successful paid renewal
- WHEN kiosk or CV looks up the member after one invalidation cycle
- THEN the renewed furthest expiration MUST be returned
- AND the stale expiration MUST NOT be served

### Requirement: Independent Access Window Enforcement

The system MUST grant access only from `start_date` through paid expiration. Displaying a future expiration MUST NOT grant early entry.

#### Scenario: Start boundary grants access

- GIVEN a paid, unexpired membership starts at the attempt time
- WHEN access is evaluated
- THEN access MUST be granted

#### Scenario: Pre-start attempt is denied

- GIVEN the displayed membership has a future `start_date`
- WHEN access is attempted before that date
- THEN access MUST be denied

#### Scenario: Cross-member cache isolation

- GIVEN two members have different windows and cached records
- WHEN either member is evaluated
- THEN only that member's memberships MUST determine display and access
