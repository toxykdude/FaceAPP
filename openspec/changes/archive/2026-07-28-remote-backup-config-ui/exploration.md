# Exploration: remote-backup-config-ui

> Sub-agent: sdd-explore. Status: EXPLORE complete. Artifact store: hybrid (filesystem +
> engram). Language: artifact English, conversation Rioplatense Spanish.
> Predecessor change: `admin-data-tools` (archived 2026-07-28).

## Current State

Remote backup today is **env-only and headless**: `scripts/backup.sh` sources
`/opt/powerhouse-membership/.env` (backup.sh:38-43), then calls
`scripts/remote_push.sh` (backup.sh:154) which dispatches on
`BACKUP_REMOTE_TYPE` (remote_push.sh:128) across `none|rsync|smb|nfs`. Remote
failure is **warn-only**; local retention always runs. A systemd timer fires it
every 30 min. The admin can download a DB dump via the Settings → System tab
(`GET /system/db-export`, system.py:87) but has **no UI to configure the remote
target or transport** — that requires SSH + `.env` edits on the server.

The predecessor spec formalized this in a requirement **"Environment-Only Remote
Credentials"** (remote-backup/spec.md:32-41) whose scenario asserts *"no remote
credential value is written to the application database"*. This change
**formally MODIFIES** that requirement: credentials move to the DB, encrypted at
rest, and are materialized into the script's env at backup time. The contract
that the *script* sees only env vars (never logs them) is preserved unchanged.

## Affected Areas

- `backend/api/system.py` — add `GET/PUT /system/backup-config` + `POST /system/backup-config/test` to the existing `/system` router (require_admin + log_action). No new router registration needed (main.py:241 already includes `system.router`).
- `backend/core/encryption.py` — reuse existing `encrypt_string`/`decrypt_string` (lines 89-115) for the password. **No new crypto needed.**
- `backend/api/settings.py` — reference for the Setting model write pattern; the new endpoint lives on `/system` (cleaner separation, matches db-export precedent) but stores into the same `settings` table.
- `backend/models/setting.py` — `value` is `JSON` (setting.py:10), so a structured config blob needs **no migration**.
- `scripts/remote_push.sh` — add `push_sftp` + `push_ftp` functions and two new `case` arms (remote_push.sh:128-148).
- `scripts/backup.sh` — add a second env source (`/etc/faceapp/backup-remote.env`) AFTER `.env` (backup.sh:38-43) so DB-managed config overrides.
- `frontend/src/pages/Settings/Settings.tsx` — add a "Backup" tab (Settings.tsx:245-275 tab list; System tab is index 3). Transport `<Select>` pattern already exists (timezone select, Settings.tsx:193-202).
- `frontend/src/api/settings.ts` — add backup-config API methods (mirrors `exportDatabase`, settings.ts:50-55).
- `frontend/src/i18n/translations.ts` — extend `settings.*` blocks (es:318-368, en:762-812).
- `install.sh` — **gap: smbclient NOT installed**; FTP/SFTP tools already present (see area 6).
- `.env.example` — **discrepancy: no backup keys present** despite archive-report.md:29 claiming they were documented. Must verify/fix.
- `openspec/.../remote-backup/spec.md` — formal MODIFY of "Environment-Only Remote Credentials".

## Approaches

### 1. Single JSON config setting (RECOMMENDED)

Store the whole remote config as one JSON value under key `backup_remote`
(category `backup`): `{type, host, port, user, path, password_enc, extra...}`,
where `password_enc = encrypt_string(plaintext)`. One row, no migration (JSON
column already supports it), clean read/write, password field encrypted.

- Pros: one setting row; mirrors RTSP-URL precedent (cameras.py stores encrypted
  conn string in a model column via `encrypt_string`); no migration; GET masks
  password, PUT is write-only for password; trivial to extend with new fields.
- Cons: GET must project/mask (strip `password_enc`, return `has_password: bool`);
  slightly more serialization code than discrete keys.
- Effort: Medium.

