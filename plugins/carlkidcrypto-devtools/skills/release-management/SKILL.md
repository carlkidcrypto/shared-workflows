---
name: release-management
description: Guidelines and procedures for preparing version bumps and releases across carlkidcrypto repositories (purpleair_api, purpleair_data_logger, ezsnmp, ezsnmp_data_logger, etc.). Enforces maintainer-only merging and release publishing, CalSemVer standards, security vulnerability resolution, and software requirements specification synchronization.
---

# Release Management Procedure & Maintainer Boundaries

This skill defines the standard procedure for preparing software releases across the `carlkidcrypto` ecosystem (`purpleair_api`, `purpleair_data_logger`, `purpleair-matterbridge`, `ezsnmp`, `ezsnmp_data_logger`, `os-specific-runner`, etc.).

---

## ⚠️ Critical Rule: Maintainer Boundaries

> [!CAUTION]
> **NEVER merge pull requests or publish releases.**
> Merging PRs into `main` and creating/publishing GitHub releases or PyPI/npm/NuGet distribution packages is strictly reserved for the **maintainer (the user, @carlkidcrypto)**.
>
> **The agent must NEVER:**
> - Merge release PRs (`gh pr merge`).
> - Create git release tags (`git tag <version>`).
> - Publish GitHub releases (`gh release create`).
> - Trigger deployment workflows or PyPI/npm/NuGet publishing (`gh workflow run build_and_publish_to_pypi.yml` or `publish_npm`).
> - Ask or prompt the user if the agent should merge or publish the release.

---

## Multi-Agent Concurrency & Git Worktree Isolation

> [!IMPORTANT]
> **Always isolate tasks using Git Worktrees.**
> Multiple agents (the human maintainer, background agentic workflows, Dependabot, Copilot, and other agentic assistants) frequently operate simultaneously across local workspaces. Switching branches or leaving unstaged changes in the primary repo clone (`<workspace_root>/<repo>`) leads to branch flapping, corrupted working states, git stash collisions, and broken builds.
>
> **Standard Worktree Rules & Lifecycle**:
> 1. **Discover Active Worktrees**: Run `git worktree list` first to discover existing active worktrees, their directory paths, and active branches before switching or adding, preventing branch collisions (`fatal: '<branch>' is already used by worktree at ...`).
> 2. **Keep Primary Clone Clean**: Never checkout feature branches or leave dirty working trees in `<workspace_root>/<repo>`. The primary checkout must stay clean on the default branch (`main`).
> 3. **Create Dedicated Worktree in Sibling Directory**: Place dedicated worktrees in sibling directories (e.g. `<workspace_root>/<repo>-<task-name>` or `<workspace_root>/wt-<repo>-<task-name>`). Never create worktrees in `/tmp` or `~/.gemini/` unless explicitly requested.
>    ```bash
>    # Fetch latest remote references first:
>    git fetch origin
>
>    # For a new feature, fix, or release branch from origin/main:
>    git worktree add -b <branch-name> <workspace_root>/wt-<repo>-<task-name> origin/main
>    cd <workspace_root>/wt-<repo>-<task-name>
>
>    # Or for checking out an existing branch:
>    git worktree add <workspace_root>/wt-<repo>-<task-name> <branch-name>
>    cd <workspace_root>/wt-<repo>-<task-name>
>    ```
> 4. **Execute In-Tree Only**: Run all dependency installations (`npm install`, `pip install --only-binary ":all:" ...`), code generation (SWIG), builds, tests, formatters (`black`, `prettier`, `csharpier`), targeted staging (`git add <files>`), and `gh pr create` strictly inside the worktree directory.
> 5. **Handle Concurrent Remote Syncs**: Sibling background agentic workflows (`sync_open_prs_with_main`) automatically push merges from `main` into open PR branches. If a push is rejected, run `git pull --rebase origin <branch-name>` inside the worktree before retrying.
> 6. **Handle Cloud Sync Ref Collisions (`main (1)`)**: File synchronization systems (iCloud Drive, OneDrive, Dropbox) can duplicate ref files in `.git/refs/` with copy suffixes (such as `main (1)` or `origin/main (1)`). Git interprets these as literal ref names, triggering `fatal: bad object refs/heads/main (1)` or fetch failures (`error: ... did not send all necessary objects`). Identify and clean them via `find .git/refs -name "* (*" -delete`.
> 7. **Handle Maintainer-Merged PR Follow-ups**: If an open PR has already been merged into `main` by the maintainer while follow-up commits are prepared, do not force-push over merged commits. Fetch `origin`, branch cleanly from `origin/main` (`git checkout -b <fix-branch> origin/main`), cherry-pick the required commit (`git cherry-pick <sha>`), and submit a new PR cleanly.
> 8. **Respect Other Agents & Clean Pruning**: Never modify or remove another agent's active worktree. Once your PR is submitted or merged, cleanly prune the worktree:
>    ```bash
>    git worktree remove <workspace_root>/wt-<repo>-<task-name>
>    git worktree prune
>    ```
>    Verify `git worktree list` confirms the worktree was cleanly detached without dangling metadata.

---

