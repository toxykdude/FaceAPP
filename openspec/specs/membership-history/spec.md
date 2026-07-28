# Membership History

## Requirements

### Requirement: Membership History Visibility Threshold

The system SHALL sort memberships by most recent end date, keep the two most recent records visible, and place the third through fiftieth fetched records in a collapsed MUI Accordion by default.

#### Scenario: Member has exactly two memberships

- GIVEN a member has exactly two memberships
- WHEN the membership section is displayed
- THEN both records are visible
- AND no older-history accordion is shown

#### Scenario: Member has exactly three memberships

- GIVEN a member has exactly three memberships
- WHEN the membership section is displayed
- THEN the two most recent records are visible
- AND the third record is available inside the collapsed accordion

#### Scenario: Member has fifty memberships

- GIVEN the membership query returns fifty records
- WHEN the older-history accordion is expanded
- THEN records three through fifty are consultable in existing sort order

### Requirement: Actionable and Localized Older Memberships

The system SHALL preserve every existing edit, renew, and delete action and its current authorization rules for records inside the accordion. The accordion's user-visible labels SHALL be available in both Spanish and English through application i18n.

#### Scenario: Administrator acts on an older membership

- GIVEN an administrator expands older membership history
- WHEN an older row is displayed
- THEN its permitted edit, renew, and delete actions remain available and functional

#### Scenario: Non-admin views older memberships

- GIVEN a non-admin expands older membership history
- WHEN an older row is displayed
- THEN admin-only actions remain unavailable under the existing authorization rules
