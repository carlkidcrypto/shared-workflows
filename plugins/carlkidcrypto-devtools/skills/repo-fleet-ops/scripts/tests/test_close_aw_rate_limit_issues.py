"""Unit tests for close_aw_rate_limit_issues.py."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import close_aw_rate_limit_issues as mod  # noqa: E402


def _make_issue(
    number: int = 101,
    title: str = "[aw] Daily Repo Status: hit engine rate limit (HTTP 429)",
    body: str = (
        "<!-- gh-aw-failure-issue: true -->\n"
        "engine: copilot\n"
        "error: engine_rate_limit_429\n"
        "Run: https://github.com/carlkidcrypto/ezsnmp/actions/runs/9876543210\n"
    ),
    author: str = "app/github-actions",
    labels: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "number": number,
        "title": title,
        "body": body,
        "author": {"login": author},
        "labels": [{"name": lbl} for lbl in (labels or [])],
        "url": f"https://github.com/carlkidcrypto/ezsnmp/issues/{number}",
    }


class TestIssueClassification:
    """Tests for is_copilot_429_issue and actor/exclusion helpers."""

    def test_matches_title_and_app_github_actions(self) -> None:
        issue = _make_issue(author="app/github-actions")
        assert mod.is_copilot_429_issue(issue) is True

    def test_matches_github_actions_bot_and_body_markers(self) -> None:
        issue = _make_issue(
            title="[aw] Some Workflow failed",
            body=(
                "gh-aw-failure-issue: true\n"
                "engine: copilot\n"
                "engine_rate_limit_429\n"
            ),
            author="github-actions[bot]",
        )
        assert mod.is_copilot_429_issue(issue) is True

    def test_matches_agentic_workflows_label(self) -> None:
        issue = _make_issue(author="some-other-actor", labels=["agentic-workflows"])
        assert mod.is_copilot_429_issue(issue) is True

    def test_rejects_human_issue_without_aw_actor_or_label(self) -> None:
        issue = _make_issue(author="carlkidcrypto", labels=["bug"])
        assert mod.is_copilot_429_issue(issue) is False

    @pytest.mark.parametrize(
        "title",
        [
            "[aw] Detection Runs",
            "[aw] No-Op Runs",
            "[aw] Security Review: activation failed",
            "Workflow activation failed for daily-triage",
        ],
    )
    def test_rejects_excluded_aw_titles(self, title: str) -> None:
        issue = _make_issue(
            title=title,
            body=(
                "gh-aw-failure-issue: true\n"
                "engine: copilot\n"
                "engine_rate_limit_429\n"
            ),
            author="app/github-actions",
            labels=["agentic-workflows"],
        )
        assert mod.is_copilot_429_issue(issue) is False

    def test_rejects_incomplete_body_markers_without_429_title(self) -> None:
        issue = _make_issue(
            title="[aw] Generic failure",
            body="gh-aw-failure-issue: true\nengine: copilot\n",
            author="app/github-actions",
        )
        assert mod.is_copilot_429_issue(issue) is False


class TestRunIdAndLogVerification:
    """Tests for extract_run_id and verify_run_logs_429."""

    def test_extract_run_id_from_body(self) -> None:
        body = "See https://github.com/carlkidcrypto/ezsnmp/actions/runs/2468135790 for logs."
        assert mod.extract_run_id(body) == "2468135790"

    def test_extract_run_id_returns_none_when_absent(self) -> None:
        assert mod.extract_run_id("No actions URL here.") is None

    @pytest.mark.parametrize(
        "log_text",
        [
            "Error: ai_credits_rate_limit_error while invoking Copilot",
            "Response failed: errorCodes=[429] upstream",
            'Failure metadata: errorTypes=["rate_limit"]',
            "agent: 429 Too Many Requests",
            "upstream_error: quota_exceeded",
            "Quota exceeded for Copilot API",
        ],
    )
    def test_verify_run_logs_429_positive(
        self, monkeypatch: pytest.MonkeyPatch, log_text: str
    ) -> None:
        calls: List[List[str]] = []

        def fake_run_gh(
            gh_bin: str, args: List[str]
        ) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            return subprocess.CompletedProcess(
                args=[gh_bin, *args], returncode=0, stdout=log_text, stderr=""
            )

        monkeypatch.setattr(mod, "run_gh", fake_run_gh)
        assert mod.verify_run_logs_429("gh", "carlkidcrypto/ezsnmp", "12345") is True
        assert calls == [
            ["run", "view", "12345", "--repo", "carlkidcrypto/ezsnmp", "--log-failed"]
        ]

    def test_verify_run_logs_429_negative_and_nonzero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            mod,
            "run_gh",
            lambda gh_bin, args: subprocess.CompletedProcess(
                args=[gh_bin, *args],
                returncode=0,
                stdout="normal test failure",
                stderr="",
            ),
        )
        assert mod.verify_run_logs_429("gh", "carlkidcrypto/ezsnmp", "12345") is False

        monkeypatch.setattr(
            mod,
            "run_gh",
            lambda gh_bin, args: subprocess.CompletedProcess(
                args=[gh_bin, *args], returncode=1, stdout="", stderr="not found"
            ),
        )
        assert mod.verify_run_logs_429("gh", "carlkidcrypto/ezsnmp", "12345") is False


class TestDryRunAndApplyCLI:
    """Tests for dry-run vs --apply and CLI flags."""

    def test_dry_run_does_not_close_issues(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls: List[List[str]] = []
        issues = [
            _make_issue(number=42),
            _make_issue(number=43, title="[aw] Detection Runs"),
        ]

        def fake_run_gh(
            gh_bin: str, args: List[str]
        ) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[0:2] == ["issue", "list"]:
                return subprocess.CompletedProcess(
                    args=[gh_bin, *args],
                    returncode=0,
                    stdout=json.dumps(issues),
                    stderr="",
                )
            raise AssertionError(f"Unexpected gh command in dry-run: {args}")

        monkeypatch.setattr(mod, "find_gh", lambda: "gh")
        monkeypatch.setattr(mod, "run_gh", fake_run_gh)

        rc = mod.main(["--repo", "carlkidcrypto/ezsnmp", "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 1
        assert payload[0]["number"] == 42
        assert payload[0]["action"] == "would-close"
        assert payload[0]["run_id"] == "9876543210"
        assert len(calls) == 1

    def test_apply_closes_verified_issue_and_skips_unverified(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        calls: List[List[str]] = []
        issues = [
            _make_issue(
                number=10,
                body="https://github.com/carlkidcrypto/ezsnmp/actions/runs/11111",
            ),
            _make_issue(
                number=11,
                body="https://github.com/carlkidcrypto/ezsnmp/actions/runs/22222",
            ),
        ]

        def fake_run_gh(
            gh_bin: str, args: List[str]
        ) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[0:2] == ["issue", "list"]:
                return subprocess.CompletedProcess(
                    args=[gh_bin, *args],
                    returncode=0,
                    stdout=json.dumps(issues),
                    stderr="",
                )
            if args[0:2] == ["run", "view"]:
                run_id = args[2]
                out = (
                    "ai_credits_rate_limit_error"
                    if run_id == "11111"
                    else "other error"
                )
                return subprocess.CompletedProcess(
                    args=[gh_bin, *args], returncode=0, stdout=out, stderr=""
                )
            if args[0:2] == ["issue", "close"]:
                return subprocess.CompletedProcess(
                    args=[gh_bin, *args], returncode=0, stdout="", stderr=""
                )
            raise AssertionError(f"Unexpected gh command: {args}")

        monkeypatch.setattr(mod, "find_gh", lambda: "gh")
        monkeypatch.setattr(mod, "run_gh", fake_run_gh)

        rc = mod.main(
            [
                "--repo",
                "carlkidcrypto/ezsnmp",
                "--verify-logs",
                "--apply",
                "--json",
            ]
        )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert [r["action"] for r in payload] == ["closed", "skipped-unverified"]
        assert [
            "issue",
            "close",
            "10",
            "--repo",
            "carlkidcrypto/ezsnmp",
            "--reason",
            "not planned",
            "--comment",
            mod.DEFAULT_COMMENT,
        ] in calls
        assert not any(c[0:3] == ["issue", "close", "11"] for c in calls)
