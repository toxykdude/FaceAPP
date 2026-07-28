# Tasks: Remote Backup Configuration UI

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~900 total (S1 ~460, S2 ~330, S3 ~110) |
| 800-line budget risk (per slice) | Low (S1 460, S2 330, S3 110 — all < 800) |
| Chained PRs recommended | Yes |
| Suggested split | S1 → S2 → S3 (feature-branch chain) |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Low

Chain base boundary (feature-branch-chain): tracker branch `feat/remote-backup-config-ui`; PR S1 base = tracker; PR S2 base = S1 branch; PR S3 base = S2 branch. Tracker merges to `main` last.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| S1 | Backend security core + scripts + spec tests | PR #1 (base: tracker) | `cd backend && set -a && . .env && set +a && /root/faceapp/.venv/bin/python -m pytest tests/test_backup_config_api.py tests/test_backup_config_test_endpoint.py tests/test_remote_backup_isolation.py -q` | `bash scripts/backup.sh` in tmp tree with mocked binaries (driven by isolation tests); `bash -n scripts/remote_push.sh scripts/backup.sh` | Revert `backend/services/backup_config.py`, 3 handlers in `backend/api/system.py`, `scripts/remote_push.sh` sftp/ftp/smb arms, `scripts/backup.sh` second-source block, 3 test files |
| S2 | Frontend Backup tab + i18n + API client | PR #2 (base: S1) | `cd frontend && npm run test -- SettingsBackupTab` | `npm run dev` → /settings Backup tab manual; vitest jsdom | Revert `Settings.tsx` tab insertion + Export-DB move, `frontend/src/api/settings.ts` 3 methods, `translations.ts` keys, `SettingsBackupTab.tsx`, `SettingsBackupTab.test.tsx` |
| S3 | install.sh deps + `.env.example` + README docs | PR #3 (base: S2) | `bash -n install.sh`; `grep -c samba-client install.sh .env.example README.md` | Manual: fresh LXC run of `install.sh`, then `command -v smbclient sshpass` | Revert `install.sh` apt list line, `.env.example` block, README section |

## Phase S1 — Backend security core, scripts, spec tests

- [x] S1.1 RED `backend/tests/test_backup_config_api.py`: GET masked (no `password_enc`, has `has_password`); PUT keep-on-omit + keep-on-empty + replace→encrypt; 400 per transport (none/rsync/sftp/ftp/smb/nfs); 403 non-admin; audit `backup_config_update` details=`{type,host}`; env file 0600 + atomic (temp+rename) + transport-change stale-key removal; `backup_remote` absent from `/settings/public`. Verify: `.venv/bin/python -m pytest tests/test_backup_config_api.py` (fails: module+routes absent). Deps: none.
- [x] S1.2 RED `backend/tests/test_backup_config_test_endpoint.py`: probe ok/fail/`timeout 20`→`ok:false`; sanitized message (scrub host/user/password tokens, no banner, ≤200 chars); argv LIST `shell=False` assertion; 403 non-admin; audit `backup_config_test` details=`{type,host,ok}`; **probe leaves no local artifacts deleted/modified** (seed files in tmp BACKUP_DIR, run test, assert byte-identical + count). Verify: `.venv/bin/python -m pytest tests/test_backup_config_test_endpoint.py` (fails). Deps: S1.1.
- [x] S1.3 GREEN `backend/services/backup_config.py` (NEW): `BackupConfig` schema (Pydantic), per-transport `validate()` (fields per design.md:69), `encrypt_string`/`decrypt_string` password round-trip, keep-sentinel (omit OR `""`), `materialize_env()` atomic temp+`os.replace` 0600 root:root writing only transport keys (D6 full rewrite), `probe()` `["timeout","20","bash","remote_push.sh"]` argv list + env-only secret + sanitized `{ok,message}`. Verify: S1.1 + S1.2 pass. Deps: S1.1, S1.2.
- [x] S1.4 GREEN `backend/api/system.py` (MODIFY): add `GET /system/backup-config` (masked + `has_password`), `PUT /system/backup-config` (validate→keep/encrypt→persist→materialize→audit `{type,host}`), `POST /system/backup-config/test` (validate→probe→audit `{type,host,ok}`); all `Depends(require_admin)`. Verify: S1.1+S1.2 green; `.venv/bin/python -m pytest tests/`. Deps: S1.3.
- [x] S1.5 RED extend `backend/tests/test_remote_backup_isolation.py`: add `test_smb_missing_smbclient_warns_samba_client` (mock PATH no `smbclient`, `BACKUP_REMOTE_TYPE=smb`, run backup.sh → log contains literal `samba-client`, rc=0, fresh local `.dump`/`.tar.gz`/`checksums_*.txt` present, `SMB_PASS` token absent); add `test_failed_remote_never_removes_local_artifacts` (seed artifacts, force each transport to fail — missing tool / unreachable host / `timeout 1` — assert seeded+fresh artifacts byte+count identical, retention ran, rc=0); add sftp+ftp log-grep asserting `SSHPASS`/`FTP_PASS` absent (mocked sshpass/curl binaries). Verify: `.venv/bin/python -m pytest tests/test_remote_backup_isolation.py` (new cases fail). Deps: none (test seeds its own mocks).
- [x] S1.6 GREEN `scripts/remote_push.sh` (MODIFY): add `push_sftp` (`sshpass -e sftp -b`, `SSHPASS` env-only, all vars quoted); add `push_ftp` (temp 0600 netrc via `mktemp`+`trap rm`, `curl --netrc-file`, no creds in URL/argv); **prepend `command -v smbclient` pre-flight inside `push_smb` (D9): on absence log one sanitized `WARNING: smbclient not found — install 'samba-client'; remote push skipped`, `return 1` WITHOUT building the `-U user%pass` argv**; add `sftp|ftp` case arms. Verify: S1.5 green; `bash -n scripts/remote_push.sh`. Deps: S1.5.
- [x] S1.7 GREEN `scripts/backup.sh` (MODIFY): insert second source block after line 43 (`.env`) — `if [ -f /etc/faceapp/backup-remote.env ]; then set -a; . /etc/faceapp/backup-remote.env; set +a; fi` so managed env overrides. Verify: S1.5 green (isolation tests already prove warn-only + local-preservation); `bash -n scripts/backup.sh`. Deps: S1.6.
- [x] S1.8 VERIFY S1 slice: `.venv/bin/python -m pytest tests/test_backup_config_api.py tests/test_backup_config_test_endpoint.py tests/test_remote_backup_isolation.py -q` all green; `flake8 . && black --check . && mypy .` from `backend/`. Work-unit commit `feat(backup): secure remote-backup config service, handlers, sftp/ftp/smb preflight`. Deps: S1.1–S1.7.