## Versioning Standards: CalSemVer & SemVer

1. **SemVer-Compliant Calendar Versioning (CalSemVer)**:
   - **Format**: `YYYY.M.D` for stable releases (e.g. `2026.11.3`).
   - **Pre-releases**:
     - Python (PEP 440): `YYYY.M.DaN` (e.g. `2026.11.3a0`, `2026.11.3b1`, `2026.11.3rc1`).
     - npm (SemVer 2.0.0): `YYYY.M.D-N` or `YYYY.M.D-alpha.N` (e.g. `2026.11.3-0`, `2026.11.3-alpha.0`).
   - **No Leading Zeroes**: Date components must never include leading zeroes (`2026.11.3`, **never** `2026.11.03`).
   - **Transition Pre-requisite**: Repositories transitioning to CalSemVer must complete and ship any pending standard Semantic Versioning releases (e.g. `v1.1.0` in `purpleair-matterbridge`, `v2.5.0` in `os-specific-runner`) before switching to CalSemVer.
   - **Multi-Language Manifest Version Mapping**:
     - Python & Meson: PEP 440 `YYYY.M.DaN` (`setup.cfg`, `pyproject.toml`, `meson.build`, `python/meson.build`, `uv.lock`).
     - JavaScript / Node.js: SemVer 2.0.0 `YYYY.M.D-alpha.N` (`package.json`, `package-lock.json`).
     - C# (.NET) / NuGet: SemVer 2.0.0 `YYYY.M.D-alpha.N` (`*.csproj`).
     - Documentation: `release = "vYYYY.M.DaN"` in `conf.py`, download shields in `README.rst`.
     - WinGet manifests: `tools/generate_winget_manifest.py` fallback default aligned to SemVer 2.0.0.
   - **Prerelease Tag Validation in CI Workflows**:
     - Workflows validating package versions against Git release tags (e.g. `build_and_publish_to_npm.yml`) must regex-map PEP 440 prereleases (`aN` -> `-alpha.N`, `bN` -> `-beta.N`, `rcN` -> `-rc.N`). Otherwise, Git release tags like `v2026.11.11a0` fail validation against SemVer package versions like `2026.11.11-alpha.0`.

2. **SWIG & Multi-Language Core Scope**:
   - Multi-language bindings across the ecosystem target strictly **4 languages**:
     1. **Python**
     2. **JavaScript**
     3. **C#**
     4. **Go**
   - Java is explicitly excluded.

3. **Specification Collision Protection**:
   - `release_tools/bump_version.sh` must exclude external specification files and references (such as Connectivity Standards Alliance **Matter 1.5.1** specifications) to prevent accidental text substitution during version bumps.

---

## Security Vulnerability & Dependabot Resolution

When preparing a release or resolving repository security advisories:

1. **Audit Open Alerts**:
   ```bash
   gh api 'repos/<owner>/<repo>/dependabot/alerts?state=open' --jq '.[] | {number: .number, dependency: .dependency.package.name, severity: .security_advisory.severity, summary: .security_advisory.summary}'
   ```

2. **Transitive npm Dependency Upgrades**:
   - When a transitive advisory (e.g. `minimatch` in `test-exclude` / `@jest/reporters`) has a published patch:
     Add an explicit override to root `package.json`:
     ```json
     "overrides": {
       "minimatch": "^11.0.4"
     }
     ```
   - Run `npm install` and verify `package-lock.json` resolves only the patched version across all dependency paths (`npm ls <dependency>`).

3. **Unpatched devDependency Handling (`first_patched_version: null`)**:
   - For low-severity advisories without an upstream patch (e.g. `deepmerge` in `jest-config`):
     1. Verify the dependency is NOT compiled into the production bundle (`dist/index.js` or wheel) via `grep -i <dependency> dist/index.js`.
     2. Confirm it is isolated to development test harness configurations and does not process untrusted user input.
     3. Dismiss via GitHub API with an architectural rationale:
        ```bash
        gh api -X PATCH repos/<owner>/<repo>/dependabot/alerts/<number> \
          -f state="dismissed" \
          -f dismissed_reason="tolerable_risk" \
          -f dismissed_comment="Transitive devDependency inside test configuration merging. Not present in runtime action bundle (dist/index.js), never exposed to untrusted user input, and no upstream patch has been released yet (first_patched_version is null)."
        ```

4. **Multi-Ecosystem Dependabot Configuration**:
   - Every repository must configure `.github/dependabot.yml` covering `github-actions`, `pip` (root and docs), `npm`, `nuget`, and `gomod` where applicable, standardizing commit message prefixes (`chore(deps)`).

5. **`node-gyp` & Transitive Resolution Engine Protection**:
   - Upgrading `node-gyp` to major version 13 (`^13.0.0` / `^13.1.0`) introduces `undici@8` and enforces engine constraint `node: "^22.22.2 || ^24.15.0 || >=26.0.0"`.
   - On Node.js 18 or 20 runners, `undici` fails during `node-gyp rebuild` with `TypeError: Cannot read properties of undefined (reading 'bind')`.
   - For repositories testing or supporting Node.js 18+ (e.g. 18.x, 20.x, 22.x, 24.x), pin or align `node-gyp` to `^11.5.0` (which uses patched `tar@7.5.22` with zero deprecation warnings, excludes `undici`, and supports Node >= 18.17.0 and >= 20.5.0).

