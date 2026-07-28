# Verification Report: remote-backup-config-ui

**Change**: `remote-backup-config-ui`
**Project**: faceapp
**Verifier**: independent SDD verify agent (did NOT author this code)
**Branch under test**: `feat/remote-backup-config-ui-slice-s3` (tip `501ebf9`)
**Chain**: tracker `feat/remote-backup-config-ui` (`e4c8bb2`) → s1 (`5dfde78`) → s2 (`20c62f2`) → **s3 (`501ebf9`)**
**Base**: `main` (`c8bc6d2`)
**Mode**: Standard verification (specs + design + tasks all present → full dimension verification)
**Persistence**: openspec file (this report) + Engram mirror

## status

`PASS WITH WARNINGS`

## executive_summary

Independent verification of the `remote-backup-config-ui` change confirms **all 11 spec requirements are met** with concrete runtime + source evidence. I re-ran the full backend and frontend suites myself and every static gate (mypy / black / flake8 / tsc / eslint / `bash -n`); all pass clean. Every security-critical behavioral claim was checked at the source level and, where applicable, cross-checked against a passing test: masked reads never emit ciphertext, write-only keep-sentinel works on both omit and empty-string, env materialization is atomic with full-rewrite stale-key removal, the probe uses an argv list with `shell=False` and sandboxes `BACKUP_DIR`, the `smbclient` pre-flight runs **before** the password-bearing `-U` argv is built, SFTP/FTP secrets travel env-only / netrc-only, and `backup.sh` sources the managed env file **after** `.env`. The frontend exposes a 6-option transport select with conditional fields, an FTP-only cleartext `Alert`, a write-only password placeholder, and full ES/EN i18n with no hardcoded user strings.

One low-severity WARNING: the **Managed Environment Override** scenario (`remote-backup/spec.md` req. "Managed Environment Override" — "managed and fallback values differ → managed wins") is verified by source inspection of deterministic shell sourcing order (`backup.sh:39-57` sources `.env` then `/etc/faceapp/backup-remote.env`) but has **no dedicated runtime test** that exercises both files with differing values. The behavior is deterministic POSIX shell semantics (last `source` wins) and cannot be implemented incorrectly as written, so this does not block archival — but it is weaker runtime evidence than the other 10 requirements and is flagged transparently.

The documented **FTP_PATH deviation** is internally consistent and **not a spec violation**: `backup_config.py:274-278` materializes `FTP_HOST/PORT/USER/PASS` only, `remote_push.sh:194` uploads to `ftp://${host}:${port}/<file>` (no path), and `.env.example` documents exactly those four keys. The FTP spec requires curl + 0600 netrc + no creds in URL + cleartext documentation — none of which requires an `FTP_PATH` key.

**Recommendation: archive.** No CRITICAL findings, no spec violations, full suite green.

## artifacts

- Branch: `feat/remote-backup-config-ui-slice-s3` (tip `501ebf9`), not pushed
- Verify report: `openspec/changes/remote-backup-config-ui/verify-report.md` (this file)
- Engram mirror: topic_key `sdd/remote-backup-config-ui/verify-report`
- Specs verified: `specs/backup-remote-config/spec.md` (5 requirements), `specs/remote-backup/spec.md` (1 MODIFIED + 5 ADDED = 6 requirements; **11 total**)
- Design: `design.md` (D1–D10 all honored — see coherence table)
- Tasks: `tasks.md` — **18/18 implementation tasks `[x]`**; 5 `[ ]` are the explicitly-deferred "Manual Verification" real-iron section (acceptable)

## next_recommended

**archive**

Rationale: all 11 requirements PASS, all automated gates green, no CRITICAL findings, the single WARNING is deterministic-behavior source-evidence that does not risk correctness. Proceed to `sdd-archive` to sync the delta specs.

## risks

