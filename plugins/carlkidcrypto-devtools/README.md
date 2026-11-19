# carlkidcrypto DevTools (Agent Plugin)

Cross-IDE **Agent Plugins 1.0** bundle packaging `carlkidcrypto` ecosystem skills for both **Antigravity** and **VS Code (GitHub Copilot)**.

## Included Skills

- `ci-cd-workflow-optimization`
- `release-management`
- `sonarqube-quality-remediation`
- `gemini-spark-blog`
- `local-validation-and-dev`

## Helper Scripts

- `skills/ci-cd-workflow-optimization/scripts/check_open_prs.py` — Scans open PRs, mergeability, base/head topology, and CI pass/fail/pending summaries across `carlkidcrypto` repositories.
- `skills/ci-cd-workflow-optimization/scripts/watch_pr_ci.py` — Polls and summarizes `gh pr checks` status for a PR (handling pending exit code 8 cleanly) with optional `--wait`, failed-run log inspection, and `rerun-failed-jobs` eligibility checks.
- `skills/local-validation-and-dev/scripts/env_preflight.sh` — Probes and exports local toolchain environment variables (Framework Python 3.13, Homebrew `net-snmp` / `openssl@3`, `PKG_CONFIG_PATH`, `DYLD_LIBRARY_PATH`).
- `skills/local-validation-and-dev/scripts/validate_local.py` — Auto-detects repo capabilities and runs local Python, C++, Sphinx/Doxygen docs, and workflow syntax validation with artifact cleanup.
- `skills/release-management/scripts/update_local_desktop.sh` — Non-editably installs desktop apps into Framework Python 3.13, cleans build artifacts, and runs import/CLI smoke tests.

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
