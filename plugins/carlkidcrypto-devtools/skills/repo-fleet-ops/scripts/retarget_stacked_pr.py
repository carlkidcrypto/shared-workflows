#!/usr/bin/env python3
"""Retarget (stack/unstack) a GitHub pull request onto a new base branch.

Handles GitHub's stacked-PR lock ("Cannot change the base branch because the
pull request is part of a stack") by automatically detecting `.stack.number`
and calling ``POST /repos/{owner}/{repo}/stacks/{stack_number}/unstack`` before
running ``gh pr edit --base <target>``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


def _run_gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        text=True,
        capture_output=True,
        check=check,
    )


def get_pr_stack_info(repo: str, pr_number: int) -> dict[str, Any]:
    """Return PR metadata including its ``stack`` object (if any)."""
    proc = _run_gh(["api", f"repos/{repo}/pulls/{pr_number}"])
    return json.loads(proc.stdout)


def unstack_pr(repo: str, stack_number: int) -> dict[str, Any]:
    """Unstack a GitHub PR stack via REST API."""
    proc = _run_gh(["api", "-X", "POST", f"repos/{repo}/stacks/{stack_number}/unstack"])
    return json.loads(proc.stdout)


def retarget_pr(
    repo: str,
    pr_number: int,
    new_base: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Unstack *pr_number* if needed and retarget its base branch to *new_base*."""
    pr_info = get_pr_stack_info(repo, pr_number)
    current_base = (pr_info.get("base") or {}).get("ref", "")
    stack = pr_info.get("stack")
    stack_number = stack.get("number") if isinstance(stack, dict) else None

    result: dict[str, Any] = {
        "repo": repo,
        "pr_number": pr_number,
        "previous_base": current_base,
        "new_base": new_base,
        "unstacked_stack_number": stack_number,
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    if stack_number is not None:
        unstack_pr(repo, int(stack_number))

    _run_gh(["pr", "edit", str(pr_number), "--repo", repo, "--base", new_base])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Retarget a GitHub pull request to a new base branch, automatically "
            "unstacking stale GitHub PR stacks when required."
        )
    )
    parser.add_argument("--repo", required=True, help="GitHub repository (owner/repo)")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    parser.add_argument("--base", required=True, help="Target base branch name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect stack state without modifying the pull request",
    )
    args = parser.parse_args(argv)

    result = retarget_pr(args.repo, args.pr, args.base, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