- **Managed-override scenario lacks a runtime test** (WARNING, low severity). Deterministic shell sourcing order makes this very low risk, but a dedicated test (`set .env value X + managed-env value Y, run backup.sh, assert Y wins`) would convert source evidence to runtime evidence. Does not block archival.
- **Manual real-iron steps unexercised** (expected, explicitly deferred). Fresh-LXC `install.sh` + `command -v smbclient sshpass`, the live UI Test button on a misconfigured host, and the live FTP/SFTP Alert toggle are in the deferred "Manual Verification" section. The isolation tests already cover the missing-`smbclient` and missing-tool branches in a mocked tree; the remaining gap is real-iron install confirmation.
- **Success-path secret isolation is structural, not separately tested.** The isolation tests mock `sshpass`/`curl`/`smbclient` to FAIL, proving no secret leaks on the failure path. The success path logs hardcoded literals ("Remote SFTP replication completed") with zero credential interpolation, so leakage is structurally impossible — but it is not separately exercised with a succeeding mock. Very low risk.

## skill_resolution

- Loaded: `/root/.claude/skills/sdd-verify/SKILL.md` (executor path — no delegation)
- Loaded: `/root/faceapp/.atl/skill-registry.md` (no project-scoped verify skill; standard SDD verify applies)
- Strict TDD: **not active for verification** (apply used Strict TDD for RED→GREEN authoring; verify runs standard compliance checks). `strict-tdd-verify.md` not loaded.
- Mode: standard (specs + design + tasks present → full dimension verification)

## verdicts — 11 spec requirements

