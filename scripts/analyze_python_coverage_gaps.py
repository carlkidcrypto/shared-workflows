#!/usr/bin/env python3
"""Analyze Python source coverage gaps statically against unit tests.

This script inspects Python source files under ``--src`` and test files under
``--tests`` to identify callable functions/methods that lack direct test
references.

Usage:
    python3 scripts/analyze_python_coverage_gaps.py --src src --tests tests
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


def collect_callables(source_path: Path) -> List[str]:
    """Return a sorted list of function/method names defined in source_path."""
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        print(f"  [WARN] SyntaxError in {source_path}: {exc}", file=sys.stderr)
        return []

    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
    return sorted(set(names))


def collect_conditional_markers(source_path: Path) -> List[str]:
    """Identify lines with pragma: no cover."""
    markers: List[str] = []
    for lineno, line in enumerate(
        source_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if "pragma: no cover" in line:
            markers.append(f"line {lineno}: {line.strip()}")
    return markers


def collect_test_references(test_dir: Path) -> Dict[str, Set[str]]:
    """Build a mapping from test filename to set of identifier tokens."""
    refs: Dict[str, Set[str]] = {}
    for test_file in sorted(test_dir.rglob("test_*.py")):
        text = test_file.read_text(encoding="utf-8")
        tokens = set(re.findall(r"[A-Za-z_]\w*", text))
        refs[test_file.name] = tokens
    return refs


def find_uncovered_callables(
    callables: List[str],
    test_refs: Dict[str, Set[str]],
    skip_private: bool = True,
) -> Tuple[List[str], List[str]]:
    """Partition callables into covered/uncovered based on test_refs."""
    all_tokens: Set[str] = set()
    for tokens in test_refs.values():
        all_tokens |= tokens

    covered: List[str] = []
    uncovered: List[str] = []
    for name in callables:
        if skip_private and name.startswith("__") and name.endswith("__"):
            covered.append(name)
            continue
        if name in all_tokens:
            covered.append(name)
        else:
            uncovered.append(name)
    return covered, uncovered


def report_file(
    source_path: Path,
    callables: List[str],
    covered: List[str],
    uncovered: List[str],
    no_cover_markers: List[str],
) -> None:
    """Print formatted gap report for a single source file."""
    total = len(callables)
    cov_count = len(covered)
    unc_count = len(uncovered)
    pct = (cov_count / total * 100) if total > 0 else 100.0

    status = "OK" if unc_count == 0 else "WARN"
    print(f"\n[{status}] {source_path.name} ({cov_count}/{total} - {pct:.0f}%)")

    if uncovered:
        print("  Potentially uncovered callables:")
        for name in uncovered:
            print(f"    - {name}")

    if no_cover_markers:
        print("  Lines with 'pragma: no cover':")
        for marker in no_cover_markers:
            print(f"    {marker}")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Analyze Python source coverage gaps against unit tests."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory (default: current working directory).",
    )
    parser.add_argument(
        "--src",
        required=True,
        help="Path to Python source directory relative to repo root.",
    )
    parser.add_argument(
        "--tests",
        default="tests",
        help="Path to test directory relative to repo root (default: 'tests').",
    )
    parser.add_argument(
        "--no-skip-dunders",
        action="store_true",
        help="Include dunder methods in uncovered checks.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    src_dir = (repo_root / args.src).resolve()
    test_dir = (repo_root / args.tests).resolve()

    if not src_dir.is_dir():
        print(f"ERROR: Source directory not found: {src_dir}", file=sys.stderr)
        return 1
    if not test_dir.is_dir():
        print(f"ERROR: Test directory not found: {test_dir}", file=sys.stderr)
        return 1

    print(f"Source package : {src_dir}")
    print(f"Test directory : {test_dir}")

    test_refs = collect_test_references(test_dir)
    print(f"Test files found: {len(test_refs)}")

    source_files = sorted(src_dir.rglob("*.py"))
    overall_has_gaps = False

    for src_file in source_files:
        callables = collect_callables(src_file)
        no_cover = collect_conditional_markers(src_file)
        covered, uncovered = find_uncovered_callables(
            callables, test_refs, skip_private=not args.no_skip_dunders
        )
        report_file(src_file, callables, covered, uncovered, no_cover)
        if uncovered:
            overall_has_gaps = True

    print("\n" + "=" * 60)
    if overall_has_gaps:
        print("Coverage gaps detected — see report above.")
        return 1

    print("No coverage gaps detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
