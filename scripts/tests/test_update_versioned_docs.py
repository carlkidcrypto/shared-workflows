"""Tests for actions/update-versioned-docs/scripts/update_versioned_docs.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "actions"
    / "update-versioned-docs"
    / "scripts"
    / "update_versioned_docs.py"
)
SPEC = importlib.util.spec_from_file_location("update_versioned_docs", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def _write_index(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Docs\n====\n\n.. VERSION_LIST_START\n\n* old\n\n.. VERSION_LIST_END\n",
        encoding="utf-8",
    )


def test_prunes_older_calsemver_and_semver_prereleases_but_keeps_newer(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in [
        "html_v1.4.1",
        "html_v1.5.1",
        "html_v1.5.1a0",
        "html_v1.5.1a1",
        "html_v2026.11.11a0",
        "html_v2026.11.24b0",
        "html_v2026.11.24-beta.0",
        "html_V2026.11.26",
        "html_v2026.12.1a0",
    ]:
        (docs / name).mkdir()

    index_rst = tmp_path / "sphinx_docs_build" / "landing" / "source" / "index.rst"
    _write_index(index_rst)

    kept, pruned = MOD.update_versioned_docs(docs, index_rst)

    assert pruned == [
        "html_v1.5.1a0",
        "html_v1.5.1a1",
        "html_v2026.11.11a0",
        "html_v2026.11.24-beta.0",
        "html_v2026.11.24b0",
    ]
    assert kept == [
        "html_v2026.12.1a0",
        "html_v2026.11.26",
        "html_v1.5.1",
        "html_v1.4.1",
    ]
    for gone in pruned:
        assert not (docs / gone).exists()
    assert (docs / "html_v2026.11.26").is_dir()

    text = index_rst.read_text(encoding="utf-8")
    assert "* `v2026.12.1a0 <./html_v2026.12.1a0/index.html>`_" in text
    assert "* `v2026.11.26 <./html_v2026.11.26/index.html>`_" in text
    assert "v2026.11.24b0" not in text
    assert "v1.5.1a0" not in text


def test_keeps_prereleases_when_no_stable_release_exists(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "html_v2026.11.11a0").mkdir()
    (docs / "html_v2026.11.24b0").mkdir()
    index_rst = tmp_path / "index.rst"
    _write_index(index_rst)

    kept, pruned = MOD.update_versioned_docs(docs, index_rst)

    assert pruned == []
    assert kept == ["html_v2026.11.24b0", "html_v2026.11.11a0"]


def test_missing_sentinels_returns_error(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    index_rst = tmp_path / "index.rst"
    index_rst.write_text("No sentinels here\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        MOD.update_versioned_docs(docs, index_rst)