### Capability `backup-remote-config` (spec.md — 5 requirements)

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | **Protected Masked Configuration** — admin-only GET, `has_password` bool, no plaintext/ciphertext, `backup_remote` ∉ `/settings/public` | **PASS** | `_mask()` (`backup_config.py:139-149`) emits only `{type,host,port,share,path,username,has_password}` — never `password_enc`/`password`. `/settings/public` (`api/settings.py:24-31`) uses a fixed allowlist `[app_name,theme_mode,business_name,business_logo,timezone]` queried with `.in_(public_keys)`; `backup_remote` is excluded by construction. Runtime: `test_get_default_config_is_none_and_masked`, `test_get_after_save_reports_has_password_without_ciphertext`, `test_backup_remote_absent_from_public_settings` all passed. 403 enforced via `Depends(require_admin)` on all 3 handlers. |
| 2 | **Validated Write-Only Persistence** — AES-256-GCM, keep-sentinel (omit/`""`), reject invalid without persist/materialize, audited w/o secrets | **PASS** | `apply_update` (`:206-233`): `if "password" in payload and payload["password"]: merged["password_enc"] = encrypt_string(...)` — omit OR `""` keeps existing. `validate()` runs BEFORE `_persist`/`materialize_env`, so invalid → 400 changes nothing. `encrypt_string`/`decrypt_string` = AES-256-GCM (`core/encryption.py:35,64,89,103`). Audit details `{type,host}` only (`system.py:222`). Runtime: `test_replace_password_encrypts_with_aes_gcm`, `test_omitted_password_keeps_existing`, `test_empty_password_keeps_existing`, `test_invalid_config_returns_400` (8 payloads), `test_invalid_put_does_not_persist_or_materialize`, `test_put_audits_safe_details` (asserts `"supersecret" not in details`) all passed. |
| 3 | **Secure Environment Materialization** — atomic temp+`os.replace`, 0600, root:root, transport-only keys, no stale keys on change, no log of contents | **PASS** | `materialize_env` (`:290-319`): `tempfile.mkstemp` in `target.parent` + `os.fsync` + `os.chmod(0o600)` + best-effort `chown root:root` + `os.replace`. `_env_lines` (`:254-287`) is a full rewrite emitting only the current transport's keys (D6). No file content is ever logged. Runtime: `test_env_file_mode_0600` (`mode == 0o600`), `test_env_file_contains_transport_keys_only`, `test_transport_change_removes_stale_keys` (smb→rsync removes `SMB_SHARE`/`SMB_PASS`), `test_materialize_leaves_no_temp_fragment` all passed. |
| 4 | **Bounded Sanitized Connection Test** — POST `/test`, 1-byte file, 20s timeout, sanitized `{ok,message}`, no secrets/banners, probe leaves local artifacts untouched | **PASS** | `run_probe` (`:336-376`): writes 1-byte `b"x"`; argv = `["timeout","20","bash",REMOTE_PUSH_SH]` via `subprocess.run(..., capture_output=True)` (no `shell=True` → `shell=False`); runs inside `tempfile.TemporaryDirectory()` sandbox with `BACKUP_DIR`/`LOG_FILE`/`DATA_DIR` forced to temp. `_sanitize_message` (`:431-454`) scrubs host/user/share/path/password tokens + regex for `password|passwd|secret|token` patterns + truncates to 200 chars. Runtime: `test_probe_ok_returns_ok_true` (asserts `isinstance(argv, list)`, `argv[:2]==["timeout","20"]`, `"bash" in argv`, `shell is False`), `test_probe_fail_returns_ok_false_sanitized` (banner with host/user/secret all scrubbed, `len(msg)<=200`), `test_probe_timeout_returns_ok_false` (rc=124), `test_secret_travels_via_env_not_argv` (`env["SSHPASS"]=="PROBE-SECRET"`, no secret in argv), `test_probe_does_not_modify_local_backup_dir` (seeded prod artifacts byte+count identical after probe) all passed. |
| 5 | **Admin Backup User Interface** — localized ES/EN Backup tab, transport select, conditional fields, write-only keep-current placeholder, save+test, Export DB moved from System, FTP cleartext warning | **PASS** | `Settings.tsx` diff: 6th `<Tab>` (`CloudUploadIcon`) inserted, admin-gated `{user?.role === 'admin' && ...}`; Export DB `<Paper>` block moved from `activeTab===3` (System) into `activeTab===5` (Backup) with `<SettingsBackupTab/>`. `SettingsBackupTab.tsx`: 6-option `<Select>` (none/rsync/sftp/ftp/smb/nfs), `VISIBLE` map drives conditional fields, `onTransportChange` clears irrelevant fields, FTP-only `<Alert severity="warning">` (`:234`), keep-current placeholder (`:203`), Save+Test buttons. `translations.ts`: all 16 `settings.backup*` keys present in **both** `es` and `en`. No hardcoded user strings in JSX (grep confirmed; transport names are untranslated technical IDs). Runtime: 7 `SettingsBackupTab.test.tsx` cases passed (6 options, conditional fields per transport, FTP warning only on ftp, keep-current helper, non-admin tab hidden, Save empty-password sentinel, Test sanitized result). |