## Phase S2 — Frontend Backup tab + i18n + API client

- [ ] S2.1 RED `frontend/src/test/SettingsBackupTab.test.tsx` (NEW): render Backup tab as admin → transport `<Select>` with 6 options; conditional fields per transport (none=∅, rsync=host+path, sftp=host+user+password+port22, ftp=host+user+password+port21+cleartext Alert, smb=share+user+password, nfs=path); keep-current password placeholder when `has_password`; FTP cleartext `<Alert>` shown only on ftp; non-admin → tab not rendered; Save calls `putBackupConfig` with masked payload (omit/`""` password on untouched); Test button calls `testBackupConfig` and renders sanitized `{ok,message}`. Verify: `cd frontend && npm run test -- SettingsBackupTab` (fails: tab absent). Deps: S1 API contract.
- [ ] S2.2 GREEN `frontend/src/api/settings.ts` (MODIFY): add `BackupConfig`/`BackupConfigInput`/`BackupTestResult` interfaces; `getBackupConfig()`→`GET /system/backup-config`; `putBackupConfig(data)`→`PUT`; `testBackupConfig()`→`POST /system/backup-config/test` (JSON, no blob). Verify: type-check `npm run type-check`. Deps: S2.1.
- [ ] S2.3 GREEN `frontend/src/pages/Settings/Settings.tsx` (MODIFY): insert 6th `<Tab icon={<CloudUploadIcon/>} label={t.settings.backup} />` after Users (index 4 → Backup index 5); move Export DB `<Paper>` block (lines 348–371) from System tab into new Backup tab; gate whole Backup tab `user?.role === 'admin'`; render `<SettingsBackupTab/>` component. Verify: S2.1 green. Deps: S2.2.
- [ ] S2.4 GREEN `frontend/src/components/settings/SettingsBackupTab.tsx` (NEW): transport Select + conditional fields + write-only password placeholder + FTP cleartext Alert + Save/Test buttons + sanitized result UI. Verify: S2.1 green. Deps: S2.3.
- [ ] S2.5 GREEN `frontend/src/i18n/translations.ts` (MODIFY): add ~16 keys under `settings.backup*` (es + en): `backup`, `backupTransport`, `backupHost`, `backupPort`, `backupShare`, `backupPath`, `backupUsername`, `backupPassword`, `backupPasswordKeep`, `backupHasPassword`, `backupTest`, `backupTesting`, `backupTestOk`, `backupTestFail`, `backupFtpWarning`, `backupSaved`. Verify: existing `SettingsExportDb.test.tsx` still green (Export moved, not removed). Deps: S2.4.
- [ ] S2.6 VERIFY S2 slice: `cd frontend && npm run test && npm run lint && npm run type-check`. Work-unit commit `feat(backup): admin Backup tab with conditional transport fields and sanitized test`. Deps: S2.1–S2.5.

## Phase S3 — Install deps, docs, hardening

