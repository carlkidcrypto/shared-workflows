#!/usr/bin/env python3
"""Normalize, prune superseded prerelease docs, and update Sphinx landing index.rst.

Supports both Semantic Versioning (e.g. v1.5.1a0 -> pruned when v1.5.1 ships) and
CalSemVer (e.g. v2026.11.11a0, v2026.11.24b0, v2026.11.24-beta.0 -> pruned when
formal production release v2026.11.26 ships, while keeping any future prereleases
newer than the latest stable release).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import sys

_VERSION_RE = re.compile(
    r"^(?P<release>\d+(?:\.\d+)*)"
    r"(?:(?P<pre_sep>[.-]?)(?P<pre_type>dev|alpha|beta|rc|a|b)[.-]?(?P<pre_num>\d+)"
    r"|-(?P<dash_num>\d+))?$",
    re.IGNORECASE,
)

_PRE_RANK = {
    "dev": 0,
    "a": 1,
    "alpha": 1,
    "b": 2,
    "beta": 2,
    "rc": 3,
}


def parse_version_key(
    dir_name: str,
) -> tuple[tuple[int, ...], int, int, int] | None:
    """Parse ``html_v<version>`` into ``(release_tuple, is_stable, pre_rank, pre_num)``.

    Returns ``None`` if ``dir_name`` does not contain a recognized version string.
    Stable releases have ``is_stable=1``; prereleases have ``is_stable=0`` so that
    any prerelease sorts strictly below its corresponding or later stable release.
    """
    clean = re.sub(r"^html_[vV]", "", dir_name).strip()
    match = _VERSION_RE.match(clean)
    if not match:
        return None
    release = tuple(int(part) for part in match.group("release").split("."))
    pre_type = match.group("pre_type")
    dash_num = match.group("dash_num")
    if pre_type is not None:
        return (
            release,
            0,
            _PRE_RANK[pre_type.lower()],
            int(match.group("pre_num")),
        )
    if dash_num is not None:
        return (release, 0, 1, int(dash_num))
    return (release, 1, 99, 0)


def is_prerelease_key(key: tuple[tuple[int, ...], int, int, int]) -> bool:
    """Return True if a parsed version key represents a prerelease."""
    return key[1] == 0


def update_versioned_docs(
    docs_dir: pathlib.Path,
    landing_index: pathlib.Path,
    latest_label: str = "Latest Version",
) -> tuple[list[str], list[str]]:
    """Normalize ``html_V*``, prune superseded prereleases, and update ``landing_index``.

    Returns ``(kept_dir_names, pruned_dir_names)``.
    """
    # 1. Normalize any legacy html_V* directories to lowercase html_v*
    for entry in sorted(docs_dir.iterdir(), key=lambda p: p.name):
        if entry.is_dir() and entry.name.startswith("html_V"):
            target = docs_dir / ("html_v" + entry.name[6:])
            if target.exists() and not entry.samefile(target):
                shutil.rmtree(entry)
            else:
                tmp = docs_dir / f".{entry.name}.rename_tmp"
                entry.rename(tmp)
                tmp.rename(target)

    # 2. Collect all html_v* directories and find latest formal stable release
    version_dirs = [
        d
        for d in docs_dir.iterdir()
        if d.is_dir() and d.name.lower().startswith("html_v")
    ]
    parsed = [(d, parse_version_key(d.name)) for d in version_dirs]
    stable_keys = [
        key for _, key in parsed if key is not None and not is_prerelease_key(key)
    ]
    latest_stable = max(stable_keys) if stable_keys else None

    # 3. Prune any prerelease superseded by the latest stable release (CalSemVer + SemVer)
    active: list[tuple[pathlib.Path, tuple[tuple[int, ...], int, int, int] | None]] = []
    pruned_names: list[str] = []
    for d, key in parsed:
        if (
            latest_stable is not None
            and key is not None
            and is_prerelease_key(key)
            and key < latest_stable
        ):
            print(f"Retiring superseded prerelease docs {d.name}")
            shutil.rmtree(d)
            pruned_names.append(d.name)
        else:
            active.append((d, key))

    # 4. Sort remaining versions newest-first (unparseable names last)
    active.sort(
        key=lambda item: (
            item[1] is not None,
            item[1] or ((0,), 0, 0, 0),
            item[0].name,
        ),
        reverse=True,
    )
    kept_names = [d.name for d, _ in active]

    # 5. Update VERSION_LIST_START / VERSION_LIST_END in landing index.rst
    entries = [f"* `{latest_label} <./html/index.html>`_"]
    for name in kept_names:
        ver_str = "v" + re.sub(r"^html_[vV]", "", name)
        entries.append(f"* `{ver_str} <./{name}/index.html>`_")

    content = landing_index.read_text(encoding="utf-8")
    updated, replacements = re.subn(
        r"\.\. VERSION_LIST_START\n.*?\.\. VERSION_LIST_END",
        ".. VERSION_LIST_START\n\n" + "\n".join(entries) + "\n\n.. VERSION_LIST_END",
        content,
        flags=re.DOTALL,
    )
    if replacements != 1:
        raise RuntimeError(
            f"Expected VERSION_LIST_START/VERSION_LIST_END sentinels once in {landing_index}, found {replacements}"
        )
    landing_index.write_text(updated, encoding="utf-8")
    print(f"Updated {landing_index} with {len(kept_names)} version(s): {kept_names}")
    return kept_names, sorted(pruned_names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument(
        "--landing-index", default="sphinx_docs_build/landing/source/index.rst"
    )
    parser.add_argument("--latest-label", default="Latest Version")
    args = parser.parse_args(argv)
    try:
        update_versioned_docs(
            pathlib.Path(args.docs_dir),
            pathlib.Path(args.landing_index),
            latest_label=args.latest_label,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
