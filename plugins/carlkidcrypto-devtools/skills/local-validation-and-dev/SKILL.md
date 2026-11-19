---
name: local-validation-and-dev
description: >-
  Local development environment preflight, git worktree isolation, and full
  validation sequence for carlkidcrypto repositories (ezsnmp, ezsnmp_data_logger,
  purpleair_api, purpleair_data_logger, shared-workflows, etc.). Covers macOS/Linux
  PATH, PKG_CONFIG_PATH, and DYLD_LIBRARY_PATH setup, sibling worktree isolation,
  formatting/linting (black, clang-format, yamllint, actionlint), native C++/Python
  builds and tests (setup.py build_ext, pytest, meson), Doxygen + Sphinx doc builds,
  and temporary build artifact cleanup.
---

# Local Validation & Development Preflight

Use this skill before running local builds, linters, tests, or documentation builds in any `carlkidcrypto` repository.

---

## 1. Environment Preflight (`PATH`, `PKG_CONFIG_PATH`, `DYLD_LIBRARY_PATH`)

Non-interactive agent shells often miss Homebrew, Framework Python, and native library pkg-config paths. Run or source [env_preflight.sh](scripts/env_preflight.sh) before invoking compilers, linters, or test runners:

```bash
# Source into current shell
source plugins/carlkidcrypto-devtools/skills/local-validation-and-dev/scripts/env_preflight.sh

# Or inspect / eval printed exports
eval "$(plugins/carlkidcrypto-devtools/skills/local-validation-and-dev/scripts/env_preflight.sh --print)"
```

What `env_preflight.sh` configures (only adding directories that exist on disk):
- **macOS `PATH`**:
  - `/Library/Frameworks/Python.framework/Versions/3.14/bin`
  - `/Library/Frameworks/Python.framework/Versions/3.13/bin`
  - `/opt/homebrew/bin` and `/opt/homebrew/sbin`
  - `/opt/homebrew/opt/openssl@3/bin`, `/opt/homebrew/opt/net-snmp/bin`, `/opt/homebrew/opt/libpq/bin` (plus `/usr/local/opt/...` fallbacks)
- **macOS `PKG_CONFIG_PATH`**:
  - `/opt/homebrew/opt/openssl@3/lib/pkgconfig`
  - `/opt/homebrew/opt/net-snmp/lib/pkgconfig`
  - `/opt/homebrew/opt/libpq/lib/pkgconfig`
  - `/opt/homebrew/lib/pkgconfig` and `/usr/local/lib/pkgconfig`
- **macOS `DYLD_LIBRARY_PATH`**:
  - `/opt/homebrew/opt/openssl@3/lib`, `/opt/homebrew/opt/net-snmp/lib`, `/opt/homebrew/opt/libpq/lib`
- **Linux `PATH` & `PKG_CONFIG_PATH`**:
  - `/usr/local/bin`, `/usr/local/sbin`, `~/.local/bin`
  - `/usr/lib/pkgconfig`, `/usr/lib/x86_64-linux-gnu/pkgconfig`, `/usr/lib/aarch64-linux-gnu/pkgconfig`, `/usr/local/lib/pkgconfig`

---

## 2. Git Worktree Isolation

> [!IMPORTANT]
> **Never build, test, or switch branches in `<workspace_root>/<repo>`.**
> Multiple agents and background workflows operate concurrently. Keep the primary checkout clean on `main` and isolate all edits and builds in a sibling worktree.

1. **Discover active worktrees** first to avoid branch or directory collisions:
   ```bash
   git worktree list
   ```
2. **Create a sibling worktree** under `<workspace_root>` (never hardcode user-specific home paths):
   ```bash
   git fetch origin
   git worktree add -b <branch-name> <workspace_root>/wt-<repo>-<task-name> origin/main
   cd <workspace_root>/wt-<repo>-<task-name>
   ```
3. **Run all commands inside `<workspace_root>/wt-<repo>-<task-name>`** (dependency installs, `build_ext`, `meson`, `pytest`, formatters, `gh pr create`).
4. **Prune cleanly** after the PR is merged or closed (never touch another agent's active worktree):
   ```bash
   git worktree remove <workspace_root>/wt-<repo>-<task-name>
   git worktree prune
   git worktree list
   ```

---

## 3. Full Local Validation Order

Run checks in this order (fast static checks first, then native builds/tests, then documentation), or use [validate_local.py](scripts/validate_local.py) to auto-detect and run applicable steps:

```bash
python3 plugins/carlkidcrypto-devtools/skills/local-validation-and-dev/scripts/validate_local.py \
  --repo <workspace_root>/wt-<repo>-<task-name>
```

Available flags for `validate_local.py`:
- `--repo <path>`: Repository or worktree path (default: `.`).
- `--skip-python`: Skip `black --check`, `setup.py build_ext --inplace`, and `pytest`.
- `--skip-cpp`: Skip `clang-format` and `meson` setup/compile/test.
- `--skip-docs`: Skip `doxygen` and `sphinx-build`.
- `--skip-workflows`: Skip `yamllint` and `actionlint`.
- `--keep-artifacts`: Keep temporary build/doc directories after validation.

Manual equivalent sequence:

1. **Python formatting**:
   ```bash
   black --check .
   ```
2. **C/C++ formatting**:
   ```bash
   clang-format -n -Werror <cpp-and-header-files>
   ```
3. **GitHub Actions workflows**:
   ```bash
   yamllint .github/workflows
   actionlint
   ```
4. **Python native extension build & test suite**:
   ```bash
   python3 setup.py build_ext --inplace && pytest
   ```
5. **C++ Meson build & test suite**:
   ```bash
   meson setup .meson_build_validate
   meson compile -C .meson_build_validate
   meson test -C .meson_build_validate --print-errorlogs
   ```
6. **Documentation (Doxygen + Sphinx)**:
   Always create `doxygen_docs_build/doxygen` before running `doxygen .doxygen`:
   ```bash
   mkdir -p doxygen_docs_build/doxygen && doxygen .doxygen && sphinx-build -b html -W sphinx_docs_build sphinx_docs_build/_build/html
   ```

---

## 4. Temporary Build Artifact Cleanup

Always leave the worktree clean before staging (`git add <file1> <file2>`) and pushing:

- `validate_local.py` automatically removes temporary artifacts it created (`build/`, `*.egg-info`, `.meson_build_validate/`, `.pytest_cache/`, `doxygen_docs_build/doxygen/`, `sphinx_docs_build/_build/`, and newly generated untracked `*_wrap.*` / `*.so` / `*.pyd` files) unless `--keep-artifacts` is passed.
- If running commands manually, remove temporary outputs and verify with `git status`:
  ```bash
  rm -rf build *.egg-info .meson_build_validate doxygen_docs_build/doxygen sphinx_docs_build/_build .pytest_cache
  git status
  ```

---

## 5. Consolidated Agent Personas & Repository Skills

- [repo-skills-and-personas.md](references/repo-skills-and-personas.md) — Canonical rules for `the_scribe.md` (`../../agents/the_scribe.md`), `pull-request-guide`, `sphinx-docs`, `python-testing`, and `cpp-testing` shared across all `carlkidcrypto` repositories.