### Capability `remote-backup` (spec.md — 1 MODIFIED + 5 ADDED = 6 requirements)

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 6 | **Environment-Only Remote Credentials** *(MODIFIED)* — creds from env only, not logged; DB password encrypted at rest + materialized into root-only env file; not in source control | **PASS** | `backup.sh:39-57` sources `.env` then `/etc/faceapp/backup-remote.env` (env-only). `remote_push.sh` reads every credential from env vars; no credential is ever echoed. `_decrypt_or_empty` (`backup_config.py:106-119`) decrypts only into the 0600 root:root env file. `.env.example` documents "read at runtime only — NEVER stored in source control, logs, or ps". Runtime: `test_unreachable_remote_preserves_local_backup` asserts `SMB-SECRET-TOKEN` and `DBPASS-SECRET` absent from the backup log. |
| 7 | **SFTP Replication** — `sshpass -e sftp -b`, `SSHPASS` env-only, never process args | **PASS** | `remote_push.sh:145`: `sshpass -e sftp -P "$port" "${user}@${host}" -b "$batch"` — `-e` reads `SSHPASS` from env; the batch file carries only path/transfer commands (`:137-143`); the secret is never on the argv, in the batch, or in a log. Runtime: `test_passwords_never_in_logs_or_argv[sftp]` asserts `SSHP-SECRET-TOKEN` absent from the `sshpass.argv` marker file, the log, stdout, AND stderr. |
| 8 | **FTP Replication** — curl + temp 0600 netrc, no creds in URL/args, cleartext risk documented | **PASS** | `remote_push.sh:159-207`: `mktemp` + `chmod 600` netrc + `curl --netrc-file` (`:191-195`); URL is `ftp://${host}:${port}/$(basename "$f")` (`:194`) — **no userinfo**; netrc is `rm -f`'d after. Cleartext risk documented in `.env.example` (FTP block warning) and `README.md` (⚠️ callout + transport table). Runtime: `test_passwords_never_in_logs_or_argv[ftp]` asserts `FTPP-SECRET-TOKEN` absent from `curl.argv` marker, log, stdout, stderr. |
| 9 | **Managed Environment Override** — `backup.sh` sources `/etc/faceapp/backup-remote.env` AFTER `.env` | **PASS** *(source-evidence — see WARNING)* | `backup.sh:39-44` sources `$ENV_FILE` (`.env`); `backup.sh:52-57` sources `/etc/faceapp/backup-remote.env` conditionally **after** `.env`. POSIX sourcing order is deterministic: last `source` wins → managed values override fallback. **No dedicated runtime test** exercises both files with differing values; the isolation tests set `ENV_FILE=does-not-exist` and inject env directly, so they do not cover this scenario's override semantics. Behavior is deterministic shell sourcing (no conditional/merge logic that could be buggy), so source inspection is authoritative, but runtime evidence is weaker than the other 10 requirements. |
| 10 | **Fresh-Install SMB Dependency** — install.sh installs `samba-client`; SMB warn-only with `samba-client` hint when `smbclient` missing | **PASS** | `install.sh:50`: `samba-client sshpass` added to `apt-get install -y`. `remote_push.sh:95-98`: `command -v smbclient >/dev/null 2>&1` pre-flight runs **BEFORE** the `-U "${user}%${pass}"` argv is constructed at `:103` (order verified — D9 honored); on absence logs `WARNING: smbclient not found — install 'samba-client'; remote push skipped` (literal `samba-client`) and `return 1`. Runtime: `test_smb_missing_smbclient_warns_samba_client` (`with_smbclient=False`) asserts `"samba-client" in log`, `rc==0`, fresh `.dump`/`.tar.gz`/`checksums_*.txt` present, retention ran, `SMB-SECRET-TOKEN` absent from log/stdout/stderr. |
| 11 | **Remote Secret Log Isolation** — no SMB/SFTP/FTP password in any log (success/warning/timeout/failure) | **PASS** | Every transport's failure path is exercised by the isolation suite with unique secret tokens (`SMB-SECRET-TOKEN`, `SSHP-SECRET-TOKEN`, `FTPP-SECRET-TOKEN`); each is asserted absent from log + stdout + stderr + the respective tool's argv marker file. The success-path log lines are hardcoded literals (`"Remote SFTP replication completed"`, etc.) with zero credential interpolation, so success-path leakage is structurally impossible. Runtime: `test_smb_missing_smbclient_warns_samba_client`, `test_passwords_never_in_logs_or_argv[sftp|ftp]`, `test_failed_push_preserves_local_artifacts[smb|sftp|ftp|rsync|nfs]` (5 transports) all passed. |

## findings

### CRITICAL
*(none)*

### WARNING
- **W1 — Managed-override scenario backed by source inspection, not runtime test** (req. 9). The "managed and fallback values differ → managed wins" scenario has no dedicated runtime test. Compliance is proven by deterministic POSIX shell sourcing order (`backup.sh:39-57`), which cannot be implemented incorrectly as two `source` statements in order. Low risk; does not block archival. *Fix (optional, pre- or post-archive):* add a test that writes a `.env` with `BACKUP_REMOTE_TYPE=rsync` and a managed `/etc/faceapp/backup-remote.env` with `BACKUP_REMOTE_TYPE=sftp`, runs `backup.sh` in the mocked tree, and asserts the sftp branch (not rsync) is the one invoked.

