#!/usr/bin/env python3
"""Audit repository documentation for common issues and typos.

This script scans documentation files (*.rst, *.md) and Python docstrings for
common spelling errors and optional custom typo patterns.

Usage:
    python3 scripts/audit_docs.py [--repo-root .] [--source-dir src] [--fix]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_CHECKS: list[tuple[str, re.Pattern[str], str | None]] = [
    (
        "Common typo 'recieve' (should be 'receive')",
        re.compile(r"\brecieve\b", re.IGNORECASE),
        "receive",
    ),
    (
        "Common typo 'occured' (should be 'occurred')",
        re.compile(r"\boccured\b", re.IGNORECASE),
        "occurred",
    ),
    (
        "Common typo 'seperate' (should be 'separate')",
        re.compile(r"\bseperate\b", re.IGNORECASE),
        "separate",
    ),
]

EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        "build",
        "dist",
        ".venv",
        "sphinx_docs_build",
        "node_modules",
    }
)


def collect_files(
    repo_root: Path | None = None,
    source_dirs: list[str] | None = None,
) -> list[Path]:
    """Return all documentation and Python source files to audit."""
    root = (repo_root or Path.cwd()).resolve()
    patterns = [
        "**/*.rst",
        "**/*.md",
        ".github/scripts/*.py",
        "scripts/*.py",
    ]
    for src_dir in source_dirs or []:
        patterns.append(f"{src_dir}/**/*.py")

    this_script = Path(__file__).resolve()
    files: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.resolve() == this_script or not path.is_file():
                continue
            parts = path.parts
            if any(
                p in EXCLUDED_DIR_NAMES
                or p.endswith(".egg-info")
                or p.endswith(".venv")
                for p in parts
            ):
                continue
            files.add(path)
    return sorted(files)


def audit_file(
    path: Path,
    checks: list[tuple[str, re.Pattern[str], str | None]] | None = None,
) -> list[tuple[int, str, str, str | None]]:
    """Audit a single file for documentation issues."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    active_checks = checks if checks is not None else DEFAULT_CHECKS
    issues: list[tuple[int, str, str, str | None]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        for desc, pattern, fix in active_checks:
            if pattern.search(line):
                issues.append((lineno, line.strip(), desc, fix))

    return issues


def fix_file(
    path: Path,
    checks: list[tuple[str, re.Pattern[str], str | None]] | None = None,
) -> int:
    """Attempt in-place fixes for auto-correctable issues in a file."""
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return 0

    active_checks = checks if checks is not None else DEFAULT_CHECKS
    original = content
    for _, pattern, fix in active_checks:
        if fix is not None:
            content = pattern.sub(fix, content)

    if content != original:
        path.write_text(content, encoding="utf-8")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Audit repository documentation for common typos."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory to scan (default: current working directory).",
    )
    parser.add_argument(
        "--source-dir",
        action="append",
        dest="source_dirs",
        default=[],
        help="Python source directory relative to repo root to scan (repeatable).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to auto-fix detected issues in-place.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    files = collect_files(repo_root=repo_root, source_dirs=args.source_dirs)
    total_issues = 0

    for file_path in files:
        issues = audit_file(file_path)
        if issues:
            rel = file_path.relative_to(repo_root)
            print(f"\n{rel}:")
            for lineno, line_text, desc, fix in issues:
                fix_hint = f" (suggested: '{fix}')" if fix else ""
                print(f"  line {lineno}: {desc}{fix_hint}")
                print(f"    {line_text}")
            total_issues += len(issues)

            if args.fix and fix_file(file_path):
                print(f"  [FIXED] Applied auto-fixes to {rel}")

    print("\n" + "=" * 60)
    if total_issues:
        print(
            f"Audit completed: {total_issues} issue(s) detected across documentation."
        )
        return 1 if not args.fix else 0

    print("Audit completed: 0 issues detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
