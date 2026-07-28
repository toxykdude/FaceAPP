# RESUME.md — How to pick up where we left off

> An agent reads this when resuming work after a gap. Concrete and actionable;
> no philosophy. For state, see [STATUS.md](./STATUS.md).

## Last session summary

Across **2026-07-27, 2026-07-28** we landed **PRs #3, #4, #5, #6** to take
FaceAPP from "no CI on GitHub" to "fully green 3-job pipeline", and then
**completed + archived two SDD changes locally** — `admin-data-tools` and
`remote-backup-config-ui`.

- **PR #3** (`b476944`) — Committed the missing CI workflow, GitHub templates,
  OpenSpec artifact trail, and hardened `.gitignore` to protect `gh.env`.
- **PR #4** (`7745610`) — Added project handoff docs (AGENTS/SKILL/STATUS/RESUME),
  baseline lint configs (`.flake8`, `mypy.ini`, `.eslintrc.cjs`), black
  reformat, and bumped lint tool versions to match local dev.
- **PR #5** (`1acf916`) — Fixed 8 hidden backend pytest failures surfaced by
  the new CI: missing `audit_logs` table, `HTTPBearer` returning 403 instead
  of 401 for missing auth, users endpoint missing pagination wrapper, test
  password mismatch, FastAPI/pydantic version drift, and missing
  `INTERNAL_API_SECRET` in CI env.
