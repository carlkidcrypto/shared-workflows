"""Unit tests for scripts/generate_release_notes.py."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "generate_release_notes.py"
_SPEC = importlib.util.spec_from_file_location(
    "generate_release_notes", str(_SCRIPT_PATH)
)
assert _SPEC is not None and _SPEC.loader is not None
gen_mod = importlib.util.module_from_spec(_SPEC)
sys.modules["generate_release_notes"] = gen_mod
_SPEC.loader.exec_module(gen_mod)


class TestGenerateReleaseNotes(unittest.TestCase):
    """Test cases for generate_release_notes."""

    def test_clean_title(self) -> None:
        raw1 = (
            "Fix rate limit header parsing (#123) by @contributor "
            "in https://github.com/owner/example_pkg/pull/123"
        )
        self.assertEqual(gen_mod.clean_title(raw1), "Fix rate limit header parsing")

        raw2 = "[docs] Update documentation for Read API #456"
        self.assertEqual(
            gen_mod.clean_title(raw2), "[docs] Update documentation for Read API"
        )

    def test_rewrite_to_natural_language(self) -> None:
        self.assertEqual(
            gen_mod.rewrite_to_natural_language(
                "feat(read): add batch sensor request option"
            ),
            "Adds batch sensor request option",
        )
        self.assertEqual(
            gen_mod.rewrite_to_natural_language(
                "fix: resolve timeout on large payload"
            ),
            "Resolves timeout on large payload",
        )
        self.assertEqual(
            gen_mod.rewrite_to_natural_language(
                "chore(deps): bump requests from 2.31 to 2.32"
            ),
            "Bumps requests from 2.31 to 2.32",
        )

    def test_categorize_item(self) -> None:
        self.assertEqual(
            gen_mod.categorize_item("Update deps", ["requirements.txt"]),
            "Dependencies",
        )
        self.assertEqual(
            gen_mod.categorize_item("Fix CI", [".github/workflows/ci.yml"]),
            "CI / Workflows",
        )
        self.assertEqual(
            gen_mod.categorize_item("Add unit test", ["tests/test_example.py"]),
            "Tests",
        )
        self.assertEqual(
            gen_mod.categorize_item(
                "Fix bug in core",
                ["example_pkg/client.py"],
                core_prefixes=("example_pkg/",),
            ),
            "Bug Fixes",
        )

    def test_parse_semver_and_determine_base_tag(self) -> None:
        self.assertEqual(gen_mod.parse_semver("v1.5.0"), (1, 5, 0, 1, ""))
        releases = [
            {"tag_name": "v1.4.0", "prerelease": False},
            {"tag_name": "v1.5.0a0", "prerelease": True},
            {"tag_name": "v1.5.0", "prerelease": False},
        ]
        self.assertEqual(
            gen_mod.determine_base_tag(
                releases[-1], releases, {"v1.4.0", "v1.5.0a0", "v1.5.0"}
            ),
            "v1.4.0",
        )

    def test_build_release_notes(self) -> None:
        release: dict[str, Any] = {
            "tag_name": "v1.5.0",
            "prerelease": False,
            "body": (
                "* Add async client support by @contributor "
                "in https://github.com/owner/example_pkg/pull/102"
            ),
        }
        git_commits: dict[str, dict[str, Any]] = {
            "abcdef1234567": {
                "title": "Add async client support (#102)",
                "files": ["example_pkg/client.py"],
            },
            "1112223334445": {
                "title": "Fix timeout handling",
                "files": ["example_pkg/http.py"],
            },
        }
        notes = gen_mod.build_release_notes(
            release,
            "v1.4.0",
            git_commits,
            repo="owner/example_pkg",
            package="example_pkg",
            core_prefixes=("example_pkg/",),
        )
        self.assertIn("example_pkg", notes)
        self.assertIn("pip install example_pkg==1.5.0", notes)
        self.assertIn("https://pypi.org/project/example_pkg/1.5.0/", notes)
        self.assertIn(
            "**Full Changelog**: https://github.com/owner/example_pkg/compare/v1.4.0...v1.5.0",
            notes,
        )


if __name__ == "__main__":
    unittest.main()
