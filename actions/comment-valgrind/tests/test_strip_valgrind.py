"""Unit tests for actions/comment-valgrind/strip_valgrind.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "strip_valgrind.py"
SPEC = importlib.util.spec_from_file_location("strip_valgrind", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def test_strip_valgrind_log_extracts_tail(tmp_path: Path) -> None:
    src = tmp_path / "valgrind.out"
    dst = tmp_path / "stripped.log"
    src.write_text(
        "\n".join([f"==1== line {i}" for i in range(1, 11)]) + "\n",
        encoding="utf-8",
    )
    out = mod.strip_valgrind_log(src, dst, tail_lines=5)
    assert dst.read_text(encoding="utf-8") == out
    assert out.splitlines() == [f"==1== line {i}" for i in range(6, 11)]


def test_strip_valgrind_log_missing_file(tmp_path: Path) -> None:
    dst = tmp_path / "stripped.log"
    rc = mod.main(["--input", str(tmp_path / "missing.out"), "--output", str(dst)])
    assert rc == 0
    assert "valgrind report unavailable" in dst.read_text(encoding="utf-8")