6. **SonarQube Cloud Analysis Scope & Path Traversal Protection (Rule S8707)**:
   - Exclude internal developer automation and release scripts (`tools/**`, `release_tools/**`) alongside `docs/**`, `sphinx_docs_build/**`, and `.github/**` in root `.sonarcloud.properties`.
   - In manifest generator scripts (`tools/generate_winget_manifest.py`), sanitize CLI parameters using strict regexes (`^[a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)+$`), canonicalize target directories with `.resolve()`, and verify paths remain strictly within target boundaries (`path.resolve().is_relative_to(target.resolve())`) before executing file writes to eliminate CWE-20 and CWE-22 agentic path injection vulnerabilities.

---

## Software Requirements Specification Standards

Whenever new architectural capabilities, CI/CD features, or release configurations are added:
1. **Traceability**: Add or update requirement tags in `sphinx_docs_build/source/software_requirements.rst` (e.g. `[CICD-xx]`, `[CORE-xx]`).
2. **Single Responsibility & Anti-Double-Stacking**:
   - Each requirement **Shall** test exactly one feature, function, or use case of the code.
   - **Never** combine multiple distinct features, operations, or target ecosystems into a single requirement identifier (e.g. do not combine PyPI and npm distribution, C++ and Python formatting, multiple storage sinks, or separate GUI tabs into one requirement).
   - Decompose compound specifications into atomic, individually testable requirements.
3. **Formatting**:
   - Strictly maximum **80 characters** per line.
   - Separate every distinct requirement block with a **blank line**.
   - Clear, unambiguous phrasing for human auditability.
4. **State Sync**: Documentation must match the current state of code before PR creation.

---

## Standardized Release Tools Directory & Scripts (`release_tools/`)

Every repository across the `carlkidcrypto` ecosystem (`purpleair_api`, `purpleair_data_logger`, `purpleair-matterbridge`, `ezsnmp`, `ezsnmp_data_logger`, `os-specific-runner`, etc.) maintains a standardized `release_tools/` directory at the repository root.

### Structure & Canonical Files
```
release_tools/
├── bump_version.sh   # Primary version bump and verification engine
├── release.sh        # Symlink to bump_version.sh (release.sh -> bump_version.sh)
└── README.md         # Documentation of touchpoints, CLI flags, and checklists
```

### Script Capabilities & Command-Line Usage
Always execute release version bumps using `./release_tools/bump_version.sh` or `./release_tools/release.sh`:

```bash
# Preview changes without altering working tree:
./release_tools/bump_version.sh --dry-run <new_version>

# Bump version and automatically execute code formatting (black), Sphinx docs (-W), and tests:
./release_tools/bump_version.sh --verify <new_version>

# Standard bump with auto-detection of current version from setup.cfg / meson.build:
./release_tools/bump_version.sh <new_version>

# Explicitly specifying old version:
./release_tools/bump_version.sh <new_version> <old_version>
```

### Automation Architecture & Guarantees
1. **Atomic Multi-Language Touchpoint Sync**:
   - Updates Python (`setup.cfg`, `pyproject.toml`, `uv.lock`), C++/Meson (`meson.build`, `python/meson.build`), Node.js (`package.json`, `package-lock.json`), C# (`*.csproj`), Sphinx (`conf.py`), and README download shields in a single atomic pass.
2. **Multi-Language Version Translation**:
   - Built-in `to_semver()` helper converts PEP 440 prereleases (`YYYY.M.DaN`) into SemVer 2.0.0 (`YYYY.M.D-alpha.N`) for npm and NuGet manifests.
3. **Pre-flight & Post-flight Audits**:
   - Confirms expected current version exists before editing.
   - Runs post-replacement git grep audit verifying zero stale old-version references remain in active tracked files.
4. **Collision & Artifact Protection**:
   - Automatically excludes `CHANGELOG.md` (managed by agentic changelog workflows), `docs/**` (built HTML artifacts), test suites, and external specifications (such as CSA Matter 1.5.1).
5. **Agent Enforcement**:
   - **Never manually edit version strings file-by-file.** Always run `./release_tools/bump_version.sh` (or `./release_tools/release.sh`) to guarantee complete synchronization and automated verification across the entire repository.

---

## Standard Agent Release Preparation Workflow

When requested to prepare a release:

1. **Environment Setup**:
   - Ensure CLI paths are set (`export PATH="/opt/homebrew/bin:$PATH"`).
   - Python Environment: Sphinx 9.2.0+ strictly requires Python >= 3.13. Ensure local doc builds and `bump_version.sh` use a Python 3.14 virtual environment (`python3.14.venv` or `.venv`).

2. **Create Release Branch via Git Worktree**:
   - Always isolate work from other active agents by adding a dedicated Git worktree:
     ```bash
     git worktree add -b release/v<version> ../<repo>-release-v<version> origin/main
     cd ../<repo>-release-v<version>
     ```
   - Never switch branches or leave dirty states in the primary checkout root (`<workspace_root>/<repo>`).

