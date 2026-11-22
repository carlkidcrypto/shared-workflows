# Coverage, Test Architecture & PR Reporting

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
4. **Component Management Boundaries & Feature Flag Carryforward**:
   - Machine-generated SWIG code in build directories is git-ignored and untracked by Codecov.
   - Only define components in `component_management` for active, hand-authored repository source code (`python_code`, `javascript_code`, `go_code`) to avoid permanent empty (`∅`) component reports.
   - Configure distinct feature flags (`python`, `javascript`, `csharp`, `go`, `java`, `cpp`) with `carryforward: true` in `codecov.yml` to prevent cross-language coverage drops when a PR only runs a subset of language matrices.
5. **Python Coverage with Subdirectory Tests (`tests/.coveragerc`)**:
   - When running tests from a subdirectory (`cd tests && coverage run -m unittest`) against a package installed into `site-packages`, `coverage` defaults to tracing the current directory, triggering `CoverageWarning: No data was collected` and exit code 1 on `coverage json`. Always declare `source = <package_name>` under `[run]` in `tests/.coveragerc` (or `python/tests/.coveragerc` in multi-language repos).
6. **Multi-Language Test Suite Isolation**:
   - In multi-language repositories with SWIG or native bindings, scope each language's tests strictly under `<language>/tests/` (`python/tests/`, `javascript/tests/`, `csharp/tests/`, `go/tests/`, `java/tests/`) and keep Python test configs (`.coveragerc`, `requirements.txt`) inside `python/tests/`.

7. **Codecov Action SHA Pinning & Step Token Authentication**:
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

8. **Change Detection & Unit Test Verification**:
   - Add `codecov.yml` to the `check-source-changes` job (`tj-actions/changed-files`) and workflow trigger paths so modifying coverage rules immediately triggers test pipelines.
   - Add automated unit test verification in the test suite to validate `codecov.yml`, `.sonarcloud.properties`, and workflow token configuration.

9. **Pre-Push Code Formatting Verification**:
   - Always run local formatters (`black` for Python, `prettier` for JavaScript/TypeScript, `csharpier` for C#) on newly created or modified files before staging and committing.
   - Unformatted files will fail PR formatting checks (`python_black.yml`) and trigger automated bot commits directly to the branch, causing subsequent git pushes to be rejected due to stale remote references.

---

---

## 20. Feature-Focused Test Suite Architecture & Flakiness Prevention

### 1. Modular Test Organization (Anti-"Full Coverage" Naming)
- **Zero Generic Test Catch-Alls**: Never author monolithic test files named `test_full_coverage.*` or `full_coverage.*`.
- **1,000-Line File Cap & Parameterization**: Keep all test files at or under **1,000 lines**. As soon as a test file grows past 1,000 lines, decompose it into smaller feature-focused files (e.g. splitting `cpp_tests/test_sessionbase.cpp` into `test_sessionbase.cpp`, `test_sessionbase_addressing.cpp`, `test_sessionbase_cli_options.cpp`, and `test_sessionbase_operations.cpp`) and collapse repetitive variant cases into parameterized tests (`TEST_P` / `INSTANTIATE_TEST_SUITE_P` in GoogleTest, `@pytest.mark.parametrize` in pytest).
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

### 5. Shared Daemon State Isolation in C/C++ Test Suites
- Tests executing mutating commands against a shared local daemon (such as SNMP SET on `sysLocation.0`) must always restore the modified state back to the original value both within the test itself AND in `TearDown()` (wrapped in `try/catch`).
- When running test suites against a single shared local daemon via Meson in Docker or CI, invoke `meson test --num-processes 1` to prevent parallel test binaries from mutating daemon state concurrently and causing intermittent race-condition failures.

### 6. Valgrind Memory Leak Reporting & `$GITHUB_OUTPUT` Sanitization
- For Valgrind memory leak workflows, parse the last 5 lines into stripped logs and render them into collapsible markdown tables (`comment-valgrind-template.md`).
- When exporting stripped logs to `$GITHUB_OUTPUT`, sanitize newlines into spaces (`tr '\r\n' ' '` or unquoted `echo KEY=$temp >> $GITHUB_OUTPUT`) to avoid multiline delimiter parsing failures (`Value cannot be null. (Parameter 'name')`).

---

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

## No-Cheat Verification & CI Triage

- **Never Cheat on Failing Tests**: Fix the underlying bug or broken test properly. **NEVER** relax assertions, add `@pytest.mark.skip` / `GTEST_SKIP()`, weaken checks, or mock around real failures just to make CI green.
- **Genuine Post-Edit Local Verification**: Always run the relevant local test suite (`pytest`, `ctest`, `meson test`, `npm test`, `go test`, `dotnet test`) and formatters (`black`, `prettier`, `clang-format`, `csharpier`) inside your worktree *after* your final edit and confirm all reported cases pass without skipped or relaxed assertions.
- **Distinguish Infra Drops from Real Failures**: Before editing code for a failed CI run, inspect logs with `scripts/triage_ci_failures.py` (or `gh run view <run_id> --log-failed`). If a job failed with `conclusion == "cancelled"` and empty steps or `runner_id == 0`, treat it as a runner infra drop and rerun only failed jobs (`--rerun-infra-drops` / `gh api .../rerun-failed-jobs -X POST`) rather than touching tests.