### SUGGESTION
- **S1 — Mark auto-covered manual items.** The "Manual Verification" section in `tasks.md` has 5 unchecked `[ ]` items. Of these, `bash -n` (I confirmed all 3 scripts pass), the missing-tool path (covered by `test_smb_missing_smbclient_warns_samba_client` + `test_failed_push_preserves_local_artifacts`), and the FTP/SFTP Alert toggle (covered by `SettingsBackupTab.test.tsx`) are already auto-covered. Consider annotating which manual lines remain genuinely real-iron (fresh-LXC `install.sh`, live UI Test against a real host) vs. auto-covered, to avoid implying all five are unverified.
- **S2 — FTP transport conditional-fields not explicitly asserted.** The frontend test asserts field visibility for none/rsync/sftp/smb/nfs but not ftp's fields directly (ftp's cleartext warning is separately tested). ftp shares sftp's field shape, so it is implicitly covered, but an explicit ftp-field assertion would close the trivial gap.
- **S3 — FTP_PATH deviation is benign but undocumented in spec terms.** The agent noted `FTP_PATH` is not materialized. This is consistent across code + `.env.example` + `remote_push.sh` and is **not** required by the FTP spec. No action needed unless a future change wants FTP subdirectory upload support.

## test_evidence

All commands run by the verifier on `feat/remote-backup-config-ui-slice-s3` (`501ebf9`), clean working tree.

### Backend (`backend/`)
| Command | Result |
|---|---|
| `set -a && . ./.env && set +a && /root/faceapp/.venv/bin/python -m pytest tests/ -q` | **140 passed**, 124 warnings, 4.87s — exit 0 |
| `/root/faceapp/.venv/bin/python -m mypy .` | **Success: no issues found in 94 source files** — exit 0 |
| `/root/faceapp/.venv/bin/python -m black --check .` | **All done — 102 files would be left unchanged** — exit 0 |
| `/root/faceapp/.venv/bin/python -m flake8 .` | clean — exit 0 |

New/extended backend test files all green within the 140: `test_backup_config_api.py`, `test_backup_config_test_endpoint.py`, `test_remote_backup_isolation.py` (incl. `TestSmbMissingSmbclient`, `TestRemotePasswordsNeverLogged[sftp|ftp]`, `TestFailedRemoteNeverRemovesLocalArtifacts[smb|sftp|ftp|rsync|nfs]`).

### Frontend (`frontend/`)
| Command | Result |
|---|---|
| `npm run test` (vitest run) | **Test Files 12 passed (12) · Tests 49 passed (49)**, 35.80s — exit 0 |
| `npm run type-check` (`tsc --noEmit`) | clean, no output — exit 0 |
| `npm run lint` (`eslint . --max-warnings 0`) | clean — exit 0 |

New frontend test file green within the 49: `SettingsBackupTab.test.tsx` (7 tests).

### Shell scripts (`/root/faceapp/`)
| Command | Result |
|---|---|
| `bash -n install.sh scripts/backup.sh scripts/remote_push.sh` | all OK — exit 0 |

### Output hashes (test summary lines, sha256)
- Backend pytest summary: `14b757ab14c8c65c21002d56f150f5b79c0896c859a0865e851b055bf6037c20`
- Frontend vitest summary: `9306ef018caa7adf0f1e5355fd469bea6dc03f7c0e348c25af71a37ac793c455`

## Completeness / Correctness / Coherence

### Task completeness
- **18/18 implementation tasks** `[x]` (S1.1–S1.8, S2.1–S2.6, S3.1–S3.4). 0 unchecked implementation tasks.
- 5 `[ ]` items are in the explicitly-deferred "Manual Verification — shell transports / tool availability" section (real-iron: fresh LXC, live UI probe, live Alert toggle). Per verify skill graceful handling, explicitly-deferred real-iron manual lines are acceptable; several are in fact auto-covered (see S1).

