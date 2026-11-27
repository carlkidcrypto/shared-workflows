#!/usr/bin/env python3
"""Propagate the 40-char carlkidcrypto/shared-workflows SHA across consumer repos.

Resolves the 40-char commit SHA via `git rev-parse` (or `gh api` fallback),
scans `.github/workflows/*.yml`, `.github/actions/*/action.yml`, and
`.github/workflows/*.md`, and optionally applies + commits updates inside
isolated worktrees (`<workspace_root>/wt-<repo>-bump-sha`).
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_OWNER = "carlkidcrypto"
DEFAULT_CONSUMER_REPOS = [
    "ezsnmp",
    "ezsnmp_data_logger",
    "purpleair_api",
    "purpleair_data_logger",
    "purpleair-matterbridge",
    "carlkidcrypto.github.io",
    "os-specific-runner",
]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PIN_RE = re.compile(
    r"(carlkidcrypto/shared-workflows(?:/[^\s@'\"]+)?@)([0-9a-f]{7,40})"
)


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


def run_cmd(
    cmd: List[str], cwd: Optional[Path] = None
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture output."""
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def clean_cloud_sync_refs(repo_dir: Path) -> List[str]:
    """Delete cloud-sync duplicate ref files (e.g., 'main (1)') under .git/refs."""
    git_dir = repo_dir / ".git"
    if not git_dir.is_dir():
        return []
    refs_dir = git_dir / "refs"
    if not refs_dir.is_dir():
        return []
    removed: List[str] = []
    for path in sorted(refs_dir.rglob("* (*")):
        if path.is_file():
            rel = str(path.relative_to(repo_dir))
            path.unlink()
            removed.append(rel)
    return removed


def resolve_target_sha(
    shared_dir: Path, ref: str, owner: str, explicit_sha: Optional[str]
) -> str:
    """Resolve and validate the 40-char SHA of carlkidcrypto/shared-workflows."""
    if explicit_sha:
        sha = explicit_sha.strip().lower()
        if not SHA_RE.match(sha):
            raise ValueError(f"Invalid 40-char SHA: {explicit_sha}")
        return sha

    if (shared_dir / ".git").exists():
        clean_cloud_sync_refs(shared_dir)
        run_cmd(["git", "-C", str(shared_dir), "fetch", "origin"])
        res = run_cmd(["git", "-C", str(shared_dir), "rev-parse", ref])
        if res.returncode == 0:
            sha = res.stdout.strip().lower()
            if SHA_RE.match(sha):
                return sha

    gh_bin = shutil.which("gh") or "/opt/homebrew/bin/gh"
    api_ref = ref.removeprefix("origin/")
    res = run_cmd(
        [
            gh_bin,
            "api",
            f"repos/{owner}/shared-workflows/git/ref/heads/{api_ref}",
            "--jq",
            ".object.sha",
        ]
    )
    if res.returncode == 0:
        sha = res.stdout.strip().lower()
        if SHA_RE.match(sha):
            return sha

    raise RuntimeError(
        f"Unable to resolve 40-char SHA for {owner}/shared-workflows@{ref}"
    )


def _is_target_rel_path(rel_path: str) -> bool:
    """Return True if a repository-relative path is a workflow, action, or gh-aw file."""
    parts = Path(rel_path).parts
    if len(parts) == 3 and parts[0] == ".github" and parts[1] == "workflows":
        return parts[2].endswith((".yml", ".yaml", ".md"))
    if len(parts) == 4 and parts[0] == ".github" and parts[1] == "actions":
        return parts[3] in ("action.yml", "action.yaml")
    return False


def iter_target_files(repo_root: Path) -> List[Path]:
    """Return workflow YAML, composite action YAML, and gh-aw MD files."""
    files: List[Path] = []
    workflows_dir = repo_root / ".github" / "workflows"
    if workflows_dir.is_dir():
        for ext in ("*.yml", "*.yaml", "*.md"):
            files.extend(sorted(workflows_dir.glob(ext)))
    actions_dir = repo_root / ".github" / "actions"
    if actions_dir.is_dir():
        for ext in ("action.yml", "action.yaml"):
            files.extend(sorted(actions_dir.glob(f"*/{ext}")))
    return files


