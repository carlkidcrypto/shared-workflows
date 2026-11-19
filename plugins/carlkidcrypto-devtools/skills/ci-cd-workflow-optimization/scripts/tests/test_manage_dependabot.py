"""Unit tests for ci-cd-workflow-optimization/scripts/manage_dependabot.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "manage_dependabot.py"
_SPEC = importlib.util.spec_from_file_location("manage_dependabot", str(_SCRIPT_PATH))
assert _SPEC is not None and _SPEC.loader is not None
dep_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["manage_dependabot"] = dep_mod
_SPEC.loader.exec_module(dep_mod)


class TestManageDependabot(unittest.TestCase):
    """Test cases for manage_dependabot."""

    def test_detect_generate_and_validate_multi_ecosystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            (root / "sphinx_docs_build").mkdir()
            (root / "sphinx_docs_build" / "requirements.txt").write_text(
                "sphinx\n", encoding="utf-8"
            )
            (root / "bindings" / "javascript").mkdir(parents=True)
            (root / "bindings" / "javascript" / "package.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (root / "bindings" / "csharp").mkdir(parents=True)
            (root / "bindings" / "csharp" / "Demo.csproj").write_text(
                "<Project/>\n", encoding="utf-8"
            )
            (root / "bindings" / "go").mkdir(parents=True)
            (root / "bindings" / "go" / "go.mod").write_text(
                "module demo\n", encoding="utf-8"
            )

            ecosystems = dep_mod.detect_ecosystems(root)
            self.assertEqual(
                ecosystems,
                [
                    ("github-actions", "/"),
                    ("pip", "/"),
                    ("pip", "/sphinx_docs_build"),
                    ("npm", "/bindings/javascript"),
                    ("nuget", "/bindings/csharp"),
                    ("gomod", "/bindings/go"),
                ],
            )

            rc_gen = dep_mod.main(["--repo-root", str(root), "--generate"])
            self.assertEqual(rc_gen, 0)
            self.assertEqual(dep_mod.validate_dependabot_yaml(root), [])

            # Remove one entry and confirm validator catches it
            cfg = root / ".github" / "dependabot.yml"
            cfg.write_text(
                dep_mod.render_dependabot_yaml(ecosystems[:-1]),
                encoding="utf-8",
            )
            errors = dep_mod.validate_dependabot_yaml(root)
            self.assertTrue(any("gomod" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
