# carlkidcrypto DevTools (Agent Plugin)

Cross-IDE **Agent Plugins 1.0** bundle packaging `carlkidcrypto` ecosystem skills for both **Antigravity** and **VS Code (GitHub Copilot)**.

## Included Skills

- `agentic-workflows` — GitHub Agentic Workflows (`gh-aw`) prompt routing, compilation, network allowlisting (`api.github.com`), AWF Squid proxy diagnostics, `skip-if-match`, `min-integrity: none`, `--allow-all-tools`, and inline skill protection.
- `aw-runs-triage` — Fleet-wide auditing and triage of `[aw] No-Op Runs` and `[aw] Detection Runs` issues (true no-ops vs. misconfigured workflows, and HTTP 429 detection failures vs. real detector/threat issues).
- `ci-cd-workflow-optimization` — GitHub Actions CI/CD patterns, smart change detection, multi-OS Meson/SWIG/Windows build standards, Codecov/Valgrind reporting, and OIDC Trusted Publishing.
- `release-management` — CalSemVer release bumps, `release_tools/`, worktree preflight, and desktop packaging.
- `sonarqube-quality-remediation` — SonarQube Cloud Automatic Analysis triage and remediation.
- `gemini-spark-blog` — End-to-end Google Drive / Gemini Spark blog ingestion, technical accuracy auditing, Sphinx/Furo builds, and stacked PR rebasing.
- `repo-fleet-ops` — Fleet-wide PR/CI/release audits, `shared-workflows` SHA propagation, cross-repo config synchronization, and workspace status/test dispatch.
- `local-validation-and-dev` — Local macOS/Linux/WSL2 toolchain preflight, worktree isolation, multi-language linting/testing, and consolidated repository personas (`The Scribe`).

## Helper Scripts

- `skills/ci-cd-workflow-optimization/scripts/check_open_prs.py` — Scans open PRs, mergeability, base/head topology, and CI pass/fail/pending summaries across `carlkidcrypto` repositories.
- `skills/ci-cd-workflow-optimization/scripts/watch_pr_ci.py` — Polls and summarizes `gh pr checks` status for a PR (handling pending exit code 8 cleanly) with optional `--wait`, failed-run log inspection, and `rerun-failed-jobs` eligibility checks.
- `skills/ci-cd-workflow-optimization/scripts/gh_pr_mail.py` — Performs 2-pass PR review/MAIL comment discovery, posts formatted `in_reply_to` replies (`Addressed in commit \`<sha>\`: <summary>`), and checks for unpushed commits.
- `skills/ci-cd-workflow-optimization/scripts/rerun_cancelled_jobs.py` — Reruns cancelled/failed jobs (especially `runner_id == 0` infra cancellations) via `gh api`.
- `skills/ci-cd-workflow-optimization/scripts/lint_ci.sh` — Pre-PR check verifying `HEAD != main`, `.github/scripts/` placement, `yamllint`, `actionlint`, and `black --check`.
- `skills/ci-cd-workflow-optimization/scripts/manage_dependabot.py` — Multi-ecosystem `.github/dependabot.yml` generator and validator (`github-actions`, `pip`, `npm`, `nuget`, `gomod`).
- `skills/local-validation-and-dev/scripts/env_preflight.sh` — Probes and exports local toolchain environment variables (Framework Python 3.13, Homebrew `net-snmp` / `openssl@3`, `PKG_CONFIG_PATH`, `DYLD_LIBRARY_PATH`).
- `skills/local-validation-and-dev/scripts/validate_local.py` — Auto-detects repo capabilities and runs local Python, C++, Sphinx/Doxygen docs, and workflow syntax validation with artifact cleanup.
- `skills/release-management/scripts/wt_preflight.sh` — Safe Git worktree lifecycle helper (`check`, `create`, `prune`, cloud-sync ref diagnostics).
- `skills/release-management/scripts/calsemver_release_helper.py` — Shared CalSemVer PEP 440 / SemVer 2.0.0 normalizer and Sphinx virtualenv (`python3.14.venv`, `python3.13.venv`, `.venv`) discovery helper.
- `skills/release-management/scripts/update_local_desktop.sh` — Non-editably installs desktop apps into Framework Python 3.13, cleans build artifacts, and runs import/CLI smoke tests.
- `skills/sonarqube-quality-remediation/scripts/sonar_triage.py` — SonarCloud Quality Gate, issue, hotspot, and coverage/duplication CLI.
- `skills/gemini-spark-blog/scripts/` — Blog workflow helpers (`sync_drive_post.py`, canonical 1887-line `validate_blog_code.py`, `rebase_stack.py`).
- `skills/repo-fleet-ops/scripts/close_aw_rate_limit_issues.py` — Scans and closes verified `gh-aw` Copilot HTTP 429 rate-limit failure issues across `carlkidcrypto` repositories.
- `skills/aw-runs-triage/scripts/audit_aw_tracking_issues.py` — Audits open `[aw] No-Op Runs` and `[aw] Detection Runs` tracking issues across `carlkidcrypto` repositories, classifies each workflow's latest run, and (with `--apply`) closes fully verified issues with an explanatory summary comment.
- `agents/the_scribe.md` & `skills/local-validation-and-dev/references/repo-skills-and-personas.md` — Canonical `The Scribe` documentation agent persona and consolidated `pull-request-guide`, `sphinx-docs`, `python-testing`, and `cpp-testing` standards.

## Usage

### Antigravity
Installed at `~/.gemini/config/plugins/carlkidcrypto-devtools/` (or `C:\Users\<user>\.gemini\config\plugins\carlkidcrypto-devtools\` on Windows).

### Windows 11 + WSL2 (`Ubuntu-24.04`) Support
- All Python helper scripts include cross-platform Windows/WSL2 path discovery (`WORKSPACE_ROOT` / `GOOGLE_DRIVE_BLOG_DIR` overrides with automatic `~/Github` and Windows/WSL2 Google Drive mount fallbacks, defaulting to `G:`).
- Run POSIX shell scripts (`env_preflight.sh`, `lint_ci.sh`, `wt_preflight.sh`, `update_local_desktop.sh`) and `validate_local.py` inside WSL2 (`Ubuntu-24.04`).
- Pass `--python <venv-python>` to `update_local_desktop.sh` when not on macOS Framework Python.
- Refresh the Windows global plugin mirror from WSL2 without copying bytecode caches:
  ```powershell
  robocopy "\\wsl.localhost\Ubuntu-24.04\home\<user>\Github\shared-workflows\plugins\carlkidcrypto-devtools" "$env:USERPROFILE\.gemini\config\plugins\carlkidcrypto-devtools" /MIR /XD __pycache__ .pytest_cache /XF *.pyc *.pyo
  ```

### VS Code (GitHub Copilot)
Add the local plugin path to VS Code `settings.json`:

```json
{
  "chat.plugins.paths": [
    "<workspace_root>/shared-workflows/plugins/carlkidcrypto-devtools"
  ]
}
```
