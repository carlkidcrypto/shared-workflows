#!/usr/bin/env python3
"""Query SonarCloud API for Quality Gate, issues, hotspots, and measures.

Supports targeting a project via ``--project KEY`` or ``--repo owner/repo``,
optionally scoped to a pull request (``--pr N``) or branch (``--branch NAME``).
Uses ``SONAR_TOKEN`` from the environment when set (HTTP Basic auth).
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

SONARCLOUD_BASE_URL = "https://sonarcloud.io"
DEFAULT_METRIC_KEYS = (
    "security_rating,"
    "reliability_rating,"
    "sqale_rating,"
    "duplicated_lines_density,"
    "security_hotspots_reviewed,"
    "coverage,"
    "bugs,"
    "vulnerabilities,"
    "code_smells"
)
RATING_MAP = {
    "1.0": "A",
    "1": "A",
    "2.0": "B",
    "2": "B",
    "3.0": "C",
    "3": "C",
    "4.0": "D",
    "4": "D",
    "5.0": "E",
    "5": "E",
}


def resolve_project_key(project: Optional[str], repo: Optional[str]) -> str:
    """Resolve the SonarCloud projectKey from --project or --repo."""
    if project:
        return project.strip()
    if repo:
        cleaned = repo.strip().strip("/")
        if "/" not in cleaned:
            raise ValueError(f"--repo must be in 'owner/repo' format, got: {repo!r}")
        owner, name = cleaned.split("/", 1)
        if not owner or not name:
            raise ValueError(f"--repo must be in 'owner/repo' format, got: {repo!r}")
        return f"{owner}_{name}"
    raise ValueError("One of --project or --repo is required.")


def build_auth_headers(token: Optional[str]) -> Dict[str, str]:
    """Return HTTP headers including Basic auth when SONAR_TOKEN is provided."""
    headers = {"Accept": "application/json"}
    if token:
        encoded = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    return headers


def build_api_url(
    endpoint: str,
    params: Dict[str, Any],
    base_url: str = SONARCLOUD_BASE_URL,
) -> str:
    """Build a SonarCloud API URL with encoded query parameters."""
    filtered = {k: v for k, v in params.items() if v is not None and v != ""}
    query = urllib.parse.urlencode(filtered)
    return (
        f"{base_url.rstrip('/')}{endpoint}?{query}"
        if query
        else f"{base_url.rstrip('/')}{endpoint}"
    )


def fetch_json(
    url: str,
    token: Optional[str] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Perform a GET request to SonarCloud and parse the JSON response."""
    req = urllib.request.Request(url, headers=build_auth_headers(token), method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _scope_params(pr: Optional[int], branch: Optional[str]) -> Dict[str, Any]:
    """Build optional pullRequest or branch query parameters."""
    params: Dict[str, Any] = {}
    if pr is not None:
        params["pullRequest"] = str(pr)
    elif branch:
        params["branch"] = branch
    return params


def collect_triage_data(
    project_key: str,
    pr: Optional[int] = None,
    branch: Optional[str] = None,
    token: Optional[str] = None,
    max_items: int = 10,
    base_url: str = SONARCLOUD_BASE_URL,
) -> Dict[str, Any]:
    """Query Quality Gate, measures, open issues, and hotspots for a project."""
    scope = _scope_params(pr, branch)

    qg_url = build_api_url(
        "/api/qualitygates/project_status",
        {"projectKey": project_key, **scope},
        base_url=base_url,
    )
    measures_url = build_api_url(
        "/api/measures/component",
        {"component": project_key, "metricKeys": DEFAULT_METRIC_KEYS, **scope},
        base_url=base_url,
    )
    issues_url = build_api_url(
        "/api/issues/search",
        {
            "componentKeys": project_key,
            "resolved": "false",
            "ps": str(max(max_items, 100)),
            **scope,
        },
        base_url=base_url,
    )
    hotspots_url = build_api_url(
        "/api/hotspots/search",
        {
            "projectKey": project_key,
            "status": "TO_REVIEW",
            "ps": str(max(max_items, 100)),
            **scope,
        },
        base_url=base_url,
    )

    qg_data = fetch_json(qg_url, token=token)
    measures_data = fetch_json(measures_url, token=token)
    issues_data = fetch_json(issues_url, token=token)
    hotspots_data = fetch_json(hotspots_url, token=token)

    project_status = qg_data.get("projectStatus", {})
    conditions = project_status.get("conditions", [])
    failing_conditions = [c for c in conditions if c.get("status") != "OK"]

    raw_measures = measures_data.get("component", {}).get("measures", [])
    measures: Dict[str, str] = {
        m["metric"]: str(m.get("value", "")) for m in raw_measures if "metric" in m
    }

    issues: List[Dict[str, Any]] = issues_data.get("issues", [])
    issue_counts: Dict[str, int] = {"BUG": 0, "VULNERABILITY": 0, "CODE_SMELL": 0}
    for issue in issues:
        itype = issue.get("type", "")
        issue_counts[itype] = issue_counts.get(itype, 0) + 1

    hotspots: List[Dict[str, Any]] = hotspots_data.get("hotspots", [])
    hotspots_total = hotspots_data.get("paging", {}).get("total", len(hotspots))
    issues_total = issues_data.get("total", len(issues))

    return {
        "projectKey": project_key,
        "scope": {"pullRequest": pr, "branch": branch},
        "qualityGate": {
            "status": project_status.get("status", "UNKNOWN"),
            "conditions": conditions,
            "failingConditions": failing_conditions,
        },
        "measures": measures,
        "issues": {
            "total": issues_total,
            "byType": issue_counts,
            "items": [
                {
                    "key": item.get("key"),
                    "type": item.get("type"),
                    "severity": item.get("severity"),
                    "rule": item.get("rule"),
                    "component": item.get("component"),
                    "line": item.get("line"),
                    "message": item.get("message"),
                }
                for item in issues[:max_items]
            ],
        },
        "hotspots": {
            "total": hotspots_total,
            "items": [
                {
                    "key": item.get("key"),
                    "vulnerabilityProbability": item.get("vulnerabilityProbability"),
                    "securityCategory": item.get("securityCategory"),
                    "component": item.get("component"),
                    "line": item.get("line"),
                    "message": item.get("message"),
                }
                for item in hotspots[:max_items]
            ],
        },
    }


def _format_rating(value: Optional[str]) -> str:
    """Map numeric SonarCloud rating values (e.g. '1.0') to letter grades."""
    if not value:
        return "N/A"
    return RATING_MAP.get(str(value), str(value))


def format_text_report(data: Dict[str, Any]) -> str:
    """Format collected SonarCloud triage data as a concise human-readable report."""
    scope = data.get("scope", {})
    if scope.get("pullRequest") is not None:
        scope_label = f"PR #{scope['pullRequest']}"
    elif scope.get("branch"):
        scope_label = f"branch {scope['branch']}"
    else:
        scope_label = "default branch"

    qg = data.get("qualityGate", {})
    measures = data.get("measures", {})
    issues = data.get("issues", {})
    hotspots = data.get("hotspots", {})

    lines = [
        f"SonarCloud Triage: {data.get('projectKey')} ({scope_label})",
        f"Quality Gate: {qg.get('status', 'UNKNOWN')}",
    ]

    failing = qg.get("failingConditions", [])
    if failing:
        lines.append("Failing Conditions:")
        for cond in failing:
            lines.append(
                f"  - {cond.get('metricKey')}: {cond.get('actualValue')} "
                f"(status={cond.get('status')}, errorThreshold={cond.get('errorThreshold')})"
            )

    lines.extend(
        [
            "Measures:",
            (
                f"  Bugs: {measures.get('bugs', 'N/A')} | "
                f"Vulnerabilities: {measures.get('vulnerabilities', 'N/A')} | "
                f"Code Smells: {measures.get('code_smells', 'N/A')}"
            ),
            (
                f"  Ratings (Sec/Rel/Maint): "
                f"{_format_rating(measures.get('security_rating'))}/"
                f"{_format_rating(measures.get('reliability_rating'))}/"
                f"{_format_rating(measures.get('sqale_rating'))}"
            ),
            (
                f"  Coverage: {measures.get('coverage', 'N/A')}% | "
                f"Duplication: {measures.get('duplicated_lines_density', 'N/A')}% | "
                f"Hotspots Reviewed: {measures.get('security_hotspots_reviewed', 'N/A')}%"
            ),
            (
                f"Open Issues: {issues.get('total', 0)} "
                f"(BUG={issues.get('byType', {}).get('BUG', 0)}, "
                f"VULNERABILITY={issues.get('byType', {}).get('VULNERABILITY', 0)}, "
                f"CODE_SMELL={issues.get('byType', {}).get('CODE_SMELL', 0)})"
            ),
        ]
    )

    for item in issues.get("items", []):
        loc = f":{item['line']}" if item.get("line") else ""
        lines.append(
            f"  - [{item.get('severity', '?')}/{item.get('type', '?')}] "
            f"{item.get('component', '')}{loc} ({item.get('rule', '')}): "
            f"{item.get('message', '')}"
        )

    lines.append(f"Security Hotspots (TO_REVIEW): {hotspots.get('total', 0)}")
    for item in hotspots.get("items", []):
        loc = f":{item['line']}" if item.get("line") else ""
        lines.append(
            f"  - [{item.get('vulnerabilityProbability', '?')}] "
            f"{item.get('component', '')}{loc}: {item.get('message', '')}"
        )

    return "\n".join(lines)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Query SonarCloud API for Quality Gate, issues, hotspots, and measures."
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--project",
        help="SonarCloud projectKey (e.g. carlkidcrypto_ezsnmp).",
    )
    target_group.add_argument(
        "--repo",
        help="GitHub repository in 'owner/repo' format (converted to owner_repo).",
    )

    scope_group = parser.add_mutually_exclusive_group()
    scope_group.add_argument(
        "--pr",
        type=int,
        help="Pull request number to scope SonarCloud queries.",
    )
    scope_group.add_argument(
        "--branch",
        help="Branch name to scope SonarCloud queries.",
    )

    parser.add_argument(
        "--max-items",
        type=int,
        default=10,
        help="Maximum sample issues and hotspots to include (default: 10).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    try:
        project_key = resolve_project_key(args.project, args.repo)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    token = os.environ.get("SONAR_TOKEN") or None

    try:
        data = collect_triage_data(
            project_key=project_key,
            pr=args.pr,
            branch=args.branch,
            token=token,
            max_items=args.max_items,
        )
    except urllib.error.HTTPError as exc:
        print(
            f"SonarCloud API HTTP error {exc.code} for {exc.url}: {exc.reason}",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as exc:
        print(f"SonarCloud API connection error: {exc.reason}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(format_text_report(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
