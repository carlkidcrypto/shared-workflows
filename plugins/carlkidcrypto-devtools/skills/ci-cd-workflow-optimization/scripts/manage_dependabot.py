#!/usr/bin/env python3
"""Multi-ecosystem .github/dependabot.yml generator and validator.

Detects active package ecosystems in a repository (github-actions, pip, npm,
nuget, gomod) and generates or validates .github/dependabot.yml with standardized
weekly schedules and 'chore(deps)' commit message prefixes.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ECOSYSTEM_PROBES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("github-actions", "/", (".github/workflows",)),
    ("pip", "/", ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg")),
    ("pip", "/sphinx_docs_build", ("sphinx_docs_build/requirements.txt",)),
    (
        "pip",
        "/sphinx_docs_build/landing",
        ("sphinx_docs_build/landing/requirements.txt",),
    ),
    ("npm", "/", ("package.json",)),
    ("npm", "/bindings/javascript", ("bindings/javascript/package.json",)),
    ("npm", "/javascript", ("javascript/package.json",)),
    ("nuget", "/bindings/csharp", ("bindings/csharp",)),
    ("nuget", "/csharp", ("csharp",)),
    ("gomod", "/bindings/go", ("bindings/go/go.mod",)),
    ("gomod", "/go", ("go/go.mod",)),
)


def detect_ecosystems(repo_root: Path) -> list[tuple[str, str]]:
    """Return a list of (package-ecosystem, directory) pairs detected in repo_root."""
    root = repo_root.resolve()
    detected: list[tuple[str, str]] = []
    for ecosystem, directory, markers in ECOSYSTEM_PROBES:
        if ecosystem == "nuget":
            target_dir = root / markers[0]
            if target_dir.is_dir() and list(target_dir.glob("*.csproj")):
                detected.append((ecosystem, directory))
            continue
        if any((root / m).exists() for m in markers):
            detected.append((ecosystem, directory))
    return detected


def render_dependabot_yaml(
    ecosystems: list[tuple[str, str]],
    interval: str = "weekly",
    open_pull_requests_limit: int = 10,
) -> str:
    """Render a canonical .github/dependabot.yml for the given ecosystems."""
    lines = [
        "---",
        "version: 2",
        "updates:",
    ]
    for ecosystem, directory in ecosystems:
        lines.extend(
            [
                f'  - package-ecosystem: "{ecosystem}"',
                f'    directory: "{directory}"',
                "    schedule:",
                f'      interval: "{interval}"',
                f"    open-pull-requests-limit: {open_pull_requests_limit}",
                "    commit-message:",
                '      prefix: "chore(deps)"',
            ]
        )
    return "\n".join(lines) + "\n"


def validate_dependabot_yaml(
    repo_root: Path,
    dependabot_path: Path | None = None,
) -> list[str]:
    """Validate an existing .github/dependabot.yml against detected ecosystems."""
    root = repo_root.resolve()
    cfg_path = dependabot_path or (root / ".github" / "dependabot.yml")
    if not cfg_path.is_file():
        return [f"Missing Dependabot configuration file: {cfg_path}"]

    text = cfg_path.read_text(encoding="utf-8")
    errors: list[str] = []

    if "version: 2" not in text:
        errors.append("Missing 'version: 2' header in dependabot.yml")

    pairs = re.findall(
        r'package-ecosystem:\s*["\']?([a-z\-]+)["\']?\s*\n\s*directory:\s*["\']?(/[^"\'\n]*)["\']?',
        text,
    )
    configured = set(pairs)
    for ecosystem, directory in detect_ecosystems(root):
        if (ecosystem, directory) not in configured:
            errors.append(
                f"Missing Dependabot entry for detected ecosystem '{ecosystem}' at '{directory}'"
            )

    if (
        'prefix: "chore(deps)"' not in text
        and "prefix: 'chore(deps)'" not in text
        and "prefix: chore(deps)" not in text
    ):
        errors.append("Missing standardized commit-message prefix 'chore(deps)'")

    return errors


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Generate or validate multi-ecosystem .github/dependabot.yml."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory (default: current directory).",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate (or overwrite) .github/dependabot.yml for detected ecosystems.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate existing .github/dependabot.yml against detected ecosystems.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional explicit path for generated dependabot.yml.",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    ecosystems = detect_ecosystems(root)

    if args.generate:
        out_path = (
            Path(args.output).resolve()
            if args.output
            else (root / ".github" / "dependabot.yml")
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_dependabot_yaml(ecosystems), encoding="utf-8")
        print(f"Generated {out_path} with {len(ecosystems)} ecosystem entries.")
        return 0

    errors = validate_dependabot_yaml(
        root, Path(args.output).resolve() if args.output else None
    )
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print(
        f"Validated .github/dependabot.yml ({len(ecosystems)} active ecosystems covered)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
