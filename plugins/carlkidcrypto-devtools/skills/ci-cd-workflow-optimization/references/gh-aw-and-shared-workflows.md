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

- Centralize shared reusable workflows, composite actions, and `gh-aw` shared fragments (`shared/codecov-coverage.md`) in **`carlkidcrypto/shared-workflows`**.
- Consumer repositories should reference `carlkidcrypto/shared-workflows/...@<commit_sha>` instead of duplicating workflow/action bodies locally.
- **Full 40-Char SHA Verification**: Never hand-type or use shortened 7-char commit SHAs in `uses: ...@<sha>`. Always obtain the exact 40-character SHA programmatically (`git rev-parse <ref>` or `gh api repos/<owner>/<repo>/commits/<ref> --jq '.sha'`) and verify it resolves (`git cat-file -t` / `gh api`) before committing.
- **Never Downgrade Dependabot Action Pins**: Always inspect `origin/main:.github/workflows/` before editing workflows, use targeted edits (`edit_file`) instead of overwriting whole files, and preserve the latest Dependabot-updated SHAs (never paste older SHAs from memory or templates).
- **`gh-aw` Lockfile Conflict Resolution**: When rebasing or merging `main` creates conflicts in `gh-aw`-generated files (`.github/aw/actions-lock.json`, `*.lock.yml`), accept `origin/main` for the generated files and re-run `gh aw compile` instead of hand-merging lockfiles.
- Whenever skills or `carlkidcrypto-devtools` plugin files are edited locally, always sync the changes into `carlkidcrypto/shared-workflows` (`plugins/carlkidcrypto-devtools/`) via a PR so the repository stays synchronized.

#### Reusable Workflows (`.github/workflows/reusable_*.yml`)

1. **`reusable_verify_syntax.yml`**: `yamllint` + `actionlint` validation (excludes `*.lock.yml`, `*.lock.yaml`, and `agentics-maintenance.yml` by default) with optional `gh aw compile --validate`.
   - Inputs: `python-version` (`'3.14'`), `yamllint-version` (`'1.38.0'`), `actionlint-version` (`'v1.7.12'`), `exclude-lock-yml` (`true`), `run-shellcheck` (`true`), `run-gh-aw` (`false`), `gh-aw-version` (`'v0.89.21'`).
2. **`reusable_python_black.yml`**: `black --check --diff` formatting check with optional automated fix PRs (`auto-fix-pr`) and PR failure comments (`comment-on-failure`).
   - Inputs: `python-version` (`'3.14'`), `black-version` (`'26.5.1'`), `target-paths` (`'.'`), `auto-fix-pr` (`false`), `comment-on-failure` (`false`).
3. **`reusable_clang_format.yml`**: `clang-format` C/C++ formatting check (`--dry-run --Werror`) with optional automated fix PRs (`auto-fix-pr`).
   - Inputs: `target-dirs` (`'.'`), `file-extensions` (`'cpp h hpp c'`), `clang-format-version` (`'20'`), `exclude-files` (`''`), `auto-fix-pr` (`false`).
4. **`reusable_sphinx_build.yml`**: Python 3.14 Sphinx HTML build with pip caching, optional Doxygen, versioned docs (`html_v<version>`), landing page build, blog audit script, `.nojekyll`, and GitHub Pages deployment.
   - Inputs: `python-version` (`'3.14'`), `docs-dir` (`'sphinx_docs_build'`), `requirements-file` (`'sphinx_docs_build/requirements.txt'`), `output-dir` (`'docs'`), `run-doxygen` (`false`), `doxygen-config` (`'.doxygen'`), `versioned-docs` (`false`), `landing-dir` (`''`), `extra-requirements-file` (`''`), `blog-audit-script` (`''`), `deploy-pages` (`false`), `pre-build-cmd` (`''`).
5. **`reusable_auto_changelog.yml`**: Deterministic `git-chglog` changelog updater and PR creator.
   - Inputs: `git-chglog-version` (`'0.15.4'`), `tag` (`''`), `base-branch` (`'main'`), `pr-branch` (`'automation/update-changelog'`).
6. **`reusable_tests_cpp_native.yml`**: Multi-OS (`ubuntu-latest`, `macos-latest`) C++ native build and test runner supporting `meson` or `cmake`, optional Net-SNMP/OpenSSL installation, optional `snmpd` daemon startup, and Codecov coverage/JUnit test result upload.
   - Inputs: `matrix-json` (`'["ubuntu-latest", "macos-latest"]'`), `build-system` (`'meson'`), `build-dir` (`'build'`), `source-dir` (`'.'`), `install-netsnmp` (`true`), `start-snmpd` (`false`), `pre-build-cmd` (`''`), `test-command` (`''`), `upload-codecov` (`true`), `codecov-flags` (`'cpp-native'`), `coverage-files` (`'./build/meson-logs/coverage.xml,./coverage.xml'`), `junit-files` (`'./build/meson-logs/testlog.junit.xml'`).
   - Secrets: `codecov-token` (optional).
7. **`reusable_pypi_publish.yml`**: Builds `cibuildwheel` wheels and/or `pure-python` sdist/wheel distributions and publishes to PyPI or TestPyPI via pure OIDC Trusted Publishing (`id-token: write`, `pypa/gh-action-pypi-publish`).
   - Inputs: `target` (`'testpypi'`), `environment-name` (`''`), `build-mode` (`'cibuildwheel'`), `package-subdir` (`'.'`), `matrix-json`, `use-local-wheel-action` (`false`), `cibuildwheel-version` (`'2.22.0'`), `python-version` (`'3.11'`), `run-verify-syntax` (`true`), `check-changes` (`false`), `changed-files-patterns` (`''`), `third-party-repo` (`''`), `third-party-ref` (`''`), `third-party-path` (`''`), `sdist-setup-cmd` (`''`), `skip-existing` (`true`), `verify-metadata` (`false`), `artifact-retention-days` (`7`).
