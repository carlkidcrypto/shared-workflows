"""Unit tests for retarget_stacked_pr.py and inspect_pr_ci.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import inspect_pr_ci
import retarget_stacked_pr


def test_retarget_pr_unstack_and_edit(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_gh(args, *, check=True):
        calls.append(args)
        if args == ["api", "repos/owner/repo/pulls/1530"]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps({"base": {"ref": "main"}, "stack": {"number": 1536}}),
                stderr="",
            )
        if args == ["api", "-X", "POST", "repos/owner/repo/stacks/1536/unstack"]:
            return subprocess.CompletedProcess(
                args, 0, stdout=json.dumps({"number": 1536, "open": False}), stderr=""
            )
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(retarget_stacked_pr, "_run_gh", fake_run_gh)
    res = retarget_stacked_pr.retarget_pr("owner/repo", 1530, "feat/base-branch")
    assert res["unstacked_stack_number"] == 1536
    assert res["new_base"] == "feat/base-branch"
    assert calls == [
        ["api", "repos/owner/repo/pulls/1530"],
        ["api", "-X", "POST", "repos/owner/repo/stacks/1536/unstack"],
        ["pr", "edit", "1530", "--repo", "owner/repo", "--base", "feat/base-branch"],
    ]


def test_summarize_pr_checks_partitions_passing_and_failed():
    payload = {
        "state": "OPEN",
        "baseRefName": "main",
        "headRefName": "fix/example",
        "headRefOid": "1234567890abcdef",
        "mergeable": "MERGEABLE",
        "statusCheckRollup": [
            {
                "name": "ok-job",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "detailsUrl": "https://github.com/o/r/actions/runs/111/job/222",
            },
            {
                "name": "fail-job",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "detailsUrl": "https://github.com/o/r/actions/runs/333/job/444",
            },
        ],
    }
    summary = inspect_pr_ci.summarize_pr_checks(payload)
    assert summary["passing"] == 1
    assert len(summary["non_passing"]) == 1
    assert summary["non_passing"][0]["run_id"] == "333"
    assert summary["non_passing"][0]["job_id"] == "444"
    assert summary["failed_run_ids"] == ["333"]
