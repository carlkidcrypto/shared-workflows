---
name: aw-runs-triage
description: >-
  Audit, verify, and remediate GitHub Agentic Workflows (gh-aw) "[aw] No-Op Runs"
  and "[aw] Detection Runs" tracking issues across carlkidcrypto repositories.
  Distinguishes genuine no-ops from misconfigured workflows (AWF SSL blocks,
  DIFC min-integrity errors, missing --allow-all-tools, incomplete runs) and
  separates Copilot HTTP 429 quota/rate-limit detection failures from real
  detector misconfigurations or threat warnings.
---

# Agentic Workflows No-Op & Detection Runs Triage

Use this skill when auditing `[aw] No-Op Runs` (`gh-aw-noop-runs`) and `[aw] Detection Runs` (`gh-aw-detection-runs`) issues across `carlkidcrypto` repositories (such as `ezsnmp#1477` and `ezsnmp#1501`).

> [!IMPORTANT]
> `[aw] No-Op Runs` and `[aw] Detection Runs` are rolling `gh-aw`-managed tracking issues (`Do not close this issue manually`). **Never** close them with `gh issue close` or `close_aw_rate_limit_issues.py`. Instead, verify every workflow posting to them and fix any misconfigured `.github/workflows/*.md` (or `shared/*.md` in `shared-workflows`) via PR.

---

## 1. Automated Fleet Discovery & Classification

Run the deterministic audit script from `carlkidcrypto-devtools`:

```bash
# Quick inventory of all open [aw] No-Op Runs and [aw] Detection Runs issues:
python3 plugins/carlkidcrypto-devtools/skills/aw-runs-triage/scripts/audit_aw_tracking_issues.py

# Deep inspection: checks the latest run per (repo, issue, workflow) via gh run view:
python3 plugins/carlkidcrypto-devtools/skills/aw-runs-triage/scripts/audit_aw_tracking_issues.py --inspect-runs

# Scope to specific repos or output JSON for downstream automation:
python3 plugins/carlkidcrypto-devtools/skills/aw-runs-triage/scripts/audit_aw_tracking_issues.py --repos ezsnmp ezsnmp_data_logger --inspect-runs --json
```

The script groups comments by `(repo, issue_kind, workflow)` and classifies each workflow's latest run into:
- `TRUE_NOOP`: `reported_no_action` outcome, `agent` job `success`, no error markers found.
- `FALSE_NOOP_SUSPECT`: `incomplete` outcome, non-success `agent` job, or firewall/DIFC/permission/tool-error markers found in failed logs.
- `RATE_LIMITED_429`: Confirmed Copilot HTTP `429` / `quota_exceeded` / `ai_credits_rate_limit_error`.
- `DETECTION_FAILURE_NON_429`: `detector_execution_failure` without HTTP 429 markers — likely a `detection` or `agent` misconfiguration.
- `THREAT_WARNING`: Threat detection produced a `warning` / `threat_detected` finding — requires immediate security review.

---

## 2. Track 1: Auditing `[aw] No-Op Runs`

A `noop` safe output should only happen when a workflow **genuinely verified** that no action was needed.

### Checklist for Any `reported_no_action` or `incomplete` Workflow

1. **Check the latest run** (`gh run view <run-id> --repo <owner/repo> --json conclusion,jobs` or `gh aw audit <run-id> --repo <owner/repo>`).
2. **Inspect `agent_output.json`** (from the `agent` artifact or `gh aw audit` output):
   - **True No-Op** has concrete verification evidence, e.g.:
     - `Codecov python_code component is at 100%`
     - `Audit script reported 0 issues`
     - `No open PRs with auto-sync label behind main`
     - `Triggering issue lacks bug label / [BUG] prefix`
   - **False No-Op (Misconfigured GH-AW)** shows signs of silent failure or blocked access:
     - Outcome is `incomplete` instead of `reported_no_action`.
     - `noop.message` says `"could not access"`, `"unable to fetch"`, `"permission denied"`, `"failed to"`, `"unreachable"`, or `"API error"`.
     - Logs show AWF Squid SSL errors (`CERTIFICATE_VERIFY_FAILED`, `DEPTH_ZERO_SELF_SIGNED_CERT`), DIFC blocks (`lower integrity than agent requires`), or interactive tool denials (`denied-no-approval-rule-and-could-not-request-from-user`).
3. **Remediate False No-Ops** (refer to `agentic-workflows` skill):
   - Missing egress host → add domain or preset (`api.github.com`, `api.codecov.io`, `python`, `go`, `npm`) to `network.allowed`.
   - Public issue/PR DIFC block → set `tools.bash: false`, `tools.cli-proxy: false`, `tools.github.min-integrity: none`.
   - Unattended URL/tool denial → add `engine.args: ["--allow-all-tools"]`.
   - Recompile with `gh aw compile` in a dedicated worktree (`wt-<repo>-<task>`), commit both `.md` and `.lock.yml`, and open a PR (never merge).
4. **Noise Control (Optional)**:
   - Only after confirming a workflow's no-ops are **100% genuine**, if its routine no-op comments create unwanted issue noise (e.g., high-frequency scheduled or event-gated checks), consider setting `safe-outputs.noop.report-as-issue: false` in the workflow frontmatter or shared import.

---

## 3. Track 2: Auditing `[aw] Detection Runs`

`gh-aw` runs a post-agent `detection` job to screen outputs for prompt injection or policy violations.

### Triage Decision Tree

| Classification | Root Cause | Action |
| :--- | :--- | :--- |
| `RATE_LIMITED_429` | Both `agent` and `detection` hit Copilot `429 Too Many Requests` / `quota_exceeded` (`THREAT_DETECTION_STATUS: reason=engine_error exit=2`). | **No workflow bug.** Do not edit workflow files for 429s; re-run affected workflows once Copilot quota resets. |
| `DETECTION_FAILURE_NON_429` | `detection` failed without 429 markers (e.g., missing `copilot-requests: write` permission, unsupported model, timeout, or AWF block). | Inspect `gh run view <run-id> --log` for the `detection` job, fix the workflow frontmatter / `shared/*.md` import, run `gh aw compile`, and open a PR. |
| `THREAT_WARNING` | Threat detection flagged suspicious content (`warning` / `threat_detected`). | Run `gh aw audit <run-id>` and inspect `detection_result.json` immediately to verify whether it is a real security/prompt-injection issue or a benign false positive. |

---

## 4. Clean Up After `gh aw audit`

`gh aw audit <run-id>` writes downloaded artifacts under `.github/aw/logs/` in the current working directory. Always remove `.github/aw/logs/` before finishing so the primary repository checkout stays clean.
