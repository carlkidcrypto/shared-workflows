#!/usr/bin/env python3
"""Worktree-isolated merge-up from origin/main across open -> main pull requests.

Never runs `gh pr merge` and never mutates primary repository checkouts.
Creates temporary detached worktrees at `<workspace_root>/wt-<repo>-sync-<pr>`,
merges `origin/main`, pushes `HEAD:<headRefName>`, reports conflicts cleanly,
and removes/prunes all created worktrees.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
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


def default_workspace_root() -> Path:
    """Resolve the default workspace root without hardcoding user home paths."""
    env_root = os.environ.get("WORKSPACE_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    macos_default = Path.home() / "Documents" / "GitHub"
    if macos_default.is_dir():
        return macos_default
    wsl_default = Path.home() / "Github"
    if wsl_default.is_dir():
        return wsl_default
    return macos_default


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


def run_cmd(
    cmd: List[str], cwd: Optional[Path] = None
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture output."""
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def sync_pr(
    primary_clone: Path,
    workspace_root: Path,
    repo: str,
    pr: Dict[str, Any],
    dry_run: bool,
    no_push: bool,
) -> Dict[str, Any]:
    """Sync a single PR branch with origin/main inside an isolated worktree."""
    num = pr["number"]
    head = pr["headRefName"]
    result: Dict[str, Any] = {
        "repo": repo,
        "number": num,
        "headRefName": head,
        "status": "unknown",
        "conflicts": [],
        "message": "",
    }

    ancestor_chk = run_cmd(
        [
            "git",
            "-C",
            str(primary_clone),
            "merge-base",
            "--is-ancestor",
            "origin/main",
            f"origin/{head}",
        ]
    )
    if ancestor_chk.returncode == 0:
        result["status"] = "up-to-date"
        return result

    if dry_run:
        result["status"] = "needs-sync"
        return result

    wt_path = workspace_root / f"wt-{repo}-sync-{num}"
    if wt_path.exists():
        result["status"] = "skipped"
        result["message"] = f"Worktree path already exists: {wt_path}"
        return result

    add_res = run_cmd(
        [
            "git",
            "-C",
            str(primary_clone),
            "worktree",
            "add",
            "--detach",
            str(wt_path),
            f"origin/{head}",
        ]
    )
    if add_res.returncode != 0:
        result["status"] = "error"
        result["message"] = add_res.stderr.strip()
        return result

    try:
        merge_res = run_cmd(
            ["git", "merge", "--no-edit", "origin/main"],
            cwd=wt_path,
        )
        if merge_res.returncode != 0:
            conflict_res = run_cmd(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=wt_path,
            )
            conflicts = [
                line.strip()
                for line in conflict_res.stdout.splitlines()
                if line.strip()
            ]
            run_cmd(["git", "merge", "--abort"], cwd=wt_path)
            result["status"] = "conflict"
            result["conflicts"] = conflicts
            result["message"] = merge_res.stderr.strip() or merge_res.stdout.strip()
            return result

        if no_push:
            result["status"] = "merged-local"
            return result

        push_res = run_cmd(
            ["git", "push", "origin", f"HEAD:{head}"],
            cwd=wt_path,
        )
        if push_res.returncode != 0:
            result["status"] = "push-failed"
            result["message"] = push_res.stderr.strip()
            return result

        result["status"] = "synced"
        return result
    finally:
        run_cmd(
            [
                "git",
                "-C",
                str(primary_clone),
                "worktree",
                "remove",
                "--force",
                str(wt_path),
            ]
        )
        run_cmd(["git", "-C", str(primary_clone), "worktree", "prune"])


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Worktree-isolated merge-up from origin/main across open -> main PRs."
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=default_workspace_root(),
        help="Parent directory containing repo clones and wt-* worktrees.",
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
        help="Repository name to sync (repeatable; defaults to all ecosystem repos).",
    )
    parser.add_argument(
        "--pr",
        type=int,
        help="Optional specific PR number (requires single --repo).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which PRs need syncing without creating worktrees or pushing.",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Test merge in isolated worktree without pushing to origin.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit machine-readable JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    args = parse_args(argv)
    if args.pr and (not args.repos or len(args.repos) != 1):
        print("Error: --pr requires specifying exactly one --repo.", file=sys.stderr)
        return 2

    gh_bin = find_gh()
    repos = args.repos if args.repos else DEFAULT_REPOS
    workspace_root = args.workspace_root.expanduser().resolve()
    results: List[Dict[str, Any]] = []

    for repo in repos:
        primary_clone = workspace_root / repo
        if not (primary_clone / ".git").exists():
            print(
                f"Warning: primary clone not found at {primary_clone}, skipping.",
                file=sys.stderr,
            )
            continue

        fetch_res = run_cmd(["git", "-C", str(primary_clone), "fetch", "origin"])
        if fetch_res.returncode != 0:
            print(
                f"Warning: git fetch failed for {repo}: {fetch_res.stderr.strip()}",
                file=sys.stderr,
            )
            continue

        pr_res = run_cmd(
            [
                gh_bin,
                "pr",
                "list",
                "--repo",
                f"{args.owner}/{repo}",
                "--state",
                "open",
                "--limit",
                "50",
                "--json",
                "number,headRefName,baseRefName,isCrossRepository,url",
            ]
        )
        if pr_res.returncode != 0:
            print(
                f"Warning: failed to list PRs for {repo}: {pr_res.stderr.strip()}",
                file=sys.stderr,
            )
            continue

        prs = json.loads(pr_res.stdout or "[]")
        for pr in prs:
            if pr.get("baseRefName") != "main" or pr.get("isCrossRepository"):
                continue
            if args.pr and pr["number"] != args.pr:
                continue
            results.append(
                sync_pr(
                    primary_clone=primary_clone,
                    workspace_root=workspace_root,
                    repo=repo,
                    pr=pr,
                    dry_run=args.dry_run,
                    no_push=args.no_push,
                )
            )

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            line = f"{r['repo']} #{r['number']} ({r['headRefName']}): {r['status']}"
            if r["conflicts"]:
                line += f" | conflicts: {', '.join(r['conflicts'])}"
            if r["message"] and r["status"] in ("error", "push-failed", "skipped"):
                line += f" | {r['message']}"
            print(line)

    has_failures = any(
        r["status"] in ("conflict", "error", "push-failed") for r in results
    )
    return 1 if has_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
