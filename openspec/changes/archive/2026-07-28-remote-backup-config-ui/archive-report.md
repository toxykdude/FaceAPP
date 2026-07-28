# Archive Report: remote-backup-config-ui

**Change**: `remote-backup-config-ui`
**Archived**: 2026-07-28
**Archive mode**: `hybrid` (per `openspec/config.yaml`)
**Verdict**: PASS WITH WARNINGS — SDD cycle complete. 11/11 requirements met (1 formally MODIFIED), 0 critical findings, full automated suite green.

> **Final-state authority**: This report reflects the FINAL state of the change at close,
> per the SDD archive hierarchy. The orchestrator's authoritative launch facts (rank 3)
> outrank the intermediate `verify-report` and `apply-progress` snapshots (rank 4). No
> snapshot claim is echoed here as a current fact unless corroborated by the final state.
> The single WARNING (W1) and the documented gate-repair history are recorded below.

## status

`PASS WITH WARNINGS` — **SDD cycle complete; archived.**

## Engram Traceability

| Artifact | Topic key | Observation |
|----------|-----------|-------------|
| Apply progress (cumulative S1+S2+S3) | `sdd/remote-backup-config-ui/apply-progress` | **#96** |
| S1 contract-validation flag | `sdd/remote-backup-config-ui/contract-validation` | **#97** |
| Verify report (independent) | `sdd/remote-backup-config-ui/verify-report` | **#100** |
| Archive report | `sdd/remote-backup-config-ui/archive-report` | (this document, persisted at close) |

On-disk artifacts (this folder): `proposal.md`, `design.md`, `exploration.md`, `tasks.md`, `verify-report.md`, `specs/{backup-remote-config,remote-backup}/spec.md`.

## executive_summary

The `remote-backup-config-ui` change delivered an admin-only **Backup** tab that lets non-CLI
operators configure, persist, and test every supported remote-backup transport (`none`,
`rsync`, `sftp`, `ftp`, `smb`, `nfs`) without server access or manual `.env` edits — and moved
**Export Database** out of the System tab into it. All 11 spec requirements are met with
concrete runtime + source evidence: masked reads never emit ciphertext, write-only keep-sentinel
works on both omit and empty-string, env materialization is atomic with full-rewrite stale-key
removal, the connection probe uses an argv list with `shell=False` and sandboxes `BACKUP_DIR`,
the `smbclient` pre-flight runs **before** the password-bearing `-U` argv is built (D9), SFTP/FTP
secrets travel env-only / 0600-netrc-only, and `backup.sh` sources the managed env file **after**
`.env`. One low-severity WARNING (W1): the Managed Environment Override scenario is verified by
deterministic POSIX sourcing-order source inspection only — no dedicated runtime test exercises
both env files with differing values. It does not risk correctness and does not block archival.

The documented **FTP_PATH deviation** is internally consistent and is **not a spec violation**:
`backup_config.py` materializes `FTP_HOST/PORT/USER/PASS` only, `remote_push.sh` uploads to
`ftp://${host}:${port}/<file>` (no path), and `.env.example` documents exactly those four keys.

**Recommendation at close: archived.** Delta specs synced; change folder relocated.

## artifacts

- **Branches (chain, all LOCAL ONLY — NO push)**:
  - tracker `feat/remote-backup-config-ui` (`c8bc6d2` tracker base; artifacts at `e4c8bb2`)
  - `feat/remote-backup-config-ui-slice-s1` (tip `5dfde78`) — backend + scripts + spec tests
  - `feat/remote-backup-config-ui-slice-s2` (tip `20c62f2`) — frontend Backup tab + i18n + API client
  - `feat/remote-backup-config-ui-slice-s3` (tip `501ebf9`) — install deps + `.env.example` + README
- **Base**: `main` (`c8bc6d2`)
- **Verify report**: `openspec/changes/archive/2026-07-28-remote-backup-config-ui/verify-report.md`
- **Engram mirrors**: #96 (apply-progress), #100 (verify-report)
- **Specs verified**: `specs/backup-remote-config/spec.md` (5 requirements), `specs/remote-backup/spec.md` (1 MODIFIED + 5 ADDED = 6 requirements; **11 total**)
- **Design**: `design.md` (D1–D10 all honored — no design deviations)
- **Tasks**: `tasks.md` — **18/18 implementation tasks `[x]`**; 5 `[ ]` are the explicitly-deferred "Manual Verification" real-iron section (acceptable; several are auto-covered by isolation + frontend tests)

## Delivered vs Proposed Scope

### Capability `backup-remote-config` (5 requirements — all NEW)

