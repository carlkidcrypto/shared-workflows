"""Unit tests for bump_shared_workflows_sha.py."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bump_shared_workflows_sha as mod  # noqa: E402

OLD_SHA = "1111111111111111111111111111111111111111"
NEW_SHA = "2222222222222222222222222222222222222222"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_clean_cloud_sync_refs(tmp_path: Path) -> None:
    refs_dir = tmp_path / ".git" / "refs" / "remotes" / "origin"
    refs_dir.mkdir(parents=True)
    good = refs_dir / "main"
    dup = refs_dir / "main (1)"
    good.write_text(f"{NEW_SHA}\n", encoding="utf-8")
    dup.write_text(f"{OLD_SHA}\n", encoding="utf-8")

    removed = mod.clean_cloud_sync_refs(tmp_path)
    assert removed == [".git/refs/remotes/origin/main (1)"]
    assert good.exists()
    assert not dup.exists()


def test_prune_old_aw_imports(tmp_path: Path) -> None:
    base = (
        tmp_path / ".github" / "aw" / "imports" / "carlkidcrypto" / "shared-workflows"
    )
    old_dir = base / OLD_SHA
    new_dir = base / NEW_SHA
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)
    (old_dir / "snippet.md").write_text("old", encoding="utf-8")
    (new_dir / "snippet.md").write_text("new", encoding="utf-8")

    dry = mod.prune_old_aw_imports(tmp_path, NEW_SHA, dry_run=True)
    assert dry == [f".github/aw/imports/carlkidcrypto/shared-workflows/{OLD_SHA}"]
    assert old_dir.exists()

    pruned = mod.prune_old_aw_imports(tmp_path, NEW_SHA, dry_run=False)
    assert pruned == [f".github/aw/imports/carlkidcrypto/shared-workflows/{OLD_SHA}"]
    assert not old_dir.exists()
    assert new_dir.exists()


def test_dry_run_scans_origin_main_not_stale_local_working_tree(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", str(remote))

    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(remote), str(seed))
    _git(seed, "checkout", "-b", "main")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")

    wf = seed / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        f"uses: carlkidcrypto/shared-workflows/.github/workflows/x.yml@{OLD_SHA}\n",
        encoding="utf-8",
    )
    _git(seed, "add", ".github/workflows/ci.yml")
    _git(seed, "commit", "-m", "initial")
    _git(seed, "push", "-u", "origin", "main")

    # Clone into consumer repo; local working tree has NEW_SHA (simulating diverged local state),
    # while origin/main still has OLD_SHA.
    consumer = tmp_path / "consumer"
    _git(tmp_path, "clone", str(remote), str(consumer))
    (consumer / ".github" / "workflows" / "ci.yml").write_text(
        f"uses: carlkidcrypto/shared-workflows/.github/workflows/x.yml@{NEW_SHA}\n",
        encoding="utf-8",
    )

    rec = mod.process_repo(
        primary_clone=consumer,
        workspace_root=tmp_path,
        repo="consumer",
        target_sha=NEW_SHA,
        branch="chore/bump-sha",
        apply=False,
        commit=False,
    )
    assert rec["status"] == "needs-bump"
    assert rec["changed_files"] == [{"file": ".github/workflows/ci.yml", "updates": 1}]
