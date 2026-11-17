shared-workflows
================

.. image:: https://img.shields.io/github/actions/workflow/status/carlkidcrypto/shared-workflows/verify_syntax.yml?branch=main&style=flat-square&label=Verify%20Syntax
   :target: https://github.com/carlkidcrypto/shared-workflows/actions/workflows/verify_syntax.yml
   :alt: Verify Syntax

.. image:: https://img.shields.io/github/license/carlkidcrypto/shared-workflows?style=flat-square
   :target: https://github.com/carlkidcrypto/shared-workflows/blob/main/LICENSE
   :alt: License

Central repository for shared GitHub Actions composite actions, reusable
workflows (``workflow_call``), ``gh-aw`` shared fragments, and CI tooling across
``carlkidcrypto`` repositories.

Layout
------

- ``actions/``: Composite GitHub Actions (``uses: carlkidcrypto/shared-workflows/actions/<name>@<sha>``)
- ``.github/workflows/``: Reusable workflows (``workflow_call``) and self-validation CI
- ``shared/``: Shared ``gh-aw`` markdown fragments (``imports:``)
- ``tools/``: Pinned tool versions (e.g. ``actionlint-version.txt``)
