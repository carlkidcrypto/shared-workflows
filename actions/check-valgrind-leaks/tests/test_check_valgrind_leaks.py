"""Unit tests for actions/check-valgrind-leaks/check_valgrind_leaks.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "check_valgrind_leaks.py"
SPEC = importlib.util.spec_from_file_location("check_valgrind_leaks", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


SAMPLE_CLEAN_LOG = """
==1234== 128 bytes in 1 blocks are definitely lost in loss record 1 of 2
==1234==    at 0x4848899: malloc (vg_replace_malloc.c:381)
==1234==    by 0x109123: PyUnicode_New (unicodeobject.c:100)
==1234==
==1234== 64 bytes in 1 blocks are definitely lost in loss record 2 of 2
==1234==    at 0x4848899: malloc (vg_replace_malloc.c:381)
==1234==    by 0x109456: PyInit__purpleair_api (purpleair_wrap.cxx:42)
==1234==
"""

SAMPLE_LEAK_LOG = """
==1234== 256 bytes in 2 blocks are definitely lost in loss record 1 of 1
==1234==    at 0x4848899: malloc (vg_replace_malloc.c:381)
==1234==    by 0x555555: PurpleAirAPI::send_url_get_request (PurpleAirAPIHelpers.cpp:86)
==1234==
"""


def test_parse_marker_list() -> None:
    assert mod.parse_marker_list(["a, b\nc", "b, d"]) == ("a", "b", "c", "d")
    assert mod.parse_marker_list([]) == ()


def test_find_native_leaks_clean_and_ignored() -> None:
    leaks = mod.find_native_leaks(
        SAMPLE_CLEAN_LOG,
        markers=("PurpleAir", "purpleair", "curl_"),
    )
    assert leaks == []


def test_find_native_leaks_detects_matching_leak() -> None:
    leaks = mod.find_native_leaks(
        SAMPLE_LEAK_LOG,
        markers=("PurpleAir", "curl_"),
    )
    assert len(leaks) == 1
    assert "PurpleAirAPI::send_url_get_request" in leaks[0]


def test_cli_pass_and_fail(tmp_path: Path) -> None:
    clean_file = tmp_path / "valgrind_clean.out"
    clean_file.write_text(SAMPLE_CLEAN_LOG, encoding="utf-8")

    rc_pass = mod.main(
        [
            "--marker",
            "PurpleAir,curl_",
            "--label",
            "purpleair_api",
            str(clean_file),
        ]
    )
    assert rc_pass == 0

    leak_file = tmp_path / "valgrind_leak.out"
    leak_file.write_text(SAMPLE_LEAK_LOG, encoding="utf-8")

    rc_fail = mod.main(
        [
            "--marker",
            "PurpleAir,curl_",
            "--label",
            "purpleair_api",
            str(leak_file),
        ]
    )
    assert rc_fail == 1


def test_cli_missing_files_returns_error(tmp_path: Path) -> None:
    rc = mod.main([str(tmp_path / "does_not_exist_*.out")])
    assert rc == 1
