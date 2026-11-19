#!/usr/bin/env python3
"""Validate GitHub Actions YAML workflows and gh-aw Markdown agentic workflows.

Discovers `.github/workflows/*.yml` (and `.yaml`) plus `.md` agentic workflows
(or explicitly specified files), runs `yamllint` and `actionlint` if installed,
and optionally runs `gh aw compile --validate` when `.md` workflow files exist
or are passed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def find_executable(name: str) -> Optional[str]:
    """Locate an executable in PATH or standard Homebrew/local locations."""
    for candidate in (
        shutil.which(name),
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def discover_workflows(
    repo_dir: Path, files: Optional[List[str]]
) -> Tuple[List[Path], List[Path]]:
    """Return (yaml_files, md_files) to validate."""
    yaml_files: List[Path] = []
    md_files: List[Path] = []

    if files:
        candidates = [
            (Path(f) if Path(f).is_absolute() else (repo_dir / f)).resolve()
            for f in files
        ]
    else:
        wf_dir = repo_dir / ".github" / "workflows"
        if not wf_dir.is_dir():
            return [], []
        candidates = sorted(wf_dir.iterdir())

    for path in candidates:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in {".yml", ".yaml"}:
            yaml_files.append(path)
        elif suffix == ".md":
            md_files.append(path)

    return yaml_files, md_files


def run_tool(cmd: List[str], cwd: Path) -> Dict[str, Any]:
    """Execute a validation command and capture its structured result."""
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "status": "passed" if proc.returncode == 0 else "failed",
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def validate_workflows(
    repo_dir: Path,
    files: Optional[List[str]] = None,
    compile_gh_aw: bool = False,
) -> Dict[str, Any]:
    """Run available linters and optional gh-aw validation on discovered workflows."""
    yaml_files, md_files = discover_workflows(repo_dir, files)
    results: Dict[str, Any] = {
        "repo_dir": str(repo_dir),
        "yaml_files": [str(p) for p in yaml_files],
        "md_files": [str(p) for p in md_files],
        "checks": {},
        "ok": True,
    }

    if yaml_files:
        yaml_args = [str(p) for p in yaml_files]

        yamllint_bin = find_executable("yamllint")
        if yamllint_bin:
            res = run_tool([yamllint_bin, "-f", "parsable", *yaml_args], repo_dir)
            results["checks"]["yamllint"] = res
            if res["returncode"] != 0:
                results["ok"] = False
        else:
            results["checks"]["yamllint"] = {
                "status": "skipped",
                "reason": "yamllint not installed",
            }

        actionlint_bin = find_executable("actionlint")
        if actionlint_bin:
            res = run_tool([actionlint_bin, *yaml_args], repo_dir)
            results["checks"]["actionlint"] = res
            if res["returncode"] != 0:
                results["ok"] = False
        else:
            results["checks"]["actionlint"] = {
                "status": "skipped",
                "reason": "actionlint not installed",
            }
    else:
        results["checks"]["yamllint"] = {
            "status": "skipped",
            "reason": "no YAML workflow files found",
        }
        results["checks"]["actionlint"] = {
            "status": "skipped",
            "reason": "no YAML workflow files found",
        }

    if compile_gh_aw:
        if not md_files:
            results["checks"]["gh_aw_compile"] = {
                "status": "skipped",
                "reason": "no .md agentic workflow files found",
            }
        else:
            gh_bin = find_executable("gh")
            if not gh_bin:
                results["checks"]["gh_aw_compile"] = {
                    "status": "skipped",
                    "reason": "gh CLI not installed",
                }
            else:
                res = run_tool([gh_bin, "aw", "compile", "--validate"], repo_dir)
                results["checks"]["gh_aw_compile"] = res
                if res["returncode"] != 0:
                    results["ok"] = False

    return results


def print_human_report(report: Dict[str, Any]) -> None:
    """Print a concise human-readable validation report."""
    print(f"Repository: {report['repo_dir']}")
    print(
        f"Discovered: {len(report['yaml_files'])} YAML workflow(s), "
        f"{len(report['md_files'])} Markdown workflow(s)"
    )

    for tool_name, info in report["checks"].items():
        status = info.get("status", "unknown").upper()
        reason = info.get("reason")
        suffix = f" ({reason})" if reason else ""
        print(f"- {tool_name}: {status}{suffix}")
        if info.get("stdout"):
            for line in info["stdout"].splitlines():
                print(f"    {line}")
        if info.get("stderr"):
            for line in info["stderr"].splitlines():
                print(f"    [stderr] {line}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Discover and validate .github/workflows/*.yml and .md agentic "
            "workflows using yamllint, actionlint, and optionally gh aw compile --validate."
        )
    )
    parser.add_argument(
        "--repo-dir",
        default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        action="extend",
        help="Specific workflow file(s) to validate instead of auto-discovery.",
    )
    parser.add_argument(
        "--compile-gh-aw",
        action="store_true",
        help="Run `gh aw compile --validate` when .md workflow files exist or are passed.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output validation results as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    repo_dir = Path(args.repo_dir).resolve()
    if not repo_dir.is_dir():
        print(f"Error: repo directory does not exist: {repo_dir}", file=sys.stderr)
        return 2

    report = validate_workflows(
        repo_dir=repo_dir,
        files=args.files,
        compile_gh_aw=args.compile_gh_aw,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human_report(report)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
