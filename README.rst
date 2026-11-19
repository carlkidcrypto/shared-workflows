shared-workflows
================

.. image:: https://img.shields.io/github/actions/workflow/status/carlkidcrypto/shared-workflows/verify_syntax.yml?branch=main&style=flat-square&label=Verify%20Syntax
   :target: https://github.com/carlkidcrypto/shared-workflows/actions/workflows/verify_syntax.yml
   :alt: Verify Syntax

.. image:: https://img.shields.io/github/license/carlkidcrypto/shared-workflows?style=flat-square
   :target: https://github.com/carlkidcrypto/shared-workflows/blob/main/LICENSE
   :alt: License

Central repository for shared GitHub Actions composite actions, reusable
workflows (``workflow_call``), ``gh-aw`` shared fragments, and portable Agent
Plugins across ``carlkidcrypto`` repositories.

Reusable Workflows (``.github/workflows/``)
-------------------------------------------

- ``reusable_auto_changelog.yml``: Deterministic ``git-chglog`` changelog updater and PR creator.
- ``reusable_clang_format.yml``: ``clang-format`` C/C++ formatting check across configurable target directories and file extensions.
- ``reusable_npm_publish.yml``: Idempotent npm package build and OIDC Trusted Publishing (``--provenance --access public``) on Node.js 24+.
- ``reusable_nuget_publish.yml``: .NET / NuGet package build and OIDC Trusted Publishing (``--skip-duplicate``).
- ``reusable_pypi_publish.yml``: Pure-Python or ``cibuildwheel`` package build and OIDC Trusted Publishing to PyPI or TestPyPI.
- ``reusable_python_black.yml``: ``black --check --diff`` formatting check.
- ``reusable_sphinx_build.yml``: Python 3.14 Sphinx HTML build with pip caching and ``.nojekyll``.
- ``reusable_tests_cpp_native.yml``: Cross-platform C++ native build and test runner (Meson or CMake, with optional Net-SNMP and OpenSSL setup).
- ``reusable_verify_syntax.yml``: ``yamllint`` + ``actionlint`` (with optional ``shellcheck``) validation (excludes ``*.lock.yml`` and ``agentics-maintenance.yml`` by default).
- ``reusable_winget_publish.yml``: WinGet manifest generation and ``wingetcreate`` PR submission for Windows release installers.

Composite Actions (``actions/``)
--------------------------------

- ``actions/check-source-changes``: Detects whether specified file patterns changed using a pinned ``tj-actions/changed-files``.
- ``actions/prepare-windows-netsnmp``: Installs/configures OpenSSL, Visual Studio environment, and Net-SNMP for Windows ``x64``/``x86``/``arm64`` wheel builds.
- ``actions/setup-actionlint``: Downloads and installs a pinned ``actionlint`` release with retries.
- ``actions/setup-copilot-gh-aw``: Checks out the repository (``persist-credentials: false``) and installs the ``gh-aw`` CLI extension.
- ``actions/setup-git-chglog``: Downloads and installs a pinned ``git-chglog`` release with retries.
- ``actions/upload-codecov``: Uploads coverage or test result files to Codecov using a pinned ``codecov/codecov-action``.

Shared ``gh-aw`` Fragments (``shared/``)
----------------------------------------

- ``shared/codecov-coverage.md``: Pre-fetches Codecov coverage summaries for agentic coverage workflows.
- ``shared/pr-preflight-checklist.md``: Pre-PR validation checklist covering branch/worktree isolation, ``.github/scripts/`` placement, ``yamllint``/``actionlint``/``black`` checks, unpushed-commit verification, and 2-pass PR review/MAIL comment replies.

Agent Plugins (``plugins/``)
----------------------------

- ``plugins/carlkidcrypto-devtools``: Agent Plugins 1.0 bundle (Antigravity + VS Code) containing ``ci-cd-workflow-optimization``, ``release-management``, ``sonarqube-quality-remediation``, and ``gemini-spark-blog``, along with bundled CLI helper scripts under ``skills/*/scripts/``.
