#!/usr/bin/env python3
"""Run local formatting, lint, build, test, and doc checks for a repository.

Automatically detects applicable checks from repository files, applies
`env_preflight.sh` environment variables (PATH, PKG_CONFIG_PATH,
DYLD_LIBRARY_PATH), creates `doxygen_docs_build/doxygen` before Doxygen runs,
and cleans temporary build artifacts unless `--keep-artifacts` is set.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

IGNORED_DIRS: Set[str] = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "third_party",
    "doxygen_docs_build",
    "_build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
}

CPP_EXTENSIONS: Set[str] = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
MESON_BUILD_DIR = ".meson_build_validate"


def load_preflight_env() -> Dict[str, str]:
    """Load environment variables from sibling `env_preflight.sh`."""
    script_path = Path(__file__).resolve().parent / "env_preflight.sh"
    if not script_path.exists():
        return os.environ.copy()

    proc = subprocess.run(
        ["bash", "-c", 'source "$1" && env -0', "_", str(script_path)],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return os.environ.copy()

    env: Dict[str, str] = {}
    for entry in proc.stdout.split(b"\x00"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        env[key.decode("utf-8", errors="replace")] = value.decode(
            "utf-8", errors="replace"
        )
    return env


def should_skip_path(path: Path, repo: Path) -> bool:
    """Return True if any path component is an ignored build/vendor directory."""
    try:
        rel_parts = path.relative_to(repo).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in IGNORED_DIRS or part.endswith(".egg-info") for part in rel_parts)


def find_files(
    repo: Path, extensions: Set[str], exclude_swig: bool = True
) -> List[Path]:
    """Recursively find source files matching `extensions` under `repo`."""
    matches: List[Path] = []
    for root, dirs, files in os.walk(repo):
        root_path = Path(root)
        dirs[:] = [
            d
            for d in dirs
            if d not in IGNORED_DIRS
            and not d.endswith(".egg-info")
            and not d.startswith(".meson_build")
        ]
        if should_skip_path(root_path, repo):
            continue
        for filename in files:
            if Path(filename).suffix not in extensions:
                continue
            if exclude_swig and "_wrap." in filename:
                continue
            matches.append(root_path / filename)
    return sorted(matches)


def run_step(
    name: str,
    cmd: List[str],
    cwd: Path,
    env: Dict[str, str],
) -> Tuple[str, str]:
    """Execute a validation command and return `(name, status)`."""
    print(f"\n==> [{name}] {' '.join(cmd)}")
    exe = shutil.which(cmd[0], path=env.get("PATH"))
    if exe is None:
        print(f"[FAIL] {name}: executable `{cmd[0]}` not found in PATH")
        return name, "FAIL"

    proc = subprocess.run(cmd, cwd=cwd, env=env, check=False)
    status = "PASS" if proc.returncode == 0 else "FAIL"
    print(f"[{status}] {name} (exit={proc.returncode})")
    return name, status


def git_untracked_snapshot(repo: Path, env: Dict[str, str]) -> Optional[Set[Path]]:
    """Return existing untracked/modified paths in `repo`, or None if not a git repo."""
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    paths: Set[Path] = set()
    for line in proc.stdout.splitlines():
        if len(line) > 3:
            paths.add((repo / line[3:].strip()).resolve())
    return paths


def cleanup_artifacts(
    repo: Path,
    pre_existing: Optional[Set[Path]],
    created_dirs: List[Path],
    env: Dict[str, str],
) -> None:
    """Remove temporary build artifacts created during validation."""
    for target in created_dirs:
        if target.exists():
            print(f"Cleaning {target.relative_to(repo)}")
            shutil.rmtree(target, ignore_errors=True)

    for egg_info in repo.glob("*.egg-info"):
        if egg_info.is_dir():
            print(f"Cleaning {egg_info.relative_to(repo)}")
            shutil.rmtree(egg_info, ignore_errors=True)

    if pre_existing is None:
        return

    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return

    for line in proc.stdout.splitlines():
        if not line.startswith("?? "):
            continue
        rel_str = line[3:].strip()
        candidate = (repo / rel_str).resolve()
        if candidate in pre_existing:
            continue
        if (
            rel_str.endswith(".so")
            or rel_str.endswith(".pyd")
            or "_wrap." in rel_str
            or rel_str.startswith("build/")
            or rel_str.startswith(".pytest_cache/")
        ):
            if candidate.is_dir():
                shutil.rmtree(candidate, ignore_errors=True)
            elif candidate.is_file():
                candidate.unlink(missing_ok=True)


def has_pytest_suite(repo: Path) -> bool:
    """Return True if the repository contains pytest tests."""
    for candidate in ("tests", "python_tests"):
        if (repo / candidate).is_dir():
            return True
    return any(repo.glob("test_*.py"))


def setup_has_extensions(setup_py: Path) -> bool:
    """Return True if `setup.py` defines native extensions."""
    if not setup_py.is_file():
        return False
    text = setup_py.read_text(encoding="utf-8", errors="replace")
    return "Extension" in text or "ext_modules" in text


def validate_repo(args: argparse.Namespace) -> int:
    """Run all applicable validation steps against `args.repo`."""
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"Repository path does not exist: {repo}", file=sys.stderr)
        return 2

    env = load_preflight_env()
    pre_existing = git_untracked_snapshot(repo, env)
    created_dirs: List[Path] = []
    results: List[Tuple[str, str]] = []

    try:
        # 1. Python formatting
        py_files = find_files(repo, {".py"}, exclude_swig=True)
        if args.skip_python:
            results.append(("black --check", "SKIP"))
        elif py_files:
            results.append(
                run_step("black --check", ["black", "--check", "."], repo, env)
            )
        else:
            results.append(("black --check", "SKIP"))

        # 2. C/C++ formatting
        cpp_files = find_files(repo, CPP_EXTENSIONS, exclude_swig=True)
        if args.skip_cpp:
            results.append(("clang-format", "SKIP"))
        elif cpp_files:
            cmd = ["clang-format", "-n", "-Werror", *[str(p) for p in cpp_files]]
            results.append(run_step("clang-format", cmd, repo, env))
        else:
            results.append(("clang-format", "SKIP"))

        # 3. GitHub Actions workflow linting
        workflows_dir = repo / ".github" / "workflows"
        workflow_files = (
            sorted(
                list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
            )
            if workflows_dir.is_dir()
            else []
        )
        if args.skip_workflows or not workflow_files:
            results.append(("yamllint", "SKIP"))
            results.append(("actionlint", "SKIP"))
        else:
            yamllint_target = (
                "."
                if (repo / ".yamllint").exists() or (repo / ".yamllint.yml").exists()
                else ".github/workflows"
            )
            results.append(
                run_step("yamllint", ["yamllint", yamllint_target], repo, env)
            )
            results.append(run_step("actionlint", ["actionlint"], repo, env))

        # 4. Python extension build & pytest
        if args.skip_python:
            results.append(("python build_ext", "SKIP"))
            results.append(("pytest", "SKIP"))
        else:
            setup_py = repo / "setup.py"
            if setup_has_extensions(setup_py):
                if not (repo / "build").exists():
                    created_dirs.append(repo / "build")
                results.append(
                    run_step(
                        "python build_ext",
                        [sys.executable, "setup.py", "build_ext", "--inplace"],
                        repo,
                        env,
                    )
                )
            else:
                results.append(("python build_ext", "SKIP"))

            if has_pytest_suite(repo):
                if not (repo / ".pytest_cache").exists():
                    created_dirs.append(repo / ".pytest_cache")
                results.append(run_step("pytest", ["pytest"], repo, env))
            else:
                results.append(("pytest", "SKIP"))

        # 5. C++ Meson build & test
        if args.skip_cpp or not (repo / "meson.build").is_file():
            results.append(("meson", "SKIP"))
        else:
            meson_dir = repo / MESON_BUILD_DIR
            created_dirs.append(meson_dir)
            if meson_dir.exists():
                shutil.rmtree(meson_dir)
            setup_res = run_step(
                "meson setup", ["meson", "setup", MESON_BUILD_DIR], repo, env
            )
            results.append(setup_res)
            if setup_res[1] == "PASS":
                compile_res = run_step(
                    "meson compile",
                    ["meson", "compile", "-C", MESON_BUILD_DIR],
                    repo,
                    env,
                )
                results.append(compile_res)
                if compile_res[1] == "PASS":
                    results.append(
                        run_step(
                            "meson test",
                            [
                                "meson",
                                "test",
                                "-C",
                                MESON_BUILD_DIR,
                                "--print-errorlogs",
                            ],
                            repo,
                            env,
                        )
                    )

        # 6. Documentation (Doxygen + Sphinx)
        if args.skip_docs:
            results.append(("doxygen", "SKIP"))
            results.append(("sphinx-build", "SKIP"))
        else:
            doxyfile = next(
                (p for p in (repo / ".doxygen", repo / "Doxyfile") if p.is_file()),
                None,
            )
            if doxyfile is not None:
                doxygen_out = repo / "doxygen_docs_build" / "doxygen"
                if not doxygen_out.exists():
                    created_dirs.append(doxygen_out)
                doxygen_out.mkdir(parents=True, exist_ok=True)
                results.append(
                    run_step("doxygen", ["doxygen", doxyfile.name], repo, env)
                )
            else:
                results.append(("doxygen", "SKIP"))

            sphinx_src = next(
                (
                    d
                    for d in (repo / "sphinx_docs_build", repo / "docs")
                    if (d / "conf.py").is_file()
                ),
                None,
            )
            if sphinx_src is not None:
                sphinx_out = sphinx_src / "_build"
                if not sphinx_out.exists():
                    created_dirs.append(sphinx_out)
                results.append(
                    run_step(
                        "sphinx-build",
                        [
                            "sphinx-build",
                            "-b",
                            "html",
                            "-W",
                            str(sphinx_src.relative_to(repo)),
                            str((sphinx_out / "html").relative_to(repo)),
                        ],
                        repo,
                        env,
                    )
                )
            else:
                results.append(("sphinx-build", "SKIP"))
    finally:
        if not args.keep_artifacts:
            cleanup_artifacts(repo, pre_existing, created_dirs, env)

    print("\n=== Validation Summary ===")
    failed = False
    for name, status in results:
        print(f"  {status:4s}  {name}")
        if status == "FAIL":
            failed = True
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run local formatting, lint, build, test, and doc checks."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the repository or worktree to validate (default: .)",
    )
    parser.add_argument(
        "--skip-python",
        action="store_true",
        help="Skip Python formatting (black) and build/pytest checks",
    )
    parser.add_argument(
        "--skip-cpp",
        action="store_true",
        help="Skip C/C++ formatting (clang-format) and Meson build/tests",
    )
    parser.add_argument(
        "--skip-docs",
        action="store_true",
        help="Skip Doxygen and Sphinx documentation builds",
    )
    parser.add_argument(
        "--skip-workflows",
        action="store_true",
        help="Skip yamllint and actionlint workflow checks",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Preserve temporary build and documentation artifacts after validation",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(validate_repo(parse_args()))
