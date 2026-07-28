# Design: Remote Backup Configuration UI

## Technical Approach

Store one JSON `backup_remote` row (key `backup_remote`, category `backup`) in the
existing `settings` table (`Setting.value` is `JSON` — no migration). Password is
encrypted at rest via the proven `encrypt_string`/`decrypt_string` AES-256-GCM
helpers (`core/encryption.py:89/103`, same path as RTSP URLs). All
crypto/validation/materialization lives in a new `services/backup_config.py`;
`api/system.py` stays a thin router (3 handlers). On successful PUT the service
atomically rewrites `/etc/faceapp/backup-remote.env` (0600 root:root) with only
transport-relevant keys; `backup.sh` sources it AFTER `.env` so DB config wins.
`remote_push.sh` gains `push_sftp` (sshpass -e), `push_ftp` (0600 netrc), AND a
`smbclient` pre-flight inside `push_smb` so a fresh install degrades to warn-only
with a `samba-client` install hint instead of an opaque smbclient-not-found error.
Frontend adds a 6th Backup tab with conditional fields and a sanitized test probe.

## Architecture Decisions

| # | Choice | Alternatives | Rationale |
|---|--------|-------------|-----------|
| D1 | Single JSON setting `backup_remote` | discrete keys / dedicated table | mirrors RTSP precedent; atomic save; no migration; clean mask-on-read |
| D2 | crypto+validate+materialize in `services/backup_config.py` | inline in system.py | matches `services/timezone.py`; testable; router stays thin |
| D3 | endpoints on `/system` router, NOT `/settings` | reuse settings routes | `/settings/{key}` is generic+plaintext; `/system` matches db-export precedent + admin-only posture |
| D4 | keep-sentinel = password omitted OR `""` | `"••••"` literal / null | JSON-clean; frontend sends `""` on untouched; null is ambiguous; spec says empty=keep |
| D5 | materialize env file on successful PUT only | also on startup | file persists across reboots; startup re-material adds lifespan ordering hazard; missing file → graceful .env fallback |
| D6 | full file rewrite each save (never append) | selective key patch | guarantees stale transport keys vanish on transport change (spec "Transport changes") |
| D7 | probe via `["timeout","20","bash","remote_push.sh"]`, argv list, env-only secret | shell=True / curl lib | identical discipline to `export_database`; no arg-injection surface |
| D8 | add `samba-client` AND `sshpass` to install.sh | samba-client only | sftp breaks without sshpass on fresh LXC; both are real install gaps. Backs spec req "Fresh-Install SMB Dependency" (specs/remote-backup/spec.md:52). |
| **D9** | **`push_smb` pre-flights `command -v smbclient` before invoking it; on absence logs one sanitized `WARNING: smbclient not found — install 'samba-client'; remote push skipped` and returns 1 (warn-only)** | fail loudly / pass through to smbclient "command not found" | fresh-install SMB transport would otherwise emit an opaque, install-agnostic shell error and risk bash printing the password-bearing `-U user%pass` argv into the log. Pre-flight guarantees the warning names the exact install package, never echoes creds, and leaves local backup/retention successful. Probe endpoint inherits the same warn-only path. |
| **D10** | **README + `.env.example` document BOTH the FTP cleartext warning AND the `samba-client`/`sshpass` install dependencies, plus the UI-override precedence** | docs-only FTP / `.env.example`-only / neither | the proposal gates rollout on "Admins can save, reload, and test every transport without secret disclosure"; FTP cleartext and the missing-tool branches are operator-visible failure modes that need a written home. `.env.example` already had a backup-key discrepancy flagged in exploration.md:37 — collapse it into one authoritative block. |

## Data Flow

