# Backup Remote Config Specification

## Purpose

Define secure, admin-managed remote-backup configuration, testing, and user experience.

## Requirements

### Requirement: Protected Masked Configuration

The system MUST expose admin-only `GET /system/backup-config`, MUST return transport configuration plus `has_password`, and MUST NOT return plaintext or ciphertext. The `backup_remote` key MUST NOT be exposed by `/settings/public`.

#### Scenario: Configuration has no password

- GIVEN an administrator requests a configuration without a stored password
- WHEN the configuration is returned
- THEN `has_password` is false and no password representation is present

#### Scenario: Unauthorized configuration access

- GIVEN a non-administrator is authenticated
- WHEN they request a backup-config endpoint
- THEN the system returns 403 without configuration data

### Requirement: Validated Write-Only Persistence

The system MUST validate and atomically persist one `backup_remote` JSON setting whose type is `none|rsync|sftp|ftp|smb|nfs` and whose fields are transport-appropriate host, port, share/path, username, and password. Password replacements MUST use existing AES-256-GCM encryption; empty or keep-sentinel input MUST preserve the current password. Successful updates MUST be audited without secrets.

#### Scenario: Empty password preserves the secret

- GIVEN an administrator updates a configuration that already has a password
- WHEN `PUT /system/backup-config` receives an empty password
- THEN the existing encrypted password remains and safe update metadata is audited

#### Scenario: Invalid transport configuration

- GIVEN an administrator submits missing or invalid transport-specific fields
- WHEN the update is validated
- THEN the system rejects it without changing persisted or materialized configuration

### Requirement: Secure Environment Materialization

After each successful update, the system MUST atomically replace `/etc/faceapp/backup-remote.env` with only transport-relevant keys, mode `0600`, and `root:root` ownership. It MUST NOT log file contents.

#### Scenario: Transport changes

- GIVEN a materialized configuration contains keys for the previous transport
- WHEN an administrator saves a different transport
- THEN the replacement contains no stale transport keys and has required mode and ownership

#### Scenario: Existing file is malformed

- GIVEN the previous managed env file is malformed
- WHEN a valid configuration is saved while a backup may read the file
- THEN the malformed file is atomically replaced and no reader can observe partial content

### Requirement: Bounded Sanitized Connection Test

The system MUST provide audited, admin-only `POST /system/backup-config/test`, probe through the remote-push contract using a one-byte file, enforce a 20-second timeout, and return only sanitized `{ok,message}` without secrets or remote banners. Probe failure MUST NOT alter local backups.

#### Scenario: Remote host is unreachable

- GIVEN valid configuration targets an unreachable host
- WHEN an administrator tests it
- THEN the probe exits non-zero and returns `ok:false` with a sanitized message
- AND an audit row is written while existing local backups remain unaffected

#### Scenario: Probe times out

- GIVEN the remote operation exceeds 20 seconds
- WHEN the test deadline is reached
- THEN the operation is terminated and returns `ok:false` with a sanitized timeout message

#### Scenario: Failure has a recognized cause

- GIVEN the probe log contains a known SMB `NT_STATUS_*` code or a known OpenSSH failure phrase
- WHEN the sanitized message is composed
- THEN a controlled reason phrase from the fixed vocabulary is appended
- AND the raw protocol code, remote banner, and matched log text are never surfaced

#### Scenario: Nothing valid is stored

- GIVEN the stored transport is `none` or fails per-transport validation
- WHEN an administrator tests it
- THEN the endpoint returns 400 and runs no probe

### Requirement: Admin Backup User Interface

The frontend MUST provide administrators a localized English/Spanish Backup tab with transport selection, conditional fields, a write-only keep-current password placeholder, save and test actions, and the Export Database block moved from System. Selecting FTP MUST show a cleartext warning.

#### Scenario: Transport selection changes

- GIVEN an administrator entered fields for one transport
- WHEN they select another transport
- THEN irrelevant fields are cleared and only applicable fields are displayed
- AND selecting FTP displays the cleartext warning

#### Scenario: Non-administrator views settings

- GIVEN a non-administrator opens Settings
- WHEN tabs are rendered
- THEN the Backup tab and its controls are not shown

#### Scenario: Test is attempted against unsaved edits

- GIVEN the probe targets the stored configuration and the form has unsaved edits, or the stored transport is `none`
- WHEN the Backup tab is rendered
- THEN the test action is disabled and states which condition applies
- AND a typed password counts as an unsaved edit

#### Scenario: Save response normalizes submitted values

- GIVEN a save whose response differs from the submitted form because the backend normalized it
- WHEN the saved baseline is updated
- THEN the response values become both the form contents and the baseline
- AND the test action becomes available again

#### Scenario: Save or test request is rejected

- GIVEN the backend rejects a save or test request
- WHEN the response arrives
- THEN the returned error detail is displayed to the administrator rather than discarded
