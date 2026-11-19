#!/usr/bin/env python3
"""Triage failing GitHub Actions workflow runs, detect runner infra drops, and optionally rerun failed jobs."""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gh_common import (
    DEFAULT_OWNER,
    find_gh,
    infer_current_repo,
    resolve_repo,
    run_gh,
    run_gh_json,
    split_repo,
)

FAILING_CONCLUSIONS = {
    "failure",
    "cancelled",
    "timed_out",
    "startup_failure",
    "action_required",
}
RUN_ID_URL_RE = re.compile(r"/actions/runs/(\d+)")


def is_infra_drop(job: Dict[str, Any]) -> bool:
    """Return True if a job looks like a GitHub Actions runner infrastructure drop."""
    if job.get("conclusion") != "cancelled":
        return False
    steps = job.get("steps") or []
    runner_id = job.get("runner_id")
    return len(steps) == 0 or runner_id in (None, 0)


def fetch_run_jobs(
    gh_bin: str, owner: str, repo: str, run_id: int
) -> List[Dict[str, Any]]:
    """Fetch jobs for a workflow run via GitHub REST API."""
    data = run_gh_json(
        gh_bin,
        ["api", f"repos/{owner}/{repo}/actions/runs/{run_id}/jobs?per_page=100"],
    )
    if not isinstance(data, dict):
        return []
    return data.get("jobs", [])


def fetch_failed_logs(
    gh_bin: str,
    full_repo: str,
    run_id: int,
    max_log_lines: int,
) -> Dict[str, Any]:
    """Fetch failed step logs via `gh run view --log-failed` and tail-truncate."""
    if max_log_lines <= 0:
        return {"lines": [], "truncated": False, "error": None}
    res = run_gh(
        gh_bin, ["run", "view", str(run_id), "--repo", full_repo, "--log-failed"]
    )
    if res.returncode != 0:
        return {
            "lines": [],
            "truncated": False,
            "error": res.stderr.strip() or f"gh run view exited {res.returncode}",
        }
    all_lines = res.stdout.splitlines()
    truncated = len(all_lines) > max_log_lines
    tail_lines = all_lines[-max_log_lines:] if truncated else all_lines
    return {"lines": tail_lines, "truncated": truncated, "error": None}


def discover_runs_for_pr(
    gh_bin: str,
    owner: str,
    repo: str,
    pr_number: int,
) -> List[Dict[str, Any]]:
    """Discover failing workflow runs associated with a pull request."""
    full_repo = f"{owner}/{repo}"
    pr_data = run_gh_json(
        gh_bin,
        [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            full_repo,
            "--json",
            "headRefName,headRefOid,statusCheckRollup",
        ],
    )
    if not isinstance(pr_data, dict):
        return []

    run_ids: Set[int] = set()
    for check in pr_data.get("statusCheckRollup") or []:
        url = check.get("detailsUrl") or check.get("targetUrl") or ""
        match = RUN_ID_URL_RE.search(url)
        if match:
            run_ids.add(int(match.group(1)))

    runs_by_id: Dict[int, Dict[str, Any]] = {}
    head_sha = pr_data.get("headRefOid")
    if head_sha:
        sha_runs = run_gh_json(
            gh_bin,
            [
                "api",
                f"repos/{owner}/{repo}/actions/runs?head_sha={head_sha}&per_page=50",
            ],
        )
        for run in (sha_runs or {}).get("workflow_runs", []):
            runs_by_id[run["id"]] = run

    for rid in sorted(run_ids):
        if rid not in runs_by_id:
            run = run_gh_json(
                gh_bin, ["api", f"repos/{owner}/{repo}/actions/runs/{rid}"]
            )
            if isinstance(run, dict) and "id" in run:
                runs_by_id[rid] = run

    return [
        run
        for run in sorted(runs_by_id.values(), key=lambda r: r["id"], reverse=True)
        if run.get("conclusion") in FAILING_CONCLUSIONS
    ]