### Behavioral compliance matrix (spec scenario → covering test, all runtime-passed)
| Spec scenario | Covering test (passed) |
|---|---|
| Config has no password → `has_password` false, no password repr | `test_get_default_config_is_none_and_masked` |
| Unauthorized → 403 | `TestAuthorization` (GET/PUT/test 403 + 401 unauth) |
| Empty password preserves secret | `test_omitted_password_keeps_existing`, `test_empty_password_keeps_existing` |
| Invalid transport → reject, no persist/materialize | `test_invalid_config_returns_400` (8), `test_invalid_put_does_not_persist_or_materialize` |
| Transport changes → no stale keys, correct mode/owner | `test_transport_change_removes_stale_keys`, `test_env_file_mode_0600` |
| Existing file malformed → atomic replace, no partial read | `test_materialize_leaves_no_temp_fragment` (atomic temp+replace path) |
| Remote unreachable → `ok:false`, sanitized, audit, local unaffected | `test_probe_fail_returns_ok_false_sanitized`, `test_probe_does_not_modify_local_backup_dir`, `test_test_audits_safe_details` |
| Probe times out (20s) → terminated, `ok:false`, sanitized | `test_probe_timeout_returns_ok_false` |
| UI transport selection → irrelevant fields cleared, FTP shows warning | `conditional fields appear/clear per transport`, `FTP cleartext warning is shown only when ftp` |
| Non-admin → Backup tab not shown | `non-admin: Backup tab is not rendered` |
| SMB client missing → `samba-client` warning, local preserved | `test_smb_missing_smbclient_warns_samba_client` |
| FTP client/netrc unavailable → warn-only, local preserved | `test_passwords_never_in_logs_or_argv[ftp]`, `test_failed_push_preserves_local_artifacts[ftp]` |
| SFTP password unavailable → warn, local preserved | `test_passwords_never_in_logs_or_argv[sftp]`, `test_failed_push_preserves_local_artifacts[sftp]` |
| Remote creds configured → env-only, encrypted at rest, not logged | `test_unreachable_remote_preserves_local_backup` (SMB+DB secret tokens absent) |
| Secret isolation across every password transport | `TestRemotePasswordsNeverLogged[sftp|ftp]` + SMB token assertions |

### Design coherence (D1–D10)
| Decision | Honored | Notes |
|---|---|---|
| D1 single JSON `backup_remote` row | ✓ | `SETTING_KEY="backup_remote"`, category `"backup"`, no migration |
| D2 service owns crypto/validate/materialize | ✓ | `services/backup_config.py`; `system.py` stays a thin router |
| D3 endpoints on `/system`, not `/settings` | ✓ | `GET/PUT /system/backup-config`, `POST /system/backup-config/test` |
| D4 keep-sentinel = omit OR `""` | ✓ | `apply_update:226` |
| D5 materialize on successful PUT only | ✓ | called inside `apply_update` after `_persist` |
| D6 full rewrite each save | ✓ | `_env_lines` rebuilds from scratch |
| D7 probe argv list, env-only secret | ✓ | verified by `test_probe_ok_returns_ok_true` argv assertions |
| D8 install `samba-client` AND `sshpass` | ✓ | `install.sh:50` |
| D9 `push_smb` pre-flights `command -v smbclient` before `-U` argv | ✓ | order confirmed `:95` before `:103` |
| D10 README + `.env.example` document FTP warning + install deps + override precedence | ✓ | both files updated; `grep` counts exceed thresholds |

No design deviations detected. The FTP_PATH note is a non-required key, not a design or spec deviation.

---

**Final verdict: PASS WITH WARNINGS** — all 11 requirements met; full suite green; one low-severity WARNING (req. 9 runtime-test gap on deterministic behavior); no CRITICAL; recommend **archive**.
