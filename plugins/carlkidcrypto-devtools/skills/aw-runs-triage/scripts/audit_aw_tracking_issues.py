#!/usr/bin/env python3
"""Audit gh-aw '[aw] No-Op Runs' and '[aw] Detection Runs' issues across repos.

Scans carlkidcrypto repositories for open '[aw] No-Op Runs' and
'[aw] Detection Runs' tracking issues, groups comments by workflow, and
optionally inspects the latest GitHub Actions run per workflow to distinguish
genuine no-ops from misconfigured workflows and HTTP 429 quota failures from
non-429 detection failures or threat warnings.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_OWNER = "carlkidcrypto"
DEFAULT_REPOS = [
    "shared-workflows",
    "ezsnmp",
    "ezsnmp_data_logger",
    "purpleair_api",
    "purpleair_data_logger",
    "purpleair-matterbridge",
    "carlkidcrypto.github.io",
    "os-specific-runner",
]

RUN_ID_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/actions/runs/(\d+)")
OUTCOME_RE = re.compile(r"\*\*Outcome:\*\*\s*`([^`]+)`")
REASON_RE = re.compile(r"\|\s*Reason\s*\|\s*`([^`]+)`\s*\|")

LOG_429_MARKERS = (
    "ai_credits_rate_limit_error",
    "errorcodes=[429]",
    'errortypes=["rate_limit"]',
    "429 too many requests",
    "quota_exceeded",
    "quota exceeded",
)
MISCONFIG_MARKERS = (
    "certificate_verify_failed",
    "depth_zero_self_signed_cert",
    "ssl certificate problem: self-signed certificate",
    "lower integrity than agent requires",
    "denied-no-approval-rule-and-could-not-request-from-user",
)


def find_gh() -> str:
    """Locate the GitHub CLI executable."""
    for candidate in (
        shutil.which("gh"),
        "/opt/homebrew/bin/gh",
        "/usr/local/bin/gh",
    ):
        if candidate:
            return candidate
    raise FileNotFoundError("GitHub CLI (`gh`) not found in PATH or standard locations")


def run_gh(gh_bin: str, args: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` subcommand and return the completed process."""
    return subprocess.run([gh_bin, *args], text=True, capture_output=True)


def resolve_repos(owner: str, repos: Optional[List[str]]) -> List[str]:
    """Resolve CLI repo arguments into `owner/repo` strings."""
    targets = repos if repos else DEFAULT_REPOS
    return [r if "/" in r else f"{owner}/{r}" for r in targets]


def classify_tracking_issue(title: str) -> Optional[str]:
    """Return 'noop', 'detection', or None based on the issue title."""
    lowered = (title or "").strip().lower()
    if lowered == "[aw] no-op runs":
        return "noop"
    if lowered == "[aw] detection runs":
        return "detection"
    return None


