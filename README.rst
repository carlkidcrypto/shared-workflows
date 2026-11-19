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
- ``reusable_pypi_publish.yml``: ``cibuildwheel`` / ``pure-python`` wheel and sdist builder with pure OIDC Trusted Publishing to PyPI or TestPyPI.
- ``reusable_npm_publish.yml``: Node.js 24+ npm build, test, pack, and OIDC Trusted Publishing (``--provenance --access public``, no ``NPM_TOKEN`` required once configured).
- ``reusable_nuget_publish.yml``: Optional multi-OS C# native runtime matrix, ``dotnet pack``, and NuGet.org OIDC Trusted Publishing (plus optional GitHub Packages push).
- ``reusable_winget_publish.yml``: WinGet manifest generation, ``winget validate`` check, artifact upload, and ``wingetcreate`` PR submission.

Composite Actions (``actions/``)
--------------------------------

- ``actions/check-source-changes``: Pinned ``tj-actions/changed-files`` wrapper outputting ``any_changed``.
- ``actions/prepare-windows-netsnmp``: Installs/configures OpenSSL, Visual Studio environment, and Net-SNMP for Windows ``x64``/``x86``/``arm64`` builds.
- ``actions/setup-actionlint``: Downloads pinned ``actionlint`` with retries.
- ``actions/setup-copilot-gh-aw``: Checks out repository (``persist-credentials: false``) and installs the pinned ``gh-aw`` CLI extension.
- ``actions/setup-git-chglog``: Downloads pinned ``git-chglog`` with retries.
- ``actions/upload-codecov``: Uploads coverage or test results using pinned ``codecov/codecov-action`` with explicit ``token`` and ``CODECOV_TOKEN``.

Shared ``gh-aw`` Fragments (``shared/``)
----------------------------------------

- ``shared/codecov-coverage.md``: Pre-fetches Codecov coverage summaries for agentic coverage workflows.

Agent Plugins (``plugins/``)
----------------------------

- ``plugins/carlkidcrypto-devtools``: Agent Plugins 1.0 bundle (Antigravity + VS Code) containing ``ci-cd-workflow-optimization``, ``release-management``, ``sonarqube-quality-remediation``, ``gemini-spark-blog``, and ``local-validation-and-dev``.
