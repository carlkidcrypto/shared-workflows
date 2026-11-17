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

## 1. Smart File-Change Detection (`tj-actions/changed-files`)

To prevent wasting GitHub Actions runner minutes on heavy multi-platform test matrices (Ubuntu, macOS, Windows) when unrelated files change, all active workflows must use smart file-change detection.

### Action Reference
- **Action**: `tj-actions/changed-files@9426d40962ed5378910ee2e21d5f8c6fcbf2dd96` (# v47.0.6)
- **Checkout**: `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` (# v4.2.2) with `fetch-depth: 0`

### Canonical Pattern
Define a lightweight pre-flight job `check-source-changes` that evaluates file changes and outputs `run_job`. Gate the heavy test matrix on this output:

```yaml
jobs:
  check-source-changes:
    name: Check Source Changes
    runs-on: ubuntu-latest
    outputs:
      run_job: ${{ steps.changed-files.outputs.any_changed }}
    steps:
      - name: Checkout Sourcecode
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0

      - name: Check for Changes in Relevant Files
        id: changed-files
        uses: tj-actions/changed-files@9426d40962ed5378910ee2e21d5f8c6fcbf2dd96 # v47.0.6
        with:
          files: |
            src/**
            include/**
            python_tests/**
            pyproject.toml
            setup.py
            .github/workflows/tests_python.yml

  python-tests:
    name: Python Tests (${{ matrix.os }}, py${{ matrix.python-version }})
    needs: check-source-changes
    if: needs.check-source-changes.outputs.run_job == 'true' || github.event_name == 'workflow_dispatch'
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]
    steps:
      - name: Checkout Sourcecode
        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
      # ... matrix steps
```

### Path Filter Principles
- **Targeted Paths**: Only include paths relevant to the workflow's scope (e.g. `bindings/javascript/**` for npm tests, `sphinx_docs_build/**` for doc builds).
- **Include Workflow File Itself**: Always list the workflow file itself in `files:` (e.g. `.github/workflows/tests_python.yml`) so changes to CI configuration trigger validation.
- **Workflow Dispatch Override**: Always include `|| github.event_name == 'workflow_dispatch'` so manual pipeline runs always execute.

---

## 2. Cross-Platform Step Consolidation (`carlkidcrypto/os-specific-runner`)

Multi-OS matrices often require different shell commands across Linux, macOS, and Windows. Instead of cluttering workflows with fragmented, repeating conditional steps (`if: runner.os == 'Linux'`, `if: runner.os == 'macOS'`, `if: runner.os == 'Windows'`), consolidate them into a single step using `carlkidcrypto/os-specific-runner`.

### Action Reference
- **Action**: `carlkidcrypto/os-specific-runner@d6494ebfd6437452a44d3f9d6633339772e95070` (# v2.4.0)

### Inputs
- `linux`: Shell script for Linux (default shell: `bash`)
- `macos`: Shell script for macOS (default shell: `zsh`)
- `windows`: Shell script for Windows (default shell: `pwsh`)
- Optional shell overrides: `linuxShell`, `macosShell`, `windowsShell`

### Canonical Pattern: System Dependency Installation
```yaml
      - name: Install System Dependencies
        uses: carlkidcrypto/os-specific-runner@d6494ebfd6437452a44d3f9d6633339772e95070 # v2.4.0
        with:
          linux: |
            sudo apt-get update
            sudo apt-get install -y libsnmp-dev meson ninja-build libgtest-dev
          macos: |
            brew update
            brew install net-snmp meson ninja googletest
          windows: |
            choco install -y net-snmp meson ninja
```

### Canonical Pattern: Native Build and Test
```yaml
      - name: Build & Run Native Tests
        uses: carlkidcrypto/os-specific-runner@d6494ebfd6437452a44d3f9d6633339772e95070 # v2.4.0
        with:
          linux: |
            meson setup build --buildtype=debug -Db_coverage=true
            meson compile -C build
            meson test -C build --verbose
          macos: |
            meson setup build --buildtype=debug
            meson compile -C build
            meson test -C build --verbose
          windows: |
            meson setup build --buildtype=debug
            meson compile -C build
            meson test -C build --verbose
```

---

## 3. Sphinx Documentation & GitHub Pages Deployment Standards

When authoring documentation workflows or deploying Sphinx sites to GitHub Pages:

### Python 3.14 Standard for Sphinx Workflows
- **Sphinx 9.2.0+ Compatibility**: Sphinx 9.2.0 strictly requires **Python $\ge$ 3.13** (`Requires-Python >= 3.13`). Workflows configured with Python 3.12 fail during pip dependency installation.
- Standardize all Sphinx documentation build workflows on **Python 3.14** using `actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` (# v7.1.0) with `python-version: "3.14"`.
- Ensure local release tools (`bump_version.sh` / `release.sh`) search for `python3.14.venv`, `python3.13.venv`, and `.venv`.

### Mandatory Pull Request CI Trigger
- Documentation workflows (`sphinx_build.yml`) must include a `pull_request: branches: [main]` trigger. Without PR validation, automated dependency bumps (e.g. Dependabot updating Sphinx or Furo) can be merged without doc build verification, causing immediate breakage on `main`.

### Gated Deployment & Artifact Upload
- The doc build job (`sphinx_docs_build`) runs on `push`, `pull_request`, and `workflow_dispatch`.
- Always gate `upload-pages-artifact` and `deploy_pages` with `if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'` to prevent unnecessary artifact creation during PR evaluation.

### Multi-Manifest Pip Cache Invalidation
- For repositories maintaining both primary documentation and a landing page (e.g. `sphinx_docs_build/requirements.txt` and `sphinx_docs_build/landing/requirements.txt`), hash both files in the cache key:
  ```yaml
  key: ${{ runner.os }}-pip-sphinx-${{ hashFiles('sphinx_docs_build/requirements.txt', 'sphinx_docs_build/landing/requirements.txt') }}
  ```

### Prerelease Replacement & Version Normalization
- When a new stable release (e.g. `2.5.0` or `2026.11.4`) is published, its versioned documentation replaces and retires all prereleases (`alpha`, `beta`, `rc`) belonging to that version series (e.g., `html_v2.5.0a0`–`html_v2.5.0b0` are removed from `docs/` and from the landing page version selector).
- Prereleases remain in `docs/` only while no stable release has been published for that series.
- Directory naming must always be normalized to lowercase `html_v<version>` regardless of git tag casing (`V2.5.0` vs `v2.5.0`).
- The automated Sphinx release workflow must prune retired prerelease directories and update landing page sentinels (`VERSION_LIST_START` / `VERSION_LIST_END`).

### `.nojekyll` Deployment Requirement
> [!IMPORTANT]
> **Always ensure `.nojekyll` exists in the published artifact.**
> By default, GitHub Pages processes published directories through Jekyll. Jekyll automatically ignores any directory or file prefixed with an underscore (such as Sphinx's `_static/`, `_sources/`, `_modules/`), resulting in broken CSS styling, missing JavaScript, and 404 errors.

### Canonical Sphinx Workflow Pattern
```yaml
name: "Sphinx Docs Build"

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  release:
    types: [published]
  workflow_dispatch:

jobs:
  sphinx_docs_build:
    if: github.event_name == 'push' || github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    steps:
      - name: Check out repository code
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1

      - name: Set up Python 3.14 for Sphinx
        uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0
        with:
          python-version: "3.14"

      - name: Cache pip dependencies
        uses: actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-sphinx-${{ hashFiles('sphinx_docs_build/requirements.txt', 'sphinx_docs_build/landing/requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-sphinx-
            ${{ runner.os }}-pip-

      - name: Install Sphinx requirements
        run: python -m pip install -r sphinx_docs_build/requirements.txt

      - name: Build Sphinx documentation
        working-directory: sphinx_docs_build
        run: |
          make clean && make html SPHINXOPTS="-W"
          touch ../docs/.nojekyll

      - name: Upload artifact for GitHub Pages
        if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'
        uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5.0.0
        with:
          path: docs/

  deploy_pages:
    if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'
    needs: sphinx_docs_build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    permissions:
      pages: write
      id-token: write
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346 # v5.0.1
```

---

## 4. Multi-Ecosystem Dependabot Configuration

Every repository with dependencies must maintain `.github/dependabot.yml` covering all active language ecosystems and workflows.

### Supported Ecosystems
1. `github-actions`: Directory `"/"`
2. `pip`: Directory `"/"` (root project) and `"/sphinx_docs_build"` (doc builder)
3. `npm`: Directory `"/bindings/javascript"` or `"/"`
4. `nuget`: Directory `"/bindings/csharp"`
5. `gomod`: Directory `"/bindings/go"`

### Canonical `.github/dependabot.yml`
```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
    open-pull-requests-limit: 10

  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
    open-pull-requests-limit: 10

  - package-ecosystem: "pip"
    directory: "/sphinx_docs_build"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
    open-pull-requests-limit: 10

  - package-ecosystem: "npm"
    directory: "/bindings/javascript"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
    open-pull-requests-limit: 10

  - package-ecosystem: "nuget"
    directory: "/bindings/csharp"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
    open-pull-requests-limit: 10

  - package-ecosystem: "gomod"
    directory: "/bindings/go"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
    open-pull-requests-limit: 10
```

### Transitive Dependency Resolution & Engine Compatibility
- **`package.json` Overrides**: For vulnerable transitive dependencies in npm repositories with available patches (e.g. `minimatch`), enforce resolutions via `package.json` `"overrides"`:
  ```json
  "overrides": {
    "minimatch": "^11.0.4"
  }
  ```
- **`node-gyp` Major Version Restrictions**: Upgrading `node-gyp` to major version 13 (`^13.0.0` / `^13.1.0`) introduces `undici@8` and enforces `engines: { "node": "^22.22.2 || ^24.15.0 || >=26.0.0" }`. On Node 18 or 20 runners, `undici` fails during `node-gyp rebuild` with `TypeError: Cannot read properties of undefined (reading 'bind')`. For repositories testing or supporting Node.js 18+ (e.g. 18.x, 20.x, 22.x, 24.x), pin or align `node-gyp` to `^11.5.0` (which uses patched `tar@7.5.22` with zero deprecation warnings, excludes `undici`, and supports Node >= 18.17.0 and >= 20.5.0).

---

## 5. SonarQube Cloud Analysis Scope & Quality Standards

To maintain an **A+** grade across Reliability, Security, Maintainability, Duplication, and Coverage:

1. Maintain root `.sonarcloud.properties`:
```properties
sonar.projectKey=carlkidcrypto_<repo>
sonar.organization=carlkidcrypto

# Exclude generated code, documentation builds, and external dependencies
sonar.exclusions=docs/**,sphinx_docs_build/**,.github/**,third_party/**,**/*_wrap.cxx,**/*_wrap.h,bindings/**/generated/**

# CPD (Copy-Paste Detector) exclusions to ensure 0.0% duplication
sonar.cpd.exclusions=python_tests/**,cpp_tests/**,tests/**,configs/**,bindings/**
```

2. Exclude SWIG generated wrapper artifacts from analysis so generated C++ or Python files do not dilute repository quality metrics.
3. Exclude test suites and mock configurations from CPD duplication checks.

---

## 6. `cibuildwheel` & `delvewheel` Standards

When distributing precompiled binary wheels for C/C++ extensions across Linux, macOS, and Windows:

1. **Windows ARM64 MSVC Runtime Exclusions**:
   - Cross-compiling Windows ARM64 wheels on AMD64 runners (`windows-latest`) will fail if `delvewheel` attempts to locate host ARM64 MSVC runtime DLLs.
   - Always exclude standard Visual C++ runtime DLLs via `--no-dll`:
   ```toml
   [tool.cibuildwheel.windows]
   repair-wheel-command = "delvewheel repair -w {dest_dir} {wheel} --no-dll \"msvcp140.dll;msvcp140_1.dll;msvcp140_2.dll;msvcp140_atomic_wait.dll;msvcp140_codecvt_ids.dll;vcruntime140_1.dll\""
   ```
2. **Frontend Selection**:
   - Set `build-frontend = "build"` for `*-win_arm64` overrides.
3. **Decouple In-Tree Pytest from Wheel Building**:
   - Do **not** set `test-command = "pytest {project}/python_tests"` inside `[tool.cibuildwheel]`. Pytest prioritizes the uncompiled local source tree over the wheel installed in `site-packages`, triggering import errors for compiled binary extensions.
   - Matrix testing of installed packages belongs in dedicated `tests_python.yml` workflows.
4. **Pre-provision Vendored Dependencies via GitHub Actions**:
   - Pre-provision third-party repositories (e.g. `third_party/ezsnmp`) directly using `actions/checkout` in wheel distribution workflows (`build_and_publish_to_pypi.yml` and `build_and_publish_to_test_pypi.yml`) rather than relying on in-container unauthenticated network git clones during `cibuildwheel before-all`.
   - Equip provisioning helper scripts (`tools/prepare_*.py`) with exponential backoff retry loops and cleanup of partial clone directories to guarantee resilience against transient network resets.
5. **macOS Apple System Library Linking vs. Homebrew Vendoring (`delocate-wheel`)**:
   - For standard platform libraries natively bundled in macOS (e.g. `libcurl`, `sqlite3`, `zlib`), always link against Apple's SDK system libraries (`cpp.find_library('curl')`) rather than installing Homebrew packages (`brew install curl`) and setting `PKG_CONFIG_PATH`.
   - `delocate-wheel` treats `/usr/lib/*` and `/System/Library/*` as system libraries and does not vendor them into the wheel.
   - Linking against Homebrew bottles causes `delocate-wheel` to vendor Homebrew dylibs and their transitive dependencies, which fail with `delocate.libsana.DelocationError: Library dependencies do not satisfy target MacOS version 11.0: ... has a minimum target of 26.0` when runners use newer macOS images.
   - For libraries requiring Homebrew (e.g., custom OpenSSL builds), align `MACOSX_DEPLOYMENT_TARGET` dynamically to the runner's OS major version (`MACOS_MAJOR=$(sw_vers -productVersion | cut -d. -f1)`).

---

## 7. Software Requirements Specifications Synchronization

1. **Traceability**: All architectural features, CI/CD pipelines, and configuration standards must have corresponding requirements in `sphinx_docs_build/source/software_requirements.rst` (e.g. `[CICD-01]`, `[CICD-02]`, `[CORE-01]`, `[SWIG-01]`).
2. **Single Responsibility & Anti-Double-Stacking**: Each requirement block **Shall** test exactly one feature, function, or use case of the code. Never combine multiple distinct features or target ecosystems into a single requirement identifier.
3. **Formatting Enforcement**:
   - **Line Length**: Strictly maximum **80 characters** per line.
   - **Spacing**: A blank line must separate every distinct requirement block.
   - **Human Readability**: Plain, clear, professional descriptions.
4. **Synchronization**: Update requirements before committing changes to ensure documentation matches the current state of code.

---

## 8. C/C++ Wheel Compilation Acceleration & Object Caching

Building binary wheels across 6 OS/architecture runners and 7 Python targets (`cp311`–`cp315t`) can easily exceed 20 minutes if compiled sequentially. Accelerate builds to ~3–5 minutes using parallel compilation and cross-version object caching:

1. **Parallel Multi-Core Compilation**:
   - Disptach translation units concurrently across runner cores using `ThreadPoolExecutor(max_workers=jobs)` in `setup.py`.
   - Support `EZSNMP_BUILD_JOBS = "auto"` (defaulting to CPU count minus 1, minimum 1).
   - Use **Longest Processing Time (LPT)** scheduling to compile large translation units (such as `sqlite3.c` amalgamation) first.
   - Pre-create all object output directories upfront on the main thread and pass `/FS` on MSVC to guarantee thread safety.
2. **Deterministic Cross-Python C++ Object Caching**:
   - Python C/C++ extensions often contain mostly Python-independent translation units (e.g., SQLite3 amalgamation, native C++ core, vendored libraries). Only the SWIG wrapper (`*_wrap.cxx`) depends on `Python.h`.
   - Compute a deterministic SHA-256 cache key based on compiler identity, compilation flags, macros, non-Python include paths, debug settings, and source/header file contents.
   - When `EZSNMP_OBJECT_CACHE_DIR` is set, cache compiled `.o` / `.obj` files. The first Python target compiles all units; subsequent targets (3.12–3.15t) reuse the cached objects and only compile the SWIG wrapper (~8 seconds), reducing compilation volume by ~82%.
   - Add a GitHub Actions runner cache step in `.github/actions/build-wheels/action.yml` for macOS and Windows runners to persist cached objects across runs.
3. **High-Speed Build Frontend (`build[uv]`)**:
   - Configure `build-frontend = "build[uv]"` in `[tool.cibuildwheel]` to allow `cibuildwheel` to resolve and install build dependencies in milliseconds via `uv` (retaining standard `build` override for Windows ARM64 cross-compilation).

---

## 9. Automated Test Deployment Gating on Main

1. **Continuous Test Deployments**:
   - Configure test deployment workflows (`build_and_publish_to_test_pypi.yml`) to automatically trigger on `push: branches: [main]` in addition to `workflow_dispatch`.
   - Validates that distribution packaging, wheel building, and registry publishing succeed immediately upon merging changes into `main`, catching packaging regressions before formal releases are created.
2. **Smart Change Detection Gating**:
   - Gate heavy test deployment jobs with a lightweight `check-source-changes` job (`tj-actions/changed-files@9426d40962ed5378910ee2e21d5f8c6fcbf2dd96`).
   - Monitor all source, header, interface, build script, and workflow files (`include/**`, `src/**`, `interface/**`, `<package>/**`, `tools/**`, `pyproject.toml`, `setup.py`, `requirements.txt`).
   - Gate matrix runners with `if: needs.check-source-changes.outputs.run_job == 'true' || github.event_name == 'workflow_dispatch'`.

---

## 10. Transient Platform Incident Diagnostics & Targeted Job Recovery

1. **Diagnosing Platform Cancellations**:
   - When jobs fail with `status: "completed"`, `conclusion: "cancelled"`, `steps: []`, and `runner_id: 0`, the job was cancelled by GitHub infrastructure before a runner was provisioned.
   - Check GitHub Status API (`https://www.githubstatus.com/api/v2/incidents.json`) to confirm whether an active or recent incident affected Actions runner scheduling.
2. **Targeted Job Recovery (`rerun-failed-jobs`)**:
   - Do not re-run entire matrix workflows from scratch when 5 of 6 jobs have already succeeded.
   - Trigger targeted retries via the GitHub API:
     ```bash
     gh api /repos/<owner>/<repo>/actions/runs/<run_id>/rerun-failed-jobs -X POST
     ```
   - This preserves all existing passed matrix artifacts and only re-queues the dropped job, allowing dependent downstream publishing jobs to resume seamlessly upon completion.

---

## 11. Multi-Language Codecov Coverage & Glob Matching Standards

1. **Root & Nested Path Globs (`codecov.yml`)**:
   - In Codecov path matching, `dir/**/*.ext` only matches files nested inside subdirectories (1+ levels deep) and fails to match root files like `dir/*.ext` (e.g. `javascript/index.js`).
   - Always configure both root and nested patterns across flags and components:
     ```yaml
     paths:
       - javascript/*.js
       - javascript/**/*.js
       - go/*.go
       - go/**/*.go
       - python/*.py
       - python/**/*.py
     ```
2. **Go Package Instrumentation (`-coverpkg`)**:
   - In Go, `go test ./tests/...` only instruments the `tests` package by default. Because `codecov.yml` typically ignores test directories, Codecov discards the report resulting in 0% / empty coverage.
   - Always pass `-coverpkg=<module>/...` (e.g. `-coverpkg=github.com/carlkidcrypto/<repo>/go/...`) to instrument the actual library code.
3. **JavaScript / Node.js Coverage (`jest.config.js`)**:
   - Explicitly configure `collectCoverageFrom: ["index.js", "src/**/*.js"]` and include `"cobertura"` in `coverageReporters`.
   - Remove dead fallback branches in SWIG wrapper glue code and supply unit tests for constructor variants (default zero-argument vs pre-constructed native instances) to maintain 100% statement, branch, and line coverage.
4. **Component Management Boundaries**:
   - Machine-generated SWIG code in build directories is git-ignored and untracked by Codecov.
   - Only define components in `component_management` for active, hand-authored repository source code (`python_code`, `javascript_code`, `go_code`) to avoid permanent empty (`∅`) component reports.

5. **Codecov Action SHA Pinning & Step Token Authentication**:
   - Pin `codecov/codecov-action` to its immutable commit hash `codecov/codecov-action@0565863a31f2c772f9f0395002a31e3f06189574` (# v5.4.0) across all workflows to satisfy SonarCloud security rule S7637.
   - Always supply `token: ${{ secrets.CODECOV_TOKEN }}` directly in the action's `with:` block in addition to `env: CODECOV_TOKEN:`, as recent runner versions prioritize step inputs over environment variables.
   - Supply `fail_ci_if_error: false` to ensure test jobs do not fail on transient third-party API connectivity drops:
     ```yaml
     - name: Upload coverage reports to Codecov
       uses: codecov/codecov-action@0565863a31f2c772f9f0395002a31e3f06189574 # v5.4.0
       with:
         token: ${{ secrets.CODECOV_TOKEN }}
         files: coverage.xml
         flags: python
         fail_ci_if_error: false
       env:
         CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}
     ```

6. **Change Detection & Unit Test Verification**:
   - Add `codecov.yml` to the `check-source-changes` job (`tj-actions/changed-files`) and workflow trigger paths so modifying coverage rules immediately triggers test pipelines.
   - Add automated unit test verification in the test suite to validate `codecov.yml`, `.sonarcloud.properties`, and workflow token configuration.

7. **Pre-Push Code Formatting Verification**:
   - Always run local formatters (`black` for Python, `prettier` for JavaScript/TypeScript, `csharpier` for C#) on newly created or modified files before staging and committing.
   - Unformatted files will fail PR formatting checks (`python_black.yml`) and trigger automated bot commits directly to the branch, causing subsequent git pushes to be rejected due to stale remote references.

---

## 12. npm OIDC Trusted Publishing & Provenance Standards

When publishing npm packages from GitHub Actions, implement OIDC Trusted Publishing and Sigstore provenance attestations:

### 1. Workflow Permissions & Runner Setup
- Standardize on **Node.js 24** (which pre-provisions npm 11.19.1+ with native OIDC support):
  ```yaml
  - name: Set up Node.js
    uses: actions/setup-node@v7
    with:
      node-version: 24
      registry-url: "https://registry.npmjs.org"
  ```
- OIDC token exchange requires:
  ```yaml
  permissions:
    contents: read
    id-token: write
  ```

### 2. Provenance & Package Manifest Standards
- Always pass `--provenance --access public` when publishing:
  ```bash
  npm publish --provenance --access public
  ```
- npm verifies that `package.json` contains a matching `"repository"` entry before generating provenance attestations:
  ```json
  "repository": {
    "type": "git",
    "url": "git+https://github.com/carlkidcrypto/ezsnmp_data_logger.git"
  }
  ```

### 3. Safe Token Environment Injection
- **Do not** specify `env: NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}` unconditionally at the step level.
- If `NPM_TOKEN` is unset or empty, exporting `NODE_AUTH_TOKEN=""` causes npm to transmit an empty Bearer authorization header, failing immediately with `ENEEDAUTH` instead of initiating OIDC exchange.
- Use conditional token injection in the run step:
  ```bash
  if [ -n "${{ secrets.NPM_TOKEN }}" ]; then
    echo "Configuring npm authentication via NPM_TOKEN secret"
    npm config set //registry.npmjs.org/:_authToken "${{ secrets.NPM_TOKEN }}"
  else
    echo "No NPM_TOKEN provided; using npm OIDC trusted publishing"
  fi
  npm publish --provenance --access public
  ```

### 4. npm vs PyPI Trusted Publishing Bootstrap Lifecycle
- **PyPI Model**: PyPI supports *Pending Publishers*, allowing a maintainer to register repository OIDC publishers *before* the package exists on PyPI.
- **npm Model**: npm does **not** allow configuring trusted publishers for a package until the package has been published at least once.
- **Bootstrap Sequencing**:
  1. For initial release of a new package, authenticate via `NPM_TOKEN` (or maintainer local CLI publish `npm publish --access public`).
  2. Navigate to `https://www.npmjs.com/package/<pkg>/access` -> **Publishing Access** -> **Trusted Publishers**.
  3. Add GitHub Actions publisher specifying owner (`carlkidcrypto`), repository, workflow filename (`publish_npm.yml` or `build_and_publish_to_npm.yml`), and environment.
  4. Subsequent releases publish seamlessly via OIDC token exchange without static secrets.

### 5. Idempotent Registry Pre-Check
- npm is an immutable registry; attempting to re-publish an already-published version fails with `E404` or `E403`.
- To allow safe workflow re-runs or dispatch testing without failing pipelines, pre-check version existence before publishing:
  ```bash
  PACKAGE_VERSION=$(node -p "require('./package.json').version")
  PACKAGE_NAME=$(node -p "require('./package.json').name")
  if npm view "${PACKAGE_NAME}@${PACKAGE_VERSION}" version >/dev/null 2>&1; then
    echo "Notice: ${PACKAGE_NAME}@${PACKAGE_VERSION} is already published on npm; skipping publish step idempotently."
    exit 0
  fi
  ```

---

## 13. Cross-Language Native C++ Standard Conformance

When building multi-language native SWIG bindings (Python, Node.js N-API, C#, Go) incorporating C/C++ libraries (such as Net-SNMP and OpenSSL):

### 1. Net-SNMP Macro Compatibility & Strict ANSI Conformance
- Net-SNMP 5.10 header `net-snmp/library/asn1.h` provides macro `OID_LENGTH(x)` defined as:
  ```c
  #define OID_LENGTH(x) (sizeof(x)/sizeof(oid) + 0 * sizeof(struct { \
       unsigned int _asn1_check_pointer : \
       __builtin_types_compatible_p(__typeof__(x), oid *) ? -1 : 1; }))
  ```
- `__builtin_types_compatible_p` is a **C-only** GCC builtin. When evaluated in C++ compilation, GCC throws:
  `error: '__builtin_types_compatible_p' was not declared in this scope`.
- The Net-SNMP macro evaluates this block only if `__GNUC__` is defined and `__STRICT_ANSI__` is **NOT** defined.
- In CMake, `CMAKE_CXX_EXTENSIONS` defaults to `ON`, which passes GNU dialect flags (e.g. `-std=gnu++17`), leaving `__STRICT_ANSI__` undefined.
- **Standard Solution**:
  1. Disable compiler extensions to enforce strict C++17 standard conformance:
     ```cmake
     set(CMAKE_CXX_EXTENSIONS OFF)
     ```
  2. Explicitly define `__STRICT_ANSI__` on non-MSVC builds in native CMake targets:
     ```cmake
     if(NOT MSVC)
       target_compile_definitions(<target_name> PRIVATE __STRICT_ANSI__)
     endif()
     ```

### 2. CMake OBJECT Library Transitive Interface Includes
- CMake `OBJECT` libraries (`add_library(<name> OBJECT ...)`) compile translation units into object files without linking.
- Because object libraries do not link, they do not automatically inherit `INTERFACE_INCLUDE_DIRECTORIES` from targets specified via `target_link_libraries()`.
- When external dependency headers (such as `openssl/ossl_typ.h` or `net-snmp/net-snmp-config.h`) are needed across platforms (e.g. macOS Homebrew `/opt/homebrew/include`), explicitly supply them directly:
  ```cmake
  if(OPENSSL_FOUND)
    target_include_directories(<target_name> PUBLIC ${OPENSSL_INCLUDE_DIR})
  endif()
  ```

---

## 14. Multi-Ecosystem Release Publishing Gating & Artifact Preservation

In repositories managing automated deployment across multiple ecosystems (PyPI wheels, npm packages, NuGet `.nupkg`, WinGet manifests):

### 1. Decouple Packaging from Registry Publishing
- Never combine package building and registry uploading into an atomic step that discards build outputs on upload failure.
- Structure workflows to build and pack distribution artifacts first (e.g. `dotnet pack`, `npm pack`), upload them to GitHub Actions run artifacts (`actions/upload-artifact@4cec3d8aa04e39d1a68397de0c4cd6fb9dce8ec1` # v5.0.0), and then invoke publishing commands.

### 2. Graceful Step Gating for Unconfigured Secrets
- During repository onboarding, maintainers may enable publishing workflows before all third-party API tokens are registered in repository secrets.
- Protect publish jobs from failing whole release pipelines:
  ```bash
  if [ -z "${{ secrets.NUGET_API_KEY }}" ]; then
    echo "::warning ::NUGET_API_KEY secret is not configured; skipping NuGet package upload. Distribution packages have been saved as workflow artifacts."
    exit 0
  fi
  dotnet nuget push ...
  ```
- This ensures successful PyPI and npm releases are not marked as failed releases simply because an optional or onboarding ecosystem token has not yet been populated.

---

## 15. NuGet OIDC Trusted Publishing Standards

NuGet.org supports keyless Trusted Publishing via OpenID Connect (OIDC), eliminating static `NUGET_API_KEY` secrets in GitHub Actions:

### 1. NuGet.org Policy Setup
1. Sign in to [nuget.org](https://www.nuget.org).
2. Go to **Account Settings** (or Organization Settings) -> **Trusted Publishing**.
3. Create a publishing policy specifying:
   * **Policy Name**: Descriptive label (e.g. `Release Workflow`)
   * **Repository Owner**: GitHub username or organization (`carlkidcrypto`)
   * **Repository**: Exact GitHub repository name (`ezsnmp_data_logger`, `purpleair_api`, etc.)
   * **Workflow File**: Workflow filename (`build_and_publish_to_nuget.yml`)

### 2. Workflow Permissions & Authentication
- Grant OIDC permissions at the job or workflow level:
  ```yaml
  permissions:
    contents: read
    id-token: write
  ```
- Authenticate via the official `nuget/login` action:
  ```yaml
  - name: Authenticate with NuGet.org (OIDC Trusted Publishing)
    if: env.NUGET_API_KEY == ''
    uses: nuget/login@v1
    with:
      owner: carlkidcrypto
  ```

### 3. Push Command & Idempotency
- When authenticated via `nuget/login`, `dotnet nuget push` does not require an API key:
  ```bash
  if [ -n "${NUGET_API_KEY:-}" ]; then
    dotnet nuget push dist-nuget/*.nupkg --api-key "$NUGET_API_KEY" --source https://api.nuget.org/v3/index.json --skip-duplicate
  else
    dotnet nuget push dist-nuget/*.nupkg --source https://api.nuget.org/v3/index.json --skip-duplicate
  fi
  ```
- Always pass `--skip-duplicate` so re-dispatched workflows or rerun matrix jobs do not fail when packages already exist.

---

## 16. WinGet Community Distribution Standards (`wingetcreate`)

When publishing Windows desktop applications and CLI tools to Microsoft's Windows Package Manager Community Repository (`microsoft/winget-pkgs`):

### 1. Canonical Manifest Directory Hierarchy
- `microsoft/winget-pkgs` strictly enforces directory structure:
  `manifests/{first-letter}/{Publisher}/{AppName}/{Version}/`
  (e.g., `manifests/c/carlkidcrypto/EzSnmpDataLogger/2026.11.6/`).
- Each version directory must contain three conforming YAML manifests:
  1. `<PackageIdentifier>.yaml` (Version manifest: `DefaultLocale`, `ManifestType: version`, `ManifestVersion`)
  2. `<PackageIdentifier>.installer.yaml` (Installer manifest: `Architecture`, `InstallerType: inno` or `zip`, `InstallerUrl`, `InstallerSha256`, switches, `AppsAndFeaturesEntries` or `NestedInstallerFiles`)
  3. `<PackageIdentifier>.locale.en-US.yaml` (DefaultLocale manifest: `Publisher`, `PackageName`, `License`, `ShortDescription`, `Description`, `Moniker`, `Tags`)

### 2. Microsoft `wingetcreate` CLI Tool Integration
- Download official `wingetcreate` binary from `https://aka.ms/wingetcreate/latest` on `windows-latest` runners.
- Verify binary presence via file system tests (`Test-Path .\wingetcreate.exe`) rather than invoking help/version commands that may return exit code 1 under .NET CommandLineParser error defaults.
- Automated submission commands:
  - **Initial / Direct Submission**: `.\wingetcreate.exe submit "<path-to-manifest.yaml>" --token "$token" --no-open`
  - **Update Fallback**: `.\wingetcreate.exe update <PackageIdentifier> --version <version> --urls <url> --token "$token" --no-open --submit`

### 3. Secret Token Flexibility & PR Gating
- Support secret aliases: `secrets.WINGET_CREATE_PAT || secrets.WINGET_TOKEN || secrets.WINGET_ACC_TOKEN`.
- If the token is not populated, generate and upload manifests as workflow artifacts, log an actionable diagnostic notice, and exit 0 cleanly.
- When triggered on pull requests (`github.event_name == 'pull_request'`), generate manifests and validate CLI execution locally, then skip remote PR submission.

---

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

## 18. GitHub CLI Release Asset Upload Context (`gh release upload`)

When configuring automated release publication jobs that download artifacts and attach them to a GitHub release:

### 1. Root Cause of Asset Upload Failures
- If the publishing job only downloads artifacts without running `actions/checkout`, the working directory is empty and not a git repository.
- Running `gh release view <tag>` or `gh release upload <tag> <asset>` without git remote context causes the GitHub CLI to fail with:
  `fatal: not a git repository` or `##[error]GitHub Release <tag> not found in repository`.

### 2. Standard Context Invariants
Always equip release asset upload steps with:
1. `actions/checkout@v7` step.
2. `env: GH_REPO: ${{ github.repository }}`.
3. Explicit `--repo "${{ github.repository }}"` parameter to all `gh release` subcommands:
   ```yaml
   - name: Publish Release Assets
     shell: bash
     env:
       GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
       GH_REPO: ${{ github.repository }}
     run: |
       set -euo pipefail
       TARGET_TAG="${{ github.event.release.tag_name || github.event.inputs.release_tag }}"
       gh release view "${TARGET_TAG}" --repo "${{ github.repository }}"
       for asset in dist-desktop/*; do
         gh release upload "${TARGET_TAG}" "${asset}" --repo "${{ github.repository }}" --clobber
       done
   ```

---

## 19. Multi-Platform Desktop Distribution Packaging

To provide users with native standalone executables and system package managers:

### 1. Matrix Packaging Strategy
Build and package across 3 target platforms:
- **Linux** (`ubuntu-latest`):
  - `.deb`: Constructed via `dpkg-deb --build` with control file in `DEBIAN/control` specifying `Package`, `Version`, `Architecture: amd64`, `Maintainer`, and `Description`.
  - `.rpm`: Built via `rpmbuild -bb` with `.spec` file.
  - `.tar.gz`: Portable binary archive.
- **Windows** (`windows-latest`):
  - Inno Setup Installer (`ISCC.exe`): Generates `EzSnmpDataLogger-Windows-x64-Setup.exe` with desktop shortcut and uninstaller.
  - Standalone `.zip`: Portable directory archive containing `EzSnmpDataLogger.exe` and runtime assets.
- **macOS** (`macos-latest`):
  - `.dmg`: Generated via `hdiutil create` wrapping the `.app` bundle.
  - Standalone `.app` bundle: Conforming macOS application directory structure with `Contents/MacOS/`, `Contents/Resources/`, and `Contents/Info.plist`.

### 2. Decouple Building from Publishing
Always build and verify packaging across matrix runners and upload to workflow run artifacts before running the single publishing step, preserving outputs if publishing credentials or release tags are pending.

---

## 20. Feature-Focused Test Suite Architecture & Flakiness Prevention

### 1. Modular Test Organization (Anti-"Full Coverage" Naming)
- **Zero Generic Test Catch-Alls**: Never author monolithic test files named `test_full_coverage.*` or `full_coverage.*`.
- **Feature Set Decomposition**: Group tests into small, cohesive test files targeting specific architectural components or subsystems:
  - Python: `test_cli_and_entrypoints.py`, `test_cli_bridge.py`, `test_locale_and_launcher.py`, `test_gui_server.py`, `test_desktop_tk.py`.
  - C++ (GoogleTest / Meson): `test_json_utils.cpp`, `test_config_and_datatypes.cpp`, `test_queue_and_sinks.cpp`, `test_sink_inspector.cpp`, `test_data_logger_and_cli.cpp`, `test_main_binary.cpp`.
- This ensures test failures isolate exact architectural regressions immediately, avoids runner timeouts on monolithic tests, and enables clean test parallelization.

### 2. Subprocess Stream Reader Concurrency & Mock Synchronization
When testing streaming subprocess managers (e.g. background stdout/stderr reader threads polling `proc.stdout` and `proc.stderr`):
- Never provide an empty iterator (`fake_proc.stdout = iter([])`). The daemon reader thread will consume an empty iterator in micro-seconds, call `proc.wait()`, and clear the active process reference (`self._run_proc = None`) before the calling test can execute `stop_run()`.
- Synchronize mock process streams with an explicit synchronization primitive:
  ```python
  stop_event = threading.Event()

  def fake_stdout_gen():
      stop_event.wait(5.0)
      return
      yield

  fake_proc.stdout = fake_stdout_gen()
  fake_proc.send_signal.side_effect = lambda sig: stop_event.set()
  fake_proc.terminate.side_effect = lambda: stop_event.set()
  fake_proc.kill.side_effect = lambda: stop_event.set()
  ```

### 3. Cross-Platform C stdio Buffer Flushing in Pytest (`capfd`)
When testing Python CLI dispatchers that call native C/C++ binaries or SWIG extension modules where stdout/stderr is buffered in C runtime libc buffers:
- Standard `ctypes.CDLL(None).fflush(None)` fails or raises errors on Windows because MSVC does not support `None` module resolution.
- Always implement platform-aware stdio flushing helper:
  ```python
  def _flush_libc() -> None:
      try:
          import ctypes

          if sys.platform == "win32":
              ctypes.cdll.msvcrt.fflush(None)
          else:
              ctypes.CDLL(None).fflush(None)
      except Exception:
          pass
      try:
          sys.stdout.flush()
          sys.stderr.flush()
      except Exception:
          pass
  ```

### 4. Meson / gcovr Stale Coverage Artifact Purging
When restructuring, renaming, or deleting C++ test files in Meson:
- Meson's build directory (`build-cov/<subdir>/<target>.p/`) retains obsolete `.gcno` and `.gcda` files.
- `ninja coverage-text` invokes `gcovr`, which attempts to match all existing `.gcno` files against source files and fails with `RuntimeError: GCOV could not find source file`.
- Always delete obsolete target directories before coverage evaluation:
  ```bash
  rm -rf build-cov/cpp_tests/test_old_target.p
  ninja -C build-cov coverage-text
  ```

---

## 21. Standardized Multi-Ecosystem Distribution Architecture (`build_and_publish_to_*.yml`)

Across repositories distributing multi-language bindings and packages (`ezsnmp_data_logger`, `purpleair_api`, `ezsnmp`), workflows must adhere to 6 standardized distribution templates:

### Canonical Pipeline Matrix
1. **NuGet (`build_and_publish_to_nuget.yml`)**:
   - Generates SWIG C# wrappers and compiles C# assemblies with Meson/Ninja or dotnet CLI.
   - Packs `.nupkg` via `dotnet pack -c Release -o dist-nuget`.
   - Uploads `.nupkg` artifacts to run artifacts before publishing.
   - Authenticates via OIDC Trusted Publishing (`NuGet/login@v1` for `carlkidcrypto-nuget`) with fallback to `NUGET_API_KEY`.
   - Idempotently publishes to NuGet.org (`--skip-duplicate`) and GitHub Packages.

2. **npm (`build_and_publish_to_npm.yml`)**:
   - Executes under Node.js 24 on Ubuntu.
   - Validates release git tag against `package.json` version (supporting SemVer 2.0 and CalSemVer prerelease formats).
   - Generates SWIG wrappers and compiles native Node-API addons via `node-gyp rebuild`.
   - Packages and preserves `.tgz` archive to workflow run artifacts before publishing.
   - Safely negotiates authentication (OIDC with fallback to `NPM_TOKEN`), pre-checks existing package versions on npm, and publishes with `--access public --provenance` (using `--tag next` for prereleases, `--tag latest` for stable releases).

3. **PyPI (`build_and_publish_to_pypi.yml`)**:
   - Compiles binary wheels across `ubuntu-latest`, `windows-latest`, `macos-13` (x86_64), and `macos-14` (arm64) using `cibuildwheel`.
   - Builds source distribution (`sdist`) via `python -m build`.
   - Decoupled packaging and artifact uploads (`wheels-*`, `sdist`) before publishing.
   - Publishes to PyPI via `pypa/gh-action-pypi-publish@release/v1.14` with OIDC Trusted Publishing and `skip-existing: true`.

4. **TestPyPI (`build_and_publish_to_test_pypi.yml`)**:
   - Push-to-`main` gated test distribution protected by smart file-change detection (`tj-actions/changed-files@v47.0.6`).
   - Decoupled wheel and sdist artifact preservation.
   - Publishes to `https://test.pypi.org/legacy/` with `skip-existing: true`.

5. **Go (`build_and_publish_to_go.yml`)**:
   - Configures Go 1.23, compiles C++ core and SWIG Go bindings, and executes test suite (`go test -v ./tests/...`).
   - Packages Go module files into `.tar.gz` workflow artifact.
   - Pre-warms official Go proxy cache (`proxy.golang.org`) on published releases.

6. **WinGet (`build_and_publish_to_winget.yml`) & Generator (`tools/generate_winget_manifest.py`)**:
   - Generates multi-file WinGet manifests (version, installer, defaultLocale) conforming to specification 1.6.0 for `carlkidcrypto.<PackageName>`.
   - Enforces strict TLS certificate verification in `compute_sha256()` (never disable `check_hostname` or set `CERT_NONE`) and resolves local paths strictly against `REPO_ROOT` to eliminate SonarCloud vulnerabilities (S5527, S4830, S8707).
   - Validates manifests locally with `winget validate`.
   - Decouples manifest generation and artifact upload from PR submission.
   - Marked `[FUTURE / WIP]`: logs diagnostic notices and cleanly skips PR submission to `microsoft/winget-pkgs` when API secrets (`WINGET_CREATE_PAT`, `WINGET_TOKEN`, `WINGET_ACC_TOKEN`) are not configured.

---

## 22. Standardized Workflow Validation Pipeline (`verify_syntax.yml` & ezsnmp Pattern)

Across all carlkidcrypto repositories, workflow syntax and action schema validation must strictly follow the **`ezsnmp` pattern** combining `yamllint` and `actionlint`.

### Architecture & Canonical Implementation
```yaml
name: Validate Workflow Files

concurrency:
  group: verify_syntax-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

on:
  push:
    branches: [main]
    paths:
      - '.github/workflows/*.yml'
      - '.github/workflows/*.yaml'
      - '!.github/workflows/*.lock.yml'
      - '!.github/workflows/*.lock.yaml'
      - '!.github/workflows/agentics-maintenance.yml'
      - 'tools/actionlint-version.txt'
      - '.yamllint'
  pull_request:
    branches: [main]
    paths:
      - '.github/workflows/*.yml'
      - '.github/workflows/*.yaml'
      - '!.github/workflows/*.lock.yml'
      - '!.github/workflows/*.lock.yaml'
      - '!.github/workflows/agentics-maintenance.yml'
      - 'tools/actionlint-version.txt'
      - '.yamllint'
  workflow_dispatch:
  workflow_call:

permissions:
  contents: read

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v7

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: "3.14"

      - name: Install yamllint
        run: python -m pip install --only-binary ":all:" yamllint==1.38.0

      - name: Install actionlint
        run: |
          set -e
          version=$(cat tools/actionlint-version.txt)
          archive="actionlint_${version#v}_linux_amd64.tar.gz"
          curl --proto =https -fsSL --retry 5 --retry-delay 2 --retry-all-errors "https://github.com/rhysd/actionlint/releases/download/${version}/${archive}" -o /tmp/actionlint.tar.gz
          mkdir -p /tmp/actionlint
          tar -xzf /tmp/actionlint.tar.gz -C /tmp/actionlint
          sudo install -m 0755 /tmp/actionlint/actionlint /usr/local/bin/actionlint
          actionlint -version

      - name: Lint workflow YAML files
        run: |
          set -e
          echo "Linting all workflow YAML files (excluding generated agentic lock files and agentics-maintenance.yml) in .github/workflows/ ..."
          find .github/workflows/ \( -name "*.yml" -o -name "*.yaml" \) ! -name "*.lock.yml" ! -name "*.lock.yaml" ! -name "agentics-maintenance.yml" -print0 | xargs -0 yamllint -c .yamllint
          echo "All workflow YAML files passed linting."

      - name: Validate workflow actions
        run: |
          set -e
          echo "Validating workflow actions with actionlint..."
          find .github/workflows/ \( -name "*.yml" -o -name "*.yaml" \) ! -name "*.lock.yml" ! -name "*.lock.yaml" ! -name "agentics-maintenance.yml" -print0 | xargs -0 actionlint -shellcheck=
          echo "All workflow files passed actionlint."
```

### Essential Invariants & Failure Modes
1. **Pinned Tool Versions**: Always store actionlint version in `tools/actionlint-version.txt` (`v1.7.12`). Pin `yamllint==1.38.0`.
2. **Resilient Network Flags**: Always download actionlint using `--retry 5 --retry-delay 2 --retry-all-errors` to eliminate CI drop failures from transient GitHub Release asset timeouts.
3. **YAML Scalar Mapping Trap**: In plain scalar `run:` commands, colons followed by a space (such as `--only-binary :all:`) will trigger YAML parser syntax errors (`mapping values are not allowed in this context`). Always wrap in double quotes (`run: python -m pip install --only-binary ":all:" yamllint==1.38.0`) or multiline block strings (`run: |`).
4. **Agentic Lock File Exclusions**: Always exclude `*.lock.yml`, `*.lock.yaml`, and `agentics-maintenance.yml` in both path triggers and `find ... -print0` expressions. Generated lock files contain specialized Copilot extensions (`copilot-requests`, `concurrency: queue: max`, `job.workflow_ref`) that fail standard linter schemas.
5. **SonarCloud Analysis Scopes**: Ensure root `.sonarcloud.properties` specifies `sonar.exclusions=docs/**,sphinx_docs_build/**,.github/**` and `sonar.cpd.exclusions=docs/**,sphinx_docs_build/**,.github/**` so workflow files are excluded from static application security analysis.
6. **HTTPS Protocol Enforcement**: Always specify `--proto =https` on `curl` commands in CI workflows to satisfy SonarCloud security rule S6506.
7. **Custom Runner Label Registration**: If workflows use custom or legacy runner labels (such as `macos-13`), configure `.github/actionlint.yaml` with:
   ```yaml
   self-hosted-runner:
     labels:
       - macos-13
   ```
   This prevents actionlint from flagging unknown runner labels.
8. **PowerShell Exit Code Propagation in CI Runners**:
   In Windows GitHub Actions runners executing PowerShell (`pwsh`), running an external command (such as `python -m pytest` or `python setup.py`) does not raise an exception or abort the step on non-zero exit codes. Always append `if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }` after critical execution steps to ensure CI failures are correctly propagated.
9. **Windows SWIG Native DLL Loading & AST Purity**:
   In Python 3.8+ on Windows, `PATH` is ignored by `LoadLibraryEx` during extension import. Use SWIG's `%pythonbegin %{ ... %}` directive in `.i` interface files to register package directories and dependency directories via `os.add_dll_directory` at the top of the generated wrapper module. This guarantees that dependent DLLs (`netsnmp.dll`, `libcrypto.dll`) resolve cleanly on Windows without introducing executable logic or AST violations (`[GEN-05]`) into `__init__.py`.
10. **Windows Universal CRT (ucrtbase) Stream Flushing**:
    On modern Windows runners (Python 3.8-3.13), standard C/C++ I/O streams are managed by `ucrtbase.dll`, not legacy `msvcrt.dll`. Calling `ctypes.cdll.msvcrt.fflush(None)` fails to flush standard output captured by pytest fixtures (`capfd`). Tests capturing C++ standard streams on Windows must flush `ucrtbase` via `ctypes.CDLL("ucrtbase").fflush(None)`.

---

## 20. Automated Pull Request Test & Coverage Commenting Architecture

To provide immediate, collapsible feedback on pull requests and commits without cluttering PR conversation threads, workflows publish structured markdown test reports using dedicated comment action workflows:

### 1. Pytest Coverage Comment Pattern (`MishaKav/pytest-coverage-comment`)
Matrix testing jobs produce both JUnit XML and stdout capture files, uploaded as individual workflow artifacts:
- **Pytest Invocation with Pipeline Exit Code Preservation**:
  ```bash
  # Linux & macOS:
  python -m pytest -v \
    -o junit_family=legacy \
    --cov=pkg --cov-report=xml:coverage_${{ matrix.os }}_${{ matrix.python-version }}.xml \
    --junitxml=test-results_${{ matrix.os }}_${{ matrix.python-version }}.xml \
    --cov-report=term | tee test-outputs_${{ matrix.os }}_${{ matrix.python-version }}.txt
  TEST_EXIT_CODE=${PIPESTATUS[0]}
  if [ -f .coverage ]; then python -m coverage report > pytest-coverage_${{ matrix.os }}_${{ matrix.python-version }}.txt || true; fi
  exit $TEST_EXIT_CODE
  ```
  ```powershell
  # Windows PowerShell:
  python -m pytest -v `
    -o junit_family=legacy `
    --cov=pkg --cov-report=xml:coverage_${{ matrix.os }}_${{ matrix.python-version }}.xml `
    --junitxml=test-results_${{ matrix.os }}_${{ matrix.python-version }}.xml `
    --cov-report=term | Tee-Object -FilePath test-outputs_${{ matrix.os }}_${{ matrix.python-version }}.txt
  $testExitCode = $LASTEXITCODE
  if (Test-Path .coverage) {
    python -m coverage report | Out-File -Encoding utf8 pytest-coverage_${{ matrix.os }}_${{ matrix.python-version }}.txt
  }
  if ($testExitCode -ne 0) { exit $testExitCode }
  ```

- **Artifact Packaging**:
  ```yaml
  - name: Upload Test Results Artifacts
    if: always()
    uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
    with:
      name: pytest-results_${{ matrix.os }}_${{ matrix.python-version }}
      path: |
        test-results_${{ matrix.os }}_${{ matrix.python-version }}.xml
        test-outputs_${{ matrix.os }}_${{ matrix.python-version }}.txt
        pytest-coverage_${{ matrix.os }}_${{ matrix.python-version }}.txt
        coverage_${{ matrix.os }}_${{ matrix.python-version }}.xml
  ```

- **Collapsible Comment Aggregation Job (`comment-pytest-coverage-report`)**:
  ```yaml
  comment-pytest-coverage-report:
    runs-on: ubuntu-latest
    needs: python-matrix-tests
    if: always() && needs.python-matrix-tests.result != 'skipped'
    permissions:
      pull-requests: write
      contents: write
    steps:
      - name: Download Artifacts
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          pattern: pytest-results_*
          merge-multiple: false

      - name: Pytest coverage comment - Native
        id: pytest-coverage-native
        uses: MishaKav/pytest-coverage-comment@9516bf7f32a9229cf18d5e1717ae387c7154f279 # v1.13.0
        with:
          title: Pytest Coverage Report - Native
          unique-id-for-comment: native-tests
          hide-badge: true
          hide-report: true
          create-new-comment: false
          hide-comment: true
          report-only-changed-files: false
          multiple-files: |
            ubuntu-latest - Native - 3.12, pytest-results_ubuntu-latest_3.12/test-outputs_ubuntu-latest_3.12.txt, pytest-results_ubuntu-latest_3.12/test-results_ubuntu-latest_3.12.xml
            windows-latest - Native - 3.12, pytest-results_windows-latest_3.12/test-outputs_windows-latest_3.12.txt, pytest-results_windows-latest_3.12/test-results_windows-latest_3.12.xml

      - name: Strip leading newlines from Native summaryReport
        id: clean-native-report
        env:
          SUMMARY_REPORT: ${{ steps.pytest-coverage-native.outputs.summaryReport }}
        run: |
          python3 -c "
          import os, json
          report = os.environ.get('SUMMARY_REPORT', '')
          try:
              decoded = json.loads(report)
              if isinstance(decoded, str):
                  report = decoded
          except (json.JSONDecodeError, ValueError):
              pass
          lines = [line.strip() for line in report.splitlines() if line.strip()]
          report = '\n'.join(lines)
          delimiter = 'GHADELIMITER'
          with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
              f.write(f'report<<{delimiter}\n')
              f.write(report)
              if not report.endswith('\n'):
                  f.write('\n')
              f.write(f'{delimiter}\n')
          "

      - name: Find existing pytest coverage comment (PR) - Native
        id: find-native-comment
        if: github.event_name == 'pull_request'
        uses: peter-evans/find-comment@v4
        with:
          issue-number: ${{ github.event.pull_request.number }}
          comment-author: 'github-actions[bot]'
          body-includes: '<!-- pytest-coverage-native -->'

      - name: Post collapsible pytest coverage comment (PR) - Native
        if: github.event_name == 'pull_request'
        uses: peter-evans/create-or-update-comment@2b6bdb56ad3073fa0e4beef00447158f55a18414 # v5
        with:
          issue-number: ${{ github.event.pull_request.number }}
          comment-id: ${{ steps.find-native-comment.outputs.comment-id }}
          edit-mode: replace
          body: |
            <!-- pytest-coverage-native -->
            ## Pytest Coverage Report - Native 🐍
            <details>
            <summary>📊 Test Results (click to expand)</summary>

            ${{ steps.clean-native-report.outputs.report }}
            </details>
  ```

### 2. Multi-Environment Comment Separation
- **Native vs. Homebrew vs. Docker**: Separate reports into distinct comments identified by HTML comment sentinels:
  - `<!-- pytest-coverage-native -->` & `## Pytest Coverage Report - Native 🐍`
  - `<!-- pytest-coverage-homebrew -->` & `## Pytest Coverage Report - Homebrew 🐍`
  - `<!-- pytest-coverage-dockerized -->` & `## Pytest Coverage Report - Dockerized Tests 🐍`
  - `<!-- pytest-coverage-macports -->` & `## Pytest Coverage Report - MacPorts 🐍`
- **Markdown Table Integrity**: Blank newlines inside GFM tables cause GitHub markdown parsers to terminate table rendering prematurely. Always clean `summaryReport` using a Python filter step (`lines = [line.strip() for line in report.splitlines() if line.strip()]`).

### 3. Native C++ Test Reporting (`publish-unit-test-result-action`)
For native C++ suites compiled with CMake or Meson (generating GoogleTest JUnit XML):
- Upload JUnit XML artifacts:
  ```yaml
  - name: Upload C++ test results artifacts
    if: always()
    uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2
    with:
      name: cpp-test-results-${{ matrix.os }}
      path: build/meson-logs/testlog.junit.xml
  ```
- Publish results using `EnricoMi/publish-unit-test-result-action@7622c5bf3d112a72ab4fa3951c2aa5723d8ab92d # v2`:
  ```yaml
  comment-cpp-test-report:
    runs-on: ubuntu-latest
    needs: cpp-meson-tests
    permissions:
      pull-requests: write
      contents: write
      checks: write
    if: always() && github.event_name == 'pull_request' && needs.cpp-meson-tests.result != 'skipped'
    steps:
      - name: Download All Test Results
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2
        with:
          pattern: cpp-test-results-*
          path: test-results

      - name: Publish C++ Test Results
        uses: EnricoMi/publish-unit-test-result-action@7622c5bf3d112a72ab4fa3951c2aa5723d8ab92d # v2
        with:
          files: test-results/**/*.xml
          check_name: C++ Test Results - Native
          comment_title: C++ Test Results - Native
  ```

---

### 21. Codecov JavaScript Bundle Analysis Setup

Codecov's JavaScript Bundle Analysis tracks bundle size changes, asset breakdowns, and module weights directly on Pull Requests to safeguard against bundle regressions:

1. **`codecov.yml` Configuration**:
   ```yaml
   bundle_analysis:
     warning_threshold: "5%"
     status: "informational"

   comment:
     layout: "header, diff, flags, components, files, footer"
     require_bundle_changes: true
     bundle_change_threshold: "1Kb"
   ```

2. **GitHub Actions Upload Step**:
   Run `@codecov/bundle-analyzer` on the frontend assets directory during a single representative matrix job (e.g. Linux with newest Python/Node.js):
   ```yaml
   - name: Upload JavaScript Bundle Analysis to Codecov
     if: runner.os == 'Linux' && matrix.python-version == '3.13'
     env:
       CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}
     run: |
       npx --yes @codecov/bundle-analyzer <assets_or_dist_dir> --bundle-name=<bundle-identifier> --upload-token="${CODECOV_TOKEN}" || true
   ```

---

### 22. Homebrew Local Tap Formula Testing (`Homebrew/brew` 7.0.14+)

`Homebrew/brew` 7.0.14+ (`Homebrew/brew#24442`) permanently enforces `HOMEBREW_FORBID_PACKAGES_FROM_PATHS` (ignoring `HOMEBREW_DEVELOPER=1`), so `brew install --formula /tmp/<formula>.rb` fails with `No available formula with the name "<pkg>".`:

- Always stage modified or local formulas in a temporary local tap via `brew tap-new --no-git local/<pkg>`, copy the formula to `$(brew --repository)/Library/Taps/local/homebrew-<pkg>/Formula/<pkg>.rb`, and install `local/<pkg>/<pkg>` (see `carlkidcrypto/ezsnmp#1492`).
- Note: Among `carlkidcrypto` repositories, only `ezsnmp` maintains a Homebrew `Formula/` (`ezsnmp.rb`); sibling repos only install upstream Homebrew build dependencies.

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





