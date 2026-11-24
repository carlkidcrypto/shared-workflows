#!/usr/bin/env python3
"""Inspect GitHub PR CI statusCheckRollup, fetch failed job logs, or rerun failed jobs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

_PASSING_CONCLUSIONS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})
_RUN_ID_RE = re.compile(r"/actions/runs/(\d+)")
_JOB_ID_RE = re.compile(r"/job/(\d+)")


def _run_gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=True,
        check=check,
    )


def summarize_pr_checks(pr_data: dict[str, Any]) -> dict[str, Any]:
    """Partition statusCheckRollup into passing and non-passing entries."""
    passing = 0
    non_passing: list[dict[str, Any]] = []
    run_ids: set[str] = set()

    for check in pr_data.get("statusCheckRollup", []):
        name = check.get("name") or check.get("context") or "<unnamed>"
        status = check.get("status") or check.get("state") or ""
        conclusion = check.get("conclusion") or ""
        url = check.get("detailsUrl") or check.get("targetUrl") or ""

        if conclusion in _PASSING_CONCLUSIONS and status == "COMPLETED":
            passing += 1
            continue

        run_match = _RUN_ID_RE.search(url)
        job_match = _JOB_ID_RE.search(url)
        run_id = run_match.group(1) if run_match else None
        job_id = job_match.group(1) if job_match else None
        if run_id and conclusion in ("FAILURE", "CANCELLED", "TIMED_OUT"):
            run_ids.add(run_id)

        non_passing.append(
            {
                "name": name,
                "status": status,
                "conclusion": conclusion,
                "run_id": run_id,
                "job_id": job_id,
                "url": url,
            }
        )

    return {
        "state": pr_data.get("state"),
        "base": pr_data.get("baseRefName"),
        "head": pr_data.get("headRefName"),
        "sha": (pr_data.get("headRefOid") or "")[:7],
        "mergeable": pr_data.get("mergeable"),
        "passing": passing,
        "non_passing": non_passing,
        "failed_run_ids": sorted(run_ids),
    }


def fetch_pr_status(repo: str, pr_number: int) -> dict[str, Any]:
    proc = _run_gh(
        [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repo,
            "--json",
            "state,baseRefName,headRefName,headRefOid,mergeable,statusCheckRollup",
        ]
    )
    return summarize_pr_checks(json.loads(proc.stdout))


def rerun_failed_runs(repo: str, run_ids: list[str]) -> list[str]:
    triggered: list[str] = []
    for run_id in run_ids:
        _run_gh(
            [
                "api",
                "-X",
                "POST",
                f"repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
            ]
        )
        triggered.append(run_id)
    return triggered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect PR CI checks, summarize non-passing jobs, and optionally rerun failed jobs."
    )
    parser.add_argument("--repo", required=True, help="GitHub repository (owner/repo)")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit machine-readable JSON output",
    )
    parser.add_argument(
        "--rerun-failed",
        action="store_true",
        help="Trigger rerun-failed-jobs for every workflow run with failed/cancelled jobs",
    )
    args = parser.parse_args(argv)

    summary = fetch_pr_status(args.repo, args.pr)
    if args.rerun_failed and summary["failed_run_ids"]:
        summary["rerun_triggered"] = rerun_failed_runs(
            args.repo, summary["failed_run_ids"]
        )

    if args.as_json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"PR #{args.pr} ({args.repo}): {summary['state']} "
            f"{summary['head']} -> {summary['base']} sha={summary['sha']} "
            f"mergeable={summary['mergeable']}"
        )
        print(
            f"Passing/Skipped/Neutral: {summary['passing']}, "
            f"Non-Success/Pending: {len(summary['non_passing'])}"
        )
        for item in summary["non_passing"]:
            print(
                f"  [{item['conclusion'] or item['status']}] {item['name']} "
                f"(run={item['run_id']}, job={item['job_id']}) {item['url']}"
            )
        if summary.get("rerun_triggered"):
            print(
                f"Triggered rerun-failed-jobs for runs: {', '.join(summary['rerun_triggered'])}"
            )

    return 0 if not summary["non_passing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
