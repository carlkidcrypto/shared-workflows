# carlkidcrypto DevTools (Agent Plugin)

Cross-IDE **Agent Plugins 1.0** bundle packaging `carlkidcrypto` ecosystem skills for both **Antigravity** and **VS Code (GitHub Copilot)**.

## Included Skills

- `ci-cd-workflow-optimization`
- `release-management`
- `sonarqube-quality-remediation`
- `gemini-spark-blog`
- `repo-fleet-ops`
- `local-validation-and-dev`

## Helper Scripts

- `skills/ci-cd-workflow-optimization/scripts/check_open_prs.py` — Scans open PRs, mergeability, base/head topology, and CI pass/fail/pending summaries across `carlkidcrypto` repositories.
- `skills/ci-cd-workflow-optimization/scripts/watch_pr_ci.py` — Polls and summarizes `gh pr checks` status for a PR (handling pending exit code 8 cleanly) with optional `--wait`, failed-run log inspection, and `rerun-failed-jobs` eligibility checks.
- `skills/ci-cd-workflow-optimization/scripts/gh_pr_mail.py` — Performs 2-pass PR review/MAIL comment discovery, posts formatted `in_reply_to` replies (`Addressed in commit \`<sha>\`: <summary>`), and checks for unpushed commits.
- `skills/ci-cd-workflow-optimization/scripts/rerun_cancelled_jobs.py` — Reruns cancelled/failed jobs (especially `runner_id == 0` infra cancellations) via `gh api`.
- `skills/ci-cd-workflow-optimization/scripts/lint_ci.sh` — Pre-PR check verifying `HEAD != main`, `.github/scripts/` placement, `yamllint`, `actionlint`, and `black --check`.
- `skills/local-validation-and-dev/scripts/env_preflight.sh` — Probes and exports local toolchain environment variables (Framework Python 3.13, Homebrew `net-snmp` / `openssl@3`, `PKG_CONFIG_PATH`, `DYLD_LIBRARY_PATH`).
- `skills/local-validation-and-dev/scripts/validate_local.py` — Auto-detects repo capabilities and runs local Python, C++, Sphinx/Doxygen docs, and workflow syntax validation with artifact cleanup.
- `skills/release-management/scripts/wt_preflight.sh` — Safe Git worktree lifecycle helper (`check`, `create`, `prune`, cloud-sync ref diagnostics).
- `skills/release-management/scripts/update_local_desktop.sh` — Non-editably installs desktop apps into Framework Python 3.13, cleans build artifacts, and runs import/CLI smoke tests.
- `skills/sonarqube-quality-remediation/scripts/sonar_triage.py` — SonarCloud Quality Gate, issue, hotspot, and coverage/duplication CLI.
- `skills/gemini-spark-blog/scripts/` — Blog workflow helpers (`sync_drive_post.py`, `validate_blog_code.py`, `rebase_stack.py`).

## Usage

### Antigravity
Installed at `~/.gemini/config/plugins/carlkidcrypto-devtools/`.

### VS Code (GitHub Copilot)
Add the local plugin path to VS Code `settings.json`:

```json
{
  "chat.plugins.paths": [
    "<workspace_root>/shared-workflows/plugins/carlkidcrypto-devtools"
  ]
}
```
