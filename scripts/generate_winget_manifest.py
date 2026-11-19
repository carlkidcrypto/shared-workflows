#!/usr/bin/env python3
"""Generate WinGet (Windows Package Manager) community repository manifests.

Produces valid multi-file manifests (version, installer, defaultLocale) conforming to
WinGet manifest specification 1.6.0 for submission to microsoft/winget-pkgs.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import urllib.request
from pathlib import Path

MANIFEST_VERSION = "1.6.0"


def _normalize_prerelease(raw: str) -> str:
    """Convert PEP 440 prerelease tags (e.g. a0, b1, rc2) to SemVer 2.0.0."""
    for pep_tag, semver_tag in (("a", "alpha"), ("b", "beta"), ("rc", "rc")):
        match = re.fullmatch(rf"(.+?){pep_tag}(\d+)", raw)
        if match and "-" not in raw:
            return f"{match.group(1)}-{semver_tag}.{match.group(2)}"
    return raw


def read_current_version(repo_root: Path | None = None) -> str:
    """Auto-detect the current package version from standard project manifests."""
    root = (repo_root or Path.cwd()).resolve()

    for rel in ("setup.cfg", "python/setup.cfg"):
        cfg = root / rel
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("version") and "=" in line:
                    raw = line.split("=", 1)[1].strip()
                    return _normalize_prerelease(raw)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        match = re.search(
            r'^version\s*=\s*["\']([^"\']+)["\']',
            pyproject.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            return _normalize_prerelease(match.group(1).strip())

    meson_file = root / "meson.build"
    if meson_file.is_file():
        match = re.search(
            r"version\s*:\s*['\"]([^'\"]+)['\"]",
            meson_file.read_text(encoding="utf-8"),
        )
        if match:
            return _normalize_prerelease(match.group(1).strip())

    for csproj in sorted(root.glob("**/*.csproj")):
        match = re.search(
            r"<Version>([^<]+)</Version>",
            csproj.read_text(encoding="utf-8"),
        )
        if match:
            return match.group(1).strip()

    raise ValueError("Unable to detect package version; pass --version explicitly.")


def get_canonical_manifest_dir(
    package_id: str,
    package_version: str,
    out_dir: Path,
) -> Path:
    """Return canonical WinGet directory: manifests/{first-letter}/{Publisher}/{AppName}/{Version}/."""
    if not re.fullmatch(r"^[a-zA-Z0-9_\-]+(?:\.[a-zA-Z0-9_\-]+)+$", package_id):
        raise ValueError(f"Invalid package_id format: {package_id}")
    if not re.fullmatch(r"^[0-9a-zA-Z.\-_]+$", package_version):
        raise ValueError(f"Invalid package_version format: {package_version}")

    parts = package_id.split(".", 1)
    publisher = parts[0]
    app_name = parts[1] if len(parts) > 1 else package_id
    first_letter = publisher[0].lower()

    base_out = out_dir.resolve()
    if base_out.name.lower() == "manifests":
        target = base_out / first_letter / publisher / app_name / package_version
    else:
        target = (
            base_out
            / "manifests"
            / first_letter
            / publisher
            / app_name
            / package_version
        )

    target_resolved = target.resolve()
    if not target_resolved.is_relative_to(base_out):
        raise ValueError(f"Path traversal detected in manifest directory: {target}")
    return target_resolved


def compute_sha256(path_or_url: str, repo_root: Path | None = None) -> str:
    """Compute the lowercase SHA256 hex digest of a local file or remote URL."""
    h = hashlib.sha256()

    if path_or_url.startswith(("http://", "https://")):
        try:
            req = urllib.request.Request(
                path_or_url, headers={"User-Agent": "winget-manifest-gen/1.0"}
            )
            with urllib.request.urlopen(req) as resp:
                while chunk := resp.read(65536):
                    h.update(chunk)
            return h.hexdigest().lower()
        except Exception as exc:
            print(
                f"Warning: Could not fetch remote URL for SHA256 ({exc}); using zero digest."
            )
            return "0" * 64

    root = (repo_root or Path.cwd()).resolve()
    safe_name = Path(path_or_url).name
    candidate_paths = [
        (root / path_or_url).resolve(),
        (root / "dist" / safe_name).resolve(),
    ]
    for path in candidate_paths:
        if path.is_file() and path.is_relative_to(root):
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest().lower()

    raise FileNotFoundError(f"Cannot compute hash for: {path_or_url}")


def generate_manifests(
    package_id: str,
    package_version: str,
    installer_url: str,
    *,
    package_name: str = "",
    publisher: str = "",
    publisher_url: str = "",
    repo: str = "",
    short_description: str = "",
    description: str = "",
    moniker: str = "",
    tags: list[str] | None = None,
    installer_sha256: str = "",
    out_dir: Path | None = None,
    architecture: str = "x64",
    installer_type: str = "auto",
    product_code: str = "",
    relative_file_path: str = "",
    portable_command_alias: str = "",
    license_name: str = "MIT",
    copyright_text: str = "",
    repo_root: Path | None = None,
) -> dict[str, Path]:
    """Generate the 3 canonical WinGet manifest YAML files."""
    root = (repo_root or Path.cwd()).resolve()
    resolved_out = out_dir or (root / "dist-winget")

    parts = package_id.split(".", 1)
    resolved_publisher = publisher or parts[0]
    resolved_app = parts[1] if len(parts) > 1 else package_id
    resolved_name = package_name or resolved_app
    resolved_pub_url = publisher_url or f"https://github.com/{resolved_publisher}"
    resolved_repo = repo or f"{resolved_publisher}/{resolved_app}"
    resolved_short_desc = short_description or f"{resolved_name} Windows package."
    resolved_desc = description or resolved_short_desc
    resolved_moniker = moniker or re.sub(
        r"[^a-z0-9-]+", "-", resolved_app.lower()
    ).strip("-")
    resolved_copyright = copyright_text or f"Copyright (c) {resolved_publisher}"

    dest = get_canonical_manifest_dir(package_id, package_version, resolved_out)
    dest.mkdir(parents=True, exist_ok=True)

    resolved_type = (installer_type or "auto").strip().lower()
    if resolved_type in ("", "auto"):
        resolved_type = "zip" if installer_url.lower().endswith(".zip") else "inno"

    if not installer_sha256:
        installer_sha256 = (
            "0" * 64
            if not installer_url.startswith("http")
            and not Path(installer_url).is_file()
            else compute_sha256(installer_url, repo_root=root)
        )

    version_yaml = (
        f"PackageIdentifier: {package_id}\n"
        f"PackageVersion: {package_version}\n"
        "DefaultLocale: en-US\n"
        "ManifestType: version\n"
        f"ManifestVersion: {MANIFEST_VERSION}\n"
    )

    tag_lines = ""
    if tags:
        tag_lines = "Tags:\n" + "".join(f"  - {t}\n" for t in tags)

    desc_indented = "\n".join(
        f"  {line}" if line else "" for line in resolved_desc.splitlines()
    )

    locale_yaml = (
        f"PackageIdentifier: {package_id}\n"
        f"PackageVersion: {package_version}\n"
        "PackageLocale: en-US\n"
        f"Publisher: {resolved_publisher}\n"
        f"PublisherUrl: {resolved_pub_url}\n"
        f"PublisherSupportUrl: https://github.com/{resolved_repo}/issues\n"
        f"Author: {resolved_publisher}\n"
        f"PackageName: {resolved_name}\n"
        f"PackageUrl: https://github.com/{resolved_repo}\n"
        f"License: {license_name}\n"
        f"LicenseUrl: https://raw.githubusercontent.com/{resolved_repo}/main/LICENSE\n"
        f"Copyright: {resolved_copyright}\n"
        f"CopyrightUrl: https://raw.githubusercontent.com/{resolved_repo}/main/LICENSE\n"
        f"ShortDescription: {resolved_short_desc}\n"
        "Description: |-\n"
        f"{desc_indented}\n"
        f"Moniker: {resolved_moniker}\n"
        f"{tag_lines}"
        "ManifestType: defaultLocale\n"
        f"ManifestVersion: {MANIFEST_VERSION}\n"
    )

    if resolved_type == "inno":
        product_code_line = (
            f"    ProductCode: '{product_code}'\n" if product_code else ""
        )
        installer_yaml = (
            f"PackageIdentifier: {package_id}\n"
            f"PackageVersion: {package_version}\n"
            "InstallerLocale: en-US\n"
            "Platform:\n"
            "  - Windows.Desktop\n"
            "MinimumOSVersion: 10.0.0.0\n"
            "InstallerType: inno\n"
            "Scope: user\n"
            "InstallModes:\n"
            "  - interactive\n"
            "  - silent\n"
            "  - silentWithProgress\n"
            "InstallerSwitches:\n"
            "  Silent: /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-\n"
            "  SilentWithProgress: /SILENT /SUPPRESSMSGBOXES /NORESTART /SP-\n"
            "UpgradeBehavior: install\n"
            "AppsAndFeaturesEntries:\n"
            f"  - DisplayName: {resolved_name}\n"
            f"    Publisher: {resolved_publisher}\n"
            f"    DisplayVersion: {package_version}\n"
            f"{product_code_line}"
            "Installers:\n"
            f"  - Architecture: {architecture}\n"
            f"    InstallerUrl: {installer_url}\n"
            f"    InstallerSha256: {installer_sha256.upper()}\n"
            "ManifestType: installer\n"
            f"ManifestVersion: {MANIFEST_VERSION}\n"
        )
    else:
        rel_path = relative_file_path or f"{resolved_app}.exe"
        alias = portable_command_alias or resolved_app
        installer_yaml = (
            f"PackageIdentifier: {package_id}\n"
            f"PackageVersion: {package_version}\n"
            "InstallerLocale: en-US\n"
            "Platform:\n"
            "  - Windows.Desktop\n"
            "MinimumOSVersion: 10.0.0.0\n"
            "InstallerType: zip\n"
            "NestedInstallerType: portable\n"
            "NestedInstallerFiles:\n"
            f"  - RelativeFilePath: {rel_path}\n"
            f"    PortableCommandAlias: {alias}\n"
            "Installers:\n"
            f"  - Architecture: {architecture}\n"
            f"    InstallerUrl: {installer_url}\n"
            f"    InstallerSha256: {installer_sha256.upper()}\n"
            "ManifestType: installer\n"
            f"ManifestVersion: {MANIFEST_VERSION}\n"
        )

    target_dir = dest.resolve()
    version_path = (target_dir / f"{package_id}.yaml").resolve()
    locale_path = (target_dir / f"{package_id}.locale.en-US.yaml").resolve()
    installer_path = (target_dir / f"{package_id}.installer.yaml").resolve()

    for path in (version_path, locale_path, installer_path):
        if not path.is_relative_to(target_dir):
            raise ValueError(f"Path traversal detected in manifest output file: {path}")

    version_path.write_text(version_yaml, encoding="utf-8")
    locale_path.write_text(locale_yaml, encoding="utf-8")
    installer_path.write_text(installer_yaml, encoding="utf-8")

    return {
        "version": version_path,
        "locale": locale_path,
        "installer": installer_path,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Generate WinGet manifests.")
    parser.add_argument(
        "--package-id",
        required=True,
        help="WinGet PackageIdentifier (e.g. Publisher.PackageName).",
    )
    parser.add_argument("--package-name", default="")
    parser.add_argument("--publisher", default="")
    parser.add_argument("--publisher-url", default="")
    parser.add_argument(
        "--repo", default="", help="GitHub repository slug (owner/repo)."
    )
    parser.add_argument("--version", default="")
    parser.add_argument("--installer-url", required=True)
    parser.add_argument("--sha256", default="")
    parser.add_argument("--out-dir", default="dist-winget")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--arch", default="x64")
    parser.add_argument(
        "--installer-type",
        default="auto",
        choices=["auto", "inno", "zip"],
    )
    parser.add_argument("--short-description", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--moniker", default="")
    parser.add_argument("--tag", action="append", dest="tags", default=[])
    parser.add_argument("--product-code", default="")
    parser.add_argument("--relative-file-path", default="")
    parser.add_argument("--portable-alias", default="")
    parser.add_argument("--license", dest="license_name", default="MIT")
    parser.add_argument("--copyright", dest="copyright_text", default="")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    ver = args.version or read_current_version(repo_root=repo_root)
    res = generate_manifests(
        package_id=args.package_id,
        package_version=ver,
        installer_url=args.installer_url,
        package_name=args.package_name,
        publisher=args.publisher,
        publisher_url=args.publisher_url,
        repo=args.repo,
        short_description=args.short_description,
        description=args.description,
        moniker=args.moniker,
        tags=args.tags,
        installer_sha256=args.sha256,
        out_dir=Path(args.out_dir),
        architecture=args.arch,
        installer_type=args.installer_type,
        product_code=args.product_code,
        relative_file_path=args.relative_file_path,
        portable_command_alias=args.portable_alias,
        license_name=args.license_name,
        copyright_text=args.copyright_text,
        repo_root=repo_root,
    )

    print(f"Generated WinGet manifests for {args.package_id} v{ver}:")
    for kind, path in res.items():
        print(f"  {kind}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