def discover_recent_failing_runs(
    gh_bin: str,
    owner: str,
    repo: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch recent failing or cancelled workflow runs for a repository."""
    data = run_gh_json(
        gh_bin,
        ["api", f"repos/{owner}/{repo}/actions/runs?per_page={limit}"],
    )
    runs = (data or {}).get("workflow_runs", [])
    return [run for run in runs if run.get("conclusion") in FAILING_CONCLUSIONS]


def triage_run(
    gh_bin: str,
    owner: str,
    repo: str,
    run: Dict[str, Any],
    rerun_infra_drops: bool,
    dry_run: bool,
    max_log_lines: int,
) -> Dict[str, Any]:
    """Inspect a single failing workflow run for infra drops and failed logs."""
    full_repo = f"{owner}/{repo}"
    run_id = run["id"]
    jobs = fetch_run_jobs(gh_bin, owner, repo, run_id)

    infra_drops: List[Dict[str, Any]] = []
    failed_jobs: List[Dict[str, Any]] = []
    for job in jobs:
        conclusion = job.get("conclusion")
        if conclusion not in FAILING_CONCLUSIONS:
            continue
        job_summary = {
            "id": job.get("id"),
            "name": job.get("name"),
            "conclusion": conclusion,
            "runner_id": job.get("runner_id"),
            "runner_name": job.get("runner_name"),
            "step_count": len(job.get("steps") or []),
            "html_url": job.get("html_url"),
        }
        if is_infra_drop(job):
            infra_drops.append(job_summary)
        else:
            failed_jobs.append(job_summary)

    rerun_status = "not_requested"
    rerun_error: Optional[str] = None
    if rerun_infra_drops and infra_drops:
        if dry_run:
            rerun_status = "dry_run"
        else:
            res = run_gh(
                gh_bin,
                [
                    "api",
                    f"repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
                    "-X",
                    "POST",
                ],
            )
            if res.returncode == 0:
                rerun_status = "rerun_triggered"
            else:
                rerun_status = "rerun_failed"
                rerun_error = res.stderr.strip() or f"exit {res.returncode}"

    logs = {"lines": [], "truncated": False, "error": None}
    if failed_jobs or (not infra_drops and max_log_lines > 0):
        logs = fetch_failed_logs(gh_bin, full_repo, run_id, max_log_lines)

    return {
        "run_id": run_id,
        "name": run.get("name"),
        "conclusion": run.get("conclusion"),
        "head_branch": run.get("head_branch"),
        "head_sha": run.get("head_sha"),
        "html_url": run.get("html_url"),
        "infra_drops": infra_drops,
        "failed_jobs": failed_jobs,
        "rerun_status": rerun_status,
        "rerun_error": rerun_error,
        "failed_logs": logs,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Triage failing GitHub Actions runs, detect infra drops, and print failed logs."
    )
    parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER,
        help=f"GitHub owner/org (default: {DEFAULT_OWNER}).",
    )
    parser.add_argument(
        "--repo",
        "-r",
        help="Repository name or owner/repo (defaults to current git repo).",
    )
    parser.add_argument(
        "--pr",
        type=int,
        help="Pull request number to triage.",
    )
    parser.add_argument(
        "--run-id",
        type=int,
        help="Specific workflow run ID to triage.",
    )
    parser.add_argument(
        "--rerun-infra-drops",
        action="store_true",
        help="Rerun failed jobs for runs containing runner infrastructure drops.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview rerun actions without calling the GitHub API POST endpoint.",
    )
    parser.add_argument(
        "--max-log-lines",
        type=int,
        default=50,
        help="Maximum tail lines of failed step logs to print per run (default: 50; 0 disables).",
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
    gh_bin = find_gh()

    full_repo = (
        resolve_repo(args.repo, args.owner) if args.repo else infer_current_repo(gh_bin)
    )
    if not full_repo:
        print(
            "Error: --repo is required when not inside a GitHub repository.",
            file=sys.stderr,
        )
        return 2
    owner, repo = split_repo(full_repo, args.owner)

    if args.run_id:
        run_obj = run_gh_json(
            gh_bin, ["api", f"repos/{owner}/{repo}/actions/runs/{args.run_id}"]
        )
        runs = [run_obj] if isinstance(run_obj, dict) else []
    elif args.pr:
        runs = discover_runs_for_pr(gh_bin, owner, repo, args.pr)
    else:
        runs = discover_recent_failing_runs(gh_bin, owner, repo)

    report = [
        triage_run(
            gh_bin,
            owner,
            repo,
            run,
            rerun_infra_drops=args.rerun_infra_drops,
            dry_run=args.dry_run,
            max_log_lines=args.max_log_lines,
        )
        for run in runs
    ]

    if args.json_output:
        print(json.dumps({"repo": full_repo, "runs": report}, indent=2))
        return 0

    if not report:
        print(f"No failing workflow runs found for {full_repo}.")
        return 0

    print(f"=== CI Triage: {full_repo} ({len(report)} failing run(s)) ===")
    for item in report:
        print(
            f"\nRun #{item['run_id']} [{item['conclusion']}] {item['name']} "
            f"({item['head_branch']})"
        )
        if item["html_url"]:
            print(f"  URL: {item['html_url']}")
        if item["infra_drops"]:
            print(f"  Infra drops ({len(item['infra_drops'])}):")
            for job in item["infra_drops"]:
                print(
                    f"    - {job['name']} (job {job['id']}, runner_id={job['runner_id']}, "
                    f"steps={job['step_count']})"
                )
            print(f"  Rerun status: {item['rerun_status']}")
            if item["rerun_error"]:
                print(f"  Rerun error: {item['rerun_error']}")
        if item["failed_jobs"]:
            print(f"  Failed jobs ({len(item['failed_jobs'])}):")
            for job in item["failed_jobs"]:
                print(f"    - {job['name']} [{job['conclusion']}] (job {job['id']})")
        logs = item["failed_logs"]
        if logs["lines"]:
            trunc_note = " (tail-truncated)" if logs["truncated"] else ""
            print(f"  Failed logs{trunc_note}:")
            for line in logs["lines"]:
                print(f"    {line}")
        elif logs["error"]:
            print(f"  Failed logs unavailable: {logs['error']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