```
Admin UI ─PUT─▶ system.py ─▶ backup_config_service ─▶ settings table (password_enc)
                         │                       └─▶ /etc/faceapp/backup-remote.env (0600)
                         └─▶ audit (type, host only)
backup.sh: .env ─source─▶ backup-remote.env ─source─▶ remote_push.sh (env-only)
                                                            └─ push_smb: command -v smbclient ─missing─▶ WARN 'samba-client', return 1
Test btn ─▶ backup_config_service.test() ─▶ timeout 20 bash remote_push.sh ─▶ {ok,message}
                                                  └─ probe failure / missing tool ─▶ ok:false; LOCAL ARTIFACTS UNTOUCHED
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/services/backup_config.py` | Create | Config schema, per-transport validation, encrypt/decrypt, atomic env materializer, sanitized probe runner |
| `backend/api/system.py` | Modify | Add `GET/PUT /system/backup-config`, `POST /system/backup-config/test` (require_admin + log_action) |
| `scripts/remote_push.sh` | Modify | Add `push_sftp` (sshpass -e sftp -b), `push_ftp` (curl --netrc-file 0600 + trap), 2 case arms; **prepend `command -v smbclient` pre-flight inside existing `push_smb` (D9)** |
| `scripts/backup.sh` | Modify | Second source block after line 43 (`.env` then `/etc/faceapp/backup-remote.env`) |
| `frontend/src/pages/Settings/Settings.tsx` | Modify | 6th Backup tab; move Export DB block (348-374) into it; transport select + conditional fields |
| `frontend/src/api/settings.ts` | Modify | `getBackupConfig`/`putBackupConfig`/`testBackupConfig` (JSON, no blob) |
| `frontend/src/i18n/translations.ts` | Modify | ~16 es/en keys under `settings.backup*` |
| `install.sh` | Modify | Add `samba-client sshpass` to apt-get list (line 38-48) |
| **`.env.example`** | **Modify** | **Authoritative block: `BACKUP_REMOTE_TYPE=none` fallback, UI-override pointer, FTP cleartext warning, `samba-client`/`sshpass` install note (D10)** |
| **`README.md`** | **Modify** | **Backup section: point at admin UI tab, repeat FTP cleartext warning, repeat `samba-client`/`sshpass` install dependencies (D10)** |
| **`backend/tests/test_remote_backup_isolation.py`** | **Modify** | **Add RED cases (corrections #2 + #3) below** |

## Interfaces / Contracts

**Config schema** (`backup_remote.value`):
```json
{"type":"none|rsync|sftp|ftp|smb|nfs","host":"","port":null,
 "share":"","path":"","username":"","password_enc":"<b64>"}
```

**Per-transport required fields:** none=∅ · rsync=host,path · sftp=host,username,password_enc(port 22) · ftp=host,username,password_enc(port 21) · smb=share,username,password_enc · nfs=path.

**GET `/system/backup-config`** → 200 `{type,host,port,share,path,username,has_password}`. Never returns `password_enc`/ciphertext. 403 non-admin.

**PUT `/system/backup-config`** ← `{type,host?,port?,share?,path?,username?,password?}`. `password` omitted OR `""` → keep existing; non-empty → `encrypt_string()`+store. Returns masked GET shape. 400 validation, 403 non-admin. Audited `backup_config_update` details `{type,host}`.

**POST `/system/backup-config/test`** → 200 `{ok:bool,message:string}`. Decrypts in-memory, runs 1-byte probe through `timeout 20 bash remote_push.sh`, sanitizes (rc→ok; trimmed last log line≤200 chars, regex-scrubbed of host/user/password tokens, no banner). 400 if config incomplete. Audited `backup_config_test` details `{type,host,ok}`.

**Materialized env keys:** always `BACKUP_REMOTE_TYPE`; rsync→`RSYNC_HOST/PATH/USER`; sftp→`SFTP_HOST/PORT/USER/PATH,SSHPASS`; ftp→`FTP_HOST/PORT/USER,FTP_PASS`; smb→`SMB_SHARE/USER/PASS/PATH`; nfs→`NFS_MOUNT`. Atomic: temp+`os.replace`, mode 0600, full rewrite.

## Testing Strategy

| Layer | File | Cases |
|-------|------|-------|
| Unit/API | `test_backup_config_api.py` (NEW) | masked GET (no ciphertext, has_password), write-only PUT (omit/""/replace), validation 400s per transport, 403 non-admin, audit safe-details, env file 0600+atomic+content, transport-change stale-key removal, `backup_remote` NOT in `/settings/public` |
| Unit/API | `test_backup_config_test_endpoint.py` (NEW) | probe ok/fail/timeout, sanitized output (no password/banner), 403 non-admin, audit `backup_config_test`, **probe leaves no local artifacts deleted/modified (correction #3)** |
| Integration (shell) | extend `backend/tests/test_remote_backup_isolation.py` | sftp + ftp paths (mocked sshpass/curl), warn-only preserved, log-grep `SSHPASS`/`FTP_PASS` absent; **NEW `test_smb_missing_smbclient_warns_samba_client` (correction #2): mock PATH so `command -v smbclient` finds nothing, set `BACKUP_REMOTE_TYPE=smb`, run `backup.sh`, assert (a) log contains literal `samba-client`, (b) script exits warn-only (parent backup.sh rc=0), (c) fresh local `.dump`/`.tar.gz`/`checksums_*.txt` still present; also assert `SMB_PASS` token absent from log**; **NEW `test_failed_remote_never_removes_local_artifacts` (correction #3): seed pre-existing local artifacts, force each transport to fail (missing tool / unreachable host / probe-timeout via `timeout 1`), then assert seeded + freshly produced local artifacts remain unchanged in count and content, retention still ran, rc=0** |
| Component | `SettingsBackupTab.test.tsx` (NEW) | conditional fields per transport, FTP cleartext Alert, keep-current placeholder, non-admin tab hidden, submit payload, Test button |

RED-first per file (STRICT TDD active, `strict_tdd: true`).

## Threat Matrix

Predefined rows (git/PR routing, commit/push state, executable-md, repo selection): **N/A** — this change touches no VCS/PR/routing/commit boundary.

**Security threat cases (subprocess + shell + secret boundary — design requirements, propagate to tasks unchanged):**

| Boundary | Safe behavior | Fail behavior | RED test |
|---|---|---|---|
| Test-endpoint subprocess argv | argv LIST, `shell=False`, secret via env only | n/a — no shell surface | test_endpoint sanitized + argv asserts |
| push_sftp/push_ftp shell args | all vars double-quoted, no eval, SSHPASS env-only, FTP creds in 0600 netrc not URL/cmdline | warn-only return 1, no echo | isolation sftp+ftp log-grep |
| **push_smb missing smbclient (D9)** | **`command -v smbclient` gate BEFORE constructing the `-U user%pass` argv; on absence log sanitized `samba-client` hint, return 1** | **no argv built → password never reaches the bash "command not found" stderr line; warn-only, parent backup.sh rc=0, local artifacts preserved** | **`test_smb_missing_smbclient_warns_samba_client` (NEW in isolation test)** |
| Materialized env-file race | temp+`os.replace` atomic, 0600 root:root | malformed prior file fully replaced, no partial read | api env-file atomic test |
| **Failed remote probe/replication cannot touch local artifacts (correction #3)** | **probe runs in its own tmp cwd; `remote_push.sh`/probe never `rm` from `BACKUP_DIR`; backup.sh writes local artifacts BEFORE invoking remote push and never re-touches them on push failure** | **any rc≠0 from remote_push (missing tool / unreachable / `timeout 20`) leaves seeded + fresh local dumps, tarballs, and checksums byte-identical and count-identical** | **`test_failed_remote_never_removes_local_artifacts` (NEW isolation test) + test_endpoint "probe leaves no local artifacts deleted/modified"** |
| Secret in logs/ps/audit/banner | never log password; audit details={type,host}; scrub probe output | n/a | api audit-details + test_endpoint sanitized |

## Migration / Rollout

No DB migration. LXC deployment needs only a redeploy (install.sh adds
`samba-client`+`sshpass`; README/`.env.example` now carry the matching docs).
Existing `.env`-only configs keep working (file sources after `.env`; absent
managed file = pure fallback). Rollback: remove endpoints/UI/managed file; `.env`
sourcing restored.

## Open Questions

- None blocking. (Password-clear UX is a non-goal; clearing requires DB edit.)

## Slicing (budget ~800; bumped for D9 branch + 2 new isolation RED tests)

- **S1 — backend+scripts+spec tests (~460 ln)**: `services/backup_config.py`, system.py handlers, remote_push.sh sftp/ftp + **smbclient pre-flight in push_smb (D9)**, backup.sh source, `test_backup_config_api.py`, `test_backup_config_test_endpoint.py`, extend `test_remote_backup_isolation.py` with **`test_smb_missing_smbclient_warns_samba_client` + `test_failed_remote_never_removes_local_artifacts`**. Lands first — defines contract. *(Bumped +50 ln from 410 for the SMB branch and two RED cases.)*
- **S2 — frontend+i18n (~330 ln)**: SettingsBackupTab, Settings.tsx integration, settingsApi ext, translations es/en, `SettingsBackupTab.test.tsx`.
- **S3 — install+docs+hardening (~110 ln)**: install.sh `samba-client sshpass`, `.env.example` authoritative block + FTP cleartext warning + install deps, README Backup section pointer. *(Bumped +20 ln from 90 for explicit D10 docs in BOTH files.)*
