#!/usr/bin/env python3
"""Audit open Dependabot alerts and unpinned GitHub Actions `uses:` references.

Lists open Dependabot alerts via `gh api repos/{owner}/{repo}/dependabot/alerts?state=open`
(gracefully handling 403/404 when Dependabot is disabled or inaccessible) and
optionally scans `.github/workflows/*.yml` for `uses:` tags lacking 40-char commit SHAs.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
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
    "carlkidcrypto.github.io",
    "os-specific-runner",
]

USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*[\"']?([^\"'\s#]+)[\"']?")
SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def find_gh() -> Optional[str]:
    """Locate the GitHub CLI executable."""
    for candidate in (
        shutil.which("gh"),
        "/opt/homebrew/bin/gh",
        "/usr/local/bin/gh",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def run_gh(gh_bin: str, args: List[str]) -> subprocess.CompletedProcess[str]:
    """Run a `gh` subcommand and return the completed process."""
    return subprocess.run([gh_bin, *args], text=True, capture_output=True)


def normalize_repo(repo_arg: str) -> str:
    """Normalize a repository argument to `owner/repo`."""
    return repo_arg if "/" in repo_arg else f"{DEFAULT_OWNER}/{repo_arg}"


def detect_current_repo(gh_bin: Optional[str]) -> Optional[str]:
    """Attempt to detect the current repository `owner/repo` via `gh`."""
    if not gh_bin:
        return None
    res = run_gh(
        gh_bin, ["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return None


def fetch_dependabot_alerts(gh_bin: str, full_repo: str) -> Dict[str, Any]:
    """Fetch open Dependabot alerts for a repository, handling 403/404 gracefully."""
    endpoint = f"repos/{full_repo}/dependabot/alerts?state=open&per_page=100"
    res = run_gh(gh_bin, ["api", endpoint])
    if res.returncode != 0:
        err = (res.stderr or res.stdout).strip()
        if "403" in err or "404" in err or "disabled" in err.lower():
            return {
                "status": "disabled_or_forbidden",
                "count": 0,
                "alerts": [],
                "note": err,
            }
        return {
            "status": "error",
            "count": 0,
            "alerts": [],
            "note": err,
        }

    raw_alerts = json.loads(res.stdout or "[]")
    alerts: List[Dict[str, Any]] = []
    for item in raw_alerts:
        advisory = item.get("security_advisory") or {}
        dep = item.get("dependency") or {}
        pkg = dep.get("package") or {}
        alerts.append(
            {
                "number": item.get("number"),
                "severity": advisory.get("severity", "unknown"),
                "package": pkg.get("name", "unknown"),
                "ecosystem": pkg.get("ecosystem", "unknown"),
                "summary": advisory.get("summary", ""),
                "html_url": item.get("html_url", ""),
            }
        )
    return {
        "status": "ok",
        "count": len(alerts),
        "alerts": alerts,
    }


def scan_yaml_for_unpinned_uses(filename: str, content: str) -> List[Dict[str, Any]]:
    """Scan workflow YAML text for `uses:` references not pinned to a 40-char SHA."""
    findings: List[Dict[str, Any]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        match = USES_RE.match(line)
        if not match:
            continue
        ref_target = match.group(1)
        if ref_target.startswith("./") or ref_target.startswith("docker://"):
            continue
        if "@" not in ref_target:
            findings.append(
                {
                    "file": filename,
                    "line": lineno,
                    "uses": ref_target,
                    "ref": "",
                    "reason": "missing @ref",
                }
            )
            continue
        _, ref = ref_target.rsplit("@", 1)
        if not SHA40_RE.match(ref):
            findings.append(
                {
                    "file": filename,
                    "line": lineno,
                    "uses": ref_target,
                    "ref": ref,
                    "reason": "not pinned to 40-char commit SHA",
                }
            )
    return findings


def check_local_workflows(workflows_dir: Path) -> List[Dict[str, Any]]:
    """Scan local `.github/workflows/*.yml` and `*.yaml` files."""
    findings: List[Dict[str, Any]] = []
    for path in sorted(workflows_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}:
            content = path.read_text(encoding="utf-8", errors="replace")
            findings.extend(scan_yaml_for_unpinned_uses(str(path), content))
    return findings


def check_remote_workflows(gh_bin: str, full_repo: str) -> Dict[str, Any]:
    """Fetch and scan `.github/workflows/*.yml` from a GitHub repository via `gh api`."""
    res = run_gh(gh_bin, ["api", f"repos/{full_repo}/contents/.github/workflows"])
    if res.returncode != 0:
        err = (res.stderr or res.stdout).strip()
        if "404" in err:
            return {"status": "none", "unpinned": []}
        return {"status": "error", "unpinned": [], "note": err}

    entries = json.loads(res.stdout or "[]")
    if not isinstance(entries, list):
        return {"status": "none", "unpinned": []}

    findings: List[Dict[str, Any]] = []
    for entry in entries:
        name = entry.get("name", "")
        if not name.lower().endswith((".yml", ".yaml")):
            continue
        file_res = run_gh(
            gh_bin,
            ["api", f"repos/{full_repo}/contents/.github/workflows/{name}"],
        )
        if file_res.returncode != 0:
            continue
        file_obj = json.loads(file_res.stdout or "{}")
        encoded = file_obj.get("content", "")
        if not encoded:
            continue
        decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
        findings.extend(
            scan_yaml_for_unpinned_uses(f".github/workflows/{name}", decoded)
        )
    return {"status": "ok", "unpinned": findings}


def print_human_report(results: List[Dict[str, Any]]) -> None:
    """Print a concise human-readable audit report."""
    for repo_res in results:
        repo = repo_res["repo"]
        print(f"=== {repo} ===")
        dep = repo_res.get("dependabot")
        if dep:
            status = dep["status"]
            if status == "ok":
                print(f"Dependabot open alerts: {dep['count']}")
                for alert in dep["alerts"]:
                    print(
                        f"  - #{alert['number']} [{alert['severity']}] "
                        f"{alert['package']} ({alert['ecosystem']}): {alert['summary']}"
                    )
            else:
                print(f"Dependabot: {status} ({dep.get('note', '')})")

        wf = repo_res.get("workflows")
        if wf:
            unpinned = wf.get("unpinned", [])
            print(f"Unpinned workflow `uses:`: {len(unpinned)}")
            for item in unpinned:
                print(
                    f"  - {item['file']}:{item['line']} -> {item['uses']} ({item['reason']})"
                )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Audit open Dependabot alerts via gh api and optionally scan "
            ".github/workflows/*.yml for unpinned uses: references."
        )
    )
    parser.add_argument(
        "--repo",
        action="append",
        dest="repos",
        help="Target repository (<owner/repo> or <repo>; repeatable).",
    )
    parser.add_argument(
        "--all-repos",
        action="store_true",
        help="Audit all default carlkidcrypto ecosystem repositories.",
    )
    parser.add_argument(
        "--check-workflows",
        action="store_true",
        help="Scan .github/workflows/*.yml for unpinned uses: tags lacking 40-char SHAs.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output audit results as JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    gh_bin = find_gh()

    target_repos: List[str] = []
    if args.all_repos:
        target_repos = [f"{DEFAULT_OWNER}/{r}" for r in DEFAULT_REPOS]
    elif args.repos:
        target_repos = [normalize_repo(r) for r in args.repos]
    else:
        detected = detect_current_repo(gh_bin)
        if detected:
            target_repos = [detected]

    local_wf_dir = Path.cwd() / ".github" / "workflows"
    if not target_repos and args.check_workflows and local_wf_dir.is_dir():
        unpinned = check_local_workflows(local_wf_dir)
        payload = [
            {
                "repo": str(Path.cwd().name),
                "dependabot": {
                    "status": "skipped",
                    "count": 0,
                    "alerts": [],
                    "note": "gh CLI unavailable or repository not specified",
                },
                "workflows": {"status": "ok", "unpinned": unpinned},
            }
        ]
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print_human_report(payload)
        return 0

    if not target_repos:
        print(
            "Error: specify --repo, --all-repos, or run inside a GitHub repository.",
            file=sys.stderr,
        )
        return 2

    if not gh_bin:
        print("Error: GitHub CLI (`gh`) not found in PATH.", file=sys.stderr)
        return 2

    results: List[Dict[str, Any]] = []
    for full_repo in target_repos:
        entry: Dict[str, Any] = {
            "repo": full_repo,
            "dependabot": fetch_dependabot_alerts(gh_bin, full_repo),
        }
        if args.check_workflows:
            if not args.all_repos and not args.repos and local_wf_dir.is_dir():
                entry["workflows"] = {
                    "status": "ok",
                    "unpinned": check_local_workflows(local_wf_dir),
                }
            else:
                entry["workflows"] = check_remote_workflows(gh_bin, full_repo)
        results.append(entry)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_human_report(results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
