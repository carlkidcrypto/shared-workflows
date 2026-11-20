"""Unit tests for release-management/scripts/calsemver_release_helper.py."""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "calsemver_release_helper.py"
_SPEC = importlib.util.spec_from_file_location(
    "calsemver_release_helper", str(_SCRIPT_PATH)
)
assert _SPEC is not None and _SPEC.loader is not None
helper_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["calsemver_release_helper"] = helper_mod
_SPEC.loader.exec_module(helper_mod)


class TestCalSemVerReleaseHelper(unittest.TestCase):
    """Test cases for calsemver_release_helper."""

    def test_parse_calsemver_stable_and_prerelease(self) -> None:
        stable = helper_mod.parse_calsemver("2026.11.19")
        self.assertEqual(stable.pep440, "2026.11.19")
        self.assertEqual(stable.semver, "2026.11.19")
        self.assertEqual(stable.git_tag, "v2026.11.19")
        self.assertFalse(stable.is_prerelease)

        pre_pep = helper_mod.parse_calsemver("v2026.11.19a2")
        self.assertEqual(pre_pep.pep440, "2026.11.19a2")
        self.assertEqual(pre_pep.semver, "2026.11.19-alpha.2")
        self.assertTrue(pre_pep.is_prerelease)

        pre_sem = helper_mod.parse_calsemver("2026.11.19-beta.1")
        self.assertEqual(pre_sem.pep440, "2026.11.19b1")
        self.assertEqual(pre_sem.semver, "2026.11.19-beta.1")

    def test_rejects_leading_zeros(self) -> None:
        with self.assertRaises(ValueError):
            helper_mod.parse_calsemver("2026.05.03")

    def test_today_calsemver_and_venv_discovery(self) -> None:
        forms = helper_mod.today_calsemver(prerelease="a0", today=dt.date(2026, 11, 3))
        self.assertEqual(forms.pep440, "2026.11.3a0")
        self.assertEqual(forms.semver, "2026.11.3-alpha.0")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv_bin = root / "python3.14.venv" / "bin"
            venv_bin.mkdir(parents=True)
            (venv_bin / "python").write_text("", encoding="utf-8")
            discovered = helper_mod.discover_sphinx_venv(root)
            self.assertEqual(discovered, (root / "python3.14.venv").resolve())


if __name__ == "__main__":
    unittest.main()
