# Admin Database Export

## Requirements

### Requirement: Fresh Custom-Format Database Download

The system SHALL let an administrator request an on-demand, fresh PostgreSQL custom-format (`pg_dump -F c`) database download from the Settings system area. The response SHALL be downloadable without omitting application tables, including encrypted biometric data.

#### Scenario: Administrator downloads a fresh dump

- GIVEN an authenticated administrator is viewing System Settings
- WHEN the administrator activates Export Database
- THEN the system generates and downloads a fresh custom-format database dump

### Requirement: Export Authorization

The system SHALL require backend administrator authorization for every database export and SHALL NOT rely only on UI visibility to protect the operation.

#### Scenario: Unauthenticated export attempt

- GIVEN a request has no valid authentication
- WHEN it requests the database export
- THEN the system responds with 401 and SHALL NOT generate or disclose a dump

#### Scenario: Authenticated non-admin export attempt

- GIVEN an authenticated non-admin user
- WHEN the user requests the database export directly
- THEN the system responds with 403 and SHALL NOT generate or disclose a dump

### Requirement: Export Audit Record

The system SHALL create an audit-log entry identifying the administrator and database-export action for every successful download.

#### Scenario: Successful export is audited

- GIVEN an authenticated administrator
- WHEN a database export succeeds
- THEN an audit entry records the administrator and export action
