#!/usr/bin/env python3
"""Unit tests for _gh_common.py and enhanced check_open_prs.py fleet CI tooling."""

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _gh_common  # noqa: E402
import check_open_prs  # noqa: E402


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["mock"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestGhCommonFindGh(unittest.TestCase):
    """Tests for robust gh executable resolution in _gh_common.py."""

    def test_find_gh_prefers_env_override_when_executable(self):
        with (
            mock.patch.dict(os.environ, {"GH_BIN": "/custom/env/gh"}, clear=False),
            mock.patch("_gh_common.shutil.which", return_value="/usr/bin/gh"),
            mock.patch("_gh_common.os.path.isfile", return_value=True),
            mock.patch("_gh_common.os.access", return_value=True),
        ):
            self.assertEqual(_gh_common.find_gh(), "/custom/env/gh")

    def test_find_gh_uses_which_when_in_path(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("_gh_common.shutil.which", return_value="/custom/bin/gh"),
            mock.patch("_gh_common.os.path.isfile", return_value=True),
            mock.patch("_gh_common.os.access", return_value=True),
        ):
            self.assertEqual(_gh_common.find_gh(), "/custom/bin/gh")

    def test_find_gh_falls_back_to_homebrew_when_not_in_path(self):
        def fake_isfile(path: str) -> bool:
            return path == "/opt/homebrew/bin/gh"

        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("_gh_common.shutil.which", return_value=None),
            mock.patch("_gh_common.os.path.isfile", side_effect=fake_isfile),
            mock.patch("_gh_common.os.access", return_value=True),
        ):
            self.assertEqual(_gh_common.find_gh(), "/opt/homebrew/bin/gh")

    def test_find_gh_skips_missing_homebrew_and_uses_usr_local_bin(self):
        def fake_isfile(path: str) -> bool:
            return path == "/usr/local/bin/gh"

        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("_gh_common.shutil.which", return_value=None),
            mock.patch("_gh_common.os.path.isfile", side_effect=fake_isfile),
            mock.patch("_gh_common.os.access", return_value=True),
        ):
            self.assertEqual(_gh_common.find_gh(), "/usr/local/bin/gh")

    def test_find_gh_skips_non_executable_file(self):
        def fake_access(path: str, _mode: int) -> bool:
            return path == "/usr/bin/gh"

        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("_gh_common.shutil.which", return_value=None),
            mock.patch("_gh_common.os.path.isfile", return_value=True),
            mock.patch("_gh_common.os.access", side_effect=fake_access),
        ):
            self.assertEqual(_gh_common.find_gh(), "/usr/bin/gh")

    def test_find_gh_raises_when_unavailable(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("_gh_common.shutil.which", return_value=None),
            mock.patch("_gh_common.os.path.isfile", return_value=False),
        ):
            with self.assertRaises(FileNotFoundError):
                _gh_common.find_gh()