3. **Execute Version Bump & Touchpoint Sync**:
   - Run `./release_tools/bump_version.sh <version>` (or pass dependency version e.g. `./release_tools/bump_version.sh <version> <dep_version>`).
   - Verify package configs (`setup.cfg`, `pyproject.toml`, `package.json`), docs config (`conf.py`), READMEs, manifests, and test requirements.
   - Synchronize CI matrices (`tests.yml`, `sphinx_build.yml`, `verify_syntax.yml`, `.github/actions/build-distribution`). Ensure `sphinx_build.yml` specifies `python-version: "3.14"` and includes `pull_request` triggers targeting `main`.
   - Ensure `.nojekyll` is in place for GitHub Pages documentation deployments.
   - Update `sphinx_docs_build/source/software_requirements.rst` adhering to the <= 80 chars per line rule.

4. **Verify Locally**:
   - Formatting check (`black --check .` / `npm run format:check`).
   - Linter (`yamllint -c .yamllint .github/workflows/*.yml`, `oxlint`, `flake8`).
   - Typechecking & build (`npm run typecheck`, `npm run build`, `tsc`, `meson compile`).
   - Test suite execution (`pytest`, `unittest`, `vitest`, GoogleTest).
   - Documentation build with zero warnings (`sphinx-build -b html -W` or `make html SPHINXOPTS="-W"` with Python 3.14).

5. **Commit, Push & Open Pull Request**:
   - Use targeted `git add <files>` (never blanket `git add .` or `-A`).
   - Commit changes: `git commit -m "chore(release): bump version to <version> ..."`
   - Push to origin: `git push -u origin release/v<version>`
   - Open Pull Request targeting `main`: `gh pr create ...`

6. **Monitor CI & Report Status**:
   - Inspect CI check status (`gh pr checks <PR_NUMBER>`).
   - Present a concise summary of the PR and CI check status to the maintainer.
   - **Stop and hand off to the maintainer.**

7. **Mandatory Review Comment & Mail Item Replies**:
   - When review feedback (human or automated Copilot review comments) is addressed:
     - Implement fixes and commit using targeted staging (`git add <files>`).
     - Post threaded replies to **every** review comment thread on GitHub:
       ```bash
       gh api repos/<owner>/<repo>/pulls/<pr>/comments \
         -F in_reply_to=<comment_id> \
         -f body="Addressed in commit \`<commit_sha>\`: <description>"
       ```
     - Always include both the exact commit hash and a summary of the fix.

8. **Post-Merge Test Deployment Verification & Staged Rollout**:
   - Following the maintainer's merge of the release PR to `main`, verify the automated test deployment to TestPyPI (`build_and_publish_to_test_pypi.yml`) triggers on `push: branches: [main]` and passes all matrix runners.
   - If a transient GitHub Actions infrastructure interruption occurs (dropped queued jobs with `runner_id: 0`), use targeted job recovery (`POST /actions/runs/<run_id>/rerun-failed-jobs`) to resume only interrupted matrix jobs.
   - Once TestPyPI verifies the complete wheel matrix and package distribution, hand off to the maintainer to publish the formal release tag (`vYYYY.M.D`).
   - For multi-ecosystem repositories (Python, npm, NuGet, WinGet), execute and verify registry deployments one by one.
   - **Post-Release Versioned Documentation & Prerelease Pruning**: The automated `sphinx_docs_build_release` workflow builds versioned documentation into `docs/html_v<version>/`. When a new stable release (e.g. `2.5.0` or `2026.11.4`) is published, its documentation replaces and retires all prereleases (`alpha`, `beta`, `rc`) belonging to that version series (e.g., `html_v2.5.0a0`–`html_v2.5.0b0` are removed from `docs/` and from the landing page version selector). Prereleases remain in `docs/` only while no stable release has been published for that series. Versioned documentation directory names must always normalize to lowercase `html_v<version>`.