### 2. Discrete setting keys per field

`backup_remote_type`, `backup_remote_host`, ..., `backup_remote_password` (enc).

- Pros: each field independently editable via existing `PUT /settings/{key}`.
- Cons: leaks schema in the settings table; partial writes leave inconsistent
  state (type=sftp but host empty); password masking must special-case one key;
  no atomic save.
- Effort: Medium.

### 3. Dedicated `backup_config` table

New model + Alembic migration.

- Pros: typed columns, cleanest relational model.
- Cons: over-engineered for a single global config; migration cost; diverges
  from the established settings-table pattern; spec delta larger.
- Effort: High.

### Recommendation

**Approach 1 (single JSON setting, password encrypted via `encrypt_string`).**
It reuses the exact crypto + table already proven for RTSP URLs, needs no
migration, gives atomic saves, and keeps the password encrypted at rest with a
clean write-only / mask-on-read API surface.

## Risks (security-first)

- **Formal spec inversion.** The MODIFIED requirement must be worded so the
  *script-level* invariant holds ("creds only via env, never logged") while
  permitting DB-at-rest. If the wording is sloppy, the log-grep test
  (`test_remote_backup_isolation`) and threat matrix (design.md:140) regress.
- **Plaintext leakage via GET.** The read endpoint MUST mask. Returning the
  ciphertext is also risky (offline attack if DB dumps leak — the dump itself is
  admin-only but still). Recommend returning only `has_password: bool`.
- **Materialization file exposure.** `/etc/faceapp/backup-remote.env` holds
  plaintext at runtime. Must be `chmod 0600`, `chown root:root`, and the backend
  process must run as root (it does, per LXC/systemd install) OR a dedicated
  group. Re-write atomically (temp + rename) on save.
- **FTP is cleartext.** UI must warn. Same for SMB `-U user%pass` process-list
  visibility (known W-2 risk, design.md:75 / verify-report.md:158).
- **smbclient not installed.** SMB transport is currently non-functional on a
  fresh install. install.sh must add `samba-client`.
- **`.env.example` discrepancy.** Grep found NO backup keys in `.env.example`
  though archive-report.md:29 lists them as delivered. Verify whether they were
  never added or were removed; the new DB-managed flow makes most `.env` keys
  obsolete anyway (only `BACKUP_REMOTE_TYPE=none` default + DB fallback matter).
- **Test-endpoint SSRF/abuse.** `POST /system/backup-config/test` runs a network
  operation with admin-supplied target → must be admin-only, audited
  (`backup_config_test`), timeout-bounded, rate-limitable, and never echo the
  remote server's banner verbatim (sanitize).

## Credential Model Recommendation

**Storage:** one settings row, key `backup_remote`, category `backup`, value:
```json
{
  "type": "none|rsync|sftp|ftp|smb|nfs",
  "host": "...", "port": 22, "user": "...", "path": "...",
  "password_enc": "<base64 AES-256-GCM via encrypt_string()>",
  "ssh_key_path": "/root/.ssh/id_backup"   // optional, sftp/rsync
}
```

**API surface (on `/system` router):**
- `GET /system/backup-config` → admin-only. Returns everything EXCEPT
  `password_enc`; emits `has_password: bool` and `configured_type`.
- `PUT /system/backup-config` → admin-only + audited (`backup_config_update`,
  details = `{type, host}` only, never password). Accepts `password` as a
  **write-only** field: empty/`"••••"` sentinel → keep existing; non-empty →
  `encrypt_string()` and store.
- `POST /system/backup-config/test` → admin-only + audited
  (`backup_config_test`). Decrypts in-memory, runs `remote_push.sh` against a
  throwaway probe dir with `timeout 20s`, returns `{ok, message}` sanitized.