8. **`reusable_npm_publish.yml`**: Builds, tests, packs, and publishes npm packages with Node.js 24+ OIDC Trusted Publishing (`id-token: write`, `--provenance --access public`), CalSemVer/PEP 440 tag validation, idempotent registry pre-check, and optional `npm-token` fallback.
   - Inputs: `working-directory` (`'.'`), `node-version` (`'24'`), `needs-python` (`false`), `python-version` (`'3.14'`), `setup-cmd` (`''`), `install-cmd` (`'npm ci'`), `build-cmd` (`'npm run build'`), `test-cmd` (`''`), `validate-release-tag` (`true`), `pack-and-upload-artifact` (`true`), `artifact-retention-days` (`7`), `run-verify-syntax` (`true`).
   - Secrets: `npm-token` (optional fallback; leave unset to use OIDC Trusted Publishing).
9. **`reusable_nuget_publish.yml`**: Optional multi-OS native C# runtime build matrix, `dotnet pack`, and NuGet.org publishing via OIDC Trusted Publishing (`NuGet/login` with `id-token: write`) + optional GitHub Packages push and optional `nuget-api-key` fallback.
   - Inputs: `project-path` (required), `dotnet-version` (`'8.0.x'`), `python-version` (`'3.14'`), `environment-name` (`'build_and_publish_to_nuget'`), `nuget-user` (`'carlkidcrypto-nuget'`), `build-runtimes` (`false`), `runtime-matrix-json`, `prepare-windows-netsnmp` (`false`), `net-snmp-version` (`'5.10.pre2'`), `net-snmp-sha256`, `runtime-setup-cmd` (`''`), `runtime-build-cmd` (`''`), `runtime-artifact-path` (`'bindings/csharp/runtimes'`), `pack-setup-cmd` (`''`), `pack-extra-args` (`''`), `publish-github-packages` (`true`), `github-packages-owner` (`'carlkidcrypto'`), `artifact-retention-days` (`7`), `run-verify-syntax` (`true`).
   - Secrets: `nuget-api-key` (optional fallback; leave unset to use OIDC Trusted Publishing).
10. **`reusable_winget_publish.yml`**: Generates, validates (`winget validate`), uploads, and optionally submits WinGet manifests to `microsoft/winget-pkgs` via `wingetcreate`.
    - Inputs: `package-identifier` (required), `installer-filename` (required), `release-tag` (`''`), `python-version` (`'3.14'`), `version-reader-fn` (`'_read_current_calsemver'`), `manifest-generator-script` (`'tools/generate_winget_manifest.py'`), `installer-type` (`'inno'`), `artifact-retention-days` (`7`), `run-verify-syntax` (`true`).
    - Secrets: `winget-acc-token` (optional GitHub PAT with `public_repo` scope).

#### Composite Actions (`actions/*/action.yml`)

1. **`actions/check-source-changes`**: Pinned `tj-actions/changed-files@9426d40962ed5378910ee2e21d5f8c6fcbf2dd96` (`v47.0.6`) wrapper. Inputs: `files` (required); Outputs: `any_changed`.
2. **`actions/prepare-windows-netsnmp`**: Installs/configures OpenSSL, Visual Studio environment, and Net-SNMP for Windows `x64`/`x86`/`arm64` builds. Inputs: `net-snmp-version` (`"5.10.rc1"`), `net-snmp-sha256`, `arch` (`"x64"`).
3. **`actions/setup-actionlint`**: Downloads pinned `actionlint` with retries (`--retry 5 --retry-delay 2 --retry-all-errors`). Inputs: `version` (`'v1.7.12'`).
4. **`actions/setup-copilot-gh-aw`**: Checks out repository (`persist-credentials: false`) and installs the `gh-aw` CLI extension. Inputs: `gh-aw-version` (`'v0.89.21'`).
5. **`actions/setup-git-chglog`**: Downloads pinned `git-chglog` with retries. Inputs: `version` (`'0.15.4'`).
6. **`actions/upload-codecov`**: Uploads coverage or test results via pinned `codecov/codecov-action@0565863a31f2c772f9f0395002a31e3f06189574` (`v5.4.0`), setting both `CODECOV_TOKEN` env and `token` input. Inputs: `token` (required), `files` (`''`), `flags` (`''`), `name` (`''`), `fail-ci-if-error` (`'false'`).

#### OIDC Trusted Publishing (`NPM_TOKEN` Removal) & Immutable Releases

- **OIDC Trusted Publishing Default**: Prefer OIDC Trusted Publishing (`permissions: id-token: write`, `contents: read`) across PyPI/TestPyPI (`reusable_pypi_publish.yml`), npm (`reusable_npm_publish.yml` on Node.js 24+), and NuGet (`reusable_nuget_publish.yml` via `NuGet/login`). Once Trusted Publishing is configured for a package, omit static `NPM_TOKEN` / `PYPI_API_TOKEN` / `NUGET_API_KEY` secrets—and never pass an empty `NODE_AUTH_TOKEN` env var unconditionally, as it causes npm to fail with `ENEEDAUTH` instead of negotiating OIDC.
- **GitHub Immutable Releases**: Repositories using GitHub Immutable Releases lock release assets once a release is published. Asset-uploading workflows (e.g. desktop installers) must trigger on `release: types: [created, published]`, upload assets while `github.event.release.draft == true` (before publishing), and guard against post-publish uploads when the release is immutable.
