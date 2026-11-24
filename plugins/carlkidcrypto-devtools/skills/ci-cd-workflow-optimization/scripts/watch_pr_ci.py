#!/usr/bin/env python3
"""Watch and summarize GitHub Actions CI checks for a pull request.

Runs `gh pr checks` (treating exit code 8 as pending rather than an error),
summarizes passed/pending/failed/skipped/cancelled check counts, supports
polling with `--wait`, and optionally fetches `--log-failed` output or checks
`rerun-failed-jobs` eligibility for failed workflow runs.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gh_common import find_gh, run_gh  # noqa: E402

GH_PENDING_EXIT_CODE = 8
RUN_ID_RE = re.compile(r"/actions/runs/(\d+)")
CHECK_JSON_FIELDS = "name,state,bucket,link,workflow,description"


def extract_run_ids(checks: List[Dict[str, Any]]) -> List[str]:
    """Extract unique GitHub Actions run IDs from check link URLs."""
    seen: Set[str] = set()
    run_ids: List[str] = []
    for check in checks:
        link = check.get("link") or ""
        match = RUN_ID_RE.search(link)
        if match:
            run_id = match.group(1)
            if run_id not in seen:
                seen.add(run_id)
                run_ids.append(run_id)
    return run_ids


def fetch_pr_checks(
    gh_bin: str, repo: str, pr: int
) -> tuple[int, List[Dict[str, Any]], str]:
    """Fetch PR checks JSON via `gh pr checks`, handling exit code 8 cleanly."""
    res = run_gh(
        gh_bin,
        [
            "pr",
            "checks",
            str(pr),
            "--repo",
            repo,
            "--json",
            CHECK_JSON_FIELDS,
        ],
    )
    stdout = (res.stdout or "").strip()
    if stdout:
        try:
            checks = json.loads(stdout)
            if isinstance(checks, list):
                return res.returncode, checks, (res.stderr or "").strip()
        except json.JSONDecodeError:
            pass

    if res.returncode not in (0, GH_PENDING_EXIT_CODE):
        raise RuntimeError(
            f"`gh pr checks` failed (exit {res.returncode}): {(res.stderr or stdout).strip()}"
        )
    return res.returncode, [], (res.stderr or "").strip()


def summarize_checks(checks: List[Dict[str, Any]], returncode: int) -> Dict[str, Any]:
    """Compute bucket counts and overall status from parsed check items."""
    counts = {
        "pass": 0,
        "pending": 0,
        "fail": 0,
        "skipping": 0,
        "cancel": 0,
        "other": 0,
    }
    failed_checks: List[Dict[str, Any]] = []
    pending_checks: List[Dict[str, Any]] = []

    for check in checks:
        bucket = (check.get("bucket") or "other").lower()
        if bucket in counts:
            counts[bucket] += 1
        else:
            counts["other"] += 1

        if bucket in ("fail", "cancel"):
            failed_checks.append(check)
        elif bucket == "pending":
            pending_checks.append(check)

    if counts["fail"] > 0 or counts["cancel"] > 0:
        status = "fail"
    elif counts["pending"] > 0 or returncode == GH_PENDING_EXIT_CODE:
        status = "pending"
    else:
        status = "pass"

    return {
        "status": status,
        "counts": {**counts, "total": len(checks)},
        "failed_checks": failed_checks,
        "pending_checks": pending_checks,
    }


def fetch_failed_logs(
    gh_bin: str, repo: str, run_ids: List[str], tail_lines: int
) -> Dict[str, str]:
    """Fetch `--log-failed` output for each failed workflow run ID."""
    logs: Dict[str, str] = {}
    for run_id in run_ids:
        res = run_gh(
            gh_bin,
            ["run", "view", run_id, "--repo", repo, "--log-failed"],
        )
        if res.returncode == 0:
            lines = (res.stdout or "").splitlines()
            if tail_lines > 0 and len(lines) > tail_lines:
                lines = [
                    f"... ({len(lines) - tail_lines} earlier lines omitted)",
                    *lines[-tail_lines:],
                ]
            logs[run_id] = "\n".join(lines)
        else:
            logs[run_id] = (
                f"Failed to fetch --log-failed (exit {res.returncode}): "
                f"{(res.stderr or res.stdout).strip()}"
            )
    return logs


def check_rerun_eligibility(
    gh_bin: str, repo: str, run_ids: List[str]
) -> List[Dict[str, Any]]:
    """Inspect run jobs to determine `rerun-failed-jobs` eligibility."""
    results: List[Dict[str, Any]] = []
    for run_id in run_ids:
        res = run_gh(
            gh_bin,
            ["api", f"repos/{repo}/actions/runs/{run_id}/jobs"],
        )
        if res.returncode != 0:
            results.append(
                {
                    "run_id": run_id,
                    "eligible": False,
                    "error": (res.stderr or res.stdout).strip(),
                }
            )
            continue

        payload = json.loads(res.stdout or "{}")
        jobs = payload.get("jobs", [])
        failed_jobs = [
            {
                "id": j.get("id"),
                "name": j.get("name"),
                "status": j.get("status"),
                "conclusion": j.get("conclusion"),
                "runner_id": j.get("runner_id"),
                "infra_drop": (
                    j.get("conclusion") == "cancelled"
                    and (j.get("runner_id") in (0, None) or not j.get("steps"))
                ),
            }
            for j in jobs
            if j.get("conclusion") in ("failure", "cancelled", "timed_out")
        ]
        in_progress = any(j.get("status") != "completed" for j in jobs)
        eligible = bool(failed_jobs) and not in_progress
        results.append(
            {
                "run_id": run_id,
                "eligible": eligible,
                "in_progress": in_progress,
                "failed_jobs": failed_jobs,
                "rerun_command": (
                    f"gh api -X POST repos/{repo}/actions/runs/{run_id}/rerun-failed-jobs"
                    if eligible
                    else None
                ),
            }
        )
    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Watch and summarize `gh pr checks` for a pull request "
            "(exit code 0=pass, 1=fail/error, 8=pending)."
        )
    )
    parser.add_argument("--pr", type=int, required=True, help="Pull request number.")
    parser.add_argument(
        "--repo",
        required=True,
        help="Target repository in `owner/repo` format.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until all pending checks finish or --max-polls is reached.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Seconds between polls when --wait is enabled (default: 30).",
    )
    parser.add_argument(
        "--max-polls",
        type=int,
        default=20,
        help="Maximum poll attempts when --wait is enabled (default: 20).",
    )
    parser.add_argument(
        "--log-failed",
        action="store_true",
        help="Fetch `gh run view --log-failed` output for failed workflow runs.",
    )
    parser.add_argument(
        "--log-tail-lines",
        type=int,
        default=80,
        help="Maximum trailing lines to keep per failed run log (default: 80, 0=all).",
    )
    parser.add_argument(
        "--check-rerun",
        action="store_true",
        help="Check whether failed workflow runs are eligible for `rerun-failed-jobs`.",
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

    max_polls = max(1, args.max_polls) if args.wait else 1
    polls = 0
    returncode = 0
    checks: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}

    for poll_idx in range(1, max_polls + 1):
        polls = poll_idx
        returncode, checks, _ = fetch_pr_checks(gh_bin, args.repo, args.pr)
        summary = summarize_checks(checks, returncode)
        if not args.wait or summary["status"] != "pending" or poll_idx == max_polls:
            break
        if not args.json_output:
            c = summary["counts"]
            print(
                f"[poll {poll_idx}/{max_polls}] pending={c['pending']} "
                f"pass={c['pass']} fail={c['fail']} — sleeping {args.interval}s...",
                file=sys.stderr,
            )
        time.sleep(max(1, args.interval))

    failed_run_ids = extract_run_ids(summary["failed_checks"])
    failed_logs: Optional[Dict[str, str]] = None
    rerun_info: Optional[List[Dict[str, Any]]] = None

    if args.log_failed and failed_run_ids:
        failed_logs = fetch_failed_logs(
            gh_bin, args.repo, failed_run_ids, args.log_tail_lines
        )
    if args.check_rerun and failed_run_ids:
        rerun_info = check_rerun_eligibility(gh_bin, args.repo, failed_run_ids)

    if args.json_output:
        output: Dict[str, Any] = {
            "repo": args.repo,
            "pr": args.pr,
            "polls": polls,
            "status": summary["status"],
            "counts": summary["counts"],
            "checks": checks,
            "failed_checks": summary["failed_checks"],
            "pending_checks": summary["pending_checks"],
        }
        if failed_logs is not None:
            output["failed_logs"] = failed_logs
        if rerun_info is not None:
            output["rerun_eligibility"] = rerun_info
        print(json.dumps(output, indent=2))
    else:
        c = summary["counts"]
        print(
            f"PR #{args.pr} ({args.repo}) | status={summary['status']} | "
            f"pass={c['pass']} pending={c['pending']} fail={c['fail']} "
            f"skipping={c['skipping']} cancel={c['cancel']} total={c['total']}"
        )
        if summary["pending_checks"]:
            print("Pending checks:")
            for chk in summary["pending_checks"]:
                print(
                    f"  - {chk.get('name')} ({chk.get('state')}) {chk.get('link', '')}"
                )
        if summary["failed_checks"]:
            print("Failed/Cancelled checks:")
            for chk in summary["failed_checks"]:
                print(
                    f"  - {chk.get('name')} [{chk.get('bucket')}] "
                    f"({chk.get('state')}) {chk.get('link', '')}"
                )
        if rerun_info:
            print("Rerun eligibility:")
            for item in rerun_info:
                print(
                    f"  - run {item['run_id']}: eligible={item.get('eligible')} "
                    f"cmd={item.get('rerun_command')}"
                )
        if failed_logs:
            for run_id, log_text in failed_logs.items():
                print(f"\n--- Failed log for run {run_id} ---")
                print(log_text)

    if summary["status"] == "fail":
        return 1
    if summary["status"] == "pending":
        return GH_PENDING_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
