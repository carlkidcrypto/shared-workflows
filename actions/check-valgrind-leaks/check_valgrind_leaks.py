#!/usr/bin/env python3
"""Scan Valgrind memcheck logs for native C/C++ library memory leaks."""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

DEFAULT_IGNORE_MARKERS: tuple[str, ...] = (
    "PyInit_",
    "SWIG_mod_exec",
)

_BLOCK_SPLIT_RE = re.compile(r"\n==\d+==\s*\n")
_LOST_RE = re.compile(r"bytes in \d+ blocks are (?:definitely|indirectly) lost")


def parse_marker_list(raw_values: list[str] | None) -> tuple[str, ...]:
    """Split comma- or newline-separated marker arguments into a clean tuple."""
    if not raw_values:
        return ()
    parsed: list[str] = []
    for raw in raw_values:
        for item in re.split(r"[\n,]+", raw):
            stripped = item.strip()
            if stripped and stripped not in parsed:
                parsed.append(stripped)
    return tuple(parsed)


def find_native_leaks(
    log_text: str,
    markers: tuple[str, ...],
    ignore_markers: tuple[str, ...] = DEFAULT_IGNORE_MARKERS,
) -> list[str]:
    """Return all Valgrind record blocks matching *markers* (excluding *ignore_markers*)."""
    leaked_blocks: list[str] = []
    for block in _BLOCK_SPLIT_RE.split(log_text):
        if not _LOST_RE.search(block):
            continue
        if any(ignored in block for ignored in ignore_markers):
            continue
        if not markers or any(marker in block for marker in markers):
            leaked_blocks.append(block.strip())
    return leaked_blocks


def check_valgrind_log_files(
    patterns: list[str],
    markers: tuple[str, ...],
    ignore_markers: tuple[str, ...] = DEFAULT_IGNORE_MARKERS,
    label: str = "native",
) -> int:
    """Validate one or more Valgrind log file paths/globs and return an exit code."""
    matched_files: list[Path] = []
    for pattern in patterns:
        expanded = sorted(Path(p) for p in glob.glob(pattern, recursive=True))
        if expanded:
            matched_files.extend(p for p in expanded if p.is_file())
        else:
            candidate = Path(pattern)
            if candidate.is_file():
                matched_files.append(candidate)

    # Deduplicate while preserving order
    unique_files = list(dict.fromkeys(matched_files))

    if not unique_files:
        print(
            f"ERROR: No Valgrind log files matched: {patterns}",
            file=sys.stderr,
        )
        return 1

    all_leaks: list[tuple[Path, str]] = []
    for log_path in unique_files:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for block in find_native_leaks(
            text, markers=markers, ignore_markers=ignore_markers
        ):
            all_leaks.append((log_path, block))

    if all_leaks:
        print(
            f"ERROR: Valgrind detected {len(all_leaks)} {label} memory leak block(s):",
            file=sys.stderr,
        )
        for log_path, block in all_leaks[:10]:
            print(f"[{log_path}]\n{block}\n---", file=sys.stderr)
        return 1

    print(
        f"Valgrind {label} leak check: PASS "
        f"(0 matching leak blocks across {len(unique_files)} file(s))"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail if Valgrind memcheck logs contain native memory leaks."
    )
    parser.add_argument(
        "logs",
        nargs="*",
        default=["valgrind_*.out"],
        help="Valgrind log file paths or glob patterns (default: valgrind_*.out)",
    )
    parser.add_argument(
        "--marker",
        action="append",
        dest="markers",
        default=[],
        help="Symbol/library substring to match (repeatable, or comma/newline-separated).",
    )
    parser.add_argument(
        "--ignore-marker",
        action="append",
        dest="ignore_markers",
        default=[],
        help="Symbol substring to exclude (defaults to PyInit_,SWIG_mod_exec).",
    )
    parser.add_argument(
        "--label",
        default="native",
        help="Human-readable label for log output (default: native).",
    )
    args = parser.parse_args(argv)
    markers = parse_marker_list(args.markers)
    ignore_markers = (
        parse_marker_list(args.ignore_markers)
        if args.ignore_markers
        else DEFAULT_IGNORE_MARKERS
    )
    return check_valgrind_log_files(
        patterns=list(args.logs),
        markers=markers,
        ignore_markers=ignore_markers,
        label=args.label,
    )


if __name__ == "__main__":
    raise SystemExit(main())
