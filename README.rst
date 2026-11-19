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

- ``reusable_verify_syntax.yml``: ``yamllint`` + ``actionlint`` validation (excludes ``*.lock.yml``, ``*.lock.yaml``, and ``agentics-maintenance.yml`` by default) with optional ``gh aw compile --validate``.
- ``reusable_python_black.yml``: ``black --check --diff`` formatting check with optional automated fix PRs and PR failure comments.
- ``reusable_clang_format.yml``: ``clang-format`` C/C++ formatting check with optional automated fix PRs.
- ``reusable_sphinx_build.yml``: Python 3.14 Sphinx HTML build with pip caching, optional Doxygen, versioned docs, landing page, blog audit, ``.nojekyll``, and GitHub Pages deployment.
- ``reusable_auto_changelog.yml``: Deterministic ``git-chglog`` changelog updater and PR creator.
- ``reusable_tests_cpp_native.yml``: Multi-OS (``ubuntu-latest`` / ``macos-latest``) C++ native build and test runner (Meson or CMake) with optional ``snmpd`` and Codecov upload.
- ``reusable_tests_python.yml``: Multi-OS / multi-Python-version ``pytest`` runner with optional third-party checkout, setup command, Codecov coverage upload, and JUnit test results upload.
- ``reusable_swig_multilang.yml``: Multi-OS SWIG 4.x binding generator for Python, JavaScript, C#, and Go.
- ``reusable_docker_publish.yml``: Docker Buildx multi-registry (Docker Hub + GHCR) image builder and publisher with GitHub Actions layer caching.
- ``reusable_pypi_publish.yml``: ``cibuildwheel`` / ``pure-python`` wheel and sdist builder with pure OIDC Trusted Publishing to PyPI or TestPyPI.
- ``reusable_npm_publish.yml``: Node.js 24+ npm build, test, pack, and OIDC Trusted Publishing (``--provenance --access public``, no ``NPM_TOKEN`` required once configured).
- ``reusable_nuget_publish.yml``: Optional multi-OS C# native runtime matrix, ``dotnet pack``, and NuGet.org OIDC Trusted Publishing (plus optional GitHub Packages push).
- ``reusable_winget_publish.yml``: WinGet manifest generation, ``winget validate`` check, artifact upload, and ``wingetcreate`` PR submission.

Composite Actions (``actions/``)
--------------------------------

- ``actions/build-distribution``: Builds Python sdist (and optional pure-Python wheel) and downloads prebuilt ``cibw-wheels-*`` artifacts.
- ``actions/build-wheels``: Builds Python wheels across Linux, macOS, and Windows using ``cibuildwheel`` with pip/cibw/object caching and optional Windows Net-SNMP setup.
- ``actions/check-source-changes``: Pinned ``tj-actions/changed-files`` wrapper outputting ``any_changed``.
- ``actions/prepare-netsnmp``: Builds minimal shared ``libnetsnmp`` from source with SHA256 verification on Linux or macOS.
- ``actions/prepare-windows-netsnmp``: Installs/configures OpenSSL, Visual Studio environment, and Net-SNMP for Windows ``x64``/``x86``/``arm64`` builds.
- ``actions/setup-actionlint``: Downloads pinned ``actionlint`` with retries.
- ``actions/setup-copilot-gh-aw``: Checks out repository (``persist-credentials: false``) and installs the ``gh-aw`` CLI extension.
- ``actions/setup-git-chglog``: Downloads pinned ``git-chglog`` with retries.
- ``actions/upload-codecov``: Uploads coverage or test results using pinned ``codecov/codecov-action`` with explicit ``token``, ``CODECOV_TOKEN``, and optional ``report-type``.

Shared CI Scripts (``scripts/``)
--------------------------------

- ``scripts/fetch_codecov_report.py``: Codecov API v2 reporter with ``MAX_LOOKBACK=30`` fallback and component/flag support.
- ``scripts/generate_release_notes.py``: Parameterized GitHub release notes generator and publisher.
- ``scripts/audit_docs.py``: Documentation and docstring typo auditor with optional ``--fix``.
- ``scripts/analyze_python_coverage_gaps.py``: Static AST analyzer comparing Python callables against unit test references.
- ``scripts/generate_winget_manifest.py``: Parameterized WinGet 1.6.0 manifest generator with path-traversal protection.

Shared ``gh-aw`` Fragments (``shared/``)
----------------------------------------

- ``shared/codecov-coverage.md``: Pre-fetches Codecov coverage summaries for agentic coverage workflows.
- ``shared/pr-preflight-checklist.md``: Pre-PR validation checklist covering branch/worktree isolation, ``.github/scripts/`` placement, ``yamllint``/``actionlint``/``black`` checks, unpushed-commit verification, and 2-pass PR review/MAIL comment replies.

Agent Plugins (``plugins/``)
----------------------------

- ``plugins/carlkidcrypto-devtools``: Agent Plugins 1.0 bundle (Antigravity + VS Code) containing ``ci-cd-workflow-optimization``, ``release-management``, ``sonarqube-quality-remediation``, ``gemini-spark-blog``, and ``local-validation-and-dev``, along with bundled CLI helper scripts under ``skills/*/scripts/``.
