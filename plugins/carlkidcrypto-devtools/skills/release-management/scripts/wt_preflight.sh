#!/usr/bin/env bash
set -euo pipefail

# wt_preflight.sh - Safe Git worktree preflight, creation, and pruning helper.
#
# Enforces multi-agent worktree isolation:
# - Never modifies or deletes other agents' worktrees.
# - Checks primary checkout cleanliness and branch (main/master).
# - Detects cloud-sync duplicate refs (* (* in .git/refs).
# - Creates sibling worktrees at ../wt-<repo>-<task-name>.

usage() {
    cat <<'EOF'
Usage:
  wt_preflight.sh check [--repo-dir PATH]
  wt_preflight.sh create <repo-dir> <branch> <task-name> [--existing]
  wt_preflight.sh prune <repo-dir> <worktree-path>

Subcommands:
  check    List active worktrees, verify primary checkout is clean on main/master,
           and detect cloud-sync duplicate refs (* (* in .git/refs).
  create   Fetch origin and create ../wt-<repo>-<task-name> from origin/main
           (or check out an existing branch when --existing is passed).
  prune    Safely remove and prune a dedicated worktree and verify git worktree list.
EOF
}

resolve_abs_dir() {
    local target="$1"
    if [ ! -d "$target" ]; then
        echo "Error: directory does not exist: $target" >&2
        return 1
    fi
    (cd "$target" && pwd -P)
}

get_git_common_dir() {
    local repo_dir="$1"
    local common_dir
    common_dir="$(git -C "$repo_dir" rev-parse --git-common-dir)"
    if [[ "$common_dir" != /* ]]; then
        common_dir="$(resolve_abs_dir "$repo_dir/$common_dir")"
    else
        common_dir="$(resolve_abs_dir "$common_dir")"
    fi
    printf '%s\n' "$common_dir"
}

get_primary_worktree() {
    local repo_dir="$1"
    git -C "$repo_dir" worktree list --porcelain | awk '/^worktree / { sub(/^worktree /, ""); print; exit }'
}

cmd_check() {
    local repo_dir="."
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --repo-dir)
                if [ "$#" -lt 2 ]; then
                    echo "Error: --repo-dir requires a path argument" >&2
                    return 2
                fi
                repo_dir="$2"
                shift 2
                ;;
            -h|--help)
                usage
                return 0
                ;;
            *)
                echo "Error: unknown argument for check: $1" >&2
                return 2
                ;;
        esac
    done

    local abs_repo
    abs_repo="$(resolve_abs_dir "$repo_dir")"

    if ! git -C "$abs_repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Error: not a git repository: $abs_repo" >&2
        return 1
    fi

    local common_dir primary_wt primary_branch dirty_status dup_refs
    common_dir="$(get_git_common_dir "$abs_repo")"
    primary_wt="$(get_primary_worktree "$abs_repo")"

    echo "=== Worktree Preflight Check ==="
    echo "Repository: $abs_repo"
    echo "Primary checkout: $primary_wt"
    echo ""
    echo "Active worktrees:"
    git -C "$abs_repo" worktree list
    echo ""

    local has_issues=0

    primary_branch="$(git -C "$primary_wt" symbolic-ref --short HEAD 2>/dev/null || echo "DETACHED")"
    if [ "$primary_branch" != "main" ] && [ "$primary_branch" != "master" ]; then
        echo "[WARN] Primary checkout branch is '$primary_branch' (expected 'main' or 'master')."
        has_issues=1
    else
        echo "[OK] Primary checkout is on '$primary_branch'."
    fi

    dirty_status="$(git -C "$primary_wt" status --porcelain)"
    if [ -n "$dirty_status" ]; then
        echo "[WARN] Primary checkout has uncommitted changes:"
        printf '%s\n' "$dirty_status" | sed 's/^/  /'
        has_issues=1
    else
        echo "[OK] Primary checkout working tree is clean."
    fi

    if [ -d "$common_dir/refs" ]; then
        dup_refs="$(find "$common_dir/refs" -name "* (*" 2>/dev/null || true)"
    else
        dup_refs=""
    fi

    if [ -n "$dup_refs" ]; then
        echo "[WARN] Cloud-sync duplicate refs detected in $common_dir/refs:"
        printf '%s\n' "$dup_refs" | sed 's/^/  /'
        echo "  To clean: find \"$common_dir/refs\" -name \"* (*\" -delete"
        has_issues=1
    else
        echo "[OK] No cloud-sync duplicate refs found."
    fi

    if [ "$has_issues" -ne 0 ]; then
        echo ""
        echo "Summary: Preflight check found warnings."
        return 1
    fi

    echo ""
    echo "Summary: Preflight check passed."
    return 0
}

cmd_create() {
    local existing=0
    local positional=()

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --existing)
                existing=1
                shift
                ;;
            -h|--help)
                usage
                return 0
                ;;
            -*)
                echo "Error: unknown option for create: $1" >&2
                return 2
                ;;
            *)
                positional+=("$1")
                shift
                ;;
        esac
    done

    if [ "${#positional[@]}" -ne 3 ]; then
        echo "Error: create requires <repo-dir> <branch> <task-name>" >&2
        usage >&2
        return 2
    fi

    local repo_dir="${positional[0]}"
    local branch="${positional[1]}"
    local task_name="${positional[2]}"

    local abs_repo primary_wt repo_name parent_dir wt_path
    abs_repo="$(resolve_abs_dir "$repo_dir")"
    if ! git -C "$abs_repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        echo "Error: not a git repository: $abs_repo" >&2
        return 1
    fi

    primary_wt="$(get_primary_worktree "$abs_repo")"
    repo_name="$(basename "$primary_wt")"
    parent_dir="$(dirname "$primary_wt")"
    wt_path="${parent_dir}/wt-${repo_name}-${task_name}"

    if [ -e "$wt_path" ]; then
        echo "Error: target worktree path already exists (refusing to overwrite): $wt_path" >&2
        return 1
    fi

    local in_use
    in_use="$(git -C "$abs_repo" worktree list --porcelain | awk -v b="refs/heads/${branch}" '$1 == "branch" && $2 == b { print "yes"; exit }')"
    if [ "$in_use" = "yes" ]; then
        echo "Error: branch '$branch' is already checked out in an existing worktree." >&2
        return 1
    fi

    git -C "$abs_repo" fetch origin

    if [ "$existing" -eq 1 ]; then
        git -C "$abs_repo" worktree add "$wt_path" "$branch"
    else
        local base_ref="origin/main"
        if ! git -C "$abs_repo" rev-parse --verify --quiet "$base_ref" >/dev/null; then
            if git -C "$abs_repo" rev-parse --verify --quiet "origin/master" >/dev/null; then
                base_ref="origin/master"
            else
                echo "Error: neither origin/main nor origin/master exists in $abs_repo" >&2
                return 1
            fi
        fi
        git -C "$abs_repo" worktree add -b "$branch" "$wt_path" "$base_ref"
    fi

    printf '%s\n' "$wt_path"
}

cmd_prune() {
    if [ "$#" -lt 2 ]; then
        echo "Error: prune requires <repo-dir> <worktree-path>" >&2
        usage >&2
        return 2
    fi

    local repo_dir="$1"
    local wt_path="$2"

    local abs_repo primary_wt abs_wt
    abs_repo="$(resolve_abs_dir "$repo_dir")"
    primary_wt="$(get_primary_worktree "$abs_repo")"

    if [ -d "$wt_path" ]; then
        abs_wt="$(resolve_abs_dir "$wt_path")"
    else
        abs_wt="$wt_path"
    fi

    if [ "$abs_wt" = "$primary_wt" ]; then
        echo "Error: refusing to remove primary checkout: $primary_wt" >&2
        return 1
    fi

    local registered
    registered="$(git -C "$abs_repo" worktree list --porcelain | awk -v target="$abs_wt" '$1 == "worktree" { sub(/^worktree /, ""); if ($0 == target) { print "yes"; exit } }')"
    if [ "$registered" != "yes" ]; then
        echo "Error: worktree path is not registered in $abs_repo: $abs_wt" >&2
        return 1
    fi

    git -C "$abs_repo" worktree remove "$abs_wt"
    git -C "$abs_repo" worktree prune
    echo "Remaining worktrees:"
    git -C "$abs_repo" worktree list
}

main() {
    if [ "$#" -eq 0 ]; then
        usage >&2
        return 2
    fi

    local subcmd="$1"
    shift

    case "$subcmd" in
        check)
            cmd_check "$@"
            ;;
        create)
            cmd_create "$@"
            ;;
        prune)
            cmd_prune "$@"
            ;;
        -h|--help|help)
            usage
            return 0
            ;;
        *)
            echo "Error: unknown subcommand: $subcmd" >&2
            usage >&2
            return 2
            ;;
    esac
}

main "$@"
