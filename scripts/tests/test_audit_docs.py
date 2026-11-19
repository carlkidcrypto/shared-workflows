"""Unit tests for scripts/audit_docs.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "audit_docs.py"
_SPEC = importlib.util.spec_from_file_location("audit_docs", str(_SCRIPT_PATH))
assert _SPEC is not None and _SPEC.loader is not None
audit_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["audit_docs"] = audit_mod
_SPEC.loader.exec_module(audit_mod)


class TestAuditDocs(unittest.TestCase):
    """Test cases for audit_docs."""

    def test_audit_file_clean(self) -> None:
        clean_text = (
            '"""This is a clean docstring."""\n' "def receive_data():\n" "    pass\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(clean_text)
            tf_path = Path(tf.name)

        try:
            self.assertEqual(audit_mod.audit_file(tf_path), [])
        finally:
            tf_path.unlink(missing_ok=True)

    def test_audit_file_with_issues_and_fix(self) -> None:
        dirty_text = (
            "# We will recieve data here.\n"
            "# An error occured during export.\n"
            "# Keep these seperate.\n"
        )
        with tempfile.NamedTemporaryFile(
            suffix=".rst", mode="w", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(dirty_text)
            tf_path = Path(tf.name)

        try:
            issues = audit_mod.audit_file(tf_path)
            self.assertEqual(len(issues), 3)
            descriptions = [i[2] for i in issues]
            self.assertTrue(any("recieve" in d for d in descriptions))
            self.assertTrue(any("occured" in d for d in descriptions))
            self.assertTrue(any("seperate" in d for d in descriptions))

            changed = audit_mod.fix_file(tf_path)
            self.assertEqual(changed, 1)

            fixed_content = tf_path.read_text(encoding="utf-8")
            self.assertIn("receive", fixed_content)
            self.assertIn("occurred", fixed_content)
            self.assertIn("separate", fixed_content)
            self.assertEqual(audit_mod.audit_file(tf_path), [])
        finally:
            tf_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
