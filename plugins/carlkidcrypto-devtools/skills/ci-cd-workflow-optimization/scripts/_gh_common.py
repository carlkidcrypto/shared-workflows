#!/usr/bin/env python3
"""Shared GitHub CLI helpers and repository constants for devtools scripts."""

import argparse
import json
import os
import shutil
import subprocess
from typing import Any, List, Optional, Tuple

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

STANDARD_BIN_DIRS = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
)


def find_tool(name: str, extra_candidates: Tuple[Optional[str], ...] = ()) -> str:
    """Locate an executable in PATH or standard Homebrew/local bin directories."""
    candidates = [
        *extra_candidates,
        shutil.which(name),
        *(f"{bin_dir}/{name}" for bin_dir in STANDARD_BIN_DIRS),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        f"Executable `{name}` not found in PATH or standard locations"
    )


def find_gh() -> str:
    """Locate the GitHub CLI executable even when Homebrew/local bins are not in PATH."""
    try:
        return find_tool("gh", extra_candidates=(os.environ.get("GH_BIN"),))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "GitHub CLI (`gh`) not found in PATH or standard locations"
        ) from exc


def run_gh(
    gh_bin: str,
    args: List[str],
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a `gh` subcommand and return the completed process."""
    res = subprocess.run([gh_bin, *args], text=True, capture_output=True)
    if check and res.returncode != 0:
        raise RuntimeError(
            f"`gh {' '.join(args)}` failed (exit {res.returncode}): {res.stderr.strip()}"
        )
    return res


def run_gh_json(gh_bin: str, args: List[str]) -> Any:
    """Run a `gh` subcommand and parse its JSON stdout."""
    res = run_gh(gh_bin, args, check=True)
    stdout = res.stdout.strip()
    if not stdout:
        return None
    return json.loads(stdout)


def resolve_repo(repo: Optional[str], owner: str = DEFAULT_OWNER) -> str:
    """Normalize a repository argument into `owner/repo` format."""
    if not repo:
        raise ValueError("Repository name is required")
    if "/" in repo:
        return repo
    return f"{owner}/{repo}"


def split_repo(full_repo: str, default_owner: str = DEFAULT_OWNER) -> Tuple[str, str]:
    """Split `owner/repo` (or bare `repo`) into `(owner, repo)`."""
    if "/" in full_repo:
        owner, repo = full_repo.split("/", 1)
        return owner, repo
    return default_owner, full_repo


def infer_current_repo(gh_bin: str) -> Optional[str]:
    """Infer `owner/repo` from the current working directory via `gh repo view`."""
    res = run_gh(
        gh_bin,
        ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return None


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for quick inspection of shared constants."""
    parser = argparse.ArgumentParser(
        description="Shared GitHub CLI helpers and default repository list."
    )
    parser.parse_args(argv)
    print(f"DEFAULT_OWNER: {DEFAULT_OWNER}")
    print("DEFAULT_REPOS:")
    for repo in DEFAULT_REPOS:
        print(f"  - {repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