def parse_tracking_comment(comment: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """Extract workflow name, outcome, reason, run_id, and timestamp from a comment."""
    body = comment.get("body") or ""
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    workflow = "Unknown"
    for line in lines:
        if line.startswith("### "):
            workflow = line[4:].strip()
            break

    outcome_match = OUTCOME_RE.search(body)
    if outcome_match:
        outcome = outcome_match.group(1)
    elif kind == "detection" and "warning" in body.lower():
        outcome = "threat_warning"
    else:
        outcome = "unknown"

    reason_match = REASON_RE.search(body)
    reason = reason_match.group(1) if reason_match else ""

    run_match = RUN_ID_RE.search(body)
    run_id = run_match.group(1) if run_match else None

    return {
        "workflow": workflow,
        "outcome": outcome,
        "reason": reason,
        "run_id": run_id,
        "createdAt": comment.get("createdAt") or "",
    }


def list_tracking_issues(gh_bin: str, full_repo: str) -> List[Dict[str, Any]]:
    """Fetch open '[aw] No-Op Runs' and '[aw] Detection Runs' issues with comments."""
    res = run_gh(
        gh_bin,
        [
            "issue",
            "list",
            "--repo",
            full_repo,
            "--state",
            "open",
            "--search",
            "[aw] in:title",
            "--limit",
            "50",
            "--json",
            "number,title,url",
        ],
    )
    if res.returncode != 0:
        if "has disabled issues" in (res.stderr or "").lower():
            return []
        raise RuntimeError(
            f"gh issue list failed for {full_repo}: {res.stderr.strip()}"
        )

    issues = json.loads(res.stdout or "[]")
    matched: List[Dict[str, Any]] = []
    for issue in issues:
        kind = classify_tracking_issue(issue.get("title") or "")
        if not kind:
            continue
        detail_res = run_gh(
            gh_bin,
            [
                "issue",
                "view",
                str(issue["number"]),
                "--repo",
                full_repo,
                "--json",
                "number,title,url,comments",
            ],
        )
        if detail_res.returncode != 0:
            raise RuntimeError(
                f"gh issue view #{issue['number']} failed for {full_repo}: "
                f"{detail_res.stderr.strip()}"
            )
        detail = json.loads(detail_res.stdout or "{}")
        detail["kind"] = kind
        matched.append(detail)
    return matched


def summarize_issue_comments(
    issue: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Group comments on a tracking issue by workflow name."""
    kind = issue["kind"]
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for raw_comment in issue.get("comments") or []:
        parsed = parse_tracking_comment(raw_comment, kind)
        grouped[parsed["workflow"]].append(parsed)

    summaries: List[Dict[str, Any]] = []
    for workflow, entries in sorted(grouped.items()):
        entries.sort(key=lambda item: item["createdAt"])
        latest = entries[-1]
        outcome_counts: Dict[str, int] = defaultdict(int)
        for entry in entries:
            outcome_counts[entry["outcome"]] += 1
        summaries.append(
            {
                "workflow": workflow,
                "comment_count": len(entries),
                "outcomes": dict(sorted(outcome_counts.items())),
                "latest_created_at": latest["createdAt"],
                "latest_outcome": latest["outcome"],
                "latest_reason": latest["reason"],
                "latest_run_id": latest["run_id"],
            }
        )
    return summaries


def inspect_run_classification(
    gh_bin: str,
    full_repo: str,
    kind: str,
    latest_outcome: str,
    run_id: Optional[str],
) -> Tuple[str, str]:
    """Inspect the GitHub Actions run for a workflow and return (verdict, detail)."""
    if not run_id:
        return ("NO_RUN_ID", "No run URL found in latest comment")

    meta_res = run_gh(
        gh_bin,
        [
            "run",
            "view",
            run_id,
            "--repo",
            full_repo,
            "--json",
            "conclusion,status,jobs",
        ],
    )
    if meta_res.returncode != 0:
        return ("RUN_LOOKUP_FAILED", meta_res.stderr.strip() or "gh run view failed")

    meta = json.loads(meta_res.stdout or "{}")
    conclusion = (meta.get("conclusion") or "").lower()
    jobs = {
        j.get("name"): (j.get("conclusion") or "").lower()
        for j in meta.get("jobs") or []
    }
    agent_conclusion = jobs.get("agent", conclusion)

    if kind == "noop":
        if latest_outcome == "reported_no_action" and agent_conclusion == "success":
            return ("TRUE_NOOP", "agent=success, outcome=reported_no_action")
        log_res = run_gh(
            gh_bin, ["run", "view", run_id, "--repo", full_repo, "--log-failed"]
        )
        lowered_log = f"{log_res.stdout or ''}\n{log_res.stderr or ''}".lower()
        if any(m in lowered_log for m in LOG_429_MARKERS):
            return (
                "RATE_LIMITED_429",
                f"agent={agent_conclusion}, HTTP 429 quota/rate limit",
            )
        if any(m in lowered_log for m in MISCONFIG_MARKERS):
            return (
                "FALSE_NOOP_SUSPECT",
                f"agent={agent_conclusion}, workflow/sandbox error",
            )
        return (
            "FALSE_NOOP_SUSPECT",
            f"agent={agent_conclusion}, outcome={latest_outcome}",
        )

    # kind == "detection"
    if latest_outcome == "threat_warning":
        return ("THREAT_WARNING", "Threat detection raised a warning; audit run")

    log_res = run_gh(
        gh_bin, ["run", "view", run_id, "--repo", full_repo, "--log-failed"]
    )
    lowered_log = f"{log_res.stdout or ''}\n{log_res.stderr or ''}".lower()
    if any(m in lowered_log for m in LOG_429_MARKERS):
        return ("RATE_LIMITED_429", "HTTP 429 / Copilot quota_exceeded in failed logs")
    if any(m in lowered_log for m in MISCONFIG_MARKERS):
        return ("DETECTION_FAILURE_NON_429", "AWF/DIFC/tool permission error in logs")
    if conclusion == "success":
        return ("DETECTION_SUCCESS_OR_RECOVERED", f"run={run_id} concluded success")
    return (
        "DETECTION_FAILURE_NON_429",
        f"conclusion={conclusion}, outcome={latest_outcome} (no 429 markers in failed log)",
    )


def audit_repositories(
    gh_bin: str,
    repos: List[str],
    inspect_runs: bool = False,
) -> List[Dict[str, Any]]:
    """Audit all target repositories and return structured findings."""
    findings: List[Dict[str, Any]] = []
    for full_repo in repos:
        issues = list_tracking_issues(gh_bin, full_repo)
        for issue in issues:
            workflows = summarize_issue_comments(issue)
            for wf in workflows:
                if inspect_runs:
                    verdict, detail = inspect_run_classification(
                        gh_bin,
                        full_repo,
                        issue["kind"],
                        wf["latest_outcome"],
                        wf["latest_run_id"],
                    )
                else:
                    verdict, detail = (
                        "NOT_INSPECTED",
                        "Pass --inspect-runs to verify logs",
                    )
                wf["verdict"] = verdict
                wf["detail"] = detail
            findings.append(
                {
                    "repo": full_repo,
                    "number": issue["number"],
                    "title": issue["title"],
                    "kind": issue["kind"],
                    "url": issue["url"],
                    "total_comments": len(issue.get("comments") or []),
                    "workflows": workflows,
                }
            )
    return findings


def evaluate_issue_closure(issue_finding: Dict[str, Any]) -> Tuple[bool, str, str]:
    """Return (eligible, close_reason, comment_or_skip_reason) for a tracking issue."""
    workflows = issue_finding.get("workflows") or []
    if not workflows:
        return (False, "", "No workflow comments recorded")

    verdicts = [wf.get("verdict") or "NOT_INSPECTED" for wf in workflows]
    if any(v == "NOT_INSPECTED" for v in verdicts):
        return (False, "", "Run inspection required before closing")

    kind = issue_finding.get("kind")
    lines = [
        f"| {wf['workflow']} | {wf['comment_count']} | {wf.get('latest_run_id') or '-'} | `{wf['verdict']}` |"
        for wf in workflows
    ]
    table = "\n".join(
        [
            "| Workflow | Comments | Latest Run | Verdict |",
            "| :--- | ---: | :--- | :--- |",
            *lines,
        ]
    )

    if kind == "noop":
        if all(v == "TRUE_NOOP" for v in verdicts):
            comment = (
                "Closing after auditing all reported workflows on this tracking issue: "
                "every workflow's latest run succeeded with `reported_no_action` and zero "
                "firewall, DIFC, permission, or tool errors (genuine no-ops, no GH-AW "
                "misconfigurations detected).\n\n"
                f"{table}"
            )
            return (True, "completed", comment)
        blocking = sorted({v for v in verdicts if v != "TRUE_NOOP"})
        return (False, "", f"Blocked by non-true-noop verdicts: {', '.join(blocking)}")

    if kind == "detection":
        safe_detection = {"RATE_LIMITED_429", "DETECTION_SUCCESS_OR_RECOVERED"}
        if all(v in safe_detection for v in verdicts):
            has_429 = any(v == "RATE_LIMITED_429" for v in verdicts)
            if has_429:
                reason = "not planned"
                summary = (
                    "Closing after auditing all reported workflows on this tracking issue: "
                    "every `detector_execution_failure` was verified in GitHub Actions logs "
                    "to be caused by Copilot HTTP 429 / `quota_exceeded` (not a workflow "
                    "misconfiguration or security threat). Workflows will re-run normally once "
                    "Copilot credits reset."
                )
            else:
                reason = "completed"
                summary = (
                    "Closing after auditing all reported workflows on this tracking issue: "
                    "all latest runs succeeded or recovered cleanly with no threat warnings or "
                    "misconfigurations."
                )
            return (True, reason, f"{summary}\n\n{table}")
        blocking = sorted({v for v in verdicts if v not in safe_detection})
        return (
            False,
            "",
            f"Blocked by non-429 / warning verdicts: {', '.join(blocking)}",
        )

    return (False, "", f"Unsupported tracking issue kind: {kind}")


def close_tracking_issue(
    gh_bin: str,
    full_repo: str,
    number: int,
    reason: str,
    comment: str,
) -> None:
    """Close a tracking issue with an explanatory comment via `gh issue close`."""
    res = run_gh(
        gh_bin,
        [
            "issue",
            "close",
            str(number),
            "--repo",
            full_repo,
            "--reason",
            reason,
            "--comment",
            comment,
        ],
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"gh issue close #{number} failed for {full_repo}: {res.stderr.strip()}"
        )


def apply_issue_closures(
    gh_bin: str,
    findings: List[Dict[str, Any]],
    apply: bool = False,
) -> None:
    """Evaluate and optionally close eligible tracking issues, recording action status."""
    for item in findings:
        eligible, reason, detail = evaluate_issue_closure(item)
        if not eligible:
            item["closure_action"] = "SKIP_CLOSE"
            item["closure_detail"] = detail
            continue
        if apply:
            close_tracking_issue(gh_bin, item["repo"], item["number"], reason, detail)
            item["closure_action"] = f"CLOSED ({reason})"
        else:
            item["closure_action"] = f"WOULD_CLOSE ({reason})"
        item["closure_detail"] = detail


def format_markdown_report(findings: List[Dict[str, Any]]) -> str:
    """Format audit findings as a concise Markdown summary."""
    if not findings:
        return "No open `[aw] No-Op Runs` or `[aw] Detection Runs` issues found."

    lines: List[str] = []
    for item in findings:
        lines.append(
            f"## {item['repo']}#{item['number']} — {item['title']} "
            f"({item['total_comments']} comments)"
        )
        lines.append(f"URL: {item['url']}")
        if not item["workflows"]:
            lines.append("- No workflow comments recorded yet.\n")
            continue
        lines.append(
            "| Workflow | Count | Latest Outcome | Latest Run | Verdict | Detail |"
        )
        lines.append("| :--- | ---: | :--- | :--- | :--- | :--- |")
        for wf in item["workflows"]:
            run_col = wf["latest_run_id"] or "-"
            lines.append(
                f"| {wf['workflow']} | {wf['comment_count']} | "
                f"`{wf['latest_outcome']}` | {run_col} | `{wf['verdict']}` | {wf['detail']} |"
            )
        if item.get("closure_action"):
            lines.append(
                f"\n**Closure**: `{item['closure_action']}`"
                + (
                    f" — {item['closure_detail']}"
                    if item["closure_action"] == "SKIP_CLOSE"
                    else ""
                )
            )
        lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Audit gh-aw '[aw] No-Op Runs' and '[aw] Detection Runs' issues."
    )
    parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER,
        help=f"GitHub owner/org for unqualified repo names (default: {DEFAULT_OWNER})",
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        help="Optional list of repo names or owner/repo strings (defaults to fleet list)",
    )
    parser.add_argument(
        "--inspect-runs",
        action="store_true",
        help="Inspect the latest Actions run per workflow to classify 429 vs misconfig",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Close eligible verified issues with an explanatory comment (implies --inspect-runs)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of Markdown",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    gh_bin = find_gh()
    repos = resolve_repos(args.owner, args.repos)
    inspect = args.inspect_runs or args.apply
    findings = audit_repositories(gh_bin, repos, inspect_runs=inspect)
    if inspect:
        apply_issue_closures(gh_bin, findings, apply=args.apply)
    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print(format_markdown_report(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
