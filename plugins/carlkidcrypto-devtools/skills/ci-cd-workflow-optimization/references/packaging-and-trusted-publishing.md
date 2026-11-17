# Packaging, Trusted Publishing & Release Distribution

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

---

### 22. Homebrew Local Tap Formula Testing (`Homebrew/brew` 7.0.14+)

`Homebrew/brew` 7.0.14+ (`Homebrew/brew#24442`) permanently enforces `HOMEBREW_FORBID_PACKAGES_FROM_PATHS` (ignoring `HOMEBREW_DEVELOPER=1`), so `brew install --formula /tmp/<formula>.rb` fails with `No available formula with the name "<pkg>".`:

- Always stage modified or local formulas in a temporary local tap via `brew tap-new --no-git local/<pkg>`, copy the formula to `$(brew --repository)/Library/Taps/local/homebrew-<pkg>/Formula/<pkg>.rb`, and install `local/<pkg>/<pkg>` (see `carlkidcrypto/ezsnmp#1492`).
- Note: Among `carlkidcrypto` repositories, only `ezsnmp` maintains a Homebrew `Formula/` (`ezsnmp.rb`); sibling repos only install upstream Homebrew build dependencies.

---