- **PR #6** (`6fcab85`) — `chore/refresh-status-resume`: docs refresh only.
- **`admin-data-tools` SDD cycle** — COMPLETE + ARCHIVED (local only, NOT
  pushed). 6 admin features (#1 DB export, #2 remote backup, #3 timezone,
  #4 custom-range diagnosis, #5 CSV export, #6 membership accordion)
  delivered as a 3-slice feature-branch chain. 12/12 requirements, 18/18
  scenarios, 0 critical findings. Delta specs synced into `openspec/specs/`
  (4 new domain specs); change folder moved to
  `openspec/changes/archive/2026-07-28-admin-data-tools/`. See the archive
  report there for the full terminal record.
- **`remote-backup-config-ui` SDD cycle** — COMPLETE + ARCHIVED (local only,
  NOT pushed). Admin **Backup** tab for secure remote-backup configuration
  (6 transports: none/rsync/sftp/ftp/smb/nfs), sanitized connection probe,
  and **Export Database** relocated from System. 11/11 requirements (1 formally
  MODIFIED — `remote-backup` "Environment-Only Remote Credentials" now permits
  DB-encrypted credentials), 0 critical findings, 1 accepted low WARNING
  (managed-override runtime-test gap). Delivered as a 3-slice feature-branch
  chain. Backend 140/140 pytest, frontend 49/49 vitest, mypy/black/flake8/
  tsc/eslint/`bash -n` all clean. Delta specs synced into `openspec/specs/`
  (NEW `backup-remote-config` + UPDATED `remote-backup`); change folder moved
  to `openspec/changes/archive/2026-07-28-remote-backup-config-ui/`. See its
  `archive-report.md` for the full terminal record (incl. the S1 contract-gate
  repair `5dfde78` and the accepted W1).

**Current state**: `main` is at `6fcab85` (88 commits, 6 PRs merged). CI runs
end-to-end green on `main`: backend (flake8/black/mypy/pytest 69/69), frontend
(lint/type-check/test 24/24), cv_service (pytest 12/12). Remote is clean —
only `refs/heads/main` exists. **Two archived-but-unpushed feature-branch
chains** are now local-only: `admin-data-tools` (tracker + slices a/b/c) and
`remote-backup-config-ui` (tracker + slices s1/s2/s3). Both await a push/PR
decision.

## Immediate next actions

1. **Decide the push/PR strategy for BOTH archived SDD chains.** Both cycles are
   complete and archived, but their feature-branch-chain branches are **LOCAL ONLY**
   and CI has run on neither:
   - **`remote-backup-config-ui`** (just archived) — tracker
     `feat/remote-backup-config-ui` + slices `feat/remote-backup-config-ui-slice-s{1,2,3}`
     (tips `5dfde78` / `20c62f2` / `501ebf9`). Chain: PR S1→tracker, S2→S1, S3→S2,
     tracker→`main` last. The archive move is an uncommitted change on slice-s3.
   - **`admin-data-tools`** — tracker `feature/admin-data-tools` + slices
     `feat/admin-data-tools-slice-{a,b,c}`. Options per `tasks.md`: 3 chained PRs
     (A→tracker, B and C onto A), squash to one, or push chain as-is. The archive
     move is an uncommitted change on slice-c.
   Commit each archive move somewhere coherent before pushing.
2. **Provide SMB/SFTP tooling on the dev LXC.** The current LXC lacks `smbclient`
   (SMB transport) and `sshpass` (SFTP). Either rerun the updated `install.sh`
   (now installs `samba-client sshpass`) or `apt-get install samba-client sshpass`.
   Until then SMB/SFTP degrade to the documented warn-only path with the literal
   `samba-client` hint; local backup still succeeds. `rsync`/`nfs`/`ftp` unaffected.
3. **Feature #4 — rebuild the LXC frontend** if the deployed instance still
   hides the custom-range flow. Code is correct in `main` (PR #1); symptom is
   a stale deployed build. Procedure: `docs/deployed-build-diagnosis.md`.
4. **Rotate the `gh.env` PAT** — its value was discussed in chat. Replace the
   file contents with a fresh fine-grained PAT. The file is gitignored.
5. **Adopt a dependency lockfile** — `uv lock` or `pip freeze > requirements.lock`.
   The silent venv-vs-requirements.txt drift caused most of the PR #4/#5 pain.
6. **If starting new feature work**, open an SDD change in `openspec/changes/`
   before writing code (see [SKILL.md SDD workflow](./SKILL.md)).
7. **Update STATUS.md** after any merge lands — keep the snapshot honest.
8. **Reconcile `feature/tracker`** against `main`:
   `git log main..feature/tracker --oneline`. Delete if all commits already
   landed via PR #1.

## Open threads

- **`remote-backup-config-ui` SDD change — ARCHIVED but UNPUSHED.** The full SDD
  cycle (admin Backup tab, 6 transports, sanitized probe, Export-DB relocation;
  11/11 requirements, 1 MODIFIED, 0 critical findings, 1 accepted low WARNING)
  is complete and archived at
  `openspec/changes/archive/2026-07-28-remote-backup-config-ui/`, with delta
  specs synced into `openspec/specs/` (NEW `backup-remote-config` + UPDATED
  `remote-backup`). Feature-branch chain (tracker + slices s1/s2/s3) is **LOCAL
  ONLY** — no CI run yet, no PR opened. The archive move is an uncommitted change
  on `feat/remote-backup-config-ui-slice-s3`. SMB/SFTP tooling still needed on
  the dev LXC (smbclient + sshpass). See the archive-report.md for the gate
  history (S1 contract-repair `5dfde78`) and accepted W1.
- **`admin-data-tools` SDD change — ARCHIVED but UNPUSHED.** The full SDD cycle
  (6 features, 12/12 requirements, 18/18 scenarios, 0 critical findings) is
  complete and archived at
  `openspec/changes/archive/2026-07-28-admin-data-tools/`, with delta specs
  synced into `openspec/specs/` (4 new domain specs). The feature-branch chain
  (`feature/admin-data-tools` + `feat/admin-data-tools-slice-{a,b,c}`) is
  **LOCAL ONLY** — no CI run yet, no PR opened. Push/PR strategy is the user's
  decision. The archive filesystem move is currently an uncommitted change on
  `feat/admin-data-tools-slice-c`. Feature #4 (custom-range) is reframed: code
  is correct; the user-facing "not visible" symptom is a stale LXC build —
  rebuild per `docs/deployed-build-diagnosis.md`.
- **`/root/faceapp/gh.env` fine-grained PAT** — required for `git push` because
  the default OAuth token lacks `workflow` scope. Discussed in chat → rotate.
  Push pattern that does not persist the token in remote URL config:
  ```bash
  TOKEN=$(grep '^github_pat_' gh.env)
  git push "https://x-access-token:${TOKEN}@github.com/toxykdude/FaceAPP.git" BRANCH:BRANCH
  ```
  For `gh` commands: `export GH_TOKEN=$(grep '^github_pat_' gh.env)`.
- **`requirements.txt` drift is a real recurring hazard.** Local `.venv` is
  the de facto source of truth; CI installs whatever `requirements.txt` pins.
  PR #4 bumped lint tools, PR #5 bumped core app deps to close the gap, but
  nothing prevents the next drift. Lockfile is the durable fix.
- **Dev DB masks CI bugs.** `backend/.env` sets `INTERNAL_API_SECRET`,
  `API_KEY`, `APP_ENV`, `ENVIRONMENT`, `DEBUG`. CI only sets the first one now
  (PR #5 `a468e73`). Local pytest is NOT a substitute for CI verification —
  always check what env vars CI provides before trusting local test results.
- **OpenSpec `membership-report-kiosk-tunnel` Phases 4–5** are unchecked
  (portal security + tunnel deployment). Explicitly out of scope for the last
  sessions; resume when portal work is prioritized. Start point: task 4.1 in
  [`openspec/changes/membership-report-kiosk-tunnel/tasks.md`](./openspec/changes/membership-report-kiosk-tunnel/tasks.md).
- **`WOMPI_INTEGRITY_SECRET`** is referenced in code but must be provisioned
  from the Wompi dashboard before production payments go live.
- **Optional tech-debt cleanup** (all documented as TODOs in their respective
  config files): re-enable 4 silenced ESLint rules after cleaning up
  `Kiosk.tsx:630` and 89 `any`/unused-vars warnings; migrate SQLAlchemy models
  to `Mapped[T]`/`mapped_column()` to drop mypy `disable_error_code` scopes;
  clean up the F401/E402/E722 flake8 categories.

## Key artifacts to read first

Ordered reading list for a fresh agent:

1. [README.md](./README.md) — features, architecture diagram, API reference
2. [AGENTS.md](./AGENTS.md) — repo layout, run commands, traps, conventions
3. [STATUS.md](./STATUS.md) — current HEAD, branches, open work
4. [SECURITY.md](./SECURITY.md) — security contract (skim §1, §2, §4, §6 before
   touching auth/biometrics/payments)
5. [SKILL.md](./SKILL.md) — domain primer, kiosk state machine, memorable bugs
6. [openspec/changes/membership-report-kiosk-tunnel/proposal.md](./openspec/changes/membership-report-kiosk-tunnel/proposal.md)
   — in-flight SDD change (Phases 4–5 outstanding: portal security + tunnel)
7. [openspec/changes/archive/2026-07-28-remote-backup-config-ui/archive-report.md](./openspec/changes/archive/2026-07-28-remote-backup-config-ui/archive-report.md)
   — terminal record of the just-archived `remote-backup-config-ui` cycle (unpushed)
8. [openspec/changes/archive/2026-07-28-admin-data-tools/archive-report.md](./openspec/changes/archive/2026-07-28-admin-data-tools/archive-report.md)
   — terminal record of the prior archived `admin-data-tools` cycle (unpushed)

## Key commands

```bash
# --- Tests (per service) ---
docker-compose up -d db redis              # backend tests need Postgres + Redis
cd backend && pytest tests/                # backend suite (69 tests)
cd backend && python init_db.py            # (re)initialize test DB
cd frontend && npm run test                # vitest run (24 tests)
cd cv_service && pytest tests/             # 12 tests

# --- Lint / type-check (CI mirrors) ---
cd backend && flake8 . && black --check . && mypy .
cd frontend && npm run lint && npm run type-check

# --- Dev servers ---
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev
cd cv_service && uvicorn main:app --port 8001

# --- Git push (requires gh.env PAT, see Open threads) ---
TOKEN=$(grep '^github_pat_' gh.env)
git push "https://x-access-token:${TOKEN}@github.com/toxykdude/FaceAPP.git" BRANCH:BRANCH
export GH_TOKEN=$(grep '^github_pat_' gh.env)
gh pr create --title "<type>: <subject>" --body-file <file>

# --- SDD / CodeGraph ---
codegraph status                            # check local code index
git log main..feature/tracker --oneline     # reconcile tracker branch
```

## Contact points / decision log

- **Engram memory**: `mem_search query="faceapp"` (or `query="facegym"`) for
  past decisions, bug fixes, and session summaries across sessions. Topic keys
  of note: `ci-pipeline/bootstrap`, `ci-pipeline/baseline-config`,
  `ci-pipeline/pr5-test-failures`, `ci-pipeline/local-verification`,
  `project/handoff-docs`.
- **SDD changes**: [`openspec/changes/`](./openspec/changes/) — each change has
  `proposal.md`, `design.md`, `tasks.md` recording the decision trail.
- **Security decisions**: [SECURITY.md](./SECURITY.md) is the authoritative
  security contract; updates there are the security decision log.
- **Commit history**: `git log --oneline` — Conventional Commits, 86 commits on
  main, 5 PRs merged (`#1`–`#5`).

## Rollback / safety

**Roll back the last merge (PR #5):**
```bash
git revert -m 1 1acf916                    # revert the merge commit, keeps history
git push origin main
```
PR #5 fixed 8 pytest failures and bumped core deps. Reverting re-introduces
the failures and reverts the dep bumps; expect CI to go red on the revert.
Prefer a forward-fix over a revert unless the dep bump caused a regression.

**Roll back PR #4** (`7745610`) — removed lint configs, docs, and black
reformat baseline. Reverting re-introduces 1216 flake8 violations and the
cross-version tool divergence. **Do not revert casually** — instead, fix
forward.

**Roll back PR #3** (`b476944`) — removed CI workflow and OpenSpec artifacts.
Low-risk revert (no production code touched) but disables CI entirely.

**Roll back PR #2 or PR #1** — higher risk; these touched production code
(kiosk + reports + admin UI). Use `git revert -m 1 <merge-sha>` and re-run the
full test suite locally before pushing. Do NOT revert individual commits from
inside a merge — revert the merge commit with `-m 1`.

**Disable CI temporarily** (without rolling back):
```bash
git rm .github/workflows/ci.yml             # in a new branch + PR
```

**Disable a misbehaving service in prod** (from
[SECURITY.md §9](./SECURITY.md)):
```bash
systemctl stop powerhouse-cv                # or powerhouse-backend
```

**Disable the Cloudflare Tunnel** (if portal is misbehaving): stop `cloudflared`
on the host; the tunnel allowlist is the portal's public boundary.
