# Workflow Optimization, Docs, Dependabot & Syntax Validation

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
- **Avoid Restrictive `paths:` on General Test Workflows**: For repo-wide test workflows (`tests.yml`), prefer `paths-ignore:` targeting pure documentation (`**/*.md`, `**/*.rst`, `docs/**`, `sphinx_docs_build/**`, `.github/aw/**`) rather than restrictive `paths:` whitelists that accidentally skip dependency manifests (`docker/requirements.txt`, `docker/package.json`), configs, or scripts.
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
4. **Automatic Analysis Default-Branch Requirement**: SonarQube Cloud Automatic Analysis strictly reads `.sonarcloud.properties` from the default branch (`main`) and **completely ignores** `sonar-project.properties`. If a PR fails the Quality Gate due to generated docs duplication (>3%), security hotspots, or reliability issues (`_build/**,docs/**` for `carlkidcrypto.github.io`, `docs/**` elsewhere), ensure `.sonarcloud.properties` exists on `main`, then rebase or merge `main` into the PR branch to trigger a clean re-analysis.
5. **CodeQL Default Setup vs. Custom Workflows**: Repositories using GitHub Default Setup for CodeQL reject custom SARIF uploads with `CodeQL analyses from advanced configurations cannot be processed when the default setup is enabled`. Never add custom CodeQL workflows (`quality_codeql.yml`) to repositories configured with Default Setup.

---

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
11. **Windows Runner PowerShell vs. Bash Path Mangling (`${{ github.workspace }}`)**:
    On Windows runners, `${{ github.workspace }}` expands with Windows backslashes (e.g. `D:\a\repo\repo`). Passing it inside a step with `shell: bash` causes bash to interpret backslashes as escape sequences (`\a` -> ASCII BEL `\x07`, `\p` -> `p`), silently corrupting compiler include paths and MSBuild properties (`-p:GeneratedSourcesDir`). Separate Windows test steps (`if: runner.os == 'Windows'`) using the default Windows PowerShell (`pwsh`) runner without `shell: bash`, and use forward slashes or double backslashes when passing paths to CLI tools.
12. **macOS Package Manager Version Detection, SDK Header Fallback & MacPorts Caching**:
    - **Multi-Segment Versions**: MacPorts versions often contain 4+ dot-separated numeric segments (e.g. `net-snmp @5.9.5.2_0+perl5_34+ssl`). Use `\d+(?:\.\d+)*` rather than fixed 3-part regexes (`\d+\.\d+\.\d+`).
    - **Prevent Apple SDK 5.6 Header Fallback**: If `/opt/local/include` (MacPorts) or `/opt/homebrew/include` (Homebrew) is missing from compiler include paths, clang++ silently falls back to Apple SDK Net-SNMP 5.6 headers under `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/net-snmp`, causing misleading undeclared identifier errors (e.g. `netsnmp_cleanup_session`). Always add the active package manager's include and lib paths to `incdirs` and `libdirs`.
    - **MacPorts Cache & Timeout**: Cold `port -N install net-snmp openssl3` runs take ~20–25 minutes; set `timeout-minutes: 45`. Never partition `/opt/local/var/macports/software` and `distfiles` caches by `${{ matrix.python-version }}` so subsequent Python matrix jobs reuse compiled C archives (~5 min instead of ~25 min).

---