9. **Multi-Ecosystem Registry Onboarding & OIDC-First Publishing**:
   - **Prefer OIDC Trusted Publishing Over Static Tokens by Default**: All publishing pipelines for **PyPI**, **TestPyPI**, **npm**, and **NuGet** must default to keyless OIDC Trusted Publishing (`permissions: id-token: write`, `contents: read`). For PyPI and TestPyPI (`reusable_pypi_publish.yml`), use OIDC exclusively without `PYPI_API_TOKEN` / `secrets.pypi-token` fallbacks. For npm and NuGet, rely on OIDC by default and avoid static API tokens after initial package bootstrap.
   - **PyPI vs npm Trusted Publishing Bootstrap**:
     - *PyPI*: Supports "Pending Publishers", allowing OIDC registration before the package exists.
     - *npm*: Requires unscoped packages to exist on npmjs.com before trusted publishers can be configured. The initial package release must be bootstrapped via `NPM_TOKEN` (or maintainer local CLI publish `npm publish --access public`).
     - Once published, configure GitHub Actions Trusted Publisher at `https://www.npmjs.com/package/<pkg>/access` (owner: `carlkidcrypto`, repository, workflow filename, environment).
     - Subsequent releases publish seamlessly via OIDC token exchange with `--provenance`.
   - **NuGet.org Trusted Publishing**:
     - Supports keyless publishing via OpenID Connect (`nuget/login@v1`).
     - Configure Trusted Publishing policy under NuGet.org Account Settings -> Trusted Publishing for repository owner `carlkidcrypto` and workflow `build_and_publish_to_nuget.yml`.
     - Pass `--skip-duplicate` to ensure idempotent pushes.
   - **Safe Auth Token Injection & Idempotency**: Standardize npm publishing on Node 24 (`actions/setup-node@v7` with `node-version: 24`, pre-provisioning npm 11.19.1+ with native OIDC support) and always specify `registry-url: https://registry.npmjs.org` in `actions/setup-node`. Never set `NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}` unconditionally in workflow steps; empty tokens cause npm to send an empty bearer header and throw `ENEEDAUTH` rather than negotiating OIDC credentials. Conditionally export `NODE_AUTH_TOKEN` inside the publish script only when `NPM_TOKEN` is non-empty (`if [ -n "${{ secrets.NPM_TOKEN }}" ]; then export NODE_AUTH_TOKEN="${{ secrets.NPM_TOKEN }}"; fi`), maintaining pure OIDC as the default. Always pre-check or use duplicate skipping flags (`--skip-duplicate`, `npm view`) so immutable registries do not fail repeated runs.
   - **npm Packaging Hard-Link Protection (Rule E415)**: For native Node.js addons compiled during CI, `package.json` must explicitly define `"files": [...]` (including `index.js`, compiled `.node` addons in `build/Release/`, and dynamic libraries) and include a `.npmignore` file excluding `build/Release/obj.target`, `build/Release/.deps`, and temporary build archives. In Linux, GCC / node-gyp creates hard links in `.deps/` and object trees; omitting `files` causes `npm publish` to pack the entire build directory with hard links, triggering `npm error 415 Unsupported Media Type - Hard link is not allowed` at the npm registry. Additionally, set `"install": "node -e \"\""` and remove `"gypfile": true` so end users installing from npm do not attempt in-tree node-gyp rebuilds looking for source files outside the package.
   - **cibuildwheel Multi-OS Runner Matrix Standards**: Standardize wheel packaging runners across ecosystems on `ubuntu-latest`, `windows-latest`, and `macos-latest` (Apple Silicon arm64). Avoid deprecated `macos-13` (Intel) or retired `macos-14-arm64-us-default`. On Linux, standardize on `manylinux_2_28` (AlmaLinux 8) to avoid EOL CentOS 7 dead mirror failures in `manylinux2014`, and equip `CIBW_BEFORE_ALL_LINUX` with resilient multi-package-manager fallbacks (`dnf` / `yum` / `apt-get`). On Windows, constrain builds to `CIBW_ARCHS_WINDOWS: "AMD64"` when external dependencies (like libcurl via Chocolatey) are 64-bit only.
   - **Multi-Ecosystem Gating**: For pending tokens (`NUGET_API_KEY`, `WINGET_ACC_TOKEN`), ensure packaging steps run and upload artifacts before publish steps gracefully skip with diagnostic warnings.
   - **WinGet Community Repository Publishing (`wingetcreate`) [FUTURE / WIP]**:
     - WinGet automated community package submission is marked as **FUTURE / WIP** pending maintainer credentials provisioning (GitHub PAT with `public_repo` scope for submitting PRs to `microsoft/winget-pkgs`).
     - Generate multi-file manifests conforming to WinGet specification 1.6.0 in canonical directory hierarchy `manifests/{first-letter}/{Publisher}/{AppName}/{Version}/`.
     - Download official `wingetcreate.exe` from `https://aka.ms/wingetcreate/latest` and submit PR via `wingetcreate.exe submit "<path-to-manifest.yaml>" --token "$token" --no-open` with fallback to `wingetcreate.exe update`.
     - Support token secret aliases: `WINGET_CREATE_PAT`, `WINGET_TOKEN`, `WINGET_ACC_TOKEN`. Workflow gracefully skips PR submission with diagnostic notice when secrets are unconfigured.
   - **Standard Package Naming Across Ecosystems**: For `ezsnmp_data_logger`, standardize package, executable, and installer names on **`EzSnmpDataLogger`** (e.g. NuGet `EzSnmpDataLogger`, WinGet `carlkidcrypto.EzSnmpDataLogger`, Windows executable `EzSnmpDataLogger.exe`, Inno Setup installer `EzSnmpDataLogger-Windows-x64-Setup.exe`, macOS DMG `EzSnmpDataLogger-macOS-<arch>.dmg`, macOS bundle `EzSnmpDataLogger.app`). Avoid the 'Studio' suffix in package/installer/executable filenames.
   - **Multi-Platform Desktop Distributions & Asset Publishing**:
     - For desktop-enabled projects, package across Linux (`.deb`, `.rpm`, `.tar.gz`), Windows (Inno Setup `Setup.exe`, `.zip`), and macOS (`.dmg`, `.app`).
     - In release asset publishing jobs, ensure `actions/checkout` is executed, set `GH_REPO: ${{ github.repository }}`, and supply `--repo "${{ github.repository }}"` explicitly to `gh release view` and `gh release upload` to eliminate repository resolution errors.

