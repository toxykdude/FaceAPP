# Delta for Sales Reporting

## ADDED Requirements

### Requirement: Timezone Cache Consistency

The system SHALL resolve the configured IANA timezone through a cached application-timezone service and SHALL invalidate or refresh that cache when the timezone setting changes.

#### Scenario: Timezone changes during an active session

- GIVEN reports have used a cached timezone
- WHEN an administrator saves a different valid IANA timezone
- THEN subsequent report queries and timestamp displays use the new timezone without requiring a service restart

### Requirement: Server-Side CSV Report Export

The system SHALL provide a server-side CSV download from the existing report export action using the selected `reportRange` semantics and the same configured-timezone half-open window as on-screen reporting.

#### Scenario: Custom-range CSV matches the screen

- GIVEN an administrator displays a valid custom start and end date
- WHEN the administrator exports the report
- THEN the CSV uses `[start 00:00, end + 1 day 00:00)` in the configured timezone
- AND its range-filtered sales data matches the on-screen report exactly

## MODIFIED Requirements

### Requirement: Configured-Timezone Reporting and Sales Timestamps

The system SHALL use the saved IANA timezone for all report windows, dashboard and event date bucketing, and sales timestamp presentation. It SHALL use DST-aware timezone rules while retaining UTC persistence, and sales lists and recent-sales views SHALL show both local date and time.

(Previously: Backend report windows used fixed Colombia offsets and sales views showed browser-local dates without times.)

#### Scenario: Report crosses an America/Santiago DST boundary

- GIVEN `America/Santiago` is configured and a report range crosses a DST transition
- WHEN the report window is built and sales are rendered
- THEN each local midnight maps using the applicable offset for that date
- AND included sales and displayed date-times follow that DST-aware window

### Requirement: Deployed Custom Date Range Flow

The system SHALL expose the existing custom-range selection in the deployed Reports UI and preserve the complete dropdown-to-pickers-to-query-to-results flow. Deployment mismatch SHALL be diagnosed before code changes, and any confirmed defect SHALL be remediated without picker redesign.

(Previously: The flow existed and was tested in `main` but was unavailable in the deployed environment.)

#### Scenario: Valid custom range returns results

- GIVEN the deployed Reports page matches the current application build
- WHEN a user selects Custom, chooses a valid start and end date, and runs the report
- THEN both date pickers are available and the query returns results for that range

#### Scenario: Reversed custom dates remain rejected

- GIVEN Custom is selected with the start date after the end date
- WHEN the report range is evaluated
- THEN the existing validation error is shown
- AND no reversed-range report query is executed
