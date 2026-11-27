#!/usr/bin/env python3
"""Extract trailing Valgrind summary lines into a compact stripped log file."""

from __future__ import annotations

import argparse
from pathlib import Path


def strip_valgrind_log(
    input_path: Path,
    output_path: Path,
    tail_lines: int = 5,
) -> str:
    """Read *input_path* and write the last *tail_lines* lines to *output_path*."""
    try:
        lines = input_path.read_text(encoding="utf-8", errors="replace").splitlines(
            keepends=True
        )
        selected = lines[-tail_lines:] if tail_lines > 0 else []
        content = "".join(selected) if selected else "valgrind report empty\n"
    except OSError as exc:
        content = f"valgrind report unavailable: {exc}\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Strip a Valgrind memcheck report down to its trailing summary."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Input Valgrind .out file"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="Output stripped .log file"
    )
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=5,
        help="Number of trailing lines to retain (default: 5)",
    )
    args = parser.parse_args(argv)
    strip_valgrind_log(args.input, args.output, tail_lines=args.tail_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