10. **Repository Metadata & Discoverability Management**:
    - Apply repository topics, descriptions, and homepage URLs via GitHub CLI:
      ```bash
      gh repo edit <owner>/<repo> --add-topic <t1> --add-topic <t2> -d "..." -h "..."
      ```
      (bypasses the GitHub web UI limitation where pasted comma-delimited strings fail to split into individual topic tags).
    - Maximize repository descriptions to utilize the full 350-character budget (targeting 345–350 characters), detailing core operations, C++/SWIG backends, Python runtime support, and precompiled binary wheels.
    - Enforce up to 20 official, high-traffic, hyphenated, lowercase topic tags. Enable **Releases** and **Packages** in the repository sidebar.

11. **Repository Metadata & Topic Baseline Inventory (7 Active Repos)**:
    - Baseline established on 2026-11-04 for discoverability, search indexing, and traffic analytics.

    | Repository | Desc Len | Homepage | Topics (20/20) |
    | :--- | :---: | :--- | :--- |
    | `carlkidcrypto/ezsnmp` | 350 | `https://carlkidcrypto.github.io/ezsnmp/` | `c-plus-plus`, `devops`, `easysnmp`, `ezsnmp`, `infrastructure-monitoring`, `mib`, `net-snmp`, `network-automation`, `network-management`, `network-monitoring`, `pysnmp`, `python-snmp`, `python3`, `snmp`, `snmpv1`, `snmpv2c`, `snmpv3`, `swig`, `sysadmin`, `telemetry` |
    | `carlkidcrypto/ezsnmp_data_logger` | 350 | `https://carlkidcrypto.github.io/ezsnmp_data_logger/` | `c-plus-plus`, `cli`, `data-logger`, `ezsnmp`, `gui`, `net-snmp`, `network-automation`, `network-monitoring`, `observability`, `postgresql`, `prometheus`, `python3`, `snmp`, `snmpv1`, `snmpv2c`, `snmpv3`, `sqlite3`, `swig`, `telemetry`, `timescaledb` |
    | `carlkidcrypto/purpleair_api` | 350 | `https://carlkidcrypto.github.io/purpleair_api/` | `air-quality`, `c-plus-plus`, `calsemver`, `csharp`, `environmental-sensing`, `golang`, `home-automation`, `iot`, `matter`, `nodejs`, `pm25`, `purpleair`, `purpleair-api`, `python3`, `rest-api`, `sensors`, `smart-home`, `swig`, `telemetry`, `time-series` |
    | `carlkidcrypto/purpleair_data_logger` | 350 | `https://carlkidcrypto.github.io/purpleair_data_logger/` | `air-quality`, `data-logger`, `environmental-sensing`, `grafana`, `home-automation`, `iot`, `loki`, `matter`, `pm25`, `postgresql`, `prometheus`, `purpleair`, `purpleair-api`, `python3`, `sensors`, `smart-home`, `sqlite3`, `telemetry`, `time-series`, `timescaledb` |
    | `carlkidcrypto/purpleair-matterbridge` | 350 | `https://carlkidcrypto.github.io/purpleair-matterbridge/` | `air-quality`, `alexa`, `apple-home`, `aqi`, `calsemver`, `environmental-sensing`, `google-home`, `home-assistant`, `home-automation`, `iot`, `matter`, `matterbridge`, `nodejs`, `pm25`, `purpleair`, `sensors`, `smart-home`, `telemetry`, `typescript`, `voc` |
    | `carlkidcrypto/os-specific-runner` | 350 | `https://carlkidcrypto.github.io/os-specific-runner/` | `actions`, `automation`, `calsemver`, `ci-cd`, `continuous-integration`, `cross-platform`, `developer-tools`, `devops`, `freebsd`, `github-actions`, `linux`, `macos`, `matrix-builds`, `multi-os`, `nodejs`, `runner`, `shell-scripts`, `typescript`, `windows`, `workflow-automation` |
    | `carlkidcrypto/carlkidcrypto.github.io` | 350 | `https://carlkidcrypto.github.io/` | `air-quality`, `automation`, `blog`, `calsemver`, `ci-cd`, `cpp17`, `developer`, `devops`, `embedded-systems`, `github-actions`, `iot`, `matter`, `open-source`, `portfolio`, `python`, `sensors`, `snmp`, `swig`, `systems-engineering`, `telemetry` |

    - **Exact Baseline Descriptions (All 350/350 chars)**:
      - `ezsnmp`: `"A blazingly fast, Pythonic SNMP library based on official Net-SNMP bindings (5.10) with modern C++17 & SWIG. Active fork of Easy SNMP supporting Python 3.11+, SNMPv1/v2c/v3, and cross-platform network telemetry. Features high-speed GET, SET, WALK, and BULKWALK queries, MIB translation, and precompiled binary wheels across Linux, macOS, and Windows."`
      - `ezsnmp_data_logger`: `"Self-contained C++17 SNMP telemetry engine & data logger powered by ezsnmp (Net-SNMP 5.10). Features SWIG bindings for Python 3.11+, Node.js N-API, C# .NET 8+, and Go, plus an automation CLI and Desktop/Web GUIs. Streams SNMPv1/v2c/v3 GET, SET, and BULKWALK metrics to SQLite3, CSV, JSONL, PostgreSQL, TimescaleDB, and a built-in Prometheus exporter."`
      - `purpleair_api`: `"Multi-language PurpleAir API client powered by a shared C++17 core with SWIG bindings for Python 3.11+, Node.js N-API, C# .NET 8+, and Go. Supports official cloud and local sensor APIs, CSA Matter 1.5.1 Air Quality data translation, historical telemetry, and real-time sensor polling with prebuilt binary wheels for Linux, macOS, and Windows systems."`
      - `purpleair_data_logger`: `"High-performance air quality telemetry logger for PurpleAir sensors. Streams real-time and historical sensor data from cloud and local-network APIs to TimescaleDB PostgreSQL, SQLite3, CSV files, and Grafana Loki. Features Prometheus metrics exports and Matter 1.5.1 JSON formatting for air quality monitoring, environmental research, and smart homes."`
      - `purpleair-matterbridge`: `"Official Matterbridge plugin bridging PurpleAir sensors into Apple Home, Google Home, Amazon Alexa, and Home Assistant via CSA Matter 1.5.1. Exposes real-time PM2.5, PM10, AQI, temperature, relative humidity, pressure, and VOC clusters from local and cloud PurpleAir Matter JSON endpoints for smart home automations and indoor air quality monitoring."`
      - `os-specific-runner`: `"Cross-platform GitHub Action executing OS-specific shell commands tailored to each runner platform. Consolidates fragmented if-conditional steps across Linux, macOS, Windows, FreeBSD, OpenBSD, SunOS, and AIX into a single unified step. Eliminates workflow boilerplate, accelerates matrix builds, and optimizes multi-OS GitHub Actions CI/CD pipelines."`
      - `carlkidcrypto.github.io`: `"Personal technical blog and engineering portfolio of Carlos Santos (@carlkidcrypto). Showcasing open-source systems engineering, high-performance C++17/SWIG architectures, SNMP network telemetry (ezsnmp), IoT environmental monitoring (PurpleAir, Matter 1.5.1), and resilient GitHub Actions CI/CD automations across cross-platform software ecosystems."`

