#!/usr/bin/env python3
"""Unit tests for sonar_triage.py."""

import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sonar_triage  # noqa: E402


class _FakeHTTPResponse:
    """Minimal context-manager mock for urllib.request.urlopen responses."""

    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


def _sample_responses() -> dict:
    return {
        "/api/qualitygates/project_status": {
            "projectStatus": {
                "status": "ERROR",
                "conditions": [
                    {
                        "status": "ERROR",
                        "metricKey": "new_bugs",
                        "actualValue": "2",
                        "errorThreshold": "0",
                    },
                    {
                        "status": "OK",
                        "metricKey": "new_coverage",
                        "actualValue": "92.5",
                        "errorThreshold": "80",
                    },
                ],
            }
        },
        "/api/measures/component": {
            "component": {
                "measures": [
                    {"metric": "bugs", "value": "2"},
                    {"metric": "vulnerabilities", "value": "1"},
                    {"metric": "code_smells", "value": "5"},
                    {"metric": "coverage", "value": "88.4"},
                    {"metric": "duplicated_lines_density", "value": "0.0"},
                    {"metric": "security_hotspots_reviewed", "value": "100.0"},
                    {"metric": "security_rating", "value": "2.0"},
                    {"metric": "reliability_rating", "value": "3.0"},
                    {"metric": "sqale_rating", "value": "1.0"},
                ]
            }
        },
        "/api/issues/search": {
            "total": 3,
            "issues": [
                {
                    "key": "issue-1",
                    "type": "BUG",
                    "severity": "MAJOR",
                    "rule": "python:S1234",
                    "component": "carlkidcrypto_ezsnmp:src/mod.py",
                    "line": 42,
                    "message": "Fix potential None dereference.",
                },
                {
                    "key": "issue-2",
                    "type": "VULNERABILITY",
                    "severity": "CRITICAL",
                    "rule": "python:S5678",
                    "component": "carlkidcrypto_ezsnmp:src/auth.py",
                    "line": 17,
                    "message": "Avoid hardcoded credential.",
                },
                {
                    "key": "issue-3",
                    "type": "CODE_SMELL",
                    "severity": "MINOR",
                    "rule": "python:S9999",
                    "component": "carlkidcrypto_ezsnmp:src/util.py",
                    "line": 8,
                    "message": "Remove unused import.",
                },
            ],
        },
        "/api/hotspots/search": {
            "paging": {"total": 1},
            "hotspots": [
                {
                    "key": "hotspot-1",
                    "vulnerabilityProbability": "MEDIUM",
                    "securityCategory": "command-injection",
                    "component": "carlkidcrypto_ezsnmp:src/cli.py",
                    "line": 99,
                    "message": "Make sure command arguments are sanitized.",
                }
            ],
        },
    }


class TestSonarTriage(unittest.TestCase):
    """Test suite for SonarCloud triage CLI."""

    def test_resolve_project_key(self) -> None:
        self.assertEqual(
            sonar_triage.resolve_project_key("carlkidcrypto_ezsnmp", None),
            "carlkidcrypto_ezsnmp",
        )
        self.assertEqual(
            sonar_triage.resolve_project_key(None, "carlkidcrypto/ezsnmp"),
            "carlkidcrypto_ezsnmp",
        )
        with self.assertRaises(ValueError):
            sonar_triage.resolve_project_key(None, "invalid-repo")
        with self.assertRaises(ValueError):
            sonar_triage.resolve_project_key(None, None)

    def test_collect_triage_data_pr_and_token(self) -> None:
        responses = _sample_responses()
        seen_requests = []

        def fake_urlopen(req, timeout=20):
            seen_requests.append((req.full_url, dict(req.header_items())))
            path = urllib.parse.urlparse(req.full_url).path
            return _FakeHTTPResponse(responses[path])

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            data = sonar_triage.collect_triage_data(
                project_key="carlkidcrypto_ezsnmp",
                pr=42,
                token="secret-token",
            )

        self.assertEqual(len(seen_requests), 4)
        for url, headers in seen_requests:
            self.assertIn("pullRequest=42", url)
            self.assertIn("Authorization", headers)
            self.assertTrue(headers["Authorization"].startswith("Basic "))

        self.assertEqual(data["qualityGate"]["status"], "ERROR")
        self.assertEqual(len(data["qualityGate"]["failingConditions"]), 1)
        self.assertEqual(data["issues"]["total"], 3)
        self.assertEqual(data["issues"]["byType"]["BUG"], 1)
        self.assertEqual(data["issues"]["byType"]["VULNERABILITY"], 1)
        self.assertEqual(data["issues"]["byType"]["CODE_SMELL"], 1)
        self.assertEqual(data["hotspots"]["total"], 1)
        self.assertEqual(data["measures"]["coverage"], "88.4")

    def test_cli_json_output_with_branch_and_no_token(self) -> None:
        responses = _sample_responses()
        seen_requests = []

        def fake_urlopen(req, timeout=20):
            seen_requests.append((req.full_url, dict(req.header_items())))
            path = urllib.parse.urlparse(req.full_url).path
            return _FakeHTTPResponse(responses[path])

        buf = io.StringIO()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            redirect_stdout(buf),
        ):
            exit_code = sonar_triage.main(
                ["--repo", "carlkidcrypto/ezsnmp", "--branch", "main", "--json"]
            )

        self.assertEqual(exit_code, 0)
        for url, headers in seen_requests:
            self.assertIn("branch=main", url)
            self.assertNotIn("Authorization", headers)

        parsed = json.loads(buf.getvalue())
        self.assertEqual(parsed["projectKey"], "carlkidcrypto_ezsnmp")
        self.assertEqual(parsed["scope"]["branch"], "main")
        self.assertEqual(parsed["qualityGate"]["status"], "ERROR")

    def test_cli_text_output(self) -> None:
        responses = _sample_responses()

        def fake_urlopen(req, timeout=20):
            path = urllib.parse.urlparse(req.full_url).path
            return _FakeHTTPResponse(responses[path])

        buf = io.StringIO()
        with (
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            redirect_stdout(buf),
        ):
            exit_code = sonar_triage.main(["--project", "carlkidcrypto_ezsnmp"])

        self.assertEqual(exit_code, 0)
        output = buf.getvalue()
        self.assertIn(
            "SonarCloud Triage: carlkidcrypto_ezsnmp (default branch)", output
        )
        self.assertIn("Quality Gate: ERROR", output)
        self.assertIn("Ratings (Sec/Rel/Maint): B/C/A", output)
        self.assertIn("Coverage: 88.4% | Duplication: 0.0%", output)
        self.assertIn("Open Issues: 3 (BUG=1, VULNERABILITY=1, CODE_SMELL=1)", output)
        self.assertIn("Security Hotspots (TO_REVIEW): 1", output)

    def test_cli_http_error_returns_nonzero(self) -> None:
        http_err = urllib.error.HTTPError(
            url="https://sonarcloud.io/api/qualitygates/project_status",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_err):
            exit_code = sonar_triage.main(["--project", "carlkidcrypto_ezsnmp"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