| # | Requirement | Delivered as | Slice | Status |
|---|-------------|--------------|-------|--------|
| 1 | Protected Masked Configuration | `_mask()` (`backup_config.py`) emits only `{type,host,port,share,path,username,has_password}`; `/settings/public` uses fixed allowlist `[app_name,theme_mode,business_name,business_logo,timezone]` so `backup_remote` excluded by construction; `Depends(require_admin)` on all 3 handlers | S1 | ✅ Met |
| 2 | Validated Write-Only Persistence | `apply_update`: omit OR `""` keeps existing; non-empty → `encrypt_string` (AES-256-GCM); `validate()` runs before `_persist`/`materialize_env` so invalid → 400 changes nothing; audit details `{type,host}` only | S1 | ✅ Met |
| 3 | Secure Environment Materialization | `materialize_env`: `tempfile.mkstemp`+`os.fsync`+`os.chmod(0o600)`+best-effort `chown root:root`+`os.replace`; `_env_lines` is a full rewrite (D6) emitting only current transport keys; no file content logged | S1 | ✅ Met |
| 4 | Bounded Sanitized Connection Test | `run_probe`: 1-byte `b"x"`; argv `["timeout","20","bash",REMOTE_PUSH_SH]` via `subprocess.run(capture_output=True)` (`shell=False`); tempdir sandbox; `_sanitize_message` scrubs host/user/share/path/password tokens + regex + ≤200 chars; probe leaves local artifacts untouched | S1 | ✅ Met |
| 5 | Admin Backup User Interface | 6th `<Tab>` (CloudUploadIcon) admin-gated; Export DB moved from System → Backup; `SettingsBackupTab.tsx` 6-option Select + conditional fields + write-only placeholder + FTP-only cleartext Alert; full ES/EN i18n (19 keys es+en) | S2 | ✅ Met |

### Capability `remote-backup` (1 MODIFIED + 5 ADDED = 6 requirements)

| # | Requirement | Delivered as | Slice | Status |
|---|-------------|--------------|-------|--------|
| 6 | Environment-Only Remote Credentials **(MODIFIED)** | `backup.sh:39-57` sources `.env` then `/etc/faceapp/backup-remote.env`; `_decrypt_or_empty` decrypts only into the 0600 root:root env file; `.env.example` documents runtime-only / not-in-source-control | S1 | ✅ Met |
| 7 | SFTP Replication (ADDED) | `remote_push.sh push_sftp`: `sshpass -e sftp -P "$port" "${user}@${host}" -b "$batch"`; `SSHPASS` env-only; secret never on argv/batch/log | S1 | ✅ Met |
| 8 | FTP Replication (ADDED) | `remote_push.sh push_ftp`: `mktemp`+`chmod 600` netrc + `curl --netrc-file`; URL `ftp://${host}:${port}/<file>` has **no userinfo**; netrc `rm -f`'d after; cleartext risk documented in `.env.example` + README | S1 | ✅ Met |
| 9 | Managed Environment Override (ADDED) | `backup.sh:39-44` sources `.env`; `backup.sh:52-57` conditionally sources `/etc/faceapp/backup-remote.env` **after** `.env`. **Source-evidence only (W1)** — see Warnings. | S1 | ✅ Met (source-evidence) |
| 10 | Fresh-Install SMB Dependency (ADDED) | `install.sh:50` adds `samba-client sshpass`; `remote_push.sh:95-98` `command -v smbclient` pre-flight runs **before** the `-U user%pass` argv at `:103`; on absence logs literal `samba-client` hint + `return 1` | S1 + S3 | ✅ Met |
| 11 | Remote Secret Log Isolation (ADDED) | Every transport's failure path exercised by isolation suite with unique tokens (`SMB-SECRET-TOKEN`, `SSHP-SECRET-TOKEN`, `FTPP-SECRET-TOKEN`), each asserted absent from log + stdout + stderr + tool argv marker; success-path logs are hardcoded literals (no credential interpolation) | S1 | ✅ Met |

## Branch state at archive

Feature-branch chain (all **LOCAL ONLY — NO push**, per orchestrator/user decision):

| Branch | Tip | Contents |
|--------|-----|----------|
| `feat/remote-backup-config-ui` | `c8bc6d2` (tracker base) | tracker / chain root; artifacts committed `e4c8bb2` |
| `feat/remote-backup-config-ui-slice-s1` | `5dfde78` | backend `backup_config` service, 3 system.py handlers, `remote_push.sh` sftp/ftp + D9 smbclient preflight, `backup.sh` second env source, 3 test files |
| `feat/remote-backup-config-ui-slice-s2` | `20c62f2` | 6th Backup tab, Export DB moved, `SettingsBackupTab.tsx`, `settings.ts` API methods, ES/EN i18n |
| `feat/remote-backup-config-ui-slice-s3` | `501ebf9` | `install.sh` samba-client+sshpass, `.env.example` authoritative block, README Backups section |

