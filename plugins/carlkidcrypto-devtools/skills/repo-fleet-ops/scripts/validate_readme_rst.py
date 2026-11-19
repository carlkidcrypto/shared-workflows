#!/usr/bin/env python3
"""Validate README.rst with `rst2html --strict` and verify badge/image URLs.

Checks that:
1. `rst2html --strict` exits 0 with no warnings or errors.
2. Every `.. image::` and `.. figure::` HTTP(S) URL returns HTTP 200 and
   does not contain error SVG text (`not found`, `missing`, `invalid`, etc.).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

IMAGE_DIRECTIVE_RE = re.compile(
    r"^\s*\.\.\s+(?:image|figure)::\s+(https?://\S+)", re.MULTILINE
)
BAD_SVG_MARKERS = (
    "not found",
    "repo not found",
    "badge not found",
    "missing",
    "invalid",
    "inaccessible",
    "error 404",
)


def find_rst2html() -> Optional[str]:
    """Locate `rst2html` or `rst2html.py` in PATH."""
    for candidate in ("rst2html", "rst2html.py", "rst2html5"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def run_rst2html_strict(readme_path: Path) -> Dict[str, Any]:
    """Run `rst2html --strict` on the target README.rst file."""
    rst_bin = find_rst2html()
    if rst_bin:
        cmd = [rst_bin, "--strict", str(readme_path)]
    else:
        cmd = [
            sys.executable,
            "-c",
            (
                "import sys; from docutils.core import publish_cmdline; "
                "publish_cmdline(writer_name='html')"
            ),
            "--strict",
            str(readme_path),
        ]
    res = subprocess.run(cmd, text=True, capture_output=True)
    return {
        "ok": res.returncode == 0,
        "returncode": res.returncode,
        "stderr": res.stderr.strip(),
    }


def extract_image_urls(readme_path: Path) -> List[str]:
    """Extract unique HTTP(S) URLs from `.. image::` and `.. figure::` directives."""
    text = readme_path.read_text(encoding="utf-8")
    seen: List[str] = []
    for url in IMAGE_DIRECTIVE_RE.findall(text):
        if url not in seen:
            seen.append(url)
    return seen


def check_url(url: str, timeout: int) -> Dict[str, Any]:
    """Verify a badge/image URL returns HTTP 200 without error SVG markers."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "carlkidcrypto-repo-fleet-ops/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(65536)
            body = raw.decode("utf-8", errors="ignore").lower()
            bad_marker = None
            if "svg" in ctype or "xml" in ctype or "text" in ctype or "<svg" in body:
                for marker in BAD_SVG_MARKERS:
                    if marker in body:
                        bad_marker = marker
                        break
            ok = status == 200 and bad_marker is None
            return {
                "url": url,
                "status": status,
                "ok": ok,
                "error": f"SVG contains '{bad_marker}'" if bad_marker else "",
            }
    except urllib.error.HTTPError as exc:
        return {"url": url, "status": exc.code, "ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status": 0, "ok": False, "error": str(exc)}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Validate README.rst with rst2html --strict and check badge URLs."
    )
    parser.add_argument(
        "readme",
        nargs="?",
        type=Path,
        default=Path("README.rst"),
        help="Path to README.rst (default: ./README.rst).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP timeout in seconds per badge/image URL (default: 15).",
    )
    parser.add_argument(
        "--skip-rst",
        action="store_true",
        help="Skip rst2html --strict check.",
    )
    parser.add_argument(
        "--skip-urls",
        action="store_true",
        help="Skip HTTP badge/image URL checks.",
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
    readme_path = args.readme.expanduser().resolve()
    if not readme_path.is_file():
        print(f"Error: file not found: {readme_path}", file=sys.stderr)
        return 2

    rst_result: Dict[str, Any] = {"ok": True, "skipped": True}
    if not args.skip_rst:
        rst_result = run_rst2html_strict(readme_path)

    url_results: List[Dict[str, Any]] = []
    if not args.skip_urls:
        for url in extract_image_urls(readme_path):
            url_results.append(check_url(url, args.timeout))

    all_ok = rst_result["ok"] and all(r["ok"] for r in url_results)
    payload = {
        "readme": str(readme_path),
        "rst2html": rst_result,
        "urls": url_results,
        "ok": all_ok,
    }

    if args.json_output:
        print(json.dumps(payload, indent=2))
    else:
        rst_label = (
            "SKIP"
            if rst_result.get("skipped")
            else ("PASS" if rst_result["ok"] else "FAIL")
        )
        print(f"rst2html --strict ({readme_path.name}): {rst_label}")
        if not rst_result["ok"] and rst_result.get("stderr"):
            print(f"  {rst_result['stderr']}")
        print(f"Badge/image URLs checked: {len(url_results)}")
        for r in url_results:
            if not r["ok"]:
                print(f"  FAIL [{r['status']}] {r['url']} -> {r['error']}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
