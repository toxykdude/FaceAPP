# Delta for Remote Backup

## MODIFIED Requirements

### Requirement: Environment-Only Remote Credentials

The backup script SHALL read remote credentials only from environment configuration and SHALL NOT log them. Credentials MAY originate from the `backup_remote` database setting when encrypted at rest and materialized into a root-only runtime env file; they MUST NOT appear in source-controlled files.

(Previously: Remote credentials could originate only from `.env` and could not be persisted in the application database.)

#### Scenario: Remote credentials are configured

- GIVEN an operator or administrator configures credentials for a supported transport
- WHEN the backup workflow loads its remote configuration
- THEN the script receives credentials only through environment variables
- AND any database-held password is encrypted at rest and no credential is logged

## ADDED Requirements

### Requirement: SFTP Replication

The system SHALL support SFTP batch replication using `sshpass -e sftp -b`, with `SSHPASS` supplied only through the environment and never process arguments.

#### Scenario: SFTP password is unavailable

- GIVEN SFTP is selected without `SSHPASS`
- WHEN remote replication runs
- THEN it reports a warning without exposing credentials
- AND the overall backup exits successfully with its local copy preserved

### Requirement: FTP Replication

The system SHALL support FTP uploads using curl and a temporary credential file restricted to mode `0600`; credentials MUST NOT appear in URLs or arguments, and documentation MUST identify FTP's cleartext risk.

#### Scenario: FTP client or credential file is unavailable

- GIVEN FTP is selected but curl or its restricted credential file is unavailable
- WHEN remote replication runs
- THEN it reports a warn-only failure and the overall backup exits successfully
- AND the local copy remains preserved

### Requirement: Managed Environment Override

The backup workflow SHALL source `/etc/faceapp/backup-remote.env` after the application `.env`, so valid database-managed values override fallback values.

#### Scenario: Managed and fallback values differ

- GIVEN both files define a remote transport value
- WHEN the backup workflow loads configuration
- THEN the managed env value is used

### Requirement: Fresh-Install SMB Dependency

The installer MUST install `samba-client`, and SMB replication MUST fail warn-only with an installation hint when `smbclient` is unavailable.

#### Scenario: SMB client is missing

- GIVEN SMB is selected on a host without `smbclient`
- WHEN remote replication runs
- THEN the warning identifies `samba-client` as the missing dependency
- AND local backup success is preserved

### Requirement: Remote Secret Log Isolation

Remote replication MUST NOT emit SMB, SFTP, or FTP password values in any log, including success, warning, timeout, and failure paths.

#### Scenario: Isolation contract covers every password transport

- GIVEN unique secret tokens are configured as `SMB_PASS`, `SSHPASS`, and the FTP password
- WHEN isolation tests exercise each transport and search all captured logs
- THEN none of the secret tokens is present
