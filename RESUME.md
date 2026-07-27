# RESUME.md — How to pick up where we left off

> An agent reads this when resuming work after a gap. Concrete and actionable;
> no philosophy. For state, see [STATUS.md](./STATUS.md).

## Last session summary

On **2026-07-27** we merged **PR #3** (`b476944`, branch
`chore/add-ci-openspec-artifacts`, commit `60152b5`). It added the missing
GitHub Actions CI workflow at `.github/workflows/ci.yml`, GitHub PR/issue
templates, the OpenSpec artifact trail under `openspec/`, and `.gitignore`
hardening (covers `gh.env`, `.atl/`, etc.). The CI pipeline now exists in
`main` and will trigger on the next push or PR — it has not run on real code
yet. No code changes were made; this was a chore/infra PR.

## Immediate next actions

1. **Watch the first CI run.** Open or push the next PR to `main` and verify
   all three jobs (backend, frontend, cv_service) go green. If flake8/mypy/black
   fail on pre-existing code, fix forward.
2. **Rotate the `gh.env` PAT** (see Open threads). One-time hygiene task.
3. **Reconcile `feature/tracker`** against `main`: `git log main..feature/tracker
   --oneline`. If the only remaining commits are already merged via PR #1,
   delete the branch.
4. **Update STATUS.md** after any of the above lands — keep the snapshot honest.
5. If starting new feature work, open an SDD change in `openspec/changes/`
   before writing code (see [SKILL.md SDD workflow](./SKILL.md#sdd-workflow)).

## Open threads

- **`/root/faceapp/gh.env` fine-grained PAT** — required for `git push` because
  the default OAuth token lacks `workflow` scope. Discussed in chat; should be
  rotated. To use: `source gh.env && gh auth setup-git` (or pass `GH_TOKEN`
  inline). It is gitignored — never commit.
- **CI has not been triggered yet.** First real run = the next PR. Historical
  PRs #1/#2 have no GitHub Actions evidence; only local TDD logs.
- **OpenSpec `membership-report-kiosk-tunnel` Phases 4–5** are unchecked
  (portal security + tunnel deployment). Explicitly out of scope for the last
  session; resume when the portal work is prioritized. Start point: task 4.1
  in
  [`openspec/changes/membership-report-kiosk-tunnel/tasks.md`](./openspec/changes/membership-report-kiosk-tunnel/tasks.md).
- **`WOMPI_INTEGRITY_SECRET`** is referenced in code but must be provisioned
  from the Wompi dashboard before production payments go live.
- **Unmerged local branches** `feature/tracker` and
  `feature/pr2-membership-expiration-access` need reconciliation or deletion.

## Key artifacts to read first

Ordered reading list for a fresh agent:

1. [README.md](./README.md) — features, architecture diagram, API reference
2. [AGENTS.md](./AGENTS.md) — repo layout, run commands, traps, conventions
3. [STATUS.md](./STATUS.md) — current HEAD, branches, open work
4. [SECURITY.md](./SECURITY.md) — security contract (skim §1, §2, §4, §6 before
   touching auth/biometrics/payments)
5. [SKILL.md](./SKILL.md) — domain primer, kiosk state machine, memorable bugs
6. [openspec/changes/membership-report-kiosk-tunnel/proposal.md](./openspec/changes/membership-report-kiosk-tunnel/proposal.md)
   — active SDD change intent and scope

## Key commands

```bash
# --- Tests (per service) ---
docker-compose up -d db redis              # backend tests need Postgres + Redis
cd backend && pytest tests/                # backend suite
cd backend && python init_db.py            # (re)initialize test DB
cd frontend && npm run test                # vitest run (CI-equivalent)
cd cv_service && pytest tests/

# --- Lint / type-check (CI mirrors) ---
cd backend && flake8 . && black --check . && mypy .
cd frontend && npm run lint && npm run type-check

# --- Dev servers ---
cd backend && uvicorn main:app --reload --port 8000
cd frontend && npm run dev
cd cv_service && uvicorn main:app --port 8001

# --- Git push (requires gh.env PAT) ---
source gh.env && gh auth setup-git
git push origin main
gh pr create --title "<type>: <subject>" --body-file <file>

# --- SDD / CodeGraph ---
codegraph status                            # check local code index
git log main..feature/tracker --oneline     # reconcile tracker branch
```

## Contact points / decision log

- **Engram memory**: `mem_search query="faceapp"` (or `query="facegym"`) for
  past decisions, bug fixes, and session summaries across sessions.
- **SDD changes**: [`openspec/changes/`](./openspec/changes/) — each change has
  `proposal.md`, `design.md`, `tasks.md` recording the decision trail.
- **Security decisions**: [SECURITY.md](./SECURITY.md) is the authoritative
  security contract; updates there are the security decision log.
- **Commit history**: `git log --oneline` — Conventional Commits, 71 commits on
  main, 3 PRs merged (`#1`, `#2`, `#3`).

## Rollback / safety

**Roll back the last merge (PR #3):**
```bash
git revert -m 1 b476944                     # revert the merge commit, keeps history
git push origin main
```
PR #3 added only CI/templates/spec artifacts — no production code, so reverting
is low-risk. If you only want to disable CI temporarily instead:
```bash
git rm .github/workflows/ci.yml             # in a new branch + PR
```

**Roll back PR #2 (kiosk fixes) or PR #1 (features)** — higher risk; these
touched production code. Use `git revert -m 1 <merge-sha>` and re-run the full
test suite locally before pushing. Do NOT revert individual commits from inside
a merge — revert the merge commit with `-m 1`.

**Disable a misbehaving service in prod** (from
[SECURITY.md §9](./SECURITY.md)):
```bash
systemctl stop powerhouse-cv                # or powerhouse-backend
```

**Disable the Cloudflare Tunnel** (if portal is misbehaving): stop `cloudflared`
on the host; the tunnel allowlist is the portal's public boundary.
