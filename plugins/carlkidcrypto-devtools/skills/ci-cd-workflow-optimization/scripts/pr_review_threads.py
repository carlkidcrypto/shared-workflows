#!/usr/bin/env python3
"""Inspect inline PR review comment threads and post formatted threaded replies."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def infer_current_pr(gh_bin: str, full_repo: str) -> Optional[int]:
    """Infer PR number from the current checked-out branch."""
    res = run_gh(
        gh_bin,
        ["pr", "view", "--repo", full_repo, "--json", "number", "-q", ".number"],
    )
    if res.returncode == 0 and res.stdout.strip().isdigit():
        return int(res.stdout.strip())
    return None


def fetch_review_comments(
    gh_bin: str,
    owner: str,
    repo: str,
    pr_number: int,
) -> List[Dict[str, Any]]:
    """Fetch all inline review comments on a pull request."""
    pages = run_gh_json(
        gh_bin,
        [
            "api",
            "--paginate",
            "--slurp",
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments?per_page=100",
        ],
    )
    comments: List[Dict[str, Any]] = []
    if isinstance(pages, list):
        for page in pages:
            if isinstance(page, list):
                comments.extend(page)
            elif isinstance(page, dict):
                comments.append(page)
    return comments


def build_threads(comments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group flat PR review comments into root threads with ordered replies."""
    by_id: Dict[int, Dict[str, Any]] = {c["id"]: c for c in comments if "id" in c}
    roots: Dict[int, Dict[str, Any]] = {}
    replies_by_root: Dict[int, List[Dict[str, Any]]] = {}

    def find_root_id(comment: Dict[str, Any]) -> int:
        curr = comment
        seen = set()
        while curr.get("in_reply_to_id") and curr["in_reply_to_id"] in by_id:
            parent_id = curr["in_reply_to_id"]
            if parent_id in seen:
                break
            seen.add(parent_id)
            curr = by_id[parent_id]
        return curr["id"]

    for comment in sorted(comments, key=lambda c: c.get("id", 0)):
        if not comment.get("in_reply_to_id"):
            roots[comment["id"]] = comment
            replies_by_root.setdefault(comment["id"], [])

    for comment in sorted(comments, key=lambda c: c.get("id", 0)):
        if comment.get("in_reply_to_id"):
            root_id = find_root_id(comment)
            if root_id not in roots:
                roots[root_id] = by_id.get(root_id, comment)
            replies_by_root.setdefault(root_id, []).append(comment)

    threads: List[Dict[str, Any]] = []
    for root_id in sorted(roots):
        root = roots[root_id]
        replies = replies_by_root.get(root_id, [])
        threads.append(
            {
                "root_id": root_id,
                "author": (root.get("user") or {}).get("login", "unknown"),
                "path": root.get("path", ""),
                "line": root.get("line") or root.get("original_line"),
                "body": root.get("body", ""),
                "html_url": root.get("html_url", ""),
                "created_at": root.get("created_at", ""),
                "unreplied": len(replies) == 0,
                "reply_count": len(replies),
                "replies": [
                    {
                        "id": r.get("id"),
                        "author": (r.get("user") or {}).get("login", "unknown"),
                        "body": r.get("body", ""),
                        "created_at": r.get("created_at", ""),
                    }
                    for r in replies
                ],
            }
        )
    return threads


def format_reply_body(message: str, commit_sha: Optional[str]) -> str:
    """Format a threaded reply body following ecosystem conventions."""
    if commit_sha:
        return f"Addressed in commit `{commit_sha}`: {message}"
    return message


def post_reply(
    gh_bin: str,
    owner: str,
    repo: str,
    pr_number: int,
    comment_id: int,
    body: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Post a threaded reply to an inline PR review comment."""
    if dry_run:
        return {
            "status": "dry_run",
            "in_reply_to": comment_id,
            "body": body,
        }
    res = run_gh(
        gh_bin,
        [
            "api",
            f"repos/{owner}/{repo}/pulls/{pr_number}/comments",
            "-F",
            f"in_reply_to={comment_id}",
            "-f",
            f"body={body}",
        ],
        check=True,
    )
    created = json.loads(res.stdout) if res.stdout.strip() else {}
    return {
        "status": "posted",
        "id": created.get("id"),
        "in_reply_to": comment_id,
        "html_url": created.get("html_url"),
        "body": body,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="List PR review comment threads and post formatted threaded replies."
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
        help="Pull request number (defaults to current branch PR).",
    )
    parser.add_argument(
        "--unreplied-only",
        action="store_true",
        help="Only show threads with no replies.",
    )
    parser.add_argument(
        "--reply-to",
        type=int,
        metavar="COMMENT_ID",
        help="Comment ID to reply to.",
    )
    parser.add_argument(
        "--commit",
        metavar="SHA",
        help="Commit SHA to cite in `Addressed in commit `<sha>`: <message>`.",
    )
    parser.add_argument(
        "--message",
        metavar="TEXT",
        help="Reply message text (required with --reply-to).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the formatted reply without posting to GitHub.",
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

    pr_number = args.pr or infer_current_pr(gh_bin, full_repo)
    if not pr_number:
        print(
            "Error: --pr is required when not on a branch with an open PR.",
            file=sys.stderr,
        )
        return 2

    if args.reply_to is not None:
        if not args.message:
            print(
                "Error: --message is required when using --reply-to.", file=sys.stderr
            )
            return 2
        body = format_reply_body(args.message, args.commit)
        result = post_reply(
            gh_bin,
            owner,
            repo,
            pr_number,
            args.reply_to,
            body,
            dry_run=args.dry_run,
        )
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(
                f"[{result['status']}] Reply to comment {args.reply_to} on "
                f"{full_repo}#{pr_number}: {body}"
            )
            if result.get("html_url"):
                print(f"  URL: {result['html_url']}")
        return 0

    comments = fetch_review_comments(gh_bin, owner, repo, pr_number)
    threads = build_threads(comments)
    if args.unreplied_only:
        threads = [t for t in threads if t["unreplied"]]

    if args.json_output:
        print(
            json.dumps(
                {"repo": full_repo, "pr": pr_number, "threads": threads}, indent=2
            )
        )
        return 0

    if not threads:
        print(f"No matching review comment threads on {full_repo}#{pr_number}.")
        return 0

    print(f"=== Review Threads: {full_repo}#{pr_number} ({len(threads)} thread(s)) ===")
    for t in threads:
        status = "UNREPLIED" if t["unreplied"] else f"{t['reply_count']} reply(ies)"
        loc = f"{t['path']}:{t['line']}" if t["line"] else t["path"]
        snippet = " ".join(t["body"].split())
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        print(f"  [{status}] id={t['root_id']} @{t['author']} ({loc})")
        print(f"    {snippet}")
        if t["html_url"]:
            print(f"    {t['html_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
