#!/usr/bin/env python3
"""Unit tests for ci-cd-workflow-optimization helper scripts."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import gh_pr_mail  # noqa: E402
import rerun_cancelled_jobs  # noqa: E402


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["mock"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestGhPrMail(unittest.TestCase):
    """Tests for gh_pr_mail.py."""

    def test_find_tool_uses_which_first(self):
        with (
            mock.patch("gh_pr_mail.shutil.which", return_value="/custom/bin/gh"),
            mock.patch("gh_pr_mail.os.path.isfile", return_value=True),
            mock.patch("gh_pr_mail.os.access", return_value=True),
        ):
            self.assertEqual(gh_pr_mail.find_gh(), "/custom/bin/gh")

    def test_find_tool_falls_back_to_homebrew(self):
        def fake_isfile(path: str) -> bool:
            return path == "/opt/homebrew/bin/gh"

        with (
            mock.patch("gh_pr_mail.shutil.which", return_value=None),
            mock.patch("gh_pr_mail.os.path.isfile", side_effect=fake_isfile),
            mock.patch("gh_pr_mail.os.access", return_value=True),
        ):
            self.assertEqual(gh_pr_mail.find_gh(), "/opt/homebrew/bin/gh")

    def test_find_tool_raises_when_missing(self):
        with (
            mock.patch("gh_pr_mail.shutil.which", return_value=None),
            mock.patch("gh_pr_mail.os.path.isfile", return_value=False),
        ):
            with self.assertRaises(FileNotFoundError):
                gh_pr_mail.find_gh()

    def test_split_repo_validation(self):
        self.assertEqual(
            gh_pr_mail.split_repo("carlkidcrypto/ezsnmp"), ("carlkidcrypto", "ezsnmp")
        )
        for bad in ("ezsnmp", "a/b/c", "/repo", "owner/"):
            with self.assertRaises(ValueError):
                gh_pr_mail.split_repo(bad)

    def test_two_pass_read_filters_unresolved_and_outputs_json(self):
        graphql_payload = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "T1",
                                    "isResolved": False,
                                    "path": "src/foo.py",
                                    "line": 12,
                                    "comments": {
                                        "nodes": [
                                            {
                                                "databaseId": 101,
                                                "author": {"login": "copilot"},
                                                "body": "Fix null check",
                                            }
                                        ]
                                    },
                                },
                                {
                                    "id": "T2",
                                    "isResolved": True,
                                    "path": "src/bar.py",
                                    "line": 5,
                                    "comments": {"nodes": []},
                                },
                            ]
                        }
                    }
                }
            }
        }
        pull_comments = [
            {
                "id": 101,
                "path": "src/foo.py",
                "user": {"login": "copilot"},
                "body": "Fix null check",
            }
        ]
        issue_comments = [
            {"id": 202, "user": {"login": "carlkidcrypto"}, "body": "Please rebase"}
        ]

        def fake_run_gh(_gh_bin, args):
            if args[:2] == ["api", "graphql"]:
                return _completed(stdout=json.dumps(graphql_payload))
            if args[1] == "repos/carlkidcrypto/ezsnmp/pulls/42/comments":
                return _completed(stdout=json.dumps(pull_comments))
            if args[1] == "repos/carlkidcrypto/ezsnmp/issues/42/comments":
                return _completed(stdout=json.dumps(issue_comments))
            raise AssertionError(f"Unexpected gh args: {args}")

        stdout = io.StringIO()
        with (
            mock.patch("gh_pr_mail.find_gh", return_value="/opt/homebrew/bin/gh"),
            mock.patch("gh_pr_mail.run_gh", side_effect=fake_run_gh),
            redirect_stdout(stdout),
        ):
            rc = gh_pr_mail.main(
                ["--repo", "carlkidcrypto/ezsnmp", "--pr", "42", "--json"]
            )

        self.assertEqual(rc, 0)
        parsed = json.loads(stdout.getvalue())
        self.assertEqual(len(parsed["unresolved_threads"]), 1)
        self.assertEqual(parsed["unresolved_threads"][0]["id"], "T1")
        self.assertEqual(len(parsed["pull_comments"]), 1)
        self.assertEqual(len(parsed["issue_comments"]), 1)

    def test_two_pass_read_graphql_failure_returns_nonzero(self):
        stderr = io.StringIO()
        with (
            mock.patch("gh_pr_mail.find_gh", return_value="/opt/homebrew/bin/gh"),
            mock.patch(
                "gh_pr_mail.run_gh",
                return_value=_completed(stderr="auth failed", returncode=1),
            ),
            redirect_stderr(stderr),
        ):
            rc = gh_pr_mail.main(["--repo", "carlkidcrypto/ezsnmp", "--pr", "42"])

        self.assertEqual(rc, 1)
        self.assertIn("GraphQL reviewThreads query failed", stderr.getvalue())

    def test_reply_to_posts_formatted_threaded_reply(self):
        recorded = []

        def fake_run_gh(gh_bin, args):
            recorded.append((gh_bin, args))
            return _completed(stdout=json.dumps({"id": 777}))

        stdout = io.StringIO()
        with (
            mock.patch("gh_pr_mail.find_gh", return_value="/opt/homebrew/bin/gh"),
            mock.patch("gh_pr_mail.run_gh", side_effect=fake_run_gh),
            redirect_stdout(stdout),
        ):
            rc = gh_pr_mail.main(
                [
                    "--repo",
                    "carlkidcrypto/ezsnmp",
                    "--pr",
                    "42",
                    "--reply-to",
                    "555",
                    "--commit",
                    "abc1234",
                    "--summary",
                    "Guarded null pointer",
                ]
            )

        self.assertEqual(rc, 0)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(
            recorded[0][1],
            [
                "api",
                "repos/carlkidcrypto/ezsnmp/pulls/42/comments",
                "-X",
                "POST",
                "-F",
                "in_reply_to=555",
                "-f",
                "body=Addressed in commit `abc1234`: Guarded null pointer",
            ],
        )
        self.assertIn(
            "Addressed in commit `abc1234`: Guarded null pointer", stdout.getvalue()
        )

    def test_parse_args_rejects_partial_reply_flags(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                gh_pr_mail.parse_args(
                    ["--repo", "a/b", "--pr", "1", "--reply-to", "10"]
                )

    def test_check_unpushed_clean_and_dirty(self):
        def fake_run_clean(cmd):
            if "rev-parse" in cmd:
                return _completed(stdout="feat/my-branch\n")
            if "log" in cmd:
                self.assertIn("origin/feat/my-branch..HEAD", cmd)
                return _completed(stdout="")
            raise AssertionError(f"Unexpected cmd: {cmd}")

        stdout = io.StringIO()
        with (
            mock.patch("gh_pr_mail.find_git", return_value="/usr/bin/git"),
            mock.patch("gh_pr_mail.run_cmd", side_effect=fake_run_clean),
            redirect_stdout(stdout),
        ):
            rc = gh_pr_mail.main(
                ["--repo", "carlkidcrypto/ezsnmp", "--pr", "42", "--check-unpushed"]
            )
        self.assertEqual(rc, 0)
        self.assertIn("origin/feat/my-branch..HEAD is empty", stdout.getvalue())

        def fake_run_dirty(cmd):
            if "log" in cmd:
                return _completed(stdout="deadbeef wip commit\n")
            raise AssertionError(f"Unexpected cmd: {cmd}")

        stderr = io.StringIO()
        with (
            mock.patch("gh_pr_mail.find_git", return_value="/usr/bin/git"),
            mock.patch("gh_pr_mail.run_cmd", side_effect=fake_run_dirty),
            redirect_stderr(stderr),
        ):
            rc = gh_pr_mail.main(
                [
                    "--repo",
                    "carlkidcrypto/ezsnmp",
                    "--pr",
                    "42",
                    "--check-unpushed",
                    "--branch",
                    "feat/test",
                ]
            )
        self.assertEqual(rc, 1)
        self.assertIn("deadbeef wip commit", stderr.getvalue())


class TestRerunCancelledJobs(unittest.TestCase):
    """Tests for rerun_cancelled_jobs.py."""

    def test_parse_paginated_jobs_handles_multiple_pages(self):
        page1 = json.dumps({"total_count": 2, "jobs": [{"id": 1, "name": "linux"}]})
        page2 = json.dumps({"total_count": 2, "jobs": [{"id": 2, "name": "macos"}]})
        jobs = rerun_cancelled_jobs.parse_paginated_jobs(f"{page1}\n{page2}\n")
        self.assertEqual([j["id"] for j in jobs], [1, 2])

    def test_run_id_triggers_rerun_for_infra_cancelled_job(self):
        calls = []

        def fake_run_gh(_gh_bin, args):
            calls.append(args)
            if args[1].endswith("/jobs"):
                return _completed(
                    stdout=json.dumps(
                        {
                            "jobs": [
                                {
                                    "id": 9001,
                                    "name": "build (ubuntu-latest)",
                                    "conclusion": "cancelled",
                                    "runner_id": 0,
                                },
                                {
                                    "id": 9002,
                                    "name": "build (macos-latest)",
                                    "conclusion": "success",
                                    "runner_id": 12,
                                },
                            ]
                        }
                    )
                )
            if args[1].endswith("/rerun-failed-jobs"):
                return _completed(stdout="")
            raise AssertionError(f"Unexpected args: {args}")

        stdout = io.StringIO()
        with (
            mock.patch(
                "rerun_cancelled_jobs.find_gh", return_value="/opt/homebrew/bin/gh"
            ),
            mock.patch("rerun_cancelled_jobs.run_gh", side_effect=fake_run_gh),
            redirect_stdout(stdout),
        ):
            rc = rerun_cancelled_jobs.main(
                ["--repo", "carlkidcrypto/ezsnmp", "--run-id", "12345"]
            )

        self.assertEqual(rc, 0)
        self.assertIn(
            [
                "api",
                "repos/carlkidcrypto/ezsnmp/actions/runs/12345/rerun-failed-jobs",
                "-X",
                "POST",
            ],
            calls,
        )
        self.assertIn("infra_cancelled(runner_id==0)=1", stdout.getvalue())

    def test_dry_run_does_not_post(self):
        calls = []

        def fake_run_gh(_gh_bin, args):
            calls.append(args)
            return _completed(
                stdout=json.dumps(
                    {
                        "jobs": [
                            {
                                "id": 1,
                                "name": "test",
                                "conclusion": "cancelled",
                                "runner_id": 0,
                            }
                        ]
                    }
                )
            )

        stdout = io.StringIO()
        with (
            mock.patch(
                "rerun_cancelled_jobs.find_gh", return_value="/opt/homebrew/bin/gh"
            ),
            mock.patch("rerun_cancelled_jobs.run_gh", side_effect=fake_run_gh),
            redirect_stdout(stdout),
        ):
            rc = rerun_cancelled_jobs.main(
                ["--repo", "carlkidcrypto/ezsnmp", "--run-id", "777", "--dry-run"]
            )

        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("[DRY-RUN]", stdout.getvalue())

    def test_pr_mode_filters_runs_and_respects_infra_only(self):
        calls = []

        def fake_run_gh(_gh_bin, args):
            calls.append(args)
            if args[:2] == ["pr", "view"]:
                return _completed(
                    stdout=json.dumps(
                        {"headRefOid": "deadbeef", "headRefName": "feat/x"}
                    )
                )
            if args[1].startswith("repos/carlkidcrypto/ezsnmp/actions/runs?head_sha="):
                return _completed(
                    stdout=json.dumps(
                        {
                            "workflow_runs": [
                                {"id": 100, "name": "CI", "conclusion": "cancelled"},
                                {"id": 101, "name": "Lint", "conclusion": "failure"},
                                {"id": 102, "name": "Docs", "conclusion": "success"},
                            ]
                        }
                    )
                )
            if args[1] == "repos/carlkidcrypto/ezsnmp/actions/runs/100/jobs":
                return _completed(
                    stdout=json.dumps(
                        {
                            "jobs": [
                                {
                                    "id": 1,
                                    "name": "win-arm64",
                                    "conclusion": "cancelled",
                                    "runner_id": 0,
                                }
                            ]
                        }
                    )
                )
            if args[1] == "repos/carlkidcrypto/ezsnmp/actions/runs/101/jobs":
                return _completed(
                    stdout=json.dumps(
                        {
                            "jobs": [
                                {
                                    "id": 2,
                                    "name": "pytest",
                                    "conclusion": "failure",
                                    "runner_id": 44,
                                }
                            ]
                        }
                    )
                )
            if args[1].endswith("/rerun-failed-jobs"):
                return _completed(stdout="")
            raise AssertionError(f"Unexpected args: {args}")

        stdout = io.StringIO()
        with (
            mock.patch(
                "rerun_cancelled_jobs.find_gh", return_value="/opt/homebrew/bin/gh"
            ),
            mock.patch("rerun_cancelled_jobs.run_gh", side_effect=fake_run_gh),
            redirect_stdout(stdout),
        ):
            rc = rerun_cancelled_jobs.main(
                [
                    "--repo",
                    "carlkidcrypto/ezsnmp",
                    "--pr",
                    "88",
                    "--infra-only",
                    "--json",
                ]
            )

        self.assertEqual(rc, 0)
        summary = json.loads(stdout.getvalue())
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["run_id"], 100)
        self.assertTrue(summary[0]["triggered"])
        self.assertIn(
            [
                "api",
                "repos/carlkidcrypto/ezsnmp/actions/runs/100/rerun-failed-jobs",
                "-X",
                "POST",
            ],
            calls,
        )
        self.assertNotIn(
            [
                "api",
                "repos/carlkidcrypto/ezsnmp/actions/runs/101/rerun-failed-jobs",
                "-X",
                "POST",
            ],
            calls,
        )


class TestLintCiScript(unittest.TestCase):
    """Integration-style unit tests for lint_ci.sh guardrails."""

    def setUp(self):
        self.script = SCRIPTS_DIR / "lint_ci.sh"

    def _init_git_repo(self, path: Path, branch: str = "main") -> None:
        subprocess.run(
            ["git", "init", "-b", branch],
            cwd=path,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=path,
            check=True,
        )
        (path / "README.md").write_text("init\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=path,
            check=True,
            stdout=subprocess.DEVNULL,
        )

    def test_rejects_main_branch_without_allow_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo, branch="main")
            res = subprocess.run(
                [str(self.script), "--repo-dir", str(repo)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("HEAD is on 'main'", res.stderr)

    def test_rejects_github_script_singular_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo, branch="feat/test")
            bad_dir = repo / ".github" / "script"
            bad_dir.mkdir(parents=True)
            (bad_dir / "helper.py").write_text("print('hi')\n", encoding="utf-8")
            res = subprocess.run(
                [str(self.script), "--repo-dir", str(repo)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn(".github/script/", res.stderr)

    def test_passes_on_clean_feature_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_git_repo(repo, branch="feat/test")
            res = subprocess.run(
                [str(self.script), "--repo-dir", str(repo)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertIn("All checks passed.", res.stdout)


if __name__ == "__main__":
    unittest.main()
