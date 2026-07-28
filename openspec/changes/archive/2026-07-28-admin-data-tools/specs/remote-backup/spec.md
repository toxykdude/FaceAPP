# Delta for Remote Backup

## ADDED Requirements

### Requirement: Scheduled Remote Replication

The system SHALL run the existing local backup workflow every 30 minutes through a systemd timer and SHALL support pushing its artifacts to an environment-configured SMB, NFS, or rsync target.

#### Scenario: Scheduled replication succeeds

- GIVEN a supported remote target is configured and reachable
- WHEN the 30-minute timer invokes the backup workflow
- THEN a local backup is created and its artifacts are replicated remotely

### Requirement: Local Backup and Retention Preservation

The system SHALL preserve the existing local backup, checksums, biometric and configuration artifacts, and 30-day local retention behavior when remote replication is enabled.

#### Scenario: Remote target is unreachable

- GIVEN the local backup succeeds and the remote target is unreachable
- WHEN remote replication is attempted
- THEN the local copy remains intact
- AND the failure is logged or alerted as an unsuccessful remote replication

#### Scenario: Retention runs with replication enabled

- GIVEN remote replication is configured
- WHEN the backup workflow completes
- THEN local artifacts older than the existing retention period are removed as before

### Requirement: Environment-Only Remote Credentials

The system SHALL read remote connection credentials only from environment configuration and SHALL NOT persist those credentials in the settings table or source-controlled files.

#### Scenario: Remote credentials are configured

- GIVEN an operator configures credentials for SMB, NFS, or rsync
- WHEN the backup workflow loads its remote configuration
- THEN credentials are sourced from `.env`
- AND no remote credential value is written to the application database
