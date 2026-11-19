#!/usr/bin/env python3
"""Query SonarCloud quality gates, measures, issues, hotspots, and Codecov status.

Uses SonarCloud's public REST API (with optional `SONAR_TOKEN` env var) and
optionally Codecov's v2 REST API (with optional `CODECOV_TOKEN` env var).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

SONARCLOUD_API = "https://sonarcloud.io/api"
CODECOV_API = "https://api.codecov.io/api/v2"
DEFAULT_METRICS = (
    "coverage,bugs,vulnerabilities,code_smells,"
    "duplicated_lines_density,security_hotspots,reliability_rating,"
    "security_rating,sqale_rating"
)


def http_get_json(
    url: str,
    token: Optional[str] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Perform a GET request and return parsed JSON or a structured error dict."""
    headers = {"Accept": "application/json", "User-Agent": "devtools-quality-query/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return {"ok": True, "status": resp.status, "data": json.loads(raw)}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "ok": False,
            "status": exc.code,
            "error": f"HTTP {exc.code}: {exc.reason}",
            "body": body[:500],
        }
    except urllib.error.URLError as exc:
        return {"ok": False, "status": None, "error": f"URL error: {exc.reason}"}


def build_sonar_url(endpoint: str, params: Dict[str, Any]) -> str:
    """Build a SonarCloud API URL with non-None query parameters."""
    filtered = {k: v for k, v in params.items() if v is not None}
    return f"{SONARCLOUD_API}/{endpoint}?{urllib.parse.urlencode(filtered)}"


def query_sonarcloud(
    project_key: str,
    pr: Optional[str],
    include_hotspots: bool,
    sonar_token: Optional[str],
) -> Dict[str, Any]:
    """Query SonarCloud quality gate, measures, open issues, and optional hotspots."""
    pr_param = str(pr) if pr else None

    qg_url = build_sonar_url(
        "qualitygates/project_status",
        {"projectKey": project_key, "pullRequest": pr_param},
    )
    measures_url = build_sonar_url(
        "measures/component",
        {
            "component": project_key,
            "metricKeys": DEFAULT_METRICS,
            "pullRequest": pr_param,
        },
    )
    issues_url = build_sonar_url(
        "issues/search",
        {
            "componentKeys": project_key,
            "resolved": "false",
            "ps": 50,
            "pullRequest": pr_param,
        },
    )

    out: Dict[str, Any] = {
        "project_key": project_key,
        "pull_request": pr_param,
        "quality_gate": http_get_json(qg_url, token=sonar_token),
        "measures": http_get_json(measures_url, token=sonar_token),
        "issues": http_get_json(issues_url, token=sonar_token),
    }

    if include_hotspots:
        hotspots_url = build_sonar_url(
            "hotspots/search",
            {
                "projectKey": project_key,
                "status": "TO_REVIEW",
                "ps": 50,
                "pullRequest": pr_param,
            },
        )
        out["hotspots"] = http_get_json(hotspots_url, token=sonar_token)

    return out


def query_codecov(
    repo_slug: str,
    pr: Optional[str],
    codecov_token: Optional[str],
) -> Dict[str, Any]:
    """Query Codecov v2 API for repository totals or PR coverage."""
    if "/" not in repo_slug:
        return {
            "ok": False,
            "error": f"Invalid --repo format '{repo_slug}', expected owner/repo",
        }
    owner, repo = repo_slug.split("/", 1)
    if pr:
        url = f"{CODECOV_API}/github/{owner}/repos/{repo}/pulls/{pr}/"
    else:
        url = f"{CODECOV_API}/github/{owner}/repos/{repo}/totals/"
    return http_get_json(url, token=codecov_token)


