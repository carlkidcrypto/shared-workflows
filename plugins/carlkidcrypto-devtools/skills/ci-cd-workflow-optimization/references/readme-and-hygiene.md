# README Standards, Public-Repo Hygiene & Quota Fallbacks

This guide covers `README.rst` badge and syntax conventions, public-repository PII/path hygiene, and fallback procedures when Copilot or `gh-aw` quotas are exhausted.

---

## 1. `README.rst` & `style=flat-square` 4-Row Badge Standard

- **Format & Validation**: Ecosystem READMEs use reStructuredText (`README.rst`), validated strictly with `rst2html --strict` (zero warnings or errors) and HTTP-200 badge/image checks (no `not found`, `missing`, or `invalid` SVG responses).
- **4-Row Badge Grouping (`style=flat-square`)**: Organize badges into 4 logical rows using `style=flat-square`:
  1. **Row 1 — Build / Tests / Docs**: GitHub Actions workflow status badges (CI, multi-OS tests, Sphinx/ReadTheDocs documentation).
  2. **Row 2 — Quality & Security**: Codecov coverage, SonarCloud Quality Gate / Maintainability / Security, and CodeQL status.
  3. **Row 3 — Registries**: Published package registry version badges (PyPI, npm, NuGet, Docker/GHCR, Homebrew, WinGet).
  4. **Row 4 — Registry-Tied Downloads**: Download count badges tied directly to package registries (e.g., PyPI downloads, npm downloads, NuGet downloads). **Drop `img.shields.io/github/downloads/...` badges** where package downloads are tracked via registries.

---

## 2. Public-Repo PII & Personal-Path Hygiene

> [!CAUTION]
> **Never commit personal home directory paths, usernames, or PII into public repositories, skills, memory files, or `shared-workflows`.**

- **Use Generic Placeholders**:
  - Use `<workspace_root>` for the parent GitHub checkout directory.
  - Use `<path/to/home>` or `$HOME` for user home directories.
  - Use `<repo>` for repository names when writing generic examples.
- **Pre-Commit Hygiene Gate**: Before committing changes to `plugins/` or any public repository, verify zero personal home paths exist:
  ```bash
  grep -rnE "(/home/[a-zA-Z0-9._-]+|/U[s]ers/)" plugins/
  ```
  (Must return **0 matches**.)

---

## 3. Copilot / `gh-aw` Quota-Exhaustion Fallback

When GitHub Copilot or `gh-aw` agentic workflows hit monthly quota or rate limits:

1. **Release Notes Backfill (`auto_release_notes`)**:
   - Instead of waiting on `auto_release_notes.md`, audit historical or recent GitHub Releases against the repo's `.github/workflows/auto_release_notes.md` template and backfill non-conforming releases manually using `gh release edit <tag> --notes-file <file>`.
2. **PR Review & Main-Sync (`sync_open_prs_with_main`)**:
   - Perform cross-repo PR status audits, `origin/main` merge-ups in isolated worktrees (`<workspace_root>/wt-<repo>-sync-<pr>`), CI/Codecov checks, and Copilot/reviewer thread replies (`gh api repos/{owner}/{repo}/pulls/{pull_number}/comments -F in_reply_to=...`) directly via local scripts or an agent swarm.
   - Never use `gh pr merge`; leave merging and release publishing to the maintainer (`@carlkidcrypto`).
