#!/usr/bin/env python3
"""Scan open pull requests and CI check statuses across carlkidcrypto repositories.

Summarizes PR mergeability, base/head branch topology, pass/fail/pending check
counts, and sample failing check names using the GitHub CLI (`gh`).
"""

import argparse
import json
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

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
            "number,headRefName,baseRefName,mergeable,title,url",
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
        chk = run_gh(gh_bin, ["pr", "checks", str(num), "--repo", full_repo])
        lines = chk.stdout.splitlines()
        fails = [line.split("\t")[0].strip() for line in lines if "\tfail\t" in line]
        pend = sum(1 for line in lines if "\tpending\t" in line)
        ok = sum(1 for line in lines if "\tpass\t" in line)
        results.append(
            {
                "repo": repo,
                "number": num,
                "mergeable": pr.get("mergeable", "UNKNOWN"),
                "headRefName": pr["headRefName"],
                "baseRefName": pr["baseRefName"],
                "title": pr.get("title", ""),
                "url": pr.get("url", ""),
                "fail": len(fails),
                "pass": ok,
                "pending": pend,
                "sample_fails": fails[:max_sample_fails],
            }
        )
    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Scan open PRs and CI check statuses across carlkidcrypto repositories."
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

    if args.json_output:
        print(json.dumps(all_results, indent=2))
        return 0

    by_repo: Dict[str, List[Dict[str, Any]]] = {}
    for item in all_results:
        by_repo.setdefault(item["repo"], []).append(item)

    if not by_repo:
        print("No matching open PRs found.")
        return 0

    for repo, prs in by_repo.items():
        print(f"=== {repo} ({len(prs)} open PRs) ===")
        for p in prs:
            print(
                f"  #{p['number']} [{p['mergeable']}] {p['headRefName']} -> {p['baseRefName']} "
                f"| fail={p['fail']} pass={p['pass']} pend={p['pending']} "
                f"| sample_fails={p['sample_fails']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