def iter_git_ref_target_files(
    repo_root: Path, git_ref: str = "origin/main"
) -> List[str]:
    """List workflow, action, and gh-aw files present in a git ref (e.g. origin/main)."""
    res = run_cmd(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-tree",
            "-r",
            "--name-only",
            git_ref,
            "--",
            ".github/workflows",
            ".github/actions",
        ]
    )
    if res.returncode != 0:
        return []
    return sorted(
        line.strip()
        for line in res.stdout.splitlines()
        if line.strip() and _is_target_rel_path(line.strip())
    )


def count_text_pins(original: str, target_sha: str) -> Tuple[int, int, str]:
    """Count stale and total shared-workflows SHA pins in text and return updated text."""
    changes = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal changes
        prefix, old_sha = match.group(1), match.group(2)
        if old_sha.lower() != target_sha:
            changes += 1
            return f"{prefix}{target_sha}"
        return match.group(0)

    updated = PIN_RE.sub(_replace, original)
    return changes, len(PIN_RE.findall(original)), updated


def update_file_pins(path: Path, target_sha: str, write: bool) -> Tuple[int, int]:
    """Count or replace shared-workflows SHA pins in a single file."""
    original = path.read_text(encoding="utf-8")
    changes, total, updated = count_text_pins(original, target_sha)
    if write and changes > 0:
        path.write_text(updated, encoding="utf-8")
    return changes, total


def prune_old_aw_imports(
    repo_root: Path,
    target_sha: str,
    owner: str = DEFAULT_OWNER,
    dry_run: bool = False,
) -> List[str]:
    """Find or remove superseded .github/aw/imports/<owner>/shared-workflows/<old-sha>/ dirs."""
    imports_base = repo_root / ".github" / "aw" / "imports" / owner / "shared-workflows"
    if not imports_base.is_dir():
        return []
    pruned: List[str] = []
    for child in sorted(imports_base.iterdir()):
        if not child.is_dir():
            continue
        name_lower = child.name.lower()
        if SHA_RE.match(name_lower) and name_lower != target_sha.lower():
            rel = str(child.relative_to(repo_root))
            if not dry_run:
                shutil.rmtree(child)
            pruned.append(rel)
    return pruned


def list_git_ref_stale_aw_imports(
    repo_root: Path,
    target_sha: str,
    git_ref: str = "origin/main",
    owner: str = DEFAULT_OWNER,
) -> List[str]:
    """List superseded .github/aw/imports/<owner>/shared-workflows/<old-sha> dirs on a git ref."""
    prefix = f".github/aw/imports/{owner}/shared-workflows/"
    res = run_cmd(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-tree",
            "--name-only",
            git_ref,
            prefix,
        ]
    )
    if res.returncode != 0:
        return []
    stale: List[str] = []
    for line in sorted(res.stdout.splitlines()):
        rel = line.strip().rstrip("/")
        if not rel.startswith(prefix):
            continue
        sha_dir = rel[len(prefix) :].split("/", 1)[0]
        if SHA_RE.match(sha_dir.lower()) and sha_dir.lower() != target_sha.lower():
            stale.append(rel)
    return stale


