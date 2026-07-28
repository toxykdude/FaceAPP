# Proposal: Remote Backup Configuration UI

## Summary and Motivation

Add an admin-only **Backup** tab for configuring and testing remote destinations without server access or manual `.env` edits. Move **Export Database** from System into this tab.

## Requirement Modification

**MODIFIED — `remote-backup`: “Environment-Only Remote Credentials.”** Credentials may now originate in the `backup_remote` database setting because non-CLI administrators need a usable configuration path. Passwords remain encrypted with existing AES-256-GCM, materialized only into a root-only runtime env file, and env-only and secret-free from the script’s perspective.

## Goals

- Support `none`, `rsync`, `sftp`, `ftp`, `smb`, and `nfs` with transport-specific fields.
- Provide masked reads, write-only passwords, audited saves, and a sanitized connection probe.
- Preserve local backup, retention, warn-only remote failure, and script log-hygiene behavior.

## Non-Goals

- Managing NFS mounts, SSH keys, backup schedules, or retention policy.
- Exposing credentials, remote banners, or CV-service endpoints.

## Capabilities

### New Capabilities
- `backup-remote-config`: Admin UI/API configuration, secure credential handling, env materialization, and connection testing.

### Modified Capabilities
- `remote-backup`: Replace the database prohibition in “Environment-Only Remote Credentials”; add SFTP/FTP while preserving runtime env isolation.

## Approach and Affected Areas

| Area | Decision |
|---|---|
| `backend/api/system.py` | Store one JSON `backup_remote`; GET returns masked config plus `has_password`; PUT keeps omitted/empty passwords, encrypts replacements, audits safe metadata, and atomically writes `/etc/faceapp/backup-remote.env` as `0600 root:root`. POST `/system/backup-config/test` runs a 1-byte probe through `timeout 20` and returns sanitized `{ok,message}`. |
| `scripts/` | Source managed env after `.env`; add `push_sftp` using `sshpass -e` and `push_ftp` using a temporary `0600` netrc. |
| `frontend/src/pages/Settings/Settings.tsx` | Add Backup tab, conditional transport fields, write-only password UX, test action, FTP cleartext warning, and relocated DB export. |
| `frontend/src/api/settings.ts`, `frontend/src/i18n/translations.ts` | Add typed API calls and ES/EN strings. |
| `install.sh`, `.env.example`, `README.md` | Install `samba-client`; add SFTP/FTP keys and document UI override precedence. |

## Risks and Mitigations

- Credential leakage: never return ciphertext/plaintext; redact audits, logs, probe output, and process arguments.
- FTP cleartext and SMB process visibility: warn explicitly and recommend SFTP.
- Partial/exposed env writes: atomic temp/rename with strict ownership and mode checks.

## Rollback Plan

Remove the UI/endpoints and managed env file, restore `.env`-only sourcing, and retain existing `none|rsync|smb|nfs` behavior; the JSON row can remain unread or be deleted.

## Success Criteria

- [ ] Admins can save, reload, and test every supported transport without secret disclosure.
- [ ] Backups consume UI config while local retention and warn-only failure remain unchanged.
- [ ] Security tests cover masking, permissions, atomic writes, timeout, process visibility, and log hygiene.

## PR Slicing

Feature-branch chain: **S1** backend, scripts, security/spec tests; **S2** frontend and i18n; **S3** installer, docs, and hardening tests.
