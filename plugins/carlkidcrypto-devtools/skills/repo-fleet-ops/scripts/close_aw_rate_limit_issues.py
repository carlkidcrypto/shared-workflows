#!/usr/bin/env python3
"""Close open GitHub Agentic Workflows (gh-aw) Copilot HTTP 429 rate-limit issues.

Scans open issues across carlkidcrypto repositories for genuine `gh-aw` Copilot
HTTP 429 rate-limit / credit-exhaustion failure issues, optionally verifies the
associated GitHub Actions failed logs, and closes them as `not_planned` with an
explanatory comment when `--apply` is passed (dry-run by default).
"""

import argparse
import json
import re
import shutil
import subprocess
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
DEFAULT_COMMENT = (
    "Closing because Copilot credits / engine rate limit (HTTP 429) were "
    "exhausted. Will re-run once credits reset."
)

ALLOWED_AUTHORS = {"app/github-actions", "github-actions[bot]"}
EXCLUDED_TITLE_MARKERS = (
    "[aw] detection runs",
    "[aw] no-op runs",
    "activation failed",
)
RUN_ID_RE = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/actions/runs/(\d+)")
LOG_429_MARKERS = (
    "ai_credits_rate_limit_error",
    "errorCodes=[429]",
    'errorTypes=["rate_limit"]',
)


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


def resolve_repos(owner: str, repos: Optional[List[str]]) -> List[str]:
    """Resolve CLI repo arguments into `owner/repo` strings."""
    targets = repos if repos else DEFAULT_REPOS
    return [r if "/" in r else f"{owner}/{r}" for r in targets]


def is_excluded_aw_issue(title: str) -> bool:
    """Return True if the issue title is an excluded gh-aw summary/activation issue."""
    lowered = title.lower()
    return any(marker in lowered for marker in EXCLUDED_TITLE_MARKERS)


def is_aw_actor(issue: Dict[str, Any]) -> bool:
    """Return True if the issue was opened by GitHub Actions or has agentic-workflows label."""
    author_login = ((issue.get("author") or {}).get("login") or "").lower()
    if author_login in ALLOWED_AUTHORS:
        return True
    labels = issue.get("labels") or []
    label_names = {
        (lbl.get("name") or "").lower() for lbl in labels if isinstance(lbl, dict)
    }
    return "agentic-workflows" in label_names


def is_copilot_429_issue(issue: Dict[str, Any]) -> bool:
    """Return True only for genuine gh-aw Copilot HTTP 429 rate-limit failure issues."""
    title = issue.get("title") or ""
    body = issue.get("body") or ""
    if is_excluded_aw_issue(title):
        return False
    if not is_aw_actor(issue):
        return False
    if "hit engine rate limit (http 429)" in title.lower():
        return True
    return (
        "engine_rate_limit_429" in body
        and "engine: copilot" in body
        and "gh-aw-failure-issue: true" in body
    )


def extract_run_id(body: str) -> Optional[str]:
    """Extract the GitHub Actions run ID from an issue body, if present."""
    match = RUN_ID_RE.search(body or "")
    return match.group(1) if match else None


def verify_run_logs_429(gh_bin: str, full_repo: str, run_id: str) -> bool:
    """Return True if `gh run view --log-failed` confirms a Copilot 429 rate limit."""
    res = run_gh(
        gh_bin,
        ["run", "view", run_id, "--repo", full_repo, "--log-failed"],
    )
    if res.returncode != 0:
        return False
    combined = f"{res.stdout or ''}\n{res.stderr or ''}"
    return any(marker in combined for marker in LOG_429_MARKERS)


def list_open_issues(gh_bin: str, full_repo: str, limit: int) -> List[Dict[str, Any]]:
    """Fetch open issues for a single `owner/repo` via `gh issue list`."""
    res = run_gh(
        gh_bin,
        [
            "issue",
            "list",
            "--repo",
            full_repo,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title,body,author,labels,url",
        ],
    )
    if res.returncode != 0:
        return []
    return json.loads(res.stdout or "[]")


