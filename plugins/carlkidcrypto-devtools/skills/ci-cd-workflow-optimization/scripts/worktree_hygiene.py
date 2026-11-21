#!/usr/bin/env python3
"""Audit git repositories, primary checkouts, sibling `wt-*` worktrees, and cloud-sync duplicate refs."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def default_workspace_root() -> Path:
    """Return the default GitHub workspace root if present, else cwd."""
    for candidate in (
        Path.home() / "Documents" / "GitHub",
        Path.home() / "Github",
    ):
        if candidate.is_dir():
            return candidate
    return Path.cwd()


def run_git(repo_dir: Path, args: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a git command inside `repo_dir`."""
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        text=True,
        capture_output=True,
    )


def discover_primary_repos(root: Path) -> List[Path]:
    """Find primary git repositories (with a `.git` directory) under `root`."""
    if (root / ".git").is_dir():
        return [root]
    repos: List[Path] = []
    if not root.is_dir():
        return repos
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and (entry / ".git").is_dir():
            repos.append(entry)
    return repos


def detect_default_branch(repo_dir: Path) -> str:
    """Detect the repository's default branch (`main`, `master`, or `origin/HEAD`)."""
    res = run_git(repo_dir, ["symbolic-ref", "refs/remotes/origin/HEAD"])
    if res.returncode == 0 and res.stdout.strip():
        ref = res.stdout.strip()
        if ref.startswith("refs/remotes/origin/"):
            return ref.removeprefix("refs/remotes/origin/")
    for candidate in ("main", "master"):
        chk = run_git(
            repo_dir, ["show-ref", "--verify", "--quiet", f"refs/heads/{candidate}"]
        )
        if chk.returncode == 0:
            return candidate
    return "main"


def get_merged_branches(repo_dir: Path, base_ref: str) -> Set[str]:
    """Return local branch names already merged into `base_ref`."""
    res = run_git(
        repo_dir, ["branch", "--merged", base_ref, "--format=%(refname:short)"]
    )
    if res.returncode != 0:
        return set()
    return {line.strip() for line in res.stdout.splitlines() if line.strip()}


def parse_worktree_list(repo_dir: Path) -> List[Dict[str, Any]]:
    """Parse `git worktree list --porcelain` into structured worktree entries."""
    res = run_git(repo_dir, ["worktree", "list", "--porcelain"])
    if res.returncode != 0:
        return []

    entries: List[Dict[str, Any]] = []
    current: Dict[str, Any] = {}
    for line in res.stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line.removeprefix("worktree ").strip()
        elif line.startswith("HEAD "):
            current["head"] = line.removeprefix("HEAD ").strip()
        elif line.startswith("branch "):
            ref = line.removeprefix("branch ").strip()
            current["branch"] = ref.removeprefix("refs/heads/")
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["detached"] = True
        elif line.startswith("prunable"):
            current["prunable"] = True
            current["prunable_reason"] = line.removeprefix("prunable").strip()
    if current:
        entries.append(current)
    return entries


def find_cloud_sync_refs(repo_dir: Path) -> List[Path]:
    """Find duplicate cloud-sync ref files matching `* (*` inside `.git/refs`."""
    refs_dir = repo_dir / ".git" / "refs"
    if not refs_dir.is_dir():
        return []
    matches: List[Path] = []
    for path in sorted(refs_dir.rglob("* (*")):
        if path.is_file():
            matches.append(path)
    return matches


