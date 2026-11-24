#!/usr/bin/env python3
"""Audit open pull requests, CI checks, Codecov status, and unanswered review mail.

Queries GitHub via `gh` across carlkidcrypto repositories and prints a summary
table of PR mergeability, CI pass/fail/pending counts, Codecov check/comment
presence, and unanswered pull request review comment threads (`in_reply_to`).
"""

import argparse
import json
import os
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
    """Locate the GitHub CLI executable even when Homebrew/local bins are not in PATH."""
    for candidate in (
        os.environ.get("GH_BIN"),
        shutil.which("gh"),
        "/opt/homebrew/bin/gh",
        "/usr/local/bin/gh",
        "/usr/bin/gh",
    ):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError("GitHub CLI (`gh`) not found in PATH or standard locations")


def run_gh(gh_bin: str, args: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` subcommand and return the completed process."""
    return subprocess.run([gh_bin, *args], text=True, capture_output=True)


def get_unanswered_review_comments(
    gh_bin: str, owner: str, repo: str, pr_number: int
) -> List[Dict[str, Any]]:
    """Return root pull request review comments that have no `in_reply_to_id` reply."""
    res = run_gh(
        gh_bin,
        [
            "api",
            "--paginate",
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments",
        ],
    )
    if res.returncode != 0:
        return []
    comments = json.loads(res.stdout or "[]")
    replied_ids = {
        c["in_reply_to_id"] for c in comments if c.get("in_reply_to_id") is not None
    }
    unanswered: List[Dict[str, Any]] = []
    for comment in comments:
        if (
            comment.get("in_reply_to_id") is None
            and comment.get("id") not in replied_ids
        ):
            unanswered.append(
                {
                    "id": comment.get("id"),
                    "user": (comment.get("user") or {}).get("login", "unknown"),
                    "path": comment.get("path", ""),
                }
            )
    return unanswered


def get_codecov_comment_status(comments: List[Dict[str, Any]]) -> str:
    """Summarize Codecov PR comment presence from issue comments."""
    for comment in comments:
        author = (comment.get("author") or {}).get("login", "").lower()
        body = (comment.get("body") or "").lower()
        if "codecov" in author or "codecov" in body:
            return "comment"
    return "none"


def inspect_repo(
    gh_bin: str,
    owner: str,
    repo: str,
    limit: int,
    max_sample_fails: int,
) -> List[Dict[str, Any]]:
    """Return open PR audit records for a single repository."""
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
            "number,headRefName,baseRefName,mergeable,title,url,comments",
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

        codecov_checks = [
            line.split("\t")[1].strip()
            for line in lines
            if "codecov" in line.lower() and "\t" in line
        ]
        codecov_comment = get_codecov_comment_status(pr.get("comments") or [])
        if codecov_checks:
            codecov_status = f"chk:{codecov_checks[0]}"
            if codecov_comment == "comment":
                codecov_status += "+cmt"
        else:
            codecov_status = codecov_comment

        unanswered = get_unanswered_review_comments(gh_bin, owner, repo, num)
        results.append(
            {
                "repo": repo,
                "number": num,
                "mergeable": pr.get("mergeable", "UNKNOWN"),
                "headRefName": pr["headRefName"],
                "baseRefName": pr["baseRefName"],
                "title": pr.get("title", ""),
                "url": pr.get("url", ""),
                "pass": ok,
                "fail": len(fails),
                "pending": pend,
                "sample_fails": fails[:max_sample_fails],
                "codecov": codecov_status,
                "unanswered_count": len(unanswered),
                "unanswered_comments": unanswered,
            }
        )
    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Audit open PRs, CI checks, Codecov status, and unanswered review mail."
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
        help="Only show PRs with failing checks or unanswered review comments.",
    )
    parser.add_argument(
        "--unanswered-only",
        action="store_true",
        help="Only show PRs with unanswered review comments.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON instead of a formatted table.",
    )
    return parser.parse_args(argv)


def format_table(rows: List[Dict[str, Any]]) -> str:
    """Format PR audit records as an aligned text table."""
    if not rows:
        return "No matching open PRs found."
    header = (
        f"{'REPO':<23} {'PR':<6} {'MERGEABLE':<11} "
        f"{'CI(P/F/W)':<11} {'CODECOV':<13} {'MAIL':<5} {'BRANCHES'}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        ci = f"{row['pass']}/{row['fail']}/{row['pending']}"
        branches = f"{row['baseRefName']} <- {row['headRefName']}"
        lines.append(
            f"{row['repo']:<23} #{row['number']:<5} {row['mergeable']:<11} "
            f"{ci:<11} {row['codecov']:<13} {row['unanswered_count']:<5} {branches}"
        )
        if row["sample_fails"]:
            lines.append(f"  fails: {', '.join(row['sample_fails'])}")
        if row["unanswered_comments"]:
            ids = ", ".join(
                f"{c['id']}({c['user']})" for c in row["unanswered_comments"][:5]
            )
            lines.append(f"  unanswered: {ids}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    gh_bin = find_gh()
    repos = args.repos if args.repos else DEFAULT_REPOS

    all_rows: List[Dict[str, Any]] = []
    for repo in repos:
        all_rows.extend(
            inspect_repo(gh_bin, args.owner, repo, args.limit, args.max_sample_fails)
        )

    if args.unanswered_only:
        all_rows = [r for r in all_rows if r["unanswered_count"] > 0]
    elif args.failing_only:
        all_rows = [r for r in all_rows if r["fail"] > 0 or r["unanswered_count"] > 0]

    if args.json_output:
        print(json.dumps(all_rows, indent=2))
    else:
        print(format_table(all_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
