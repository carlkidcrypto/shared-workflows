---
name: ci-cd-workflow-optimization
description: >-
  Guidelines and best practices for creating, optimizing, and maintaining GitHub Actions
  CI/CD workflows across carlkidcrypto repositories (ezsnmp, purpleair_api, ezsnmp_data_logger, etc.).
  Covers smart file-change detection (tj-actions/changed-files), cross-platform step consolidation
  (carlkidcrypto/os-specific-runner), multi-OS matrix builds, wheel packaging (cibuildwheel/delvewheel),
  GitHub Pages doc deployments (.nojekyll), Dependabot multi-ecosystem setup, SonarQube Cloud quality gates,
  and software requirements synchronization.
---

# CI/CD Workflow Optimization & Standards Guide

This skill documents standard architectures, reusable patterns, and quality gates for authoring and optimizing GitHub Actions CI/CD workflows across the `carlkidcrypto` ecosystem (`ezsnmp`, `purpleair_api`, `ezsnmp_data_logger`, `purpleair_data_logger`, `purpleair-matterbridge`, `os-specific-runner`, etc.).

---

## ⚠️ Critical Rule: Maintainer Merge & Publish Boundaries

> [!CAUTION]
> **NEVER merge pull requests, create git release tags, or trigger automated package publishing.**
> - Merging PRs into `main` or release branches is strictly reserved for the maintainer (`@carlkidcrypto`).
> - Publishing GitHub releases, creating git tags (`vYYYY.M.D`), or running deployment workflows (PyPI, npm, NuGet) must never be executed or merged by the agent.
> - The agent prepares branches, updates configurations, verifies checks, opens PRs, and reports status.

---

## Multi-Agent Concurrency & Git Worktree Isolation

> [!IMPORTANT]
> **Always isolate local workflow updates and branch testing using Git Worktrees.**
> Multiple agents (the human maintainer, background workflows, Dependabot, Copilot, and other agentic assistants) operate simultaneously on the host machine. Checking out branches or running dirty builds in `<workspace_root>/<repo>` breaks other agents' working states.
>
> **Mandatory Worktree Workflow**:
> 1. **Check Active Worktrees**: Run `git worktree list` first to discover existing active worktrees, their directory paths, and active branches before switching or adding, preventing branch collisions (`fatal: '<branch>' is already used by worktree at ...`).
> 2. **Keep Primary Checkout Clean**: The primary checkout `<workspace_root>/<repo>` must remain clean on `main` at all times. Never switch branches or leave unstaged/staged dirty files in the primary repository checkout root.
> 3. **Spawn Dedicated Worktree in Sibling Directory**: Place dedicated worktrees in sibling directories (e.g. `<workspace_root>/<repo>-<task-name>` or `<workspace_root>/wt-<repo>-<task-name>`). Never create worktrees in `/tmp` or `~/.gemini/` unless explicitly requested.
>    ```bash
>    # Fetch latest remote references first:
>    git fetch origin
>
>    # For a new feature/fix branch from origin/main:
>    git worktree add -b <branch-name> <workspace_root>/wt-<repo>-<task-name> origin/main
>    cd <workspace_root>/wt-<repo>-<task-name>
>
>    # Or for checking out an existing branch:
>    git worktree add <workspace_root>/wt-<repo>-<task-name> <branch-name>
>    cd <workspace_root>/wt-<repo>-<task-name>
>    ```
> 4. **Execute Everything Inside Worktree**: Run all workflow edits, syntax validation (`actionlint`, `yamllint`), builds, tests, local formatters (`black`, `prettier`, `csharpier`), targeted staging (`git add <files>`), and `gh pr create` strictly inside `<workspace_root>/wt-<repo>-<task-name>`.
> 5. **Handle Upstream & Remote Syncs**: Sibling background agentic workflows (like `sync_open_prs_with_main`) frequently merge `main` into open PR branches while working. If a push is rejected, run `git pull --rebase origin <branch-name>` inside the worktree before retrying.
> 6. **Handle Maintainer-Merged PR Follow-ups**: If an open PR has already been merged into `main` by the maintainer while follow-up commits are prepared, do not force-push over merged commits. Fetch `origin`, branch cleanly from `origin/main` (`git checkout -b <fix-branch> origin/main`), cherry-pick the required commit (`git cherry-pick <sha>`), and submit a new PR cleanly.
> 7. **Clean Pruning**: Never overwrite or delete other agents' active worktrees. Prune your worktree once the PR is merged or closed:
>    ```bash
>    git worktree remove <workspace_root>/wt-<repo>-<task-name>
>    git worktree prune
>    ```
>    Verify `git worktree list` confirms the worktree was cleanly detached without dangling metadata.

