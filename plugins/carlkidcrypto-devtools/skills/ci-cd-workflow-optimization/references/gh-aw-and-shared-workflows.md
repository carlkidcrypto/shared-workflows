# GitHub Agentic Workflows (gh-aw) & Shared Workflows DRY Standards

## 17. GitHub Agentic Workflows (`gh-aw`) & Syntax Validation Standards

Repositories utilizing GitHub Agentic Workflows (`gh-aw`) author markdown workflow files (`.github/workflows/*.md`) and compile them to `.lock.yml` and `agentics-maintenance.yml`:

### 1. Compilation Protocol (`gh-aw` v1.2.2)
- Execute `gh aw compile` in the repository root using `gh-aw` **`v1.2.2`**.
- Verify 0 errors and 0 warnings.
- The compiler outputs:
  - `actions-lock.json` in `.github/aw/`
  - `.github/workflows/agentics-maintenance.yml`
  - `.github/workflows/<workflow>.lock.yml`

### 2. Syntax Validation (`verify_syntax.yml`) Gating
- `actionlint` and `yamllint` do not natively recognize `gh-aw` schema extensions such as `copilot-requests: write`, `concurrency: queue: max`, and `job.workflow_ref`.
- Always exclude generated lock files and maintenance files from both path triggers and linter executions:
  ```yaml
  on:
    push:
      branches: [main]
      paths:
        - '.github/workflows/*.yml'
        - '!.github/workflows/*.lock.yml'
        - '!.github/workflows/agentics-maintenance.yml'
    pull_request:
      branches: [main]
      paths:
        - '.github/workflows/*.yml'
        - '!.github/workflows/*.lock.yml'
        - '!.github/workflows/agentics-maintenance.yml'
  ```
  ```bash
  find .github/workflows/ -name "*.yml" ! -name "*.lock.yml" ! -name "agentics-maintenance.yml" -print0 | xargs -0 yamllint -c .yamllint
  find .github/workflows/ -name "*.yml" ! -name "*.lock.yml" ! -name "agentics-maintenance.yml" -print0 | xargs -0 actionlint -shellcheck=
  ```
- **Tool Installation Resilience (`actionlint`)**: When downloading `actionlint` or external linter binaries via `curl`, always pass retry flags `--retry 5 --retry-delay 2 --retry-all-errors` (e.g. `curl -fsSL --retry 5 --retry-delay 2 --retry-all-errors "https://github.com/rhysd/actionlint/releases/download/${version}/${archive}" -o /tmp/actionlint.tar.gz`) to prevent transient GitHub release asset download failures (HTTP 502/503/504 Gateway Timeouts) from failing PR preflight syntax checks.

### 3. Sibling Ecosystem Parity
- Sibling repositories maintain synchronized, tailored custom agents (`.github/agents/*.md`), skills (`.github/skills/*/SKILL.md`), and canonical agentic workflow filenames (`.github/workflows/*.md`):
  - Canonical Agentic Workflows: `auto_release_notes.md`, `coverage_autofix_python.md`, `coverage_autofix_cpp.md`, `docs_continuous_improvement.md`, `python_version_watcher.md`, `sync_open_prs_with_main.md`, `triage_incoming_bug_reports.md` (keep workflow filenames generic—avoid cadence suffixes like `every_3_days`).
  - Standard Deterministic Changelog Workflow: `auto_change_log.yml` (replaces agentic `auto_change_log.md`/`.lock.yml`), paired with standardized `.chglog/config.yml` (`git-chglog v0.15.4`, no `filters.Type`, `header.pattern` supporting `(scope)`, `!`, `Bump`, `Release`, `[tag]`, emoji) and `.chglog/CHANGELOG.tpl.md` (`{{-`/`-}}` trimming).
  - Agents: `agentic-workflows`, `the_flow_manager`, `the_snake_tester`, `the_ninja_tester`, `the_squasher`, `the_scribe`.
  - Skills: `agentic-workflows`, `release-management`, `python-testing`, `cpp-testing`, `cpp-swig-development`, `desktop-distribution`, `sphinx-docs`, `pull-request-guide`.

---

---

### 23. Keep `.yml` Files Focused — Extract Non-Trivial Scripts

Keep `.github/workflows/*.yml` and `actions/*/action.yml` concise and declarative; do not embed large multi-line bash/PowerShell/Python scripts inline:

- **Composite Actions (`actions/<name>/action.yml`)**: Place non-trivial logic in `actions/<name>/scripts/<script>.(ps1|sh|py)` and invoke it via `${{ github.action_path }}/scripts/<script>` with explicit named parameters or environment variables (e.g. `prepare_windows_netsnmp.ps1` with `-NetSnmpVersion`, `-NetSnmpSha256`, `-Arch`).
- **Repository Workflows (`.github/workflows/*.yml`)**: Place non-trivial logic in `.github/scripts/` (or a shared package/action) so script code can evolve, be linted, and be unit-tested independently of YAML orchestration.

---

### 24. DRY Principle (`carlkidcrypto/shared-workflows`)

Follow the **DRY (Don't Repeat Yourself)** principle across `carlkidcrypto` repositories:

- Centralize shared reusable workflows (`reusable_verify_syntax.yml`, `reusable_python_black.yml`, `reusable_sphinx_build.yml`, `reusable_auto_changelog.yml`), composite actions (`actions/prepare-windows-netsnmp`, `actions/setup-git-chglog`, `actions/setup-actionlint`), and `gh-aw` shared fragments (`shared/codecov-coverage.md`) in **`carlkidcrypto/shared-workflows`**.
- Consumer repositories should reference `carlkidcrypto/shared-workflows/...@<commit_sha>` instead of duplicating workflow/action bodies locally.
- **Full 40-Char SHA Verification**: Never hand-type or use shortened 7-char commit SHAs in `uses: ...@<sha>`. Always obtain the exact 40-character SHA programmatically (`git rev-parse <ref>` or `gh api repos/<owner>/<repo>/commits/<ref> --jq '.sha'`) and verify it resolves (`git cat-file -t` / `gh api`) before committing.
- **Never Downgrade Dependabot Action Pins**: Always inspect `origin/main:.github/workflows/` before editing workflows, use targeted edits (`edit_file`) instead of overwriting whole files, and preserve the latest Dependabot-updated SHAs (never paste older SHAs from memory or templates).
- **`gh-aw` Lockfile Conflict Resolution**: When rebasing or merging `main` creates conflicts in `gh-aw`-generated files (`.github/aw/actions-lock.json`, `*.lock.yml`), accept `origin/main` for the generated files and re-run `gh aw compile` instead of hand-merging lockfiles.
- Whenever skills or `carlkidcrypto-devtools` plugin files are edited locally, always sync the changes into `carlkidcrypto/shared-workflows` (`plugins/carlkidcrypto-devtools/`) via a PR so the repository stays synchronized.
