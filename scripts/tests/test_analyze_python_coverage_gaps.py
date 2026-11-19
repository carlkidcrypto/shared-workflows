"""Unit tests for scripts/analyze_python_coverage_gaps.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "analyze_python_coverage_gaps.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "analyze_python_coverage_gaps", str(_SCRIPT_PATH)
)
assert _SPEC is not None and _SPEC.loader is not None
gap_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["analyze_python_coverage_gaps"] = gap_mod
_SPEC.loader.exec_module(gap_mod)


class TestAnalyzePythonCoverageGaps(unittest.TestCase):
    """Test cases for analyze_python_coverage_gaps."""

    def test_collect_callables(self) -> None:
        code = (
            "def my_func():\n"
            "    pass\n\n"
            "class MyClass:\n"
            "    def method_one(self):\n"
            "        pass\n"
            "    async def async_method(self):\n"
            "        pass\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(code)
            tf_path = Path(tf.name)

        try:
            callables = gap_mod.collect_callables(tf_path)
            self.assertEqual(callables, ["async_method", "method_one", "my_func"])
        finally:
            tf_path.unlink(missing_ok=True)

    def test_collect_conditional_markers(self) -> None:
        code = "def test():\n" "    if False:  # pragma: no cover\n" "        pass\n"
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(code)
            tf_path = Path(tf.name)

        try:
            markers = gap_mod.collect_conditional_markers(tf_path)
            self.assertEqual(len(markers), 1)
            self.assertIn("line 2", markers[0])
            self.assertIn("pragma: no cover", markers[0])
        finally:
            tf_path.unlink(missing_ok=True)

    def test_find_uncovered_callables(self) -> None:
        callables = ["func_a", "func_b", "func_c", "__init__"]
        test_refs = {
            "test_one.py": {"func_a", "other_token"},
            "test_two.py": {"func_c"},
        }
        covered, uncovered = gap_mod.find_uncovered_callables(
            callables, test_refs, skip_private=True
        )
        self.assertIn("func_a", covered)
        self.assertIn("func_c", covered)
        self.assertIn("__init__", covered)
        self.assertEqual(uncovered, ["func_b"])


if __name__ == "__main__":
    unittest.main()
