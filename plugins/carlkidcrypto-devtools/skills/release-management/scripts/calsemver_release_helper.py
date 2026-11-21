#!/usr/bin/env python3
"""Shared CalSemVer, Sphinx virtualenv discovery, and git preflight helper for release tooling.

Centralizes version normalization across PEP 440 (Python/Meson), SemVer 2.0.0
(npm/NuGet/WinGet), and Sphinx documentation tags, plus Sphinx virtualenv
discovery (python3.14.venv, python3.13.venv, .venv) and external specification
collision protection.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

CALSEMVER_RE = re.compile(
    r"^(?P<year>20\d{2})\.(?P<month>[1-9]|1[0-2])\.(?P<day>[1-9]|[12]\d|3[01])"
    r"(?:(?P<pep_kind>a|b|rc)(?P<pep_num>\d+)|-(?P<sem_kind>alpha|beta|rc)\.(?P<sem_num>\d+))?$"
)

EXTERNAL_SPEC_EXCLUSIONS: tuple[str, ...] = (
    "matter-1.5.1",
    "Matter 1.5.1",
    "third_party/",
)

SPHINX_VENV_CANDIDATES: tuple[str, ...] = (
    "python3.14.venv",
    "python3.13.venv",
    "python3.12.venv",
    ".venv",
)


@dataclass(frozen=True)
class CalSemVerForms:
    """Multi-language manifest representations for a CalSemVer release."""

    base_version: str
    pep440: str
    semver: str
    git_tag: str
    sphinx_release: str
    is_prerelease: bool


def parse_calsemver(version_str: str) -> CalSemVerForms:
    """Parse a CalSemVer string (PEP 440 or SemVer 2.0.0) into all ecosystem forms."""
    cleaned = version_str.strip().lstrip("vV")
    match = CALSEMVER_RE.fullmatch(cleaned)
    if not match:
        raise ValueError(
            f"Invalid CalSemVer '{version_str}': expected YYYY.M.D[aN|-alpha.N] without leading zeros."
        )

    base = f"{match.group('year')}.{match.group('month')}.{match.group('day')}"
    pep_kind = match.group("pep_kind")
    sem_kind = match.group("sem_kind")

    if not pep_kind and not sem_kind:
        return CalSemVerForms(
            base_version=base,
            pep440=base,
            semver=base,
            git_tag=f"v{base}",
            sphinx_release=f"v{base}",
            is_prerelease=False,
        )

    kind_map = {
        "a": ("a", "alpha"),
        "b": ("b", "beta"),
        "rc": ("rc", "rc"),
        "alpha": ("a", "alpha"),
        "beta": ("b", "beta"),
    }
    raw_kind = pep_kind or sem_kind or ""
    num = match.group("pep_num") or match.group("sem_num") or "0"
    pep_tag, sem_tag = kind_map[raw_kind]
    pep440 = f"{base}{pep_tag}{num}"
    semver = f"{base}-{sem_tag}.{num}"
    return CalSemVerForms(
        base_version=base,
        pep440=pep440,
        semver=semver,
        git_tag=f"v{pep440}",
        sphinx_release=f"v{pep440}",
        is_prerelease=True,
    )


def today_calsemver(
    prerelease: str = "",
    today: dt.date | None = None,
) -> CalSemVerForms:
    """Return CalSemVer forms for today's date (or given date) and optional prerelease suffix."""
    d = today or dt.date.today()
    base = f"{d.year}.{d.month}.{d.day}"
    suffix = prerelease.strip()
    return parse_calsemver(f"{base}{suffix}" if suffix else base)


def discover_sphinx_venv(repo_root: Path | None = None) -> Path | None:
    """Discover the preferred local Sphinx virtualenv directory."""
    root = (repo_root or Path.cwd()).resolve()
    candidates = [root / name for name in SPHINX_VENV_CANDIDATES]
    shared_wsl_venv = Path.home() / "Github" / "ezsnmp" / "python3.12.venv"
    candidates.append(shared_wsl_venv)
    for candidate in candidates:
        if (candidate / "bin" / "sphinx-build").is_file() or (
            candidate / "bin" / "python"
        ).is_file():
            return candidate
    return None


def is_excluded_from_version_bump(rel_path: str) -> bool:
    """Return True if a path belongs to third-party or external specification files."""
    norm = rel_path.replace("\\", "/")
    return any(excl in norm for excl in EXTERNAL_SPEC_EXCLUSIONS)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Shared CalSemVer and Sphinx virtualenv release helper."
    )
    parser.add_argument(
        "--version",
        default="",
        help="CalSemVer string to validate and convert (defaults to today's date).",
    )
    parser.add_argument(
        "--prerelease",
        default="",
        help="Optional prerelease suffix when using today's date (e.g. a0, -alpha.0).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root for Sphinx virtualenv discovery.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "env"],
        default="json",
        help="Output format (json or shell env key=value lines).",
    )
    args = parser.parse_args(argv)

    try:
        forms = (
            parse_calsemver(args.version)
            if args.version
            else today_calsemver(prerelease=args.prerelease)
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    venv = discover_sphinx_venv(Path(args.repo_root))
    payload = asdict(forms)
    payload["sphinx_venv"] = str(venv) if venv else ""

    if args.format == "env":
        for key, val in payload.items():
            print(f"{key.upper()}={val}")
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
