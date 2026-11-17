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

- ``reusable_verify_syntax.yml``: ``yamllint`` + ``actionlint`` validation (excludes ``*.lock.yml`` and ``agentics-maintenance.yml`` by default).
- ``reusable_python_black.yml``: ``black --check --diff`` formatting check.
- ``reusable_sphinx_build.yml``: Python 3.14 Sphinx HTML build with pip caching and ``.nojekyll``.
- ``reusable_auto_changelog.yml``: Deterministic ``git-chglog`` changelog updater and PR creator.

Composite Actions (``actions/``)
--------------------------------

- ``actions/setup-actionlint``: Downloads pinned ``actionlint`` with retries.
- ``actions/setup-git-chglog``: Downloads pinned ``git-chglog`` with retries.
- ``actions/prepare-windows-netsnmp``: Installs/configures OpenSSL, Visual Studio environment, and Net-SNMP for Windows ``x64``/``x86``/``arm64`` builds.

Shared ``gh-aw`` Fragments (``shared/``)
----------------------------------------

- ``shared/codecov-coverage.md``: Pre-fetches Codecov coverage summaries for agentic coverage workflows.

Agent Plugins (``plugins/``)
----------------------------

- ``plugins/carlkidcrypto-devtools``: Agent Plugins 1.0 bundle (Antigravity + VS Code) containing ``ci-cd-workflow-optimization``, ``release-management``, ``sonarqube-quality-remediation``, and ``gemini-spark-blog``.
