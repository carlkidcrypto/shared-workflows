# carlkidcrypto DevTools (Agent Plugin)

Cross-IDE **Agent Plugins 1.0** bundle packaging `carlkidcrypto` ecosystem skills for both **Antigravity** and **VS Code (GitHub Copilot)**.

## Included Skills

- `ci-cd-workflow-optimization` (includes `scripts/check_open_prs.py`, `scripts/gh_pr_mail.py`, `scripts/rerun_cancelled_jobs.py`, `scripts/lint_ci.sh`)
- `release-management` (includes `scripts/wt_preflight.sh`)
- `sonarqube-quality-remediation` (includes `scripts/sonar_triage.py`)
- `gemini-spark-blog` (includes `scripts/sync_drive_post.py`, `scripts/validate_blog_code.py`, `scripts/rebase_stack.py`)

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