def close_issue(
    gh_bin: str, full_repo: str, number: int, comment: str
) -> subprocess.CompletedProcess[str]:
    """Close an issue as `not_planned` with an explanatory comment."""
    return run_gh(
        gh_bin,
        [
            "issue",
            "close",
            str(number),
            "--repo",
            full_repo,
            "--reason",
            "not_planned",
            "--comment",
            comment,
        ],
    )


def process_repo(
    gh_bin: str,
    full_repo: str,
    limit: int,
    verify_logs: bool,
    apply: bool,
    comment: str,
) -> List[Dict[str, Any]]:
    """Scan a repository for matching 429 issues and optionally close them."""
    issues = list_open_issues(gh_bin, full_repo, limit)
    results: List[Dict[str, Any]] = []
    for issue in issues:
        if not is_copilot_429_issue(issue):
            continue
        number = issue.get("number")
        title = issue.get("title") or ""
        body = issue.get("body") or ""
        run_id = extract_run_id(body)
        verified: Optional[bool] = None
        if verify_logs:
            verified = bool(run_id and verify_run_logs_429(gh_bin, full_repo, run_id))

        should_close = apply and (not verify_logs or bool(verified))
        action = "would-close"
        error = ""
        if verify_logs and not verified:
            action = "skipped-unverified"
        elif should_close:
            res = close_issue(gh_bin, full_repo, int(number), comment)
            if res.returncode == 0:
                action = "closed"
            else:
                action = "error"
                error = (res.stderr or "").strip()

        results.append(
            {
                "repo": full_repo,
                "number": number,
                "title": title,
                "url": issue.get("url") or "",
                "run_id": run_id,
                "log_verified": verified,
                "action": action,
                "error": error,
            }
        )
    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Close open gh-aw Copilot HTTP 429 rate-limit failure issues "
            "(dry-run by default)."
        )
    )
    parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER,
        help=f"GitHub owner/org when --repo omits owner (default: {DEFAULT_OWNER}).",
    )
    parser.add_argument(
        "--repo",
        "-r",
        action="append",
        dest="repos",
        help="Repository to scan (`owner/repo` or `repo`, repeatable).",
    )
    parser.add_argument(
        "--all-repos",
        action="store_true",
        help="Scan all DEFAULT_REPOS (default when --repo is omitted).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum open issues to fetch per repository (default: 100).",
    )
    parser.add_argument(
        "--verify-logs",
        action="store_true",
        help="Verify failed Actions logs contain Copilot 429 markers before closing.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually comment and close matching issues (default is dry-run).",
    )
    parser.add_argument(
        "--comment",
        default=DEFAULT_COMMENT,
        help="Comment posted when closing each matching issue.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON instead of a formatted table.",
    )
    return parser.parse_args(argv)


def format_table(rows: List[Dict[str, Any]]) -> str:
    """Format matched issue records as an aligned text table."""
    if not rows:
        return "No matching gh-aw Copilot HTTP 429 issues found."
    header = f"{'REPO':<34} {'ISSUE':<7} {'RUN_ID':<12} {'ACTION':<19} {'TITLE'}"
    lines = [header, "-" * len(header)]
    for row in rows:
        run_id = row["run_id"] or "-"
        lines.append(
            f"{row['repo']:<34} #{row['number']:<6} {run_id:<12} "
            f"{row['action']:<19} {row['title']}"
        )
        if row["error"]:
            lines.append(f"  error: {row['error']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    gh_bin = find_gh()
    repos = resolve_repos(args.owner, None if args.all_repos else args.repos)

    all_rows: List[Dict[str, Any]] = []
    for full_repo in repos:
        all_rows.extend(
            process_repo(
                gh_bin=gh_bin,
                full_repo=full_repo,
                limit=args.limit,
                verify_logs=args.verify_logs,
                apply=args.apply,
                comment=args.comment,
            )
        )

    if args.json_output:
        print(json.dumps(all_rows, indent=2))
    else:
        print(format_table(all_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