**Materialization (DB → script env):** on every successful PUT, backend writes
`/etc/faceapp/backup-remote.env` (mode 0600, owner root) containing the
decrypted vars in remote_push.sh's existing names (`BACKUP_REMOTE_TYPE`,
`RSYNC_*`, `SMB_*`, `SFTP_*`, `FTP_*`, `NFS_MOUNT`). `backup.sh` sources `.env`
FIRST then `/etc/faceapp/backup-remote.env` SECOND (set -a; . file; set +a) so
DB config wins. The script is unchanged in its security model: it still reads
only env, logs none. This satisfies the MODIFIED requirement: *"credentials are
sourced from environment at backup runtime; the source of that environment MAY
be the application database, stored encrypted at rest and materialized to a
root-only file on save."*

## Transport Plan

| Transport | Tool (installed?) | Mechanism | Install need | Notes |
|-----------|-------------------|-----------|--------------|-------|
| **rsync** | rsync ✓ ssh ✓ | existing `push_rsync` (remote_push.sh:42); creds via SSH key or `RSYNC_PASSWORD` env | none | **Preferred** per design.md:19. No change. |
| **sftp** | sftp ✓ sshpass ✓ | new `push_sftp`: `sshpass -e sftp -oBatchMode=no -b <batch> host` ; batch = `cd path; put -r $BACKUP_DIR/*` ; SSHPASS via env (never cmdline) | none | Add `SFTP_HOST/PORT/USER/PATH` env keys. |
| **ftp** | curl ✓ | new `push_ftp`: `curl --netrc-file <root-only 0600> -T file ftp://host/path/` ; creds from netrc, NOT URL/cmdline (avoids ps leak) | none | **Cleartext — UI MUST warn.** netrc written alongside the env file. |
| **smb** | smbclient ✗ | existing `push_smb` (remote_push.sh:76), `-U user%pass` (ps-visible, known W-2) | `apt-get install samba-client` in install.sh | Keep warn-only; document rsync-first. |
| **nfs** | cp ✓ (mount external) | existing `push_nfs` (remote_push.sh:104); no creds in script | none (mount is operator's job) | No change. |

## Key Findings (per area)

1. **Settings persistence** — `Setting` model (models/setting.py): PK `key`
   (String), `value` (JSON), `category`, `description`, `updated_at`. Routes in
   api/settings.py: GET `` (admin), GET `/public` (anon, allowlist of keys at
   settings.py:24-30 — backup key must NOT be in this list), GET/PUT `/{key}`,
   POST `/bulk`. Timezone cache pattern (services/timezone.py): Redis key
   `app:tz`, TTL 300s, **eager invalidation** via `invalidate_app_tz_cache()`
   called in both PUT and bulk (settings.py:147,187). **No setting value is
   encrypted today** — the settings table is plaintext JSON. The encrypted-field
   precedent lives in `cameras.py` (RTSP URL via `encrypt_string`), NOT in
   settings. **Gap:** no encryption hook in the settings write path; the new
   endpoint must encrypt before storing and decrypt on materialize/test, never
   via the generic settings routes.

2. **System router pattern** — system.py: `APIRouter(prefix="/system")`,
   `require_admin` dep (deps.py:107), `log_action` (audit.py:13) on success,
   subprocess with **argv list + `shell=False` + secret via env var only**
   (system.py:58-84). This is the exact template for the new backup-config
   endpoints. main.py:241 already includes `system.router` — **no registration
   change**. Integration point: add three handlers to system.py.

3. **remote_push.sh + backup.sh** — backup.sh sources only `.env` (line 38-43,
   `ENV_FILE=/opt/powerhouse-membership/.env`). remote_push.sh dispatches on
   `REMOTE_TYPE=BACKUP_REMOTE_TYPE` (line 32, 128). Adding `sftp`/`ftp` = two
   new functions + two `case` arms. Cleanest materialization: backend writes
   `/etc/faceapp/backup-remote.env` on save; backup.sh adds a second source
   block AFTER line 43 so DB config wins. **Warn-only contract untouched.**

4. **Settings.tsx** — 5 tabs (Settings.tsx:255-259): General(0), Access(1),
   Membership(2), System(3), Users(4). System tab (348-374) already holds the
   Export DB block + a `backupRemoteStatus` line (360). Two options: (a) new
   6th "Backup" tab pushing Users to index 5 (cleanest, matches "add a tab"
   request); (b) nest a Backup section inside System tab alongside Export.
   Transport `<Select>` pattern exists at 193-202 (timezone). Admin-gating is
   `user?.role === 'admin'` (350). Recommend **(a) dedicated tab** but move the
   Export DB button into it for cohesion.

5. **i18n** — `settings:` block es:318-368 / en:762-812. Already has
   `exportDb`, `exportDbHelp`, `backupRemoteStatus`. Add: `backup` (tab label),
   `backupTransport`, `backupHost`, `backupPort`, `backupUser`, `backupPassword`,
   `backupPasswordHelp` (write-only explainer), `backupPath`, `backupTest`,
   `backupTesting`, `backupTestOk`, `backupTestFail`, `backupFtpWarn`
   (cleartext warning), `backupSaved`. Both languages, neutral register.

6. **Tool availability** — verified on this host: `curl` ✓, `sshpass` ✓,
   `sftp` ✓, `rsync` ✓, `ssh` ✓, **`smbclient` ✗ NOT INSTALLED**.
   install.sh currently installs **no transport tools** (grep: no matches).
   → install.sh must add `samba-client` (and optionally `cifs-utils`). FTP/SFTP
   need nothing. This is a real install-gap independent of this change.

7. **Test-connection endpoint** — feasible. `POST /system/backup-config/test`:
   decrypt in-memory, build env, `subprocess.run(["timeout","20","bash",
   "remote_push.sh"], env=..., cwd=tmp_probe_dir)` with a 1-byte probe file,
   capture returncode + last log line, return sanitized `{ok, message}`. Admin-
   only + audited. Never echo the password or the raw remote banner. Must be
   excluded from the public settings allowlist. Reuses system.py's argv-list +
   env-only-secret discipline.

8. **Docs / .env.example** — `.env.example` has **NO backup keys** (grep
   returned no matches), contradicting archive-report.md:29. Under the new
   DB-managed model, `.env.example` should document only the fallback
   `BACKUP_REMOTE_TYPE=none` and the pointer that runtime config lives in the
   admin UI / `/etc/faceapp/backup-remote.env`. `docs/` has only
   `deployed-build-diagnosis.md` (unrelated). README backup section (if any)
   must be updated to point at the UI. **Flag the discrepancy for proposal.**

## Size Estimate & Slice Recommendation

Budget 800 lines. Estimated surface: backend ~250, scripts ~80, frontend ~300,
i18n ~60, install/docs ~30, tests ~120, spec/tasks ~50 → **~890 lines**.

**Recommend 3 slices** (security-sensitive → protect review focus, enables
chained-pr skill):

- **Slice 1 — Security core (backend + spec + scripts).** system.py endpoints,
  encrypt_string wiring, `/etc/faceapp/backup-remote.env` materializer,
  remote_push.sh sftp+ftp, backup.sh source-order, spec MODIFY of
  "Environment-Only Remote Credentials", backend tests. ~380 lines. **Must land
  first** — it defines the contract the UI consumes.
- **Slice 2 — Frontend UI + i18n.** Backup tab, transport select, write-only
  password field, test button, FTP cleartext warning, es+en strings. ~360 lines.
- **Slice 3 — Install + docs + hardening tests.** install.sh `samba-client`,
  `.env.example` cleanup + discrepancy fix, README pointer, frontend component
  test, log-grep regression test extension. ~150 lines.

## Ready for Proposal

**Yes.** Proposal should: (a) declare the **MODIFY** of "Environment-Only Remote
Credentials" with the encrypted-at-rest + materialize-on-save wording; (b) scope
to Approach 1 (single JSON setting); (c) commit to the 3-slice plan; (d) flag the
`.env.example` discrepancy and the `smbclient` install gap as in-scope fixes.
One open question for the user: **should the Export DB button move into the new
Backup tab, or stay in System?** (Recommend: move it — cohesive.)
