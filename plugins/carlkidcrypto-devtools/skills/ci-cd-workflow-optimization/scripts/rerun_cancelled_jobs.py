#!/usr/bin/env python3
"""Detect and rerun cancelled/failed GitHub Actions workflow jobs via `gh`.

Specifically highlights infrastructure-level runner cancellations
(`conclusion == "cancelled"` with `runner_id == 0`) and triggers
`gh api repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs -X POST`.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

FAILED_CONCLUSIONS = frozenset({"cancelled", "failure", "timed_out", "startup_failure"})


def find_tool(name: str) -> str:
    """Locate an executable in PATH or standard Homebrew/local bin directories."""
    for candidate in (
        shutil.which(name),
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
    ):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        f"Executable `{name}` not found in PATH or standard locations"
    )


def find_gh() -> str:
    """Locate the GitHub CLI executable."""
    return find_tool("gh")


def run_gh(gh_bin: str, args: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` subcommand and return the completed process."""
    return subprocess.run([gh_bin, *args], text=True, capture_output=True)


def parse_paginated_jobs(stdout: str) -> List[Dict[str, Any]]:
    """Parse one or more JSON pages from `gh api .../jobs --paginate`."""
    text = stdout.strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    jobs: List[Dict[str, Any]] = []
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        obj, end = decoder.raw_decode(text, idx)
        if isinstance(obj, dict) and isinstance(obj.get("jobs"), list):
            jobs.extend(obj["jobs"])
        elif isinstance(obj, list):
            jobs.extend(obj)
        idx = end
    return jobs


def fetch_run_jobs(gh_bin: str, repo: str, run_id: int) -> List[Dict[str, Any]]:
    """Fetch all jobs for a workflow run."""
    res = run_gh(
        gh_bin,
        ["api", f"repos/{repo}/actions/runs/{run_id}/jobs", "--paginate"],
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"Failed to fetch jobs for run {run_id}: {res.stderr.strip()}"
        )
    return parse_paginated_jobs(res.stdout or "")


def classify_failed_jobs(
    jobs: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split failed/cancelled jobs into `(infra_cancelled, other_failed)`."""
    infra_cancelled: List[Dict[str, Any]] = []
    other_failed: List[Dict[str, Any]] = []
    for job in jobs:
        conclusion = job.get("conclusion")
        if conclusion not in FAILED_CONCLUSIONS:
            continue
        if conclusion == "cancelled" and job.get("runner_id") == 0:
            infra_cancelled.append(job)
        else:
            other_failed.append(job)
    return infra_cancelled, other_failed


def fetch_pr_candidate_runs(gh_bin: str, repo: str, pr: int) -> List[Dict[str, Any]]:
    """Find workflow runs on a PR's head commit with non-passing conclusions."""
    pr_res = run_gh(
        gh_bin,
        ["pr", "view", str(pr), "--repo", repo, "--json", "headRefOid,headRefName"],
    )
    if pr_res.returncode != 0:
        raise RuntimeError(
            f"Failed to inspect PR #{pr} in {repo}: {pr_res.stderr.strip()}"
        )
    pr_data = json.loads(pr_res.stdout or "{}")
    head_sha = pr_data.get("headRefOid")
    if not head_sha:
        raise RuntimeError(f"PR #{pr} in {repo} has no headRefOid.")

    runs_res = run_gh(
        gh_bin,
        ["api", f"repos/{repo}/actions/runs?head_sha={head_sha}&per_page=100"],
    )
    if runs_res.returncode != 0:
        raise RuntimeError(
            f"Failed to list workflow runs for {head_sha}: {runs_res.stderr.strip()}"
        )
    runs_data = json.loads(runs_res.stdout or "{}")
    workflow_runs = runs_data.get("workflow_runs", [])
    return [run for run in workflow_runs if run.get("conclusion") in FAILED_CONCLUSIONS]


def trigger_rerun_failed_jobs(gh_bin: str, repo: str, run_id: int) -> None:
    """Trigger `rerun-failed-jobs` for a workflow run."""
    res = run_gh(
        gh_bin,
        [
            "api",
            f"repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
            "-X",
            "POST",
        ],
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"Failed to rerun failed jobs for run {run_id}: {res.stderr.strip()}"
        )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Find and rerun cancelled/failed GitHub Actions jobs."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository in `owner/repo` format.",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--run-id",
        type=int,
        help="Specific GitHub Actions workflow run ID to inspect and rerun.",
    )
    target.add_argument(
        "--pr",
        type=int,
        help="Pull request number whose head-commit workflow runs should be inspected.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print matching runs/jobs and rerun commands without executing POST.",
    )
    parser.add_argument(
        "--infra-only",
        action="store_true",
        help="Only rerun runs that have runner_id == 0 infrastructure cancellations.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    try:
        gh_bin = find_gh()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.run_id is not None:
            runs_to_check: List[Dict[str, Any]] = [
                {"id": args.run_id, "name": f"run-{args.run_id}"}
            ]
        else:
            runs_to_check = fetch_pr_candidate_runs(gh_bin, args.repo, args.pr)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    actions_taken: List[Dict[str, Any]] = []
    for run in runs_to_check:
        run_id = int(run["id"])
        run_name = run.get("name") or f"run-{run_id}"
        try:
            jobs = fetch_run_jobs(gh_bin, args.repo, run_id)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        infra_cancelled, other_failed = classify_failed_jobs(jobs)
        if args.infra_only and not infra_cancelled:
            continue
        if not infra_cancelled and not other_failed:
            continue

        entry: Dict[str, Any] = {
            "run_id": run_id,
            "name": run_name,
            "infra_cancelled_count": len(infra_cancelled),
            "other_failed_count": len(other_failed),
            "infra_cancelled_jobs": [j.get("name") for j in infra_cancelled],
            "other_failed_jobs": [j.get("name") for j in other_failed],
            "dry_run": args.dry_run,
            "triggered": False,
        }

        if not args.json_output:
            print(
                f"Run {run_id} ({run_name}): "
                f"infra_cancelled(runner_id==0)={len(infra_cancelled)}, "
                f"other_failed={len(other_failed)}"
            )
            for job in infra_cancelled:
                print(f"  - [infra cancelled] {job.get('name')} (runner_id=0)")
            for job in other_failed:
                print(
                    f"  - [{job.get('conclusion')}] {job.get('name')} "
                    f"(runner_id={job.get('runner_id')})"
                )

        if args.dry_run:
            if not args.json_output:
                print(
                    f"  [DRY-RUN] gh api repos/{args.repo}/actions/runs/{run_id}/rerun-failed-jobs -X POST"
                )
        else:
            try:
                trigger_rerun_failed_jobs(gh_bin, args.repo, run_id)
            except RuntimeError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            entry["triggered"] = True
            if not args.json_output:
                print(f"  Triggered rerun-failed-jobs for run {run_id}.")

        actions_taken.append(entry)

    if args.json_output:
        print(json.dumps(actions_taken, indent=2))
    elif not actions_taken:
        print("No workflow runs with matching cancelled or failed jobs found.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