---

---

## Core DRY & Pinning Rules

- **DRY Principle (`carlkidcrypto/shared-workflows`)**: Centralize reusable workflows (`reusable_verify_syntax.yml`, `reusable_python_black.yml`, `reusable_clang_format.yml`, `reusable_sphinx_build.yml`, `reusable_auto_changelog.yml`, `reusable_tests_cpp_native.yml`, `reusable_pypi_publish.yml`, `reusable_npm_publish.yml`, `reusable_nuget_publish.yml`, `reusable_winget_publish.yml`), composite actions (`actions/check-source-changes`, `actions/prepare-windows-netsnmp`, `actions/setup-actionlint`, `actions/setup-copilot-gh-aw`, `actions/setup-git-chglog`, `actions/upload-codecov`), and `gh-aw` shared fragments (`shared/codecov-coverage.md`) in `carlkidcrypto/shared-workflows` and pin via immutable 40-char `@<sha>`.
- **Full 40-Char SHA Verification**: Resolve SHAs programmatically (`git rev-parse <ref>` or `gh api`) and verify resolution before committing—never hand-type or use shortened SHAs.
- **Never Downgrade Dependabot Pins**: Inspect `origin/main:.github/workflows/` first and use targeted edits so Dependabot-bumped SHAs are preserved.
- **Keep `.yml` Focused**: Extract non-trivial scripts into `scripts/` next to `.yml` files.
- **Plugin Sync**: Whenever skills or `carlkidcrypto-devtools` files change locally, sync them to `carlkidcrypto/shared-workflows` (`plugins/carlkidcrypto-devtools/`) via PR.

---

## Reference Guides

Read only the specific reference file needed for the current task:

- [workflow-optimization-and-caching.md](references/workflow-optimization-and-caching.md) — Change detection (`changed-files`), `os-specific-runner`, Sphinx 3.14 & Pages, Dependabot, SonarCloud, requirements sync, wheel caching, `verify_syntax.yml`.
- [packaging-and-trusted-publishing.md](references/packaging-and-trusted-publishing.md) — `cibuildwheel`/`delvewheel`, npm & NuGet OIDC, C++17 ANSI, WinGet, `gh release upload`, desktop packaging, Homebrew 7.0.14+ local tap testing.
- [coverage-and-testing.md](references/coverage-and-testing.md) — Multi-language Codecov globs, modular test architecture & flakiness prevention, PR coverage comments, JS bundle analysis.
- [gh-aw-and-shared-workflows.md](references/gh-aw-and-shared-workflows.md) — `gh-aw v1.2.2` compilation/validation, script extraction, and `carlkidcrypto/shared-workflows` DRY standards.

---

## Bundled Scripts

- `scripts/check_open_prs.py` — Scans open PRs, mergeability, base/head topology, and CI pass/fail/pending summaries across all `carlkidcrypto` repositories (`--repo`, `--failing-only`, `--json`).
- `scripts/watch_pr_ci.py` — Monitors `gh pr checks` for a specific PR (`--pr <num> --repo <owner/repo> [--wait] [--interval 30] [--max-polls 20] [--json]`), handles pending exit code `8` cleanly, summarizes passed/pending/failed/skipped checks, and optionally fetches `--log-failed` or checks `rerun-failed-jobs` eligibility.