12. **AI-Assisted Issue & Feature Templates Standard**:
    - All repositories across the ecosystem maintain tailored GitHub issue templates in `.github/ISSUE_TEMPLATE/` (`bug_report.md` and `feature_request.md`).
    - Every template explicitly includes a standardized `> [!TIP]` callout explaining AI-assisted issue triage and feature planning:
      - *Bug Report*: "This project utilizes AI-assisted development tools to triage, diagnose, and expedite the resolution of issues. The more detailed and comprehensive the information you provide (exact version numbers, OS environment, minimal reproduction steps, and full error logs/stack traces), the faster AI tooling and maintainers can diagnose root causes and deliver verified fixes."
      - *Feature Request*: "This project utilizes AI-assisted development tools to analyze, design, and implement requested enhancements. Providing clear problem statements, detailed use cases, expected behavior, and alternative approaches helps AI tooling and maintainers rapidly evaluate architectural feasibility and accelerate implementation."
    - Issue templates tailor environment fields to the repository's domain (e.g. Python versions, Net-SNMP library versions, Node.js and Matterbridge versions, runner OS, browser/device details, or target telemetry sinks).

13. **Cross-Repository Synchronization & Architectural Alignment Protocol**:
    - **Cross-Repo Learning**: When authoring, updating, or debugging release tools, packaging configurations, CI/CD matrices, documentation builds, or security configurations, always inspect sibling repositories (`ezsnmp`, `ezsnmp_data_logger`, `purpleair_api`, `purpleair_data_logger`, `purpleair-matterbridge`, `os-specific-runner`, `carlkidcrypto.github.io`) to learn and keep implementations synchronized.
    - **Reference Implementations**:
      - *Multi-Language Core with CMake*: Reference `ezsnmp_data_logger` for CMake C++17 core architectures with SWIG bindings for Python, Node.js, C#, and Go.
      - *Multi-Language Core with Meson*: Reference `purpleair_api` for Meson/Ninja C++17 architectures with SWIG bindings.
      - *Native Python C/C++ Extensions & Wheel Packaging*: Reference `ezsnmp` for Net-SNMP C++17 bindings, parallel builds, deterministic caching, and `cibuildwheel` matrices.
      - *Multi-Ecosystem Release Pipelines*: Reference `ezsnmp_data_logger` and `purpleair_api` for the canonical 6 distribution workflows (`build_and_publish_to_nuget.yml`, `build_and_publish_to_npm.yml`, `build_and_publish_to_pypi.yml`, `build_and_publish_to_test_pypi.yml`, `build_and_publish_to_go.yml`, `build_and_publish_to_winget.yml`).
      - *Standardized Release Tools*: Reference `release_tools/bump_version.sh` and `release_tools/release.sh` across `ezsnmp_data_logger` and `purpleair_api` for atomic multi-manifest synchronization and automated verification (`--verify`, `--dry-run`).
    - **Core Uniformity Guarantees**:
      - Pin immutable commit SHAs for actions (`actions/checkout`, `actions/setup-python`, `codecov/codecov-action`).
      - Maintain root `.sonarcloud.properties` excluding `docs/**`, `sphinx_docs_build/**`, `.github/**`, `tools/**`, and `release_tools/**`.
      - Protect manifest generators and CLI tools against path traversal (SonarCloud Rule S8707).
      - Ensure `.nojekyll` is present for all GitHub Pages documentation deployments.
      - Enforce CalSemVer standards and automated PEP 440 prerelease regex translation (`aN` -> `-alpha.N`, `bN` -> `-beta.N`, `rcN` -> `-rc.N`) across all package manifests and distribution workflows.
      - **Zero-Tolerance Legacy Version Purge**: When a repository transitions to CalSemVer, conduct an exhaustive codebase audit to eliminate all legacy SemVer artifacts (e.g. `2.0.0`, `v2.0.0`, "New in v2.0") across announcements (`README.rst`), unit tests (`test_generate_release_notes.py`), documentation specifications (`software_requirements.rst`), and tooling. Retain legacy version strings only in immutable changelog history or external dependency manifests.

