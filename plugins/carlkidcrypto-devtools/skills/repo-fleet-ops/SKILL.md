---
name: repo-fleet-ops
description: >-
  Fleet-wide repository operations across carlkidcrypto repositories: cross-repo open PR/CI/Codecov/review-mail
  audits, worktree-isolated PR main merge-ups, shared-workflows 40-char SHA propagation, README.rst strict +
  badge SVG validation, and GitHub Release notes auditing/backfill.
---

# Repo Fleet Operations

Standardized, non-destructive scripts for multi-repository maintenance across the `carlkidcrypto` ecosystem (`shared-workflows`, `ezsnmp`, `ezsnmp_data_logger`, `purpleair_api`, `purpleair_data_logger`, `purpleair-matterbridge`, `carlkidcrypto.github.io`, `os-specific-runner`).

## Safety Invariants

- **Never merge PRs** (`gh pr merge` is strictly reserved for `@carlkidcrypto`).
- **Never mutate primary clones** (`<workspace_root>/<repo>` stays clean on `main`).
- **Isolate all edits in worktrees** (`<workspace_root>/wt-<repo>-<task>`), and prune worktrees when finished.
- **No personal paths** in committed files or scripts (use `$HOME`, `<workspace_root>`, or CLI flags).
- **Windows / WSL2 Workspace Root Override**: On Windows 11 + WSL2 (`Ubuntu-24.04`), set `WORKSPACE_ROOT=$HOME/Github` (or pass `--root`) when running fleet scripts whose default workspace path targets macOS `~/Documents/GitHub`.

---

## Quick Fleet CI & Maintenance One-Liners

Prefer these bundled CLI one-liners over ad-hoc inline Python scripts (all scripts resolve `gh` robustly even when `/opt/homebrew/bin` or `/usr/local/bin` is not in `PATH`):

```bash
# Fleet-wide open PRs (behind_by, mergeable, pass/fail/pend/skip + failed checks) & recent PyPI/TestPyPI/NuGet/npm/release runs
python3 ../ci-cd-workflow-optimization/scripts/check_open_prs.py --release-runs
python3 ../ci-cd-workflow-optimization/scripts/check_open_prs.py --release-runs --json

# Bulk PR merge-up via GitHub API (preview first, then apply)
python3 ../ci-cd-workflow-optimization/scripts/merge_up_prs.py --all-repos --dry-run
python3 ../ci-cd-workflow-optimization/scripts/merge_up_prs.py --all-repos

# Rerun infra-cancelled (runner_id == 0) GitHub Actions jobs on a PR or run ID
python3 ../ci-cd-workflow-optimization/scripts/rerun_cancelled_jobs.py --repo carlkidcrypto/<repo> --pr <num> --infra-only --dry-run
python3 ../ci-cd-workflow-optimization/scripts/rerun_cancelled_jobs.py --repo carlkidcrypto/<repo> --pr <num> --infra-only

# Fleet PR + Codecov + unanswered review-mail audit & worktree-isolated git merge-up
python3 scripts/audit_open_prs.py
python3 scripts/sync_prs_with_main.py --dry-run
```

---

## Bundled Scripts

All scripts live in `scripts/` relative to this skill directory and support `--help` and `--json`.

### 1. Audit Open PRs, CI, Codecov & Review Mail

```bash
python3 scripts/audit_open_prs.py
python3 scripts/audit_open_prs.py --repo ezsnmp --failing-only
```

Queries `gh pr list`, `gh pr checks`, issue comments, and pull review comments across ecosystem repos:
- Reports base/head branches, `mergeable` state, and CI `pass`/`fail`/`pending` counts.
- Detects Codecov check/comment presence.
- Counts unanswered review-mail root comments (comments with no `in_reply_to_id` reply).

### 2. Worktree-Isolated PR Sync with `origin/main`

```bash
python3 scripts/sync_prs_with_main.py --dry-run
python3 scripts/sync_prs_with_main.py --repo ezsnmp --pr 1475
```