def process_repo(
    primary_clone: Path,
    workspace_root: Path,
    repo: str,
    target_sha: str,
    branch: str,
    apply: bool,
    commit: bool,
    owner: str = DEFAULT_OWNER,
    compile_gh_aw: bool = False,
    prune_old_imports: bool = False,
    fetch: bool = True,
) -> Dict[str, Any]:
    """Scan or update a single consumer repository."""
    record: Dict[str, Any] = {
        "repo": repo,
        "target_sha": target_sha,
        "worktree": "",
        "commit_sha": "",
        "changed_files": [],
        "pruned_aw_imports": [],
        "cleaned_refs": [],
        "total_pins": 0,
        "status": "clean",
    }

    cleaned = clean_cloud_sync_refs(primary_clone)
    if cleaned:
        record["cleaned_refs"] = cleaned

    if not apply:
        if fetch:
            run_cmd(["git", "-C", str(primary_clone), "fetch", "origin", "main"])
        has_origin_main = (
            run_cmd(
                [
                    "git",
                    "-C",
                    str(primary_clone),
                    "rev-parse",
                    "--verify",
                    "origin/main",
                ]
            ).returncode
            == 0
        )
        if has_origin_main:
            for rel_path in iter_git_ref_target_files(primary_clone, "origin/main"):
                show_res = run_cmd(
                    [
                        "git",
                        "-C",
                        str(primary_clone),
                        "show",
                        f"origin/main:{rel_path}",
                    ]
                )
                if show_res.returncode != 0:
                    continue
                changes, pins, _ = count_text_pins(show_res.stdout, target_sha)
                record["total_pins"] += pins
                if changes > 0:
                    record["changed_files"].append(
                        {"file": rel_path, "updates": changes}
                    )
            if prune_old_imports:
                record["pruned_aw_imports"] = list_git_ref_stale_aw_imports(
                    primary_clone, target_sha, git_ref="origin/main", owner=owner
                )
        else:
            for fpath in iter_target_files(primary_clone):
                changes, pins = update_file_pins(fpath, target_sha, write=False)
                record["total_pins"] += pins
                if changes > 0:
                    record["changed_files"].append(
                        {
                            "file": str(fpath.relative_to(primary_clone)),
                            "updates": changes,
                        }
                    )
            if prune_old_imports:
                record["pruned_aw_imports"] = prune_old_aw_imports(
                    primary_clone, target_sha, owner=owner, dry_run=True
                )

        if record["changed_files"] or record["pruned_aw_imports"]:
            record["status"] = "needs-bump"
        return record

    wt_path = workspace_root / f"wt-{repo}-bump-sha"
    if wt_path.exists():
        record["status"] = "error"
        record["error"] = f"Worktree already exists: {wt_path}"
        return record

    if fetch:
        run_cmd(["git", "-C", str(primary_clone), "fetch", "origin"])
    add_res = run_cmd(
        [
            "git",
            "-C",
            str(primary_clone),
            "worktree",
            "add",
            "-b",
            branch,
            str(wt_path),
            "origin/main",
        ]
    )
    if add_res.returncode != 0:
        record["status"] = "error"
        record["error"] = add_res.stderr.strip()
        return record

    record["worktree"] = str(wt_path)
    touched: List[str] = []
    md_touched = False
    for fpath in iter_target_files(wt_path):
        changes, pins = update_file_pins(fpath, target_sha, write=True)
        record["total_pins"] += pins
        if changes > 0:
            rel = str(fpath.relative_to(wt_path))
            touched.append(rel)
            if rel.endswith(".md"):
                md_touched = True
            record["changed_files"].append({"file": rel, "updates": changes})

    pruned: List[str] = []
    if prune_old_imports:
        pruned = prune_old_aw_imports(wt_path, target_sha, owner=owner, dry_run=False)
        record["pruned_aw_imports"] = pruned

    if compile_gh_aw and (md_touched or pruned):
        gh_bin = shutil.which("gh") or "/opt/homebrew/bin/gh"
        compile_res = run_cmd([gh_bin, "aw", "compile", "--validate"], cwd=wt_path)
        if compile_res.returncode != 0:
            record["status"] = "error"
            record["error"] = compile_res.stderr.strip() or compile_res.stdout.strip()
            return record
        status_res = run_cmd(
            ["git", "status", "--porcelain", ".github/workflows", ".github/aw"],
            cwd=wt_path,
        )
        for line in status_res.stdout.splitlines():
            if len(line) > 3:
                rel = line[3:].strip().strip('"')
                if rel and rel not in touched and rel not in pruned:
                    touched.append(rel)

    if not touched and not pruned:
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
        record["worktree"] = ""
        record["status"] = "clean"
        return record

    record["status"] = "updated"
    if commit:
        if touched:
            run_cmd(["git", "add", "--", *touched], cwd=wt_path)
        if pruned:
            run_cmd(["git", "add", "-u", "--", *pruned], cwd=wt_path)
        commit_res = run_cmd(
            [
                "git",
                "commit",
                "-m",
                f"chore(ci): bump carlkidcrypto/shared-workflows to {target_sha[:12]}",
            ],
            cwd=wt_path,
        )
        if commit_res.returncode != 0:
            record["status"] = "error"
            record["error"] = commit_res.stderr.strip()
            return record
        rev_res = run_cmd(["git", "rev-parse", "HEAD"], cwd=wt_path)
        record["commit_sha"] = rev_res.stdout.strip()
        record["status"] = "committed"

    return record


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Resolve carlkidcrypto/shared-workflows 40-char SHA and bump consumer pins."
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=default_workspace_root(),
        help="Parent directory containing repo clones and wt-* worktrees.",
    )
    parser.add_argument(
        "--shared-workflows-dir",
        type=Path,
        help="Path to local shared-workflows clone (default: <workspace_root>/shared-workflows).",
    )
    parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER,
        help=f"GitHub owner/org (default: {DEFAULT_OWNER})",
    )
    parser.add_argument(
        "--ref",
        default="origin/main",
        help="Git ref in shared-workflows to resolve (default: origin/main).",
    )
    parser.add_argument(
        "--sha",
        help="Explicit 40-char SHA to apply instead of resolving from git/API.",
    )
    parser.add_argument(
        "--repo",
        "-r",
        action="append",
        dest="repos",
        help="Consumer repository name (repeatable; defaults to all consumer repos).",
    )
    parser.add_argument(
        "--branch",
        default="chore/bump-shared-workflows-sha",
        help="Branch name to create in isolated worktrees when --apply is set.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create isolated worktrees and apply SHA updates (default is dry-run).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly scan without creating worktrees or modifying files.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit updated files inside each isolated worktree (requires --apply).",
    )
    parser.add_argument(
        "--compile-gh-aw",
        action="store_true",
        help="Run 'gh aw compile --validate' when .github/workflows/*.md files change (requires --apply).",
    )
    parser.add_argument(
        "--prune-old-aw-imports",
        action="store_true",
        help="Remove superseded .github/aw/imports/<owner>/shared-workflows/<old-sha>/ directories.",
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
    workspace_root = args.workspace_root.expanduser().resolve()
    shared_dir = (
        args.shared_workflows_dir.expanduser().resolve()
        if args.shared_workflows_dir
        else workspace_root / "shared-workflows"
    )
    apply = args.apply and not args.dry_run
    target_sha = resolve_target_sha(shared_dir, args.ref, args.owner, args.sha)
    repos = args.repos if args.repos else DEFAULT_CONSUMER_REPOS

    results: List[Dict[str, Any]] = []
    for repo in repos:
        primary_clone = workspace_root / repo
        if not (primary_clone / ".git").exists():
            print(
                f"Warning: primary clone not found at {primary_clone}, skipping.",
                file=sys.stderr,
            )
            continue
        results.append(
            process_repo(
                primary_clone=primary_clone,
                workspace_root=workspace_root,
                repo=repo,
                target_sha=target_sha,
                branch=args.branch,
                apply=apply,
                commit=args.commit,
                owner=args.owner,
                compile_gh_aw=args.compile_gh_aw,
                prune_old_imports=args.prune_old_aw_imports,
            )
        )

    if args.json_output:
        print(json.dumps({"target_sha": target_sha, "repos": results}, indent=2))
    else:
        print(f"Target SHA: {target_sha}")
        for r in results:
            line = f"{r['repo']}: {r['status']} ({len(r['changed_files'])} files)"
            if r.get("pruned_aw_imports"):
                line += f" ({len(r['pruned_aw_imports'])} stale aw imports)"
            if r.get("commit_sha"):
                line += f" @ {r['commit_sha'][:12]}"
            if r.get("worktree"):
                line += f" [{r['worktree']}]"
            print(line)
            for f in r["changed_files"]:
                print(f"  - {f['file']} ({f['updates']} pins)")
            for pruned in r.get("pruned_aw_imports", []):
                print(f"  - prune: {pruned}")

    has_errors = any(r["status"] == "error" for r in results)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
