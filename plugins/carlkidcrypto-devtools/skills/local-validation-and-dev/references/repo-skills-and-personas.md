# Consolidated Repository Agent Personas & Skills Reference

This reference centralizes the generic rules previously duplicated across per-repository `.github/agents/the_scribe.md` and `.github/skills/{pull-request-guide,sphinx-docs,python-testing,cpp-testing}/SKILL.md` files. Repositories should keep only repo-specific commands, paths, or service fixtures locally while inheriting these canonical standards from `carlkidcrypto-devtools`.

## 1. Documentation Persona (`the_scribe.md` & `sphinx-docs`)

- **Canonical Persona**: See `plugins/carlkidcrypto-devtools/agents/the_scribe.md`.
- **Zero-Warning Sphinx Builds**:
  - Always build with `SPHINXOPTS="-W"` using the discovered Python 3.14 / 3.13 virtual environment (`python3.14.venv`, `python3.13.venv`, or `.venv`).
  - Run `doxygen Doxyfile` in `doxygen_docs_build/` first whenever C++ API XML is consumed by Breathe/Exhale.
  - Never edit compiled output under `docs/html*` directly; edit `.rst` sources in `sphinx_docs_build/` and ensure `.nojekyll` is present.
- **Typo & Docstring Auditing**:
  - Run `python3 scripts/audit_docs.py` (from `carlkidcrypto/shared-workflows`) or `.github/scripts/audit_docs.py` to catch common spelling and class-casing typos before opening documentation PRs.

## 2. Pull Request Lifecycle (`pull-request-guide`)

- **Maintainer-Only Merge Policy**:
  - Never run `gh pr merge`, `git merge <branch> main`, or publish releases/tags. Merging and release publishing are strictly reserved for `@carlkidcrypto`.
- **Worktree Isolation & Branch Naming**:
  - Always work in a dedicated sibling worktree (`wt-<repo>-<task>`) on a conventional branch (`feat/...`, `fix/...`, `chore/...`, `docs/...`), keeping the primary checkout clean on `main`.
  - Use targeted `git add <file1> <file2>` (never `git add .` or `git add -A`) and Conventional Commit messages.
- **Pre-PR Verification & Review Replies**:
  - Run `black --check`, `clang-format --dry-run --Werror` (for C/C++ repos), `yamllint`, `actionlint -shellcheck=`, and unit test suites before pushing.
  - Verify `git log origin/<branch>..HEAD` is empty and reply to every review/MAIL comment thread via 2-pass discovery (`gh_pr_mail.py`) citing the exact commit SHA (`Addressed in commit \`<sha>\`: <summary>`).

## 3. Python Testing Standards (`python-testing`)

- **Virtual Environment & Pytest**:
  - Activate the local virtual environment (`python3.14.venv`, `python3.13.venv`, or `.venv`) or use `local-validation-and-dev/scripts/env_preflight.sh`.
  - Run `pytest` with branch/line coverage (`pytest --cov=<pkg> --cov-report=term-missing`).
  - Use `scripts/analyze_python_coverage_gaps.py` to statically verify that new callables are referenced by unit tests.
- **Daemon / Fixture Hygiene**:
  - For SNMP repositories (`ezsnmp`, `ezsnmp_data_logger`), ensure local `snmpd` uses the repository's test `snmpd.conf` when running live integration tests.

## 4. C++ Native Testing Standards (`cpp-testing`)

- **Meson / CMake + GoogleTest**:
  - Configure native C++ test builds with coverage enabled (`meson setup build -Db_coverage=true` or CMake equivalent) and compile via `ninja -C build`.
  - Execute tests serially (`meson test -C build --num-processes 1 --print-errorlogs`) when test binaries share local daemon ports or `.gcda` coverage counters.
  - When debugging memory safety or undefined behavior, run under `ASAN_OPTIONS='halt_on_error=0' UBSAN_OPTIONS='halt_on_error=0'`.
