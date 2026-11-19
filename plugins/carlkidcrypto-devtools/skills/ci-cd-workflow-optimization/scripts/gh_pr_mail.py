#!/usr/bin/env python3
"""Inspect PR review threads/comments and post threaded replies via `gh`.

Supports:
  1. Two-pass read of PR feedback:
     - Pass 1: GraphQL `reviewThreads` (filtered to unresolved threads).
     - Pass 2: REST `pulls/{pr}/comments` and `issues/{pr}/comments`.
  2. Posting a formatted threaded reply to a PR review comment:
     `Addressed in commit `<sha>`: <summary>`
  3. Verifying no unpushed commits remain (`git log origin/<branch>..HEAD`).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

GRAPHQL_REVIEW_THREADS_QUERY = """
query($owner: String!, $name: String!, $pr: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 50) {
            nodes {
              databaseId
              author {
                login
              }
              body
              createdAt
              url
            }
          }
        }
      }
    }
  }
}
""".strip()


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


def find_git() -> str:
    """Locate the Git executable."""
    return find_tool("git")


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a command and return the completed process."""
    return subprocess.run(cmd, text=True, capture_output=True)


def run_gh(gh_bin: str, args: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` subcommand and return the completed process."""
    return run_cmd([gh_bin, *args])


def split_repo(repo: str) -> Tuple[str, str]:
    """Split an `owner/repo` string into `(owner, name)`."""
    if "/" not in repo or repo.count("/") != 1:
        raise ValueError(f"Expected 'owner/repo' format, got: {repo!r}")
    owner, name = repo.split("/", 1)
    if not owner or not name:
        raise ValueError(f"Expected 'owner/repo' format, got: {repo!r}")
    return owner, name


def parse_json_list_output(stdout: str) -> List[Dict[str, Any]]:
    """Parse JSON array output from `gh api --paginate`."""
    text = stdout.strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    items: List[Dict[str, Any]] = []
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        obj, end = decoder.raw_decode(text, idx)
        if isinstance(obj, list):
            items.extend(obj)
        else:
            items.append(obj)
        idx = end
    return items


def fetch_unresolved_threads(
    gh_bin: str, owner: str, name: str, pr: int
) -> List[Dict[str, Any]]:
    """Fetch unresolved GraphQL review threads for a pull request."""
    res = run_gh(
        gh_bin,
        [
            "api",
            "graphql",
            "-f",
            f"query={GRAPHQL_REVIEW_THREADS_QUERY}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"pr={pr}",
        ],
    )
    if res.returncode != 0:
        raise RuntimeError(f"GraphQL reviewThreads query failed: {res.stderr.strip()}")
    payload = json.loads(res.stdout or "{}")
    threads = (
        payload.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    return [t for t in threads if not t.get("isResolved", False)]


def fetch_rest_comments(gh_bin: str, endpoint: str) -> List[Dict[str, Any]]:
    """Fetch paginated REST comments from a GitHub API endpoint."""
    res = run_gh(gh_bin, ["api", endpoint, "--paginate"])
    if res.returncode != 0:
        raise RuntimeError(f"REST GET {endpoint} failed: {res.stderr.strip()}")
    return parse_json_list_output(res.stdout or "")


def format_reply_body(commit: str, summary: str) -> str:
    """Format a standardized threaded reply body."""
    return f"Addressed in commit `{commit}`: {summary}"


def post_threaded_reply(
    gh_bin: str, repo: str, pr: int, comment_id: int, commit: str, summary: str
) -> Dict[str, Any]:
    """Post a threaded reply to a PR review comment."""
    body = format_reply_body(commit, summary)
    endpoint = f"repos/{repo}/pulls/{pr}/comments"
    res = run_gh(
        gh_bin,
        [
            "api",
            endpoint,
            "-X",
            "POST",
            "-F",
            f"in_reply_to={comment_id}",
            "-f",
            f"body={body}",
        ],
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"Failed to post reply to comment {comment_id}: {res.stderr.strip()}"
        )
    return json.loads(res.stdout or "{}") if (res.stdout or "").strip() else {}


def check_unpushed_commits(
    git_bin: str, repo_dir: str = ".", branch: Optional[str] = None
) -> Tuple[bool, str, List[str]]:
    """Verify `git log origin/<branch>..HEAD` is empty.

    Returns `(is_clean, branch_name, unpushed_lines)`.
    """
    if not branch:
        head_res = run_cmd(
            [git_bin, "-C", repo_dir, "rev-parse", "--abbrev-ref", "HEAD"]
        )
        if head_res.returncode != 0:
            raise RuntimeError(
                f"Failed to determine current branch: {head_res.stderr.strip()}"
            )
        branch = head_res.stdout.strip()

    log_res = run_cmd(
        [git_bin, "-C", repo_dir, "log", f"origin/{branch}..HEAD", "--oneline"]
    )
    if log_res.returncode != 0:
        raise RuntimeError(
            f"Failed to check unpushed commits for origin/{branch}..HEAD: "
            f"{log_res.stderr.strip()}"
        )
    lines = [line for line in log_res.stdout.splitlines() if line.strip()]
    return (len(lines) == 0, branch, lines)


def print_mail_summary(
    repo: str,
    pr: int,
    unresolved_threads: List[Dict[str, Any]],
    pull_comments: List[Dict[str, Any]],
    issue_comments: List[Dict[str, Any]],
) -> None:
    """Print a human-readable summary of PR mail items."""
    print(f"=== PR Mail Summary: {repo}#{pr} ===")
    print(f"Unresolved reviewThreads (GraphQL): {len(unresolved_threads)}")
    for thread in unresolved_threads:
        path = thread.get("path") or "<unknown>"
        line = thread.get("line")
        loc = f"{path}:{line}" if line is not None else path
        comments = thread.get("comments", {}).get("nodes", [])
        first = comments[0] if comments else {}
        db_id = first.get("databaseId", "?")
        author = (first.get("author") or {}).get("login", "unknown")
        snippet = (first.get("body") or "").strip().splitlines()[0:1]
        preview = snippet[0][:100] if snippet else ""
        print(f"  - [thread id={db_id}] {loc} (@{author}): {preview}")

    print(f"PR review comments (REST pulls/{pr}/comments): {len(pull_comments)}")
    for comment in pull_comments:
        cid = comment.get("id", "?")
        user = (comment.get("user") or {}).get("login", "unknown")
        path = comment.get("path") or "<unknown>"
        snippet = (comment.get("body") or "").strip().splitlines()[0:1]
        preview = snippet[0][:100] if snippet else ""
        print(f"  - [comment id={cid}] {path} (@{user}): {preview}")

    print(f"Issue comments (REST issues/{pr}/comments): {len(issue_comments)}")
    for comment in issue_comments:
        cid = comment.get("id", "?")
        user = (comment.get("user") or {}).get("login", "unknown")
        snippet = (comment.get("body") or "").strip().splitlines()[0:1]
        preview = snippet[0][:100] if snippet else ""
        print(f"  - [issue comment id={cid}] (@{user}): {preview}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Read PR review threads/comments and post threaded replies via `gh`."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository in `owner/repo` format.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="Pull request number.",
    )
    parser.add_argument(
        "--reply-to",
        type=int,
        default=None,
        help="Review comment ID to reply to (requires --commit and --summary).",
    )
    parser.add_argument(
        "--commit",
        default=None,
        help="Commit SHA to reference in the threaded reply.",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Concise fix summary to include in the threaded reply.",
    )
    parser.add_argument(
        "--check-unpushed",
        action="store_true",
        help="Verify `git log origin/<branch>..HEAD` is empty.",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch name for --check-unpushed (defaults to current HEAD branch).",
    )
    parser.add_argument(
        "--repo-dir",
        default=".",
        help="Local git repository directory for --check-unpushed (default: '.').",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON output.",
    )

    args = parser.parse_args(argv)
    reply_fields = (
        args.reply_to is not None,
        args.commit is not None,
        args.summary is not None,
    )
    if any(reply_fields) and not all(reply_fields):
        parser.error("--reply-to, --commit, and --summary must be provided together.")
    if args.check_unpushed and args.reply_to is not None:
        parser.error("--check-unpushed cannot be combined with --reply-to.")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    try:
        owner, name = split_repo(args.repo)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.check_unpushed:
        try:
            git_bin = find_git()
            is_clean, branch, unpushed = check_unpushed_commits(
                git_bin, repo_dir=args.repo_dir, branch=args.branch
            )
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(
                json.dumps(
                    {
                        "branch": branch,
                        "clean": is_clean,
                        "unpushed_commits": unpushed,
                    },
                    indent=2,
                )
            )
        elif is_clean:
            print(f"OK: origin/{branch}..HEAD is empty (all commits pushed).")
        else:
            print(
                f"Unpushed commits on {branch} (origin/{branch}..HEAD):",
                file=sys.stderr,
            )
            for line in unpushed:
                print(f"  {line}", file=sys.stderr)
        return 0 if is_clean else 1

    try:
        gh_bin = find_gh()
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.reply_to is not None:
        try:
            resp = post_threaded_reply(
                gh_bin,
                args.repo,
                args.pr,
                args.reply_to,
                args.commit,
                args.summary,
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.json_output:
            print(json.dumps(resp, indent=2))
        else:
            print(
                f"Replied to comment {args.reply_to} on {args.repo}#{args.pr}: "
                f"{format_reply_body(args.commit, args.summary)}"
            )
        return 0

    try:
        unresolved_threads = fetch_unresolved_threads(gh_bin, owner, name, args.pr)
        pull_comments = fetch_rest_comments(
            gh_bin, f"repos/{args.repo}/pulls/{args.pr}/comments"
        )
        issue_comments = fetch_rest_comments(
            gh_bin, f"repos/{args.repo}/issues/{args.pr}/comments"
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(
            json.dumps(
                {
                    "repo": args.repo,
                    "pr": args.pr,
                    "unresolved_threads": unresolved_threads,
                    "pull_comments": pull_comments,
                    "issue_comments": issue_comments,
                },
                indent=2,
            )
        )
    else:
        print_mail_summary(
            args.repo, args.pr, unresolved_threads, pull_comments, issue_comments
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
