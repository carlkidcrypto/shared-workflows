"""Unit tests for audit_aw_tracking_issues.py."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_aw_tracking_issues as mod  # noqa: E402


class TestCommentAndIssueParsing:
    def test_classify_tracking_issue(self) -> None:
        assert mod.classify_tracking_issue("[aw] No-Op Runs") == "noop"
        assert mod.classify_tracking_issue("[aw] Detection Runs") == "detection"
        assert mod.classify_tracking_issue("[aw] Sync Open PRs: hit 429") is None

    def test_parse_noop_comment(self) -> None:
        comment = {
            "createdAt": "2026-11-16T09:06:35Z",
            "body": (
                "### Coverage Autofix Python\n\n"
                "**Outcome:** `reported_no_action`\n\n"
                "> Generated from [Coverage Autofix Python]"
                "(https://github.com/carlkidcrypto/ezsnmp/actions/runs/43835993194)"
            ),
        }
        parsed = mod.parse_tracking_comment(comment, "noop")
        assert parsed["workflow"] == "Coverage Autofix Python"
        assert parsed["outcome"] == "reported_no_action"
        assert parsed["run_id"] == "43835993194"

    def test_parse_detection_failure_comment(self) -> None:
        comment = {
            "createdAt": "2026-11-23T03:00:19Z",
            "body": (
                "### Auto Update Release Notes\n\n"
                "**Outcome:** `detector_execution_failure`\n\n"
                "| Conclusion | `warning` |\n"
                "| Reason | `agent_failure` |\n"
                "| Run | [View run](https://github.com/carlkidcrypto/ezsnmp/actions/runs/45094693938) |"
            ),
        }
        parsed = mod.parse_tracking_comment(comment, "detection")
        assert parsed["workflow"] == "Auto Update Release Notes"
        assert parsed["outcome"] == "detector_execution_failure"
        assert parsed["reason"] == "agent_failure"
        assert parsed["run_id"] == "45094693938"

    def test_parse_detection_warning_comment(self) -> None:
        comment = {
            "createdAt": "2026-10-07T09:22:44Z",
            "body": (
                "### Coverage Autofix Every 3 Days\n\n"
                "Threat detection produced a **warning** result for this run.\n"
                "| Run | [View run](https://github.com/carlkidcrypto/os-specific-runner/actions/runs/12345) |"
            ),
        }
        parsed = mod.parse_tracking_comment(comment, "detection")
        assert parsed["outcome"] == "threat_warning"
        assert parsed["run_id"] == "12345"


class TestRunInspection:
    def test_inspect_true_noop(self, monkeypatch: Any) -> None:
        def fake_run_gh(_gh: str, args: list[str]) -> subprocess.CompletedProcess[str]:
            assert args[0:3] == ["run", "view", "1001"]
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "conclusion": "success",
                        "status": "completed",
                        "jobs": [{"name": "agent", "conclusion": "success"}],
                    }
                ),
                stderr="",
            )

        monkeypatch.setattr(mod, "run_gh", fake_run_gh)
        verdict, _ = mod.inspect_run_classification(
            "gh", "carlkidcrypto/ezsnmp", "noop", "reported_no_action", "1001"
        )
        assert verdict == "TRUE_NOOP"

    def test_inspect_false_noop_misconfigured(self, monkeypatch: Any) -> None:
        def fake_run_gh(_gh: str, args: list[str]) -> subprocess.CompletedProcess[str]:
            if "--log-failed" in args:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="SSL: CERTIFICATE_VERIFY_FAILED self-signed certificate",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "conclusion": "failure",
                        "status": "completed",
                        "jobs": [{"name": "agent", "conclusion": "failure"}],
                    }
                ),
                stderr="",
            )

        monkeypatch.setattr(mod, "run_gh", fake_run_gh)
        verdict, _ = mod.inspect_run_classification(
            "gh", "carlkidcrypto/ezsnmp", "noop", "incomplete", "1002"
        )
        assert verdict == "FALSE_NOOP_SUSPECT"

    def test_inspect_detection_429(self, monkeypatch: Any) -> None:
        def fake_run_gh(_gh: str, args: list[str]) -> subprocess.CompletedProcess[str]:
            if "--log-failed" in args:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="agent: 429 Too Many Requests\nquota_exceeded",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "conclusion": "failure",
                        "status": "completed",
                        "jobs": [
                            {"name": "agent", "conclusion": "failure"},
                            {"name": "detection", "conclusion": "success"},
                        ],
                    }
                ),
                stderr="",
            )

        monkeypatch.setattr(mod, "run_gh", fake_run_gh)
        verdict, _ = mod.inspect_run_classification(
            "gh",
            "carlkidcrypto/ezsnmp",
            "detection",
            "detector_execution_failure",
            "45094693938",
        )
        assert verdict == "RATE_LIMITED_429"

    def test_inspect_detection_non_429(self, monkeypatch: Any) -> None:
        def fake_run_gh(_gh: str, args: list[str]) -> subprocess.CompletedProcess[str]:
            if "--log-failed" in args:
                return subprocess.CompletedProcess(
                    args=args,
                    returncode=0,
                    stdout="Permission denied: missing copilot-requests: write",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "conclusion": "failure",
                        "status": "completed",
                        "jobs": [{"name": "detection", "conclusion": "failure"}],
                    }
                ),
                stderr="",
            )

        monkeypatch.setattr(mod, "run_gh", fake_run_gh)
        verdict, _ = mod.inspect_run_classification(
            "gh",
            "carlkidcrypto/ezsnmp",
            "detection",
            "detector_execution_failure",
            "2002",
        )
        assert verdict == "DETECTION_FAILURE_NON_429"

    def test_list_tracking_issues_skips_disabled_issues(self, monkeypatch: Any) -> None:
        def fake_run_gh(_gh: str, args: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr="the 'carlkidcrypto/carlkidcrypto.github.io' repository has disabled issues",
            )

        monkeypatch.setattr(mod, "run_gh", fake_run_gh)
        assert (
            mod.list_tracking_issues("gh", "carlkidcrypto/carlkidcrypto.github.io")
            == []
        )