class TestCheckOpenPrs(unittest.TestCase):
    """Tests for check_open_prs.py behind_by, check buckets, and release runs."""

    def test_get_behind_by_same_repo_and_fork(self):
        seen_args = []

        def fake_run_gh(_gh_bin, args):
            seen_args.append(args)
            if "forkuser:feat/x" in args[1]:
                return _completed(stdout="4\n")
            return _completed(stdout="2\n")

        with mock.patch("check_open_prs.run_gh", side_effect=fake_run_gh):
            self.assertEqual(
                check_open_prs.get_behind_by(
                    "/opt/homebrew/bin/gh", "carlkidcrypto", "ezsnmp", "main", "feat/a"
                ),
                2,
            )
            self.assertEqual(
                check_open_prs.get_behind_by(
                    "/opt/homebrew/bin/gh",
                    "carlkidcrypto",
                    "ezsnmp",
                    "main",
                    "feat/x",
                    head_owner="forkuser",
                ),
                4,
            )

        self.assertIn("repos/carlkidcrypto/ezsnmp/compare/main...feat/a", seen_args[0])
        self.assertIn(
            "repos/carlkidcrypto/ezsnmp/compare/main...forkuser:feat/x", seen_args[1]
        )

    def test_get_behind_by_returns_none_on_error(self):
        with mock.patch(
            "check_open_prs.run_gh",
            return_value=_completed(stderr="Not Found", returncode=1),
        ):
            self.assertIsNone(
                check_open_prs.get_behind_by(
                    "/opt/homebrew/bin/gh", "carlkidcrypto", "ezsnmp", "main", "missing"
                )
            )

    def test_fetch_pr_checks_summary_json_buckets(self):
        checks_payload = [
            {"name": "pytest (ubuntu)", "state": "SUCCESS", "bucket": "pass"},
            {"name": "pytest (macos)", "state": "FAILURE", "bucket": "fail"},
            {"name": "build (win-arm64)", "state": "CANCELLED", "bucket": "cancel"},
            {"name": "lint", "state": "IN_PROGRESS", "bucket": "pending"},
            {"name": "deploy-pages", "state": "SKIPPED", "bucket": "skipping"},
            {"name": "extra-fail", "state": "FAILURE", "bucket": "fail"},
        ]
        with mock.patch(
            "check_open_prs.run_gh",
            return_value=_completed(stdout=json.dumps(checks_payload), returncode=1),
        ):
            summary = check_open_prs.fetch_pr_checks_summary(
                "/opt/homebrew/bin/gh", "carlkidcrypto/ezsnmp", 99, max_sample_fails=2
            )

        self.assertEqual(summary["pass"], 1)
        self.assertEqual(summary["fail"], 3)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["skip"], 1)
        self.assertEqual(
            summary["failed_checks"],
            ["pytest (macos)", "build (win-arm64)", "extra-fail"],
        )
        self.assertEqual(
            summary["sample_fails"], ["pytest (macos)", "build (win-arm64)"]
        )

    def test_fetch_pr_checks_summary_tab_fallback(self):
        tab_output = (
            "lint\tpass\t10s\thttps://example/1\n"
            "tests\tfail\t20s\thttps://example/2\n"
            "docs\tskipping\t0s\thttps://example/3\n"
            "build\tpending\t5s\thttps://example/4\n"
        )
        with mock.patch(
            "check_open_prs.run_gh",
            return_value=_completed(stdout=tab_output, returncode=1),
        ):
            summary = check_open_prs.fetch_pr_checks_summary(
                "/opt/homebrew/bin/gh", "carlkidcrypto/ezsnmp", 99, max_sample_fails=4
            )

        self.assertEqual(summary["pass"], 1)
        self.assertEqual(summary["fail"], 1)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(summary["skip"], 1)
        self.assertEqual(summary["failed_checks"], ["tests"])

    def test_fetch_release_runs_filters_and_limits(self):
        runs_payload = [
            {
                "databaseId": 1001,
                "workflowName": "Python Tests",
                "displayTitle": "chore: update tests",
                "status": "completed",
                "conclusion": "success",
                "headBranch": "main",
                "event": "push",
                "createdAt": "2026-11-24T12:00:00Z",
                "url": "https://github.com/carlkidcrypto/ezsnmp/actions/runs/1001",
            },
            {
                "databaseId": 1002,
                "workflowName": "Build and Publish to TestPyPI",
                "displayTitle": "v2026.11.24a0",
                "status": "completed",
                "conclusion": "success",
                "headBranch": "main",
                "event": "push",
                "createdAt": "2026-11-24T11:00:00Z",
                "url": "https://github.com/carlkidcrypto/ezsnmp/actions/runs/1002",
            },
            {
                "databaseId": 1003,
                "workflowName": "Build and Publish to PyPI",
                "displayTitle": "Release v2026.11.24",
                "status": "completed",
                "conclusion": "failure",
                "headBranch": "v2026.11.24",
                "event": "release",
                "createdAt": "2026-11-24T10:00:00Z",
                "url": "https://github.com/carlkidcrypto/ezsnmp/actions/runs/1003",
            },
            {
                "databaseId": 1004,
                "workflowName": "Publish NuGet Package",
                "displayTitle": "v2026.11.24",
                "status": "completed",
                "conclusion": "success",
                "headBranch": "v2026.11.24",
                "event": "release",
                "createdAt": "2026-11-24T09:00:00Z",
                "url": "https://github.com/carlkidcrypto/ezsnmp/actions/runs/1004",
            },
        ]
        with mock.patch(
            "check_open_prs.run_gh",
            return_value=_completed(stdout=json.dumps(runs_payload)),
        ):
            matched = check_open_prs.fetch_release_runs(
                "/opt/homebrew/bin/gh", "carlkidcrypto", "ezsnmp", limit=2
            )

        self.assertEqual([r["id"] for r in matched], [1002, 1003])
        self.assertEqual(matched[0]["repo"], "ezsnmp")
        self.assertEqual(matched[1]["conclusion"], "failure")

    def test_main_release_runs_json_and_text_output(self):
        def fake_run_gh(_gh_bin, args):
            if args[:2] == ["pr", "list"]:
                return _completed(
                    stdout=json.dumps(
                        [
                            {
                                "number": 42,
                                "headRefName": "feat/ci",
                                "baseRefName": "main",
                                "mergeable": "MERGEABLE",
                                "title": "Optimize CI",
                                "url": "https://github.com/carlkidcrypto/ezsnmp/pull/42",
                                "isCrossRepository": False,
                                "headRepositoryOwner": {"login": "carlkidcrypto"},
                            }
                        ]
                    )
                )
            if args[0] == "api" and "/compare/" in args[1]:
                return _completed(stdout="3\n")
            if args[:2] == ["pr", "checks"]:
                return _completed(
                    stdout=json.dumps(
                        [
                            {"name": "unit", "state": "SUCCESS", "bucket": "pass"},
                            {"name": "wheel", "state": "FAILURE", "bucket": "fail"},
                            {"name": "pages", "state": "SKIPPED", "bucket": "skipping"},
                        ]
                    )
                )
            if args[:2] == ["run", "list"]:
                return _completed(
                    stdout=json.dumps(
                        [
                            {
                                "databaseId": 555,
                                "workflowName": "Publish npm Package",
                                "displayTitle": "v2026.11.24",
                                "status": "completed",
                                "conclusion": "success",
                                "headBranch": "main",
                                "event": "release",
                                "createdAt": "2026-11-24T08:00:00Z",
                                "url": "https://github.com/carlkidcrypto/ezsnmp/actions/runs/555",
                            }
                        ]
                    )
                )
            raise AssertionError(f"Unexpected gh args: {args}")

        json_buf = io.StringIO()
        with (
            mock.patch("check_open_prs.find_gh", return_value="/opt/homebrew/bin/gh"),
            mock.patch("check_open_prs.run_gh", side_effect=fake_run_gh),
            redirect_stdout(json_buf),
        ):
            rc = check_open_prs.main(["--repo", "ezsnmp", "--release-runs", "--json"])

        self.assertEqual(rc, 0)
        payload = json.loads(json_buf.getvalue())
        self.assertEqual(len(payload["prs"]), 1)
        self.assertEqual(payload["prs"][0]["behind_by"], 3)
        self.assertEqual(payload["prs"][0]["skip"], 1)
        self.assertEqual(payload["prs"][0]["failed_checks"], ["wheel"])
        self.assertEqual(len(payload["release_runs"]), 1)
        self.assertEqual(payload["release_runs"][0]["id"], 555)

        text_buf = io.StringIO()
        with (
            mock.patch("check_open_prs.find_gh", return_value="/opt/homebrew/bin/gh"),
            mock.patch("check_open_prs.run_gh", side_effect=fake_run_gh),
            redirect_stdout(text_buf),
        ):
            rc = check_open_prs.main(["--repo", "ezsnmp", "--release-runs"])

        self.assertEqual(rc, 0)
        text = text_buf.getvalue()
        self.assertIn("#42 [MERGEABLE] behind=3 feat/ci -> main", text)
        self.assertIn("pass=1 fail=1 pend=0 skip=1", text)
        self.assertIn("failed=['wheel']", text)
        self.assertIn("Publish npm Package", text)


if __name__ == "__main__":
    unittest.main()