---

## GitHub Immutable Releases Pattern

When GitHub Immutable Releases are enabled on a repository, assets **cannot** be uploaded or modified once a release is published:

1. **Workflow Trigger & Draft Upload**:
   - Trigger release asset workflows on `release: types: [created, published]`.
   - Upload binaries/installers while `github.event.release.draft == true` (on `created`), before the release is published and locked.
2. **Immutable Guard on `published`**:
   - Before attempting `gh release upload` or asset mutation on a published release, query the release's immutability state via GitHub API:
     ```bash
     is_immutable="$(gh api "repos/${GITHUB_REPOSITORY}/releases/${RELEASE_ID}" --jq '.immutable // false')"
     ```
   - Skip asset uploads cleanly with a diagnostic notice when `is_immutable == "true"` (and `draft == "false"`), preventing `422 Unprocessable Entity` / immutable release errors on re-runs or `published` events.

---

## Upstream Dependency Bump Checklist

When bumping an upstream core dependency (e.g., `ezsnmp` beta/stable bumps in `ezsnmp_data_logger`), audit and update all touchpoints in one isolated worktree (`<workspace_root>/wt-<repo>-<task>`):

1. **Package & Build Manifests**: `pyproject.toml`, `setup.cfg`, `CMakeLists.txt`, `uv.lock` / `requirements*.txt`, and `package.json` / `*.csproj` if applicable.
2. **C++ Source & ABI Guarantees**: Update embedded version/dependency constants (e.g., `src/version.cpp` ensuring `noexcept` signatures remain intact).
3. **Test Suites**: Update version/dependency assertions in both C++ tests (GoogleTest) and Python tests (`pytest`).
4. **CI Workflows & Helper Scripts**: Sync pinned dependency versions in `.github/workflows/*.yml`, `cibuildwheel` `before-all` steps, and `tools/prepare_*` provisioning scripts.
5. **Requirements & Docs**: Update `sphinx_docs_build/source/software_requirements.rst` (<= 80 chars/line) and rebuild Sphinx docs with `-W`.

---

## Same-Day CalSemVer & Release Notes Backfill

- **Same-Day `.1` Suffix**: If a same-day hotfix release is required after `YYYY.M.D` is already tagged, use `YYYY.M.D.1` (e.g., `2026.11.19.1`) across `release_tools/bump_version.sh` and manifests.
- **Release Notes Backfill**: When prior tags lack generated release notes or require synchronized notes across releases, run:
  ```bash
  python3 tools/generate_release_notes.py --backfill --publish
  ```

---

## Local Desktop App Update

To install a local `ezsnmp_data_logger` worktree or repository non-editably into macOS Framework Python 3.13, clean build artifacts, and run `version --json` + `ezsnmp_data_logger.gui` import smoke tests, run:

```bash
./scripts/update_local_desktop.sh \
  --source-dir <workspace_root>/wt-ezsnmp_data_logger-<task> \
  [--ezsnmp-spec <pip-spec-or-wheel>]
```

---

## Bundled Scripts

- `scripts/wt_preflight.sh` — Automates safe Git worktree lifecycle management without modifying or deleting other agents' active worktrees:
  - `check [--repo-dir PATH]`: Runs `git worktree list`, verifies the primary checkout is clean on `main`/`master`, and detects cloud-sync duplicate refs (`* (*` in `.git/refs`).
  - `create <repo-dir> <branch> <task-name> [--existing]`: Fetches `origin`, creates `<workspace_root>/wt-<repo>-<task-name>` from `origin/main` (or checks out an existing branch with `--existing`), and prints the worktree path.
  - `prune <repo-dir> <worktree-path>`: Safely removes and prunes the worktree and verifies `git worktree list`.