- [ ] S3.1 GREEN `install.sh` (MODIFY): add `samba-client sshpass` to the `apt-get install -y` list (line 38–48). Verify: `bash -n install.sh`; `grep -E 'samba-client|sshpass' install.sh`. Deps: S1.
- [ ] S3.2 GREEN `.env.example` (MODIFY): collapse to one authoritative block — `BACKUP_REMOTE_TYPE=none` fallback, add `sftp`/`ftp` to transport comment, UI-override-precedence pointer ("managed `/etc/faceapp/backup-remote.env` sourced after this file → DB-managed values win"), FTP cleartext warning, `samba-client`/`sshpass` install note (D10). Verify: `grep -c 'samba-client\|sshpass\|cleartext\|backup-remote.env' .env.example` ≥ 4. Deps: S1.
- [ ] S3.3 GREEN `README.md` (MODIFY): Backup section pointing at admin UI Backup tab; repeat FTP cleartext warning + `samba-client`/`sshpass` install dependencies; note UI override precedence (D10). Verify: `grep -c 'Backup tab\|samba-client\|sshpass\|cleartext' README.md`. Deps: S3.1.
- [ ] S3.4 VERIFY S3 slice + full change: `bash -n install.sh scripts/backup.sh scripts/remote_push.sh`; backend `pytest tests/` from `backend/` with `.env` exported; frontend `npm run test && npm run lint && npm run type-check`. Work-unit commit `docs(backup): install samba-client/sshpass, document UI override and FTP cleartext`. Deps: S3.1–S3.3.

## Security Acceptance — all 11 spec requirements

| # | Requirement (spec) | Task | Acceptance |
|---|---|---|---|
| 1 | Protected Masked Configuration (no plaintext/ciphertext; not in `/settings/public`) | S1.1, S1.4 | GET returns `has_password` only; `backup_remote` ∉ public list |
| 2 | Unauthorized → 403 | S1.1, S1.2 | non-admin GET/PUT/test all 403 |
| 3 | Validated Write-Only Persistence (AES-256-GCM, keep-sentinel) | S1.1, S1.3 | omit/`""` keeps; replace encrypts; 400 on invalid |
| 4 | Invalid transport → reject, no persist/materialize | S1.1, S1.3 | 400 leaves DB + env file unchanged |
| 5 | Secure Environment Materialization (atomic 0600 root:root, no log of contents) | S1.1, S1.3 | temp+`os.replace`, mode check, stale-key removal on transport change |
| 6 | Transport changes clear stale keys | S1.1, S1.3 | full rewrite (D6), prior transport keys absent |
| 7 | Bounded Sanitized Connection Test (1-byte, 20s timeout, sanitized, no banner) | S1.2, S1.3 | argv LIST `shell=False`; message scrubbed ≤200 chars; no creds/banner |
| 8 | Probe failure MUST NOT alter local backups | S1.2, S1.5 | probe + failed remote leave seeded+fresh artifacts byte+count identical |
| 9 | SFTP/FTP/RSYNC warn-only, no secret in logs | S1.5, S1.6 | log-grep `SSHPASS`/`FTP_PASS`/`SMB_PASS` absent; rc=0 |
| 10 | Fresh-Install SMB Dependency (D9 pre-flight names `samba-client`) | S1.5, S1.6, S3.1 | missing `smbclient` → sanitized warn, rc=0, local preserved |
| 11 | Remote Secret Log Isolation (every password transport) | S1.5, S1.6 | unique tokens absent from all captured logs |

## Work-Unit Commit Plan + Rollback Boundaries

| Slice | Commits | Rollback boundary (independent revert) |
|-------|---------|----------------------------------------|
| S1 | C1 `feat(backup): add backup_config service schema, validation, env materializer, sanitized probe` (tests+impl); C2 `feat(backup): wire system.py handlers + scripts sftp/ftp/smb preflight + second env source` (tests+impl) | Remove `backend/services/backup_config.py`, 3 handlers, 3 test files, `remote_push.sh` new arms, `backup.sh` source block — `.env`-only sourcing restored |
| S2 | C3 `feat(backup): admin Backup tab, conditional fields, sanitized test UI, i18n` | Revert `Settings.tsx` tab+move, `SettingsBackupTab.tsx`, `settings.ts` 3 methods, translations keys, test — System tab Export DB restored (Export DB block moves back) |
| S3 | C4 `docs(backup): install samba-client/sshpass, document UI override + FTP cleartext` | Revert `install.sh` apt line, `.env.example` block, README section — no behavioral impact |

## Manual Verification — shell transports / tool availability (no shell test runner)

- [ ] `bash -n scripts/backup.sh scripts/remote_push.sh install.sh` (syntax).
- [ ] Fresh LXC: `sudo ./install.sh`; then `command -v smbclient sshpass` (both resolve).
- [ ] Missing-tool path: `PATH=/usr/bin:/bin BACKUP_REMOTE_TYPE=smb bash scripts/remote_push.sh` (without smbclient) → one `samba-client` WARNING line, rc=1, no password in output.
- [ ] Probe endpoint via UI Test button on a misconfigured host → `ok:false`, message ≤200 chars, no host/user/password substring.
- [ ] FTP selected in UI → cleartext Alert visible; SFTP selected → no Alert.