For each open `-> main` PR whose `origin/<head>` is behind `origin/main`:
- Creates a detached worktree at `<workspace_root>/wt-<repo>-sync-<pr>`.
- Runs `git merge --no-edit origin/main` and pushes `HEAD:<headRefName>` (unless `--no-push` or `--dry-run`).
- Aborts and reports conflicting files cleanly on merge conflict, then removes and prunes the worktree.

### 3. Bump `carlkidcrypto/shared-workflows` 40-Char SHA

```bash
python3 scripts/bump_shared_workflows_sha.py --dry-run
python3 scripts/bump_shared_workflows_sha.py --repo ezsnmp --apply --commit
```

- Resolves the 40-character SHA of `carlkidcrypto/shared-workflows` via `git rev-parse` (or `gh api` fallback).
- Scans `.github/workflows/*.yml`, `.github/actions/*/action.yml`, and `.github/workflows/*.md` for `carlkidcrypto/shared-workflows...@<sha>`.
- With `--apply`, creates `<workspace_root>/wt-<repo>-bump-sha` from `origin/main`, updates pins in place, and optionally commits (`--commit`).

### 4. Validate `README.rst` & Badge SVG Health

```bash
python3 scripts/validate_readme_rst.py /path/to/README.rst
```

- Runs `rst2html --strict` on `README.rst` to catch reStructuredText syntax/link errors.
- Fetches every `.. image::` / `.. figure::` URL and verifies HTTP `200` with no `not found`, `missing`, or `invalid` SVG error text.

### 5. Audit & Backfill GitHub Release Notes

```bash
python3 scripts/audit_release_notes.py --repo ezsnmp
python3 scripts/audit_release_notes.py --repo os-specific-runner --tag v2.2.0 --apply
```

- Audits releases via `gh api .../releases` for missing `auto_release_notes` sections (`Compared to:` / `**Full Changelog**:`, `## ` headers, or `(pypi.org/redacted)` links).
- Runs in dry-run mode by default; pass `--apply` to backfill missing notes via `gh release edit`.
- **Prefer Per-Repo Deterministic Generator**: For repositories that ship `.github/scripts/generate_release_notes.py` (`ezsnmp`, `ezsnmp_data_logger`, `purpleair_api`, `purpleair_data_logger`, `os-specific-runner`), always generate and publish release notes using `python3 .github/scripts/generate_release_notes.py --tag <tag> --publish` (or `--backfill --publish`) from a detached worktree on `origin/main` rather than hand-authoring release bodies, then verify conformance with `audit_release_notes.py --repo <repo>`.

### 6. Close `gh-aw` Copilot HTTP 429 Rate-Limit Issues

```bash
python3 scripts/close_aw_rate_limit_issues.py
python3 scripts/close_aw_rate_limit_issues.py --repo ezsnmp --verify-logs
python3 scripts/close_aw_rate_limit_issues.py --verify-logs --apply
```

- Scans open issues across `--repo` (or all `DEFAULT_REPOS` when `--repo` is omitted) for genuine `gh-aw` Copilot HTTP 429 rate-limit / credit-exhaustion failure issues (`app/github-actions` / `github-actions[bot]` or `agentic-workflows` label, title `hit engine rate limit (HTTP 429)` or body `engine_rate_limit_429` + `engine: copilot` + `gh-aw-failure-issue: true`), explicitly excluding `[aw] Detection Runs`, `[aw] No-Op Runs`, and `activation failed`.
- Runs in dry-run mode by default; pass `--apply` to post the explanatory comment and close each matched issue as `"not planned"`.
- Pass `--verify-logs` to extract the Actions `run_id` from each issue body and verify `gh run view <id> --log-failed` contains `ai_credits_rate_limit_error`, `errorCodes=[429]`, or `errorTypes=["rate_limit"]` before closing.

### 7. Retarget Stacked PRs (Auto-Unstack Stale GitHub PR Stacks)

```bash
python3 scripts/retarget_stacked_pr.py --repo carlkidcrypto/ezsnmp --pr 1530 --base main --dry-run
python3 scripts/retarget_stacked_pr.py --repo carlkidcrypto/ezsnmp --pr 1530 --base main
```

