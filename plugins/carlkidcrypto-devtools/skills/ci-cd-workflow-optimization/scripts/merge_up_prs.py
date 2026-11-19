#!/usr/bin/env python3
"""Update open pull requests with base branch changes (`gh pr update-branch`) and report conflicts."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gh_common import (
    DEFAULT_OWNER,
    DEFAULT_REPOS,
    find_gh,
    infer_current_repo,
    resolve_repo,
    run_gh,
    run_gh_json,
)


def fetch_open_prs(
    gh_bin: str, full_repo: str, limit: int = 100
) -> List[Dict[str, Any]]:
    """Fetch open PRs for a repository."""
    data = run_gh_json(
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
            "number,title,headRefName,baseRefName,mergeable,mergeStateStatus,url",
        ],
    )
    return data if isinstance(data, list) else []


def update_pr_branch(
    gh_bin: str,
    full_repo: str,
    pr: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Run `gh pr update-branch` for a single PR and classify the outcome."""
    num = pr["number"]
    base_info = {
        "repo": full_repo,
        "number": num,
        "title": pr.get("title", ""),
        "headRefName": pr.get("headRefName", ""),
        "baseRefName": pr.get("baseRefName", ""),
        "mergeable": pr.get("mergeable", "UNKNOWN"),
        "mergeStateStatus": pr.get("mergeStateStatus", "UNKNOWN"),
        "url": pr.get("url", ""),
    }

    if pr.get("mergeable") == "CONFLICTING":
        return {**base_info, "status": "conflicted", "detail": "PR has merge conflicts"}

    if dry_run:
        return {
            **base_info,
            "status": "dry_run",
            "detail": "Would run gh pr update-branch",
        }

    res = run_gh(gh_bin, ["pr", "update-branch", str(num), "--repo", full_repo])
    combined = f"{res.stdout}\n{res.stderr}".strip()
    lower = combined.lower()

    if res.returncode == 0:
        status = (
            "already_up_to_date"
            if "already up-to-date" in lower or "already up to date" in lower
            else "updated"
        )
        return {**base_info, "status": status, "detail": combined or "Updated"}

    if "conflict" in lower or "not mergeable" in lower or "merge conflict" in lower:
        return {**base_info, "status": "conflicted", "detail": combined}

    return {
        **base_info,
        "status": "error",
        "detail": combined or f"exit {res.returncode}",
    }


def process_repo(
    gh_bin: str,
    full_repo: str,
    pr_filter: Optional[int],
    include_stacked: bool,
    dry_run: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    """Inspect and update open PRs in a single repository."""
    prs = fetch_open_prs(gh_bin, full_repo)
    if pr_filter is not None:
        prs = [p for p in prs if p.get("number") == pr_filter]

    buckets: Dict[str, List[Dict[str, Any]]] = {
        "updated": [],
        "already_up_to_date": [],
        "conflicted": [],
        "skipped_stacked": [],
        "dry_run": [],
        "error": [],
    }

    for pr in prs:
        if pr.get("baseRefName") != "main" and not include_stacked:
            buckets["skipped_stacked"].append(
                {
                    "repo": full_repo,
                    "number": pr["number"],
                    "headRefName": pr.get("headRefName", ""),
                    "baseRefName": pr.get("baseRefName", ""),
                    "url": pr.get("url", ""),
                    "status": "skipped_stacked",
                }
            )
            continue

        outcome = update_pr_branch(gh_bin, full_repo, pr, dry_run=dry_run)
        buckets[outcome["status"]].append(outcome)

    return buckets


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Update open PRs targeting main via `gh pr update-branch`."
    )
    parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER,
        help=f"GitHub owner/org (default: {DEFAULT_OWNER}).",
    )
    parser.add_argument(
        "--repo",
        "-r",
        action="append",
        dest="repos",
        help="Repository name or owner/repo (repeatable; defaults to current git repo unless --all-repos).",
    )
    parser.add_argument(
        "--all-repos",
        action="store_true",
        help="Scan all default ecosystem repositories.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        help="Update only a specific PR number.",
    )
    parser.add_argument(
        "--include-stacked",
        action="store_true",
        help="Also update stacked PRs whose baseRefName is not `main`.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview which PRs would be updated without modifying branches.",
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

    if args.all_repos:
        target_repos = [resolve_repo(r, args.owner) for r in DEFAULT_REPOS]
    elif args.repos:
        target_repos = [resolve_repo(r, args.owner) for r in args.repos]
    else:
        current = infer_current_repo(gh_bin)
        if not current:
            print(
                "Error: specify --repo or --all-repos when not inside a GitHub repository.",
                file=sys.stderr,
            )
            return 2
        target_repos = [current]

    summary: Dict[str, List[Dict[str, Any]]] = {
        "updated": [],
        "already_up_to_date": [],
        "conflicted": [],
        "skipped_stacked": [],
        "dry_run": [],
        "error": [],
    }
    for full_repo in target_repos:
        try:
            repo_buckets = process_repo(
                gh_bin,
                full_repo,
                pr_filter=args.pr,
                include_stacked=args.include_stacked,
                dry_run=args.dry_run,
            )
            for key, items in repo_buckets.items():
                summary[key].extend(items)
        except RuntimeError as exc:
            summary["error"].append(
                {
                    "repo": full_repo,
                    "number": args.pr,
                    "status": "error",
                    "detail": str(exc),
                }
            )

    if args.json_output:
        print(json.dumps(summary, indent=2))
        return 1 if summary["conflicted"] or summary["error"] else 0

    for label, key in (
        ("Updated", "updated"),
        ("Already up-to-date", "already_up_to_date"),
        ("Dry-run", "dry_run"),
        ("Conflicted", "conflicted"),
        ("Skipped stacked", "skipped_stacked"),
        ("Errors", "error"),
    ):
        items = summary[key]
        if not items:
            continue
        print(f"=== {label} ({len(items)}) ===")
        for item in items:
            num = f"#{item['number']}" if item.get("number") else ""
            branch_info = (
                f" {item['headRefName']} -> {item['baseRefName']}"
                if item.get("headRefName")
                else ""
            )
            detail = f" | {item['detail']}" if item.get("detail") else ""
            print(f"  {item['repo']}{num}{branch_info}{detail}")

    if not any(summary.values()):
        print("No matching open PRs found.")

    return 1 if summary["conflicted"] or summary["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
