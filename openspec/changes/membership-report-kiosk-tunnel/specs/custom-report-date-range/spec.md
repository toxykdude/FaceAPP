# Custom Report Date Range Specification

## Purpose

Define consistent reporting for arbitrary intervals and presets.

## Requirements

### Requirement: Consistent Date-Range Reporting

The system MUST apply valid inclusive `start_date` and `end_date` values consistently to dashboard and summary results. Presets MUST use the same behavior.

#### Scenario: Custom interval succeeds

- GIVEN a valid interval containing sales
- WHEN dashboard and summary data are requested
- THEN both MUST include only data within the interval
- AND their shared totals MUST agree

#### Scenario: Single-day boundary succeeds

- GIVEN `start_date` equals `end_date`
- WHEN reporting is requested
- THEN eligible data from that date MUST be included

#### Scenario: Invalid interval is rejected

- GIVEN either date is malformed or `start_date` is after `end_date`
- WHEN reporting is requested
- THEN validation MUST fail without partial report data
