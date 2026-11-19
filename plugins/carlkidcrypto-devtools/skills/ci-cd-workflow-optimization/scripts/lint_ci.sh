#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: lint_ci.sh [--allow-main] [--repo-dir DIR] [PYTHON_FILE ...]

Run standard CI/CD pre-push checks in a repository worktree:
  1. Verify HEAD is not on `main` (unless --allow-main is passed).
  2. Verify no helper scripts exist under `.github/script/` (must use `.github/scripts/`).
  3. Run `yamllint` on `.github/workflows/*.yml` (excluding `*.lock.yml` and `agentics-maintenance.yml`).
  4. Run `actionlint -shellcheck=` on `.github/workflows/*.yml` (excluding `*.lock.yml` and `agentics-maintenance.yml`).
  5. Run `black --check` on specified or git-changed Python files.
EOF
}

find_tool() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    command -v "$name"
    return 0
  fi
  local dir
  for dir in /opt/homebrew/bin /usr/local/bin; do
    if [[ -x "${dir}/${name}" ]]; then
      echo "${dir}/${name}"
      return 0
    fi
  done
  return 1
}

allow_main=false
repo_dir="."
py_files=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-main)
      allow_main=true
      shift
      ;;
    --repo-dir)
      if [[ $# -lt 2 ]]; then
        echo "Error: --repo-dir requires a path argument." >&2
        exit 2
      fi
      repo_dir="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        py_files+=("$1")
        shift
      done
      ;;
    -*)
      echo "Error: Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      py_files+=("$1")
      shift
      ;;
  esac
done

cd "$repo_dir"

git_bin="$(find_tool git)" || {
  echo "Error: git not found in PATH or /opt/homebrew/bin or /usr/local/bin." >&2
  exit 1
}

# 1. Branch safety check: HEAD != main unless --allow-main
current_branch="$("$git_bin" rev-parse --abbrev-ref HEAD)"
if [[ "$current_branch" == "main" && "$allow_main" == false ]]; then
  echo "Error: HEAD is on 'main'. Use a feature/worktree branch or pass --allow-main." >&2
  exit 1
fi
echo "[lint_ci] Branch check passed (HEAD=${current_branch})."

# 2. Helper script placement check: forbid .github/script/ (must be .github/scripts/)
if [[ -d ".github/script" ]]; then
  bad_scripts="$(find .github/script -type f 2>/dev/null || true)"
  if [[ -n "$bad_scripts" ]]; then
    echo "Error: Helper scripts found under .github/script/ (must be .github/scripts/):" >&2
    echo "$bad_scripts" >&2
    exit 1
  fi
fi
echo "[lint_ci] .github/script/ check passed."

# Collect workflow files excluding *.lock.yml and agentics-maintenance.yml
shopt -s nullglob
workflow_files=()
for wf in .github/workflows/*.yml .github/workflows/*.yaml; do
  base="$(basename "$wf")"
  if [[ "$base" == *.lock.yml || "$base" == "agentics-maintenance.yml" ]]; then
    continue
  fi
  workflow_files+=("$wf")
done
shopt -u nullglob

# 3. yamllint
if [[ ${#workflow_files[@]} -gt 0 ]]; then
  yamllint_bin="$(find_tool yamllint)" || {
    echo "Error: yamllint not found in PATH or /opt/homebrew/bin or /usr/local/bin." >&2
    exit 1
  }
  yamllint_args=()
  if [[ -f ".yamllint" ]]; then
    yamllint_args+=(-c ".yamllint")
  fi
  echo "[lint_ci] Running yamllint on ${#workflow_files[@]} workflow file(s)..."
  "$yamllint_bin" "${yamllint_args[@]}" "${workflow_files[@]}"
else
  echo "[lint_ci] No workflow files to lint with yamllint."
fi

# 4. actionlint -shellcheck=
if [[ ${#workflow_files[@]} -gt 0 ]]; then
  actionlint_bin="$(find_tool actionlint)" || {
    echo "Error: actionlint not found in PATH or /opt/homebrew/bin or /usr/local/bin." >&2
    exit 1
  }
  echo "[lint_ci] Running actionlint -shellcheck= on ${#workflow_files[@]} workflow file(s)..."
  "$actionlint_bin" -shellcheck= "${workflow_files[@]}"
else
  echo "[lint_ci] No workflow files to lint with actionlint."
fi

# 5. black --check on specified or changed Python files
if [[ ${#py_files[@]} -eq 0 ]]; then
  changed_candidates=""
  if "$git_bin" rev-parse --verify origin/main >/dev/null 2>&1; then
    changed_candidates+="$("$git_bin" diff --name-only --diff-filter=ACMRTUXB origin/main...HEAD || true)"$'\n'
  fi
  changed_candidates+="$("$git_bin" diff --name-only --diff-filter=ACMRTUXB HEAD 2>/dev/null || true)"$'\n'
  changed_candidates+="$("$git_bin" diff --name-only --cached --diff-filter=ACMRTUXB 2>/dev/null || true)"$'\n'
  changed_candidates+="$("$git_bin" ls-files --others --exclude-standard || true)"

  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    [[ "$path" == *.py ]] || continue
    [[ -f "$path" ]] || continue
    already_seen=false
    for existing in "${py_files[@]+"${py_files[@]}"}"; do
      if [[ "$existing" == "$path" ]]; then
        already_seen=true
        break
      fi
    done
    if [[ "$already_seen" == false ]]; then
      py_files+=("$path")
    fi
  done <<< "$changed_candidates"
fi

if [[ ${#py_files[@]} -gt 0 ]]; then
  black_bin="$(find_tool black)" || {
    echo "Error: black not found in PATH or /opt/homebrew/bin or /usr/local/bin." >&2
    exit 1
  }
  echo "[lint_ci] Running black --check on ${#py_files[@]} Python file(s)..."
  "$black_bin" --check "${py_files[@]}"
else
  echo "[lint_ci] No changed Python files to check with black."
fi

echo "[lint_ci] All checks passed."
