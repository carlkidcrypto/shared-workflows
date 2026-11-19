"""Unit tests for scripts/generate_winget_manifest.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "generate_winget_manifest.py"
_SPEC = importlib.util.spec_from_file_location(
    "generate_winget_manifest", str(_SCRIPT_PATH)
)
assert _SPEC is not None and _SPEC.loader is not None
winget_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["generate_winget_manifest"] = winget_mod
_SPEC.loader.exec_module(winget_mod)


class TestGenerateWingetManifest(unittest.TestCase):
    """Test cases for generate_winget_manifest."""

    def test_get_canonical_manifest_dir_and_traversal_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            dest = winget_mod.get_canonical_manifest_dir(
                "ExampleOrg.ExampleApp", "2026.11.19", out_dir
            )
            self.assertTrue(
                str(dest).endswith("manifests/e/ExampleOrg/ExampleApp/2026.11.19")
            )

            with self.assertRaises(ValueError):
                winget_mod.get_canonical_manifest_dir("../bad.id", "1.0.0", out_dir)

            with self.assertRaises(ValueError):
                winget_mod.get_canonical_manifest_dir(
                    "ExampleOrg.ExampleApp", "../1.0.0", out_dir
                )

    def test_generate_manifests_inno(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            res = winget_mod.generate_manifests(
                package_id="ExampleOrg.ExampleApp",
                package_version="2026.11.19",
                installer_url="https://example.com/ExampleApp-Setup.exe",
                package_name="Example App",
                repo="ExampleOrg/ExampleApp",
                installer_sha256="a" * 64,
                out_dir=out_dir,
                tags=["cli", "tool"],
            )
            self.assertTrue(res["version"].is_file())
            self.assertTrue(res["locale"].is_file())
            self.assertTrue(res["installer"].is_file())
            installer_text = res["installer"].read_text(encoding="utf-8")
            self.assertIn("InstallerType: inno", installer_text)
            self.assertIn("A" * 64, installer_text)

    def test_read_current_version_from_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text(
                '[project]\nname = "demo"\nversion = "2026.11.19a0"\n',
                encoding="utf-8",
            )
            self.assertEqual(
                winget_mod.read_current_version(root), "2026.11.19-alpha.0"
            )


if __name__ == "__main__":
    unittest.main()