The **archive filesystem move (delta-spec sync + folder relocation) is an uncommitted change on
`feat/remote-backup-config-ui-slice-s3`** (same precedent as `admin-data-tools`). Decide where to
commit it (slice-s3, a `chore/` branch, or the tracker) before pushing — see Outstanding.

## Final Evidence (independent verifier-run)

> Authoritative final counts — carried from the independent `verify-report` (#100), which re-ran
> the full suite itself. All commands executed on `feat/remote-backup-config-ui-slice-s3` (`501ebf9`),
> clean working tree.

### Backend (`backend/`)
| Gate | Result |
|------|--------|
| `pytest tests/ -q` | **140 / 140 pass**, 124 warnings, 4.87s — exit 0 |
| `mypy .` | **Success: no issues found in 94 source files** — exit 0 |
| `black --check .` | All done — 102 files unchanged — exit 0 |
| `flake8 .` | clean — exit 0 |

New/extended backend test files green within the 140: `test_backup_config_api.py`,
`test_backup_config_test_endpoint.py`, `test_remote_backup_isolation.py` (incl.
`TestSmbMissingSmbclient`, `TestRemotePasswordsNeverLogged[sftp|ftp]`,
`TestFailedRemoteNeverRemovesLocalArtifacts[smb|sftp|ftp|rsync|nfs]`).

### Frontend (`frontend/`)
| Gate | Result |
|------|--------|
| `npm run test` (vitest run) | **Test Files 12 · Tests 49 / 49 pass**, 35.80s — exit 0 |
| `npm run type-check` (`tsc --noEmit`) | clean — exit 0 |
| `npm run lint` (`eslint . --max-warnings 0`) | clean — exit 0 |

New frontend test file green within the 49: `SettingsBackupTab.test.tsx` (7 tests).

### Shell scripts (`/root/faceapp/`)
| Gate | Result |
|------|--------|
| `bash -n install.sh scripts/backup.sh scripts/remote_push.sh` | all OK — exit 0 |

### Output hashes (test summary lines, sha256)
- Backend pytest summary: `14b757ab14c8c65c21002d56f150f5b79c0896c859a0865e851b055bf6037c20`
- Frontend vitest summary: `9306ef018caa7adf0f1e5355fd469bea6dc03f7c0e348c25af71a37ac793c455`

### Compliance totals
- Requirements compliant: **11 / 11**
- Critical findings: **0**

## Gate history (recorded for the audit trail)

This change exercised the SDD phase-contract gate; its history is worth recording:

- **S1 — first apply FAILED the fresh-context phase-contract gate** (#97). Two gaps: (a) the
  progress record lacked explicit `status` / `skill_resolution` / `next_recommended` contract
  fields and said "Ready for verify or S2"; (b) task S1.8 declared full `mypy .` but the supplied
  evidence named only targeted mypy files. Functional S1 scope and coverage were coherent — it was
  a contract/evidence-completeness failure, not a code defect.
- **S1 — contract-only repair** added commit **`5dfde78`** to slice-s1: ran the declared full
  `mypy .` (**94 files, 0 errors**) and added the `_stored` return-type annotation. No functional
  change to behavior. Re-run **PASSED**.
- **S2 — gate PASSED first time** (#96, cumulative). (The #96 note records a minor
  evidence-arithmetic slip that was self-disclosed; not a gate failure.)
- **S3 — gate PASSED** (#96 cumulative). install/docs-only slice; no test runner required,
  S1/S2 green evidence carried forward correctly.
- **Verify (#100) — PASS WITH WARNINGS**, recommend archive. Independently re-ran every gate.
- **Attempt ledger**: complete.

## Warnings (accepted, non-blocking)

- **W1 — Managed-override scenario backed by source inspection, not runtime test** (req. 9). The
  "managed and fallback values differ → managed wins" scenario has no dedicated runtime test.
  Compliance is proven by deterministic POSIX shell sourcing order (`backup.sh:39-57`), which
  cannot be implemented incorrectly as two `source` statements in order. Low risk; does not block
  archival. *Optional fix (pre- or post-archive):* add a test writing `.env` with
  `BACKUP_REMOTE_TYPE=rsync` + a managed `/etc/faceapp/backup-remote.env` with
  `BACKUP_REMOTE_TYPE=sftp`, run `backup.sh` in the mocked tree, assert the sftp branch is invoked.

## Suggestions (documented, non-blocking)

- **S1 — `tasks.md` "Manual Verification" section has 5 unchecked `[ ]`.** Of these, `bash -n`
  (all 3 scripts pass — verifier confirmed), the missing-tool path (covered by
  `test_smb_missing_smbclient_warns_samba_client` + `test_failed_push_preserves_local_artifacts`),
  and the FTP/SFTP Alert toggle (covered by `SettingsBackupTab.test.tsx`) are already auto-covered.
  Only the genuinely real-iron items (fresh-LXC `install.sh` run, live UI Test against a real host)
  remain unexercised. Consider annotating which manual lines are auto-covered vs. real-iron.
- **S2 — FTP transport conditional-fields not explicitly asserted** in the frontend test (ftp shares
  sftp's field shape; its cleartext Alert is separately tested). Trivial gap; an explicit ftp-field
  assertion would close it.
- **S3 — FTP_PATH deviation is benign and not a spec deviation.** Documented here and in verify-report.
  No action unless a future change wants FTP subdirectory upload support.

## Deviations from design

1. **FTP_PATH not materialized** (S3). Orchestrator flagged `FTP_PATH` as a doc key, but
   `backup_config.py:274-278` materializes `FTP_HOST/PORT/USER/PASS` only and
   `remote_push.sh:194` uploads to `ftp://host:port/<file>` (no path). `.env.example` was written to
   document the keys the code actually uses, keeping it an accurate authoritative reference.
   **Assessed consistent — no spec violation** (the FTP spec requires curl + 0600 netrc + no creds
   in URL + cleartext documentation; none of which requires `FTP_PATH`).

No design-decision deviations detected. D1–D10 all honored.

## Gates passed before archive

- **Task Completion Gate**: 18 / 18 implementation tasks `[x]` (S1.1–S1.8, S2.1–S2.6, S3.1–S3.4).
  No stale unchecked implementation tasks. The 5 `[ ]` are the explicitly-deferred "Manual
  Verification — shell transports / tool availability" real-iron section (acceptable per SDD verify
  graceful-handling convention; several are auto-covered — see S1 suggestion).
- **Critical Findings Gate**: 0 critical findings in `verify-report.md`.
- **Strict-vs-OpenSpec Archive Policy**: no CRITICAL issues; the single WARNING (W1) is accepted
  and recorded.
- **Action Context Guard**: no `workspace-planning` constraint; archive operations stayed inside
  `openspec/`.
- **Native Review Receipt Gate**: not applicable for this change — no native review
  (`review/{transaction,ledger,receipt,gate-context}`) was created for `remote-backup-config-ui`;
  the project's SDD workflow for this change did not exercise the native review pipeline
  (same precedent as `admin-data-tools`). The orchestrator's authoritative launch facts
  ("Attempt ledger: complete", "all implementation and verification COMPLETE",
  "verify-report PASS WITH WARNINGS → archive") stand as the terminal delivery receipt.

## Specs synced to source of truth

| Domain | Action | Details |
|--------|--------|---------|
| `backup-remote-config` | Created `openspec/specs/backup-remote-config/spec.md` | 5 requirements (delta was a full spec — copied verbatim) |
| `remote-backup` | Updated `openspec/specs/remote-backup/spec.md` | 1 MODIFIED (Environment-Only Remote Credentials — replaced, `(Previously: …)` note preserved as historical context) + 5 ADDED (SFTP/FTP Replication, Managed Environment Override, Fresh-Install SMB Dependency, Remote Secret Log Isolation); the 2 pre-existing untouched requirements (Scheduled Remote Replication, Local Backup and Retention Preservation) preserved verbatim. Main spec now carries 8 requirements. |

`openspec/specs/` tree now holds 6 domain specs (was 5): `admin-database-export`,
`backup-remote-config` (NEW), `membership-history`, `remote-backup` (UPDATED), `sales-reporting`,
plus the pre-existing set. Delta `## MODIFIED Requirements` / `## ADDED Requirements` wrappers were
normalized to the single `## Requirements` heading of the main spec; requirement blocks and
scenarios are verbatim from the deltas.

## next_recommended

**none** (SDD-cycle follow-ups only — see Outstanding). The change is fully planned, implemented,
independently verified, and archived. The remaining work is operational (push/PR decision + LXC
deploy), not SDD-scope.

## risks

- **W1 — managed-override runtime-test gap** (low severity, accepted). Deterministic shell sourcing
  makes this very low risk; a dedicated test would convert source evidence to runtime evidence. Does
  not block archival or merge.
- **Manual real-iron steps unexercised** (expected, explicitly deferred). Fresh-LXC `install.sh` +
  `command -v smbclient sshpass`, the live UI Test button against a real host, and the live Alert
  toggle remain real-iron. The isolation suite covers the missing-tool branches in a mocked tree;
  real-iron confirmation is still pending deploy.
- **Success-path secret isolation is structural, not separately tested.** The isolation tests mock
  `sshpass`/`curl`/`smbclient` to FAIL (proving no secret leaks on the failure path). Success-path
  logs are hardcoded literals with zero credential interpolation, so leakage is structurally
  impossible — but not separately exercised with a succeeding mock. Very low risk.
- **Branch chain unpushed — CI has not run.** No GitHub Actions validation on any commit in this
  chain. The first real CI run happens on the next push/PR (workflow fires on `main`).

## skill_resolution

- Loaded: `/root/.claude/skills/sdd-archive/SKILL.md` (executor path — no delegation)
- Loaded: `/root/faceapp/.atl/skill-registry.md` (no project-scoped archive skill; standard SDD
  archive applies — `skill_resolution: none` for project-specific skills)
- Archive mode: `hybrid` → filesystem spec-sync + folder move performed AND archive report mirrored
  to Engram (`sdd/remote-backup-config-ui/archive-report`).
- No matching project skill in the registry applied to this archive task.

## outstanding

1. **Push / PR decision — pending with user.** Four local-only branches (`feat/remote-backup-config-ui`
   tracker + `feat/remote-backup-config-ui-slice-{s1,s2,s3}`) have NOT been pushed. Per
   `tasks.md` forecast, the chain strategy is **feature-branch-chain**: PR S1 base = tracker,
   PR S2 base = S1, PR S3 base = S2, tracker → `main` last. CI has not run on any commit.
   The **archive filesystem move is currently an uncommitted change on slice-s3** — commit it
   somewhere coherent (slice-s3, a `chore/` branch, or the tracker) before pushing.
2. **Deploy to the dev LXC.** Two sub-cases:
   - **Code/UI**: rebuild + redeploy the frontend so the new Backup tab ships (per the
     `docs/deployed-build-diagnosis.md` procedure; the dev LXC serves from
     `/opt/powerhouse-membership/frontend/dist`). Backend changes need a `powerhouse-backend`
     restart.
   - **SMB/SFTP tooling on the CURRENT machine**: the LXC currently **lacks `smbclient`** (needed
     for `BACKUP_REMOTE_TYPE=smb`) and will lack `sshpass` (needed for sftp). Either (a) run the
     updated `install.sh` on the LXC (it now installs `samba-client sshpass`), or (b) manually
     `apt-get install samba-client sshpass`. Until then, SMB/SFTP transports degrade to the
     documented warn-only path with the literal `samba-client` install hint (local backup still
     succeeds). `rsync`/`nfs`/`ftp`(curl) are unaffected.
3. **Systemd backup timer — already in `main`.** The 30-minute `powerhouse-backup.{service,timer}`
   from the prior `admin-data-tools` change (req. "Scheduled Remote Replication") already ships in
   `main`; this change adds no new timer. The remote push it invokes now also honors the managed
   `/etc/faceapp/backup-remote.env` when present.
4. **Optional: close W1** with a dedicated managed-override runtime test (see Warnings).
5. **Optional: annotate the `tasks.md` Manual Verification section** to mark which lines are
   auto-covered vs. genuinely real-iron (see S1 suggestion) — purely a clarity hygiene item.

## Pre-existing issues (out of scope, surfaced during this work)

- **Backend pytest requires exporting `backend/.env`.** `conftest.py` lacks dotenv loading;
  `pytest tests/` from the backend dir fails on missing env unless
  `set -a && . ./.env && set +a` is run first. Documented in the verify-report; pre-existing
  (carried from `admin-data-tools`), not introduced by this change.
- **SMB password visibility in the process list (inherent).** `remote_push.sh push_smb` uses
  `smbclient -U "${user}%${pass}"`, visible via `ps` to other users. Inherent to smbclient's `-U`
  syntax; D9 guarantees the password-bearing argv is never built when `smbclient` is missing. No
  secret reaches the log. Design recommends rsync/sftp-first; SMB is fallback. Non-blocking.

## SDD Cycle

Complete. Change has been planned (`proposal`, `exploration`, `spec`), broken down (`tasks`),
implemented (`apply-progress` #96, with S1 contract-repair `5dfde78`), independently verified
(`verify-report` #100 + on-disk `verify-report.md`), and archived (this document). Ready for the
next change.
