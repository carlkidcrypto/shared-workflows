#!/usr/bin/env python3
"""Audit and optionally backfill GitHub Release notes against auto_release_notes.

Scans `gh api repos/<owner>/<repo>/releases` for releases missing standard
`auto_release_notes` sections (`Compared to:` / `**Full Changelog**:`, `## `
headers, or redacted `(pypi.org/redacted)` links). Runs in dry-run mode by
default; pass `--apply` to backfill missing notes via `gh release edit`.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_OWNER = "carlkidcrypto"
DEFAULT_REPOS = [
    "shared-workflows",
    "ezsnmp",
    "ezsnmp_data_logger",
    "purpleair_api",
    "purpleair_data_logger",
    "purpleair-matterbridge",
    "os-specific-runner",
]
REDACTED_PYPI_RE = re.compile(r"\(pypi\.org/redacted\)")


def find_gh() -> str:
    """Locate the GitHub CLI executable."""
    for candidate in (
        shutil.which("gh"),
        "/opt/homebrew/bin/gh",
        "/usr/local/bin/gh",
    ):
        if candidate:
            return candidate
    raise FileNotFoundError("GitHub CLI (`gh`) not found in PATH or standard locations")


def run_gh(gh_bin: str, args: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` subcommand and return the completed process."""
    return subprocess.run([gh_bin, *args], text=True, capture_output=True)


def check_release_body(body: str) -> List[str]:
    """Return a list of conformance issues found in a release body."""
    issues: List[str] = []
    stripped = (body or "").strip()
    if not stripped:
        return ["empty-body"]
    if "## " not in stripped:
        issues.append("missing-section-headers")
    if "Compared to:" not in stripped and "**Full Changelog**:" not in stripped:
        issues.append("missing-changelog-link")
    if REDACTED_PYPI_RE.search(stripped):
        issues.append("redacted-pypi-link")
    return issues


def build_backfill_notes(
    gh_bin: str,
    owner: str,
    repo: str,
    tag: str,
    prev_tag: Optional[str],
    existing_body: str,
) -> Optional[str]:
    """Construct backfilled release notes using GitHub generate-notes or cleanup."""
    body = (existing_body or "").strip()
    if body and REDACTED_PYPI_RE.search(body):
        version = tag.lstrip("vV")
        body = body.replace(
            "(pypi.org/redacted)", f"(https://pypi.org/project/{repo}/{version}/)"
        )

    if (
        body
        and "## " in body
        and ("Compared to:" in body or "**Full Changelog**:" in body)
    ):
        return body

    api_args = [
        "api",
        f"repos/{owner}/{repo}/releases/generate-notes",
        "-f",
        f"tag_name={tag}",
    ]
    if prev_tag:
        api_args.extend(["-f", f"previous_tag_name={prev_tag}"])
    gen = run_gh(gh_bin, api_args)
    if gen.returncode != 0:
        return None
    generated = json.loads(gen.stdout or "{}").get("body", "").strip()
    if not generated:
        return None
    if body and "## " not in body:
        return f"{body}\n\n---\n\n{generated}"
    return generated


def audit_repo(
    gh_bin: str,
    owner: str,
    repo: str,
    limit: int,
    tag_filter: Optional[str],
    apply: bool,
) -> List[Dict[str, Any]]:
    """Audit releases for a single repository and optionally backfill."""
    res = run_gh(
        gh_bin,
        ["api", "--paginate", f"repos/{owner}/{repo}/releases?per_page=100"],
    )
    if res.returncode != 0:
        print(
            f"Warning: failed to fetch releases for {owner}/{repo}: {res.stderr.strip()}",
            file=sys.stderr,
        )
        return []

    releases = json.loads(res.stdout or "[]")[:limit]
    findings: List[Dict[str, Any]] = []
    for idx, rel in enumerate(releases):
        tag = rel.get("tag_name", "")
        if tag_filter and tag != tag_filter:
            continue
        body = rel.get("body") or ""
        issues = check_release_body(body)
        if not issues:
            continue

        prev_tag = (
            releases[idx + 1].get("tag_name") if idx + 1 < len(releases) else None
        )
        entry: Dict[str, Any] = {
            "repo": repo,
            "tag": tag,
            "issues": issues,
            "action": "dry-run",
        }

        if apply:
            new_notes = build_backfill_notes(gh_bin, owner, repo, tag, prev_tag, body)
            if not new_notes:
                entry["action"] = "backfill-failed"
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", encoding="utf-8", delete=False
                ) as tmp:
                    tmp.write(new_notes)
                    tmp_path = Path(tmp.name)
                try:
                    edit = run_gh(
                        gh_bin,
                        [
                            "release",
                            "edit",
                            tag,
                            "--repo",
                            f"{owner}/{repo}",
                            "--notes-file",
                            str(tmp_path),
                        ],
                    )
                    entry["action"] = (
                        "updated" if edit.returncode == 0 else "edit-failed"
                    )
                    if edit.returncode != 0:
                        entry["error"] = edit.stderr.strip()
                finally:
                    tmp_path.unlink(missing_ok=True)
        findings.append(entry)
    return findings


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Audit and optionally backfill GitHub Release notes."
    )
    parser.add_argument(
        "--owner",
        default=DEFAULT_OWNER,
        help=f"GitHub owner/org (default: {DEFAULT_OWNER})",
    )
    parser.add_argument(
        "--repo",
        "-r",
        action="append",
        dest="repos",
        help="Repository name to scan (repeatable; defaults to all ecosystem repos).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum releases to inspect per repository (default: 100).",
    )
    parser.add_argument(
        "--tag",
        help="Only inspect/backfill a specific release tag.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply backfills via `gh release edit` (default is dry-run).",
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
    gh_bin = find_gh()
    repos = args.repos if args.repos else DEFAULT_REPOS

    all_findings: List[Dict[str, Any]] = []
    for repo in repos:
        all_findings.extend(
            audit_repo(gh_bin, args.owner, repo, args.limit, args.tag, args.apply)
        )

    if args.json_output:
        print(json.dumps(all_findings, indent=2))
    else:
        if not all_findings:
            print("All inspected releases conform to auto_release_notes standards.")
        else:
            for item in all_findings:
                print(
                    f"{item['repo']} {item['tag']}: "
                    f"[{', '.join(item['issues'])}] -> {item['action']}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