- Queries `GET /repos/{owner}/{repo}/pulls/{pr}` to detect whether GitHub still associates the PR with a stack (`.stack.number`), which causes `gh pr edit --base` to fail with `Cannot change the base branch because the pull request is part of a stack`.
- When a stack is attached, calls `POST /repos/{owner}/{repo}/stacks/{stack_number}/unstack` first and then retargets the PR via `gh pr edit --base <branch>`.
- Supports `--dry-run` and `--json`.

### 8. Inspect PR CI Checks & Rerun Failed Runs

```bash
python3 scripts/inspect_pr_ci.py --repo carlkidcrypto/ezsnmp --pr 1530
python3 scripts/inspect_pr_ci.py --repo carlkidcrypto/ezsnmp --pr 1530 --rerun-failed
```

- Summarizes `statusCheckRollup` counts (`pass`, `fail`, `pending`, `skipped`), lists every non-passing check with its workflow name, `run_id`, and `job_id`, and avoids ad-hoc `gh pr view --json statusCheckRollup` Python one-liners.
- Pass `--rerun-failed` (optionally with `--dry-run`) to trigger `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs` for every unique failed Actions run on the PR.

---

## Cross-Repo Configuration Synchronization (`multi-repo-sync`)

When propagating standardized templates or configs across the fleet (using `ezsnmp` as the reference repository):

### Standard Configuration Items
- **GitHub Issue & PR Templates**: `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md` (respect repo-specific naming such as lowercase `pull_request_template.md` in `purpleair_api`).
- **CI & Agentic Workflows**: `.github/workflows/*.yml` and `.github/workflows/*.md` (always explicitly whitelist `api.github.com` instead of `agy` and recompile with `gh aw compile`).
- **Dependabot**: `.github/dependabot.yml`.
- **SonarQube Cloud Exclusions**: Root `.sonarcloud.properties` on `main` with `sonar.exclusions=docs/**` and `sonar.cpd.exclusions=docs/**` (`_build/**,docs/**` for `carlkidcrypto.github.io`).
- **Release Tools**: `release_tools/bump_version.sh` (`release.sh`).

### Sync Steps
1. Fetch latest `origin/main` across target repos and create isolated sibling worktrees (`wt-<repo>-sync-<topic>` on branch `chore/sync-<topic>` or `feature/sync-<topic>`).
2. Adapt runtime/platform specifics per repo (Python vs Node.js/TypeScript vs C++/SWIG).
3. Commit with conventional messages (e.g. `chore(github): sync <item> with ezsnmp conventions`), push, and open PRs via `gh pr create --base main`. **Never merge PRs.**

---

## Quick Fleet Git Status & Test Dispatch

Run a quick clean/branch audit across all ecosystem clones (adjust `WORKSPACE_ROOT` as needed):

```bash
python3 -c "
import os, subprocess
root = os.environ.get('WORKSPACE_ROOT', os.path.expanduser('~/Github'))
repos = ['shared-workflows', 'ezsnmp', 'ezsnmp_data_logger', 'purpleair_api', 'purpleair_data_logger', 'os-specific-runner', 'purpleair-matterbridge', 'carlkidcrypto.github.io']
for r in repos:
    p = os.path.join(root, r)
    if not os.path.isdir(p):
        continue
    status = subprocess.check_output(['git', 'status', '-s'], cwd=p).decode().strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=p).decode().strip()
    print(f'[{r}] ({branch}): {status if status else \"Clean\"}')
"
```

Common per-repo test entry points (run inside a sibling worktree):
- **Python (`ezsnmp`, `purpleair_api`, `purpleair_data_logger`)**: `pytest` (or `cd tests && python3 -m unittest`)
- **Node / TypeScript (`purpleair-matterbridge`, `os-specific-runner`)**: `npm test`
- **Blog / Docs (`carlkidcrypto.github.io`)**: `.venv/bin/sphinx-build -b html source _build/html -W`
