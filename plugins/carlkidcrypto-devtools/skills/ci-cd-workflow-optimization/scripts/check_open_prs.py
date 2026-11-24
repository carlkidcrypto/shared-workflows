#!/usr/bin/env python3
"""Scan open pull requests, CI checks, and release workflow runs across carlkidcrypto repositories.

Summarizes PR mergeability, base/head branch topology, `behind_by` commit lag,
pass/fail/pending/skip check counts, failed check names, and recent
PyPI/TestPyPI/NuGet/npm/WinGet/release workflow runs using the GitHub CLI (`gh`).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gh_common import DEFAULT_OWNER, DEFAULT_REPOS, find_gh, run_gh  # noqa: E402

RELEASE_WORKFLOW_RE = re.compile(
    r"(pypi|test[\s_-]*pypi|nuget|npm|winget|release|publish)",
    re.IGNORECASE,
)


def get_behind_by(
    gh_bin: str,
    owner: str,
    repo: str,
    base_ref: str,
    head_ref: str,
    head_owner: Optional[str] = None,
) -> Optional[int]:
    """Return how many commits `head_ref` is behind `base_ref`, or None on error."""
    head_spec = (
        f"{head_owner}:{head_ref}" if head_owner and head_owner != owner else head_ref
    )
    res = run_gh(
        gh_bin,
        [
            "api",
            f"repos/{owner}/{repo}/compare/{base_ref}...{head_spec}",
            "--jq",
            ".behind_by",
        ],
    )
    if res.returncode != 0:
        return None
    raw = (res.stdout or "").strip()
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_tab_checks(stdout: str, max_sample_fails: int) -> Dict[str, Any]:
    """Fallback parser for legacy tab-separated `gh pr checks` output."""
    lines = stdout.splitlines()
    fails: List[str] = []
    pend = 0
    ok = 0
    skip = 0
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        state = parts[1].strip().lower()
        if state in ("fail", "cancel", "cancelled"):
            fails.append(name)
        elif state == "pending":
            pend += 1
        elif state == "pass":
            ok += 1
        elif state in ("skipping", "skipped"):
            skip += 1
    return {
        "pass": ok,
        "fail": len(fails),
        "pending": pend,
        "skip": skip,
        "failed_checks": fails,
        "sample_fails": fails[:max_sample_fails],
    }


def fetch_pr_checks_summary(
    gh_bin: str,
    full_repo: str,
    pr_number: int,
    max_sample_fails: int,
) -> Dict[str, Any]:
    """Fetch PR check bucket counts and failing check names."""
    res = run_gh(
        gh_bin,
        [
            "pr",
            "checks",
            str(pr_number),
            "--repo",
            full_repo,
            "--json",
            "name,state,bucket",
        ],
    )
    stdout = (res.stdout or "").strip()
    if not stdout:
        return {
            "pass": 0,
            "fail": 0,
            "pending": 0,
            "skip": 0,
            "failed_checks": [],
            "sample_fails": [],
        }

    try:
        checks = json.loads(stdout)
    except json.JSONDecodeError:
        return _parse_tab_checks(res.stdout or "", max_sample_fails)

    if not isinstance(checks, list):
        return _parse_tab_checks(res.stdout or "", max_sample_fails)

    ok = 0
    pend = 0
    skip = 0
    fails: List[str] = []
    for item in checks:
        bucket = (item.get("bucket") or "").lower()
        name = (item.get("name") or "").strip()
        if bucket == "pass":
            ok += 1
        elif bucket in ("fail", "cancel"):
            fails.append(name)
        elif bucket == "pending":
            pend += 1
        elif bucket == "skipping":
            skip += 1

    return {
        "pass": ok,
        "fail": len(fails),
        "pending": pend,
        "skip": skip,
        "failed_checks": fails,
        "sample_fails": fails[:max_sample_fails],
    }


def inspect_repo(
    gh_bin: str,
    owner: str,
    repo: str,
    limit: int,
    max_sample_fails: int,
) -> List[Dict[str, Any]]:
    """Return open PRs and CI check summaries for a single repository."""
    full_repo = f"{owner}/{repo}"
    res = run_gh(
        gh_bin,
        [
            "pr",
            "list",
            "--repo",
            full_repo,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,headRefName,baseRefName,mergeable,title,url,isCrossRepository,headRepositoryOwner",
        ],
    )
    if res.returncode != 0:
        print(
            f"Warning: failed to list PRs for {full_repo}: {res.stderr.strip()}",
            file=sys.stderr,
        )
        return []

    prs = json.loads(res.stdout or "[]")
    results: List[Dict[str, Any]] = []
    for pr in prs:
        num = pr["number"]
        head_owner = (pr.get("headRepositoryOwner") or {}).get("login")
        behind_by = get_behind_by(
            gh_bin,
            owner,
            repo,
            pr["baseRefName"],
            pr["headRefName"],
            head_owner=head_owner if pr.get("isCrossRepository") else None,
        )
        chk_summary = fetch_pr_checks_summary(gh_bin, full_repo, num, max_sample_fails)
        results.append(
            {
                "repo": repo,
                "number": num,
                "mergeable": pr.get("mergeable", "UNKNOWN"),
                "behind_by": behind_by,
                "headRefName": pr["headRefName"],
                "baseRefName": pr["baseRefName"],
                "title": pr.get("title", ""),
                "url": pr.get("url", ""),
                "fail": chk_summary["fail"],
                "pass": chk_summary["pass"],
                "pending": chk_summary["pending"],
                "skip": chk_summary["skip"],
                "failed_checks": chk_summary["failed_checks"],
                "sample_fails": chk_summary["sample_fails"],
            }
        )
    return results


def fetch_release_runs(
    gh_bin: str,
    owner: str,
    repo: str,
    limit: int = 5,
    fetch_limit: int = 30,
) -> List[Dict[str, Any]]:
    """Return recent PyPI/TestPyPI/NuGet/npm/WinGet/release workflow runs for a repo."""
    full_repo = f"{owner}/{repo}"
    res = run_gh(
        gh_bin,
        [
            "run",
            "list",
            "--repo",
            full_repo,
            "--limit",
            str(fetch_limit),
            "--json",
            "databaseId,workflowName,displayTitle,status,conclusion,headBranch,event,createdAt,url",
        ],
    )
    if res.returncode != 0:
        print(
            f"Warning: failed to list workflow runs for {full_repo}: {res.stderr.strip()}",
            file=sys.stderr,
        )
        return []

    runs = json.loads(res.stdout or "[]")
    matched: List[Dict[str, Any]] = []
    for run in runs:
        wf_name = run.get("workflowName") or ""
        title = run.get("displayTitle") or ""
        if not (
            RELEASE_WORKFLOW_RE.search(wf_name) or RELEASE_WORKFLOW_RE.search(title)
        ):
            continue
        matched.append(
            {
                "repo": repo,
                "id": run.get("databaseId"),
                "workflowName": wf_name,
                "displayTitle": title,
                "status": run.get("status", ""),
                "conclusion": run.get("conclusion") or "",
                "headBranch": run.get("headBranch", ""),
                "event": run.get("event", ""),
                "createdAt": run.get("createdAt", ""),
                "url": run.get("url", ""),
            }
        )
        if len(matched) >= limit:
            break
    return matched


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Scan open PRs, CI check statuses, behind_by lag, and recent "
            "release/publish workflow runs across carlkidcrypto repositories."
        )
    )
    parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER,
        help=f"GitHub owner/org (default: {DEFAULT_OWNER})",
    )
    parser.add_argument(
        "--repo",
        "-r",
        action="append",
        dest="repos",
        help="Repository name to scan (repeatable; defaults to all ecosystem repos).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum open PRs to fetch per repository (default: 30).",
    )
    parser.add_argument(
        "--max-sample-fails",
        type=int,
        default=4,
        help="Maximum failing check names to display per PR (default: 4).",
    )
    parser.add_argument(
        "--failing-only",
        action="store_true",
        help="Only show PRs with at least one failing check.",
    )
    parser.add_argument(
        "--release-runs",
        action="store_true",
        help="Also scan recent PyPI/TestPyPI/NuGet/npm/WinGet/release workflow runs.",
    )
    parser.add_argument(
        "--release-limit",
        type=int,
        default=5,
        help="Maximum matching release/publish runs to return per repo (default: 5).",
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
    repos = args.repos if args.repos else DEFAULT_REPOS

    all_results: List[Dict[str, Any]] = []
    all_release_runs: List[Dict[str, Any]] = []
    for repo in repos:
        repo_prs = inspect_repo(
            gh_bin,
            args.owner,
            repo,
            limit=args.limit,
            max_sample_fails=args.max_sample_fails,
        )
        if args.failing_only:
            repo_prs = [pr for pr in repo_prs if pr["fail"] > 0]
        all_results.extend(repo_prs)

        if args.release_runs:
            all_release_runs.extend(
                fetch_release_runs(
                    gh_bin,
                    args.owner,
                    repo,
                    limit=args.release_limit,
                )
            )

    if args.json_output:
        if args.release_runs:
            print(
                json.dumps(
                    {"prs": all_results, "release_runs": all_release_runs},
                    indent=2,
                )
            )
        else:
            print(json.dumps(all_results, indent=2))
        return 0

    by_repo: Dict[str, List[Dict[str, Any]]] = {}
    for item in all_results:
        by_repo.setdefault(item["repo"], []).append(item)

    if not by_repo:
        print("No matching open PRs found.")
    else:
        for repo, prs in by_repo.items():
            print(f"=== {repo} ({len(prs)} open PRs) ===")
            for p in prs:
                behind = "?" if p["behind_by"] is None else str(p["behind_by"])
                line = (
                    f"  #{p['number']} [{p['mergeable']}] behind={behind} "
                    f"{p['headRefName']} -> {p['baseRefName']} "
                    f"| pass={p['pass']} fail={p['fail']} pend={p['pending']} skip={p['skip']}"
                )
                if p["sample_fails"]:
                    line += f" | failed={p['sample_fails']}"
                print(line)

    if args.release_runs:
        runs_by_repo: Dict[str, List[Dict[str, Any]]] = {}
        for run in all_release_runs:
            runs_by_repo.setdefault(run["repo"], []).append(run)
        if not runs_by_repo:
            print("\nNo matching release/publish workflow runs found.")
        else:
            print("\n=== Recent Release / Publish Workflow Runs ===")
            for repo, runs in runs_by_repo.items():
                print(f"--- {repo} ({len(runs)}) ---")
                for r in runs:
                    outcome = r["conclusion"] or r["status"] or "unknown"
                    print(
                        f"  [{outcome}] {r['workflowName']} "
                        f"({r['event']} @ {r['headBranch']}) "
                        f"#{r['id']} {r['createdAt']}"
                    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