def inspect_repo(
    repo_dir: Path,
    prune_merged: bool,
    clean_cloud_refs: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    """Inspect a single primary repository for worktree and ref hygiene."""
    default_branch = detect_default_branch(repo_dir)
    branch_res = run_git(repo_dir, ["branch", "--show-current"])
    current_branch = branch_res.stdout.strip() if branch_res.returncode == 0 else ""

    status_res = run_git(repo_dir, ["status", "--porcelain"])
    dirty_lines = [line for line in status_res.stdout.splitlines() if line.strip()]
    is_clean = len(dirty_lines) == 0
    on_default = current_branch == default_branch

    origin_ref = f"origin/{default_branch}"
    base_chk = run_git(repo_dir, ["rev-parse", "--verify", "--quiet", origin_ref])
    merge_target = origin_ref if base_chk.returncode == 0 else default_branch
    merged_branches = get_merged_branches(repo_dir, merge_target)

    raw_worktrees = parse_worktree_list(repo_dir)
    worktrees: List[Dict[str, Any]] = []
    stale_worktrees: List[Dict[str, Any]] = []
    pruned_worktrees: List[str] = []

    repo_resolved = str(repo_dir.resolve())
    for wt in raw_worktrees:
        wt_path = Path(wt["path"])
        is_primary = (
            str(wt_path.resolve()) == repo_resolved if wt_path.exists() else False
        )
        wt_name = wt_path.name
        branch = wt.get("branch", "")
        prunable = bool(wt.get("prunable")) or not wt_path.exists()
        is_merged = bool(
            branch and branch in merged_branches and branch != default_branch
        )
        is_wt_prefix = wt_name.startswith("wt-")

        wt_dirty = False
        if wt_path.exists() and not is_primary:
            wt_status = run_git(wt_path, ["status", "--porcelain"])
            wt_dirty = bool(wt_status.stdout.strip())

        reasons: List[str] = []
        if prunable:
            reasons.append("missing_or_prunable")
        if is_merged:
            reasons.append(f"merged_into_{merge_target}")

        is_stale = (not is_primary) and (is_wt_prefix or prunable) and bool(reasons)
        entry = {
            "path": wt["path"],
            "name": wt_name,
            "branch": branch,
            "is_primary": is_primary,
            "is_wt_prefix": is_wt_prefix,
            "prunable": prunable,
            "merged": is_merged,
            "dirty": wt_dirty,
            "stale": is_stale,
            "stale_reasons": reasons,
        }
        worktrees.append(entry)
        if is_stale:
            stale_worktrees.append(entry)

        if prune_merged and is_stale and not wt_dirty:
            if dry_run:
                pruned_worktrees.append(f"[dry-run] {wt['path']}")
            else:
                if wt_path.exists():
                    rem = run_git(repo_dir, ["worktree", "remove", str(wt_path)])
                    if rem.returncode == 0:
                        pruned_worktrees.append(wt["path"])
                else:
                    pruned_worktrees.append(wt["path"])

    if prune_merged and not dry_run and pruned_worktrees:
        run_git(repo_dir, ["worktree", "prune"])

    cloud_refs = find_cloud_sync_refs(repo_dir)
    cleaned_cloud_refs: List[str] = []
    for ref_path in cloud_refs:
        if clean_cloud_refs:
            if dry_run:
                cleaned_cloud_refs.append(f"[dry-run] {ref_path}")
            else:
                ref_path.unlink(missing_ok=True)
                cleaned_cloud_refs.append(str(ref_path))

    return {
        "repo": str(repo_dir),
        "name": repo_dir.name,
        "default_branch": default_branch,
        "current_branch": current_branch,
        "primary_clean": is_clean,
        "primary_on_default": on_default,
        "primary_ok": is_clean and on_default,
        "dirty_count": len(dirty_lines),
        "worktrees": worktrees,
        "stale_worktrees": stale_worktrees,
        "pruned_worktrees": pruned_worktrees,
        "cloud_sync_refs": [str(p) for p in cloud_refs],
        "cleaned_cloud_refs": cleaned_cloud_refs,
    }


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    default_root = default_workspace_root()
    parser = argparse.ArgumentParser(
        description="Audit primary checkouts, sibling `wt-*` worktrees, and cloud-sync duplicate refs."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root,
        help=f"Workspace root containing git repositories (default: {default_root}).",
    )
    parser.add_argument(
        "--prune-merged",
        action="store_true",
        help="Remove clean stale/merged `wt-*` worktrees and run `git worktree prune`.",
    )
    parser.add_argument(
        "--clean-cloud-refs",
        action="store_true",
        help="Delete `.git/refs` cloud-sync duplicate files matching `* (*`.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview pruning and cleanup actions without modifying the filesystem.",
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
    repos = discover_primary_repos(args.root.expanduser().resolve())
    reports = [
        inspect_repo(
            repo,
            prune_merged=args.prune_merged,
            clean_cloud_refs=args.clean_cloud_refs,
            dry_run=args.dry_run,
        )
        for repo in repos
    ]

    if args.json_output:
        print(json.dumps({"root": str(args.root), "repos": reports}, indent=2))
        return 0

    if not reports:
        print(f"No primary git repositories found under {args.root}.")
        return 0

    for rep in reports:
        status = "OK" if rep["primary_ok"] else "WARN"
        print(
            f"=== {rep['name']} [{status}] branch={rep['current_branch']} "
            f"(default={rep['default_branch']}, dirty={rep['dirty_count']}) ==="
        )
        for wt in rep["worktrees"]:
            marker = " [STALE]" if wt["stale"] else ""
            dirty_note = " [dirty]" if wt["dirty"] else ""
            reasons = (
                f" ({', '.join(wt['stale_reasons'])})" if wt["stale_reasons"] else ""
            )
            print(
                f"  - {wt['path']} [{wt['branch'] or 'detached'}]{marker}{dirty_note}{reasons}"
            )
        if rep["pruned_worktrees"]:
            print(f"  Pruned worktrees: {rep['pruned_worktrees']}")
        if rep["cloud_sync_refs"]:
            print(f"  Cloud-sync refs ({len(rep['cloud_sync_refs'])}):")
            for ref in rep["cloud_sync_refs"]:
                print(f"    ! {ref}")
        if rep["cleaned_cloud_refs"]:
            print(f"  Cleaned cloud-sync refs: {rep['cleaned_cloud_refs']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