def summarize_sonar(sonar: Dict[str, Any]) -> None:
    """Print a human-readable summary of SonarCloud results."""
    print(f"SonarCloud Project: {sonar['project_key']}")
    if sonar.get("pull_request"):
        print(f"Pull Request: #{sonar['pull_request']}")

    qg = sonar["quality_gate"]
    if qg.get("ok"):
        ps = qg["data"].get("projectStatus", {})
        print(f"Quality Gate: {ps.get('status', 'UNKNOWN')}")
        for cond in ps.get("conditions", []):
            status = cond.get("status", "UNKNOWN")
            if status != "OK":
                print(
                    f"  - [{status}] {cond.get('metricKey')}: "
                    f"actual={cond.get('actualValue')} "
                    f"(threshold {cond.get('comparator')} {cond.get('errorThreshold')})"
                )
    else:
        print(f"Quality Gate: ERROR ({qg.get('error')})")

    measures = sonar["measures"]
    if measures.get("ok"):
        comp = measures["data"].get("component", {})
        vals = {
            m["metric"]: m.get("value")
            for m in comp.get("measures", [])
            if "metric" in m
        }
        if vals:
            print("Measures:")
            for k in sorted(vals):
                print(f"  - {k}: {vals[k]}")
    else:
        print(f"Measures: ERROR ({measures.get('error')})")

    issues = sonar["issues"]
    if issues.get("ok"):
        data = issues["data"]
        total = data.get("total", len(data.get("issues", [])))
        print(f"Open Issues: {total}")
        for issue in data.get("issues", [])[:10]:
            sev = issue.get("severity", "?")
            rule = issue.get("rule", "?")
            comp = issue.get("component", "").split(":")[-1]
            line = issue.get("line", "?")
            msg = issue.get("message", "")
            print(f"  - [{sev}] {rule} {comp}:{line} - {msg}")
    else:
        print(f"Open Issues: ERROR ({issues.get('error')})")

    if "hotspots" in sonar:
        hs = sonar["hotspots"]
        if hs.get("ok"):
            paging = hs["data"].get("paging", {})
            items = hs["data"].get("hotspots", [])
            total = paging.get("total", len(items))
            print(f"Security Hotspots (TO_REVIEW): {total}")
            for item in items[:10]:
                prob = item.get("vulnerabilityProbability", "?")
                comp = item.get("component", "").split(":")[-1]
                line = item.get("line", "?")
                msg = item.get("message", "")
                print(f"  - [{prob}] {comp}:{line} - {msg}")
        else:
            print(f"Security Hotspots: ERROR ({hs.get('error')})")


def summarize_codecov(codecov: Dict[str, Any]) -> None:
    """Print a human-readable summary of Codecov results."""
    print("Codecov:")
    if not codecov.get("ok"):
        print(f"  - ERROR ({codecov.get('error')})")
        return
    data = codecov.get("data", {})
    totals = data.get("totals") or data.get("head", {}).get("totals") or data
    if isinstance(totals, dict) and "coverage" in totals:
        print(f"  - Coverage: {totals.get('coverage')}%")
        for key in ("lines", "hits", "misses", "partials"):
            if key in totals:
                print(f"  - {key}: {totals[key]}")
    else:
        print(f"  - Response keys: {', '.join(sorted(data.keys()))}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Query SonarCloud quality gates, metrics, issues, hotspots, and Codecov."
    )
    parser.add_argument(
        "--project",
        help="SonarCloud project key (defaults to <owner>_<repo> if --repo is set).",
    )
    parser.add_argument(
        "--repo",
        help="GitHub repository slug (<owner/repo>) for project inference and Codecov.",
    )
    parser.add_argument(
        "--pr",
        help="Pull request number to scope SonarCloud and Codecov queries.",
    )
    parser.add_argument(
        "--include-hotspots",
        action="store_true",
        help="Also query SonarCloud security hotspots (TO_REVIEW).",
    )
    parser.add_argument(
        "--include-codecov",
        action="store_true",
        help="Also query Codecov v2 API (requires --repo).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw structured JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)

    project_key = args.project
    if not project_key and args.repo:
        project_key = args.repo.replace("/", "_")

    if not project_key:
        print("Error: --project or --repo is required.", file=sys.stderr)
        return 2

    if args.include_codecov and not args.repo:
        print("Error: --include-codecov requires --repo <owner/repo>.", file=sys.stderr)
        return 2

    sonar_token = os.environ.get("SONAR_TOKEN") or None
    codecov_token = os.environ.get("CODECOV_TOKEN") or None

    payload: Dict[str, Any] = {
        "sonarcloud": query_sonarcloud(
            project_key=project_key,
            pr=args.pr,
            include_hotspots=args.include_hotspots,
            sonar_token=sonar_token,
        )
    }

    if args.include_codecov and args.repo:
        payload["codecov"] = query_codecov(
            repo_slug=args.repo,
            pr=args.pr,
            codecov_token=codecov_token,
        )

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        summarize_sonar(payload["sonarcloud"])
        if "codecov" in payload:
            summarize_codecov(payload["codecov"])

    qg = payload["sonarcloud"]["quality_gate"]
    if not qg.get("ok"):
        return 1
    status = qg["data"].get("projectStatus", {}).get("status")
    return 0 if status in {"OK", "NONE", None} else 1


if __name__ == "__main__":
    raise SystemExit(main())
