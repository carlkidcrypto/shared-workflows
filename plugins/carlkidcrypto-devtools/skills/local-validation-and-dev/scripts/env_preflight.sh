#!/usr/bin/env bash
# Preflight environment helper for macOS and Linux local validation/development.
#
# Usage:
#   source env_preflight.sh          # Exports PATH, PKG_CONFIG_PATH, DYLD_LIBRARY_PATH
#   eval "$(./env_preflight.sh --print)"
#   ./env_preflight.sh --print       # Print shell export statements
#   ./env_preflight.sh --help        # Show usage

_env_preflight_is_sourced() {
  if [[ -n "${ZSH_EVAL_CONTEXT:-}" ]]; then
    [[ "${ZSH_EVAL_CONTEXT}" == *:file* ]]
    return $?
  fi
  if [[ -n "${BASH_VERSION:-}" ]]; then
    [[ "${BASH_SOURCE[0]}" != "${0}" ]]
    return $?
  fi
  return 1
}

_env_preflight_prepend_unique() {
  local current="$1"
  local candidate="$2"
  [[ -d "${candidate}" ]] || {
    printf '%s' "${current}"
    return 0
  }
  case ":${current}:" in
    *":${candidate}:"*)
      printf '%s' "${current}"
      ;;
    "::")
      printf '%s' "${candidate}"
      ;;
    *)
      printf '%s:%s' "${candidate}" "${current}"
      ;;
  esac
}

_env_preflight_build_env() {
  local os_name
  os_name="$(uname -s)"

  local new_path="${PATH:-}"
  local new_pkg_config="${PKG_CONFIG_PATH:-}"
  local new_dyld="${DYLD_LIBRARY_PATH:-}"

  local -a path_candidates=()
  local -a pkg_candidates=()
  local -a dyld_candidates=()

  if [[ "${os_name}" == "Darwin" ]]; then
    # Prepend in reverse priority order so highest-priority ends up first.
    path_candidates=(
      "/usr/local/opt/libpq/bin"
      "/usr/local/opt/net-snmp/bin"
      "/usr/local/opt/openssl@3/bin"
      "/usr/local/bin"
      "/opt/homebrew/opt/libpq/bin"
      "/opt/homebrew/opt/net-snmp/bin"
      "/opt/homebrew/opt/openssl@3/bin"
      "/opt/homebrew/sbin"
      "/opt/homebrew/bin"
      "/Library/Frameworks/Python.framework/Versions/3.13/bin"
      "/Library/Frameworks/Python.framework/Versions/3.14/bin"
    )
    pkg_candidates=(
      "/usr/local/lib/pkgconfig"
      "/usr/local/opt/libpq/lib/pkgconfig"
      "/usr/local/opt/net-snmp/lib/pkgconfig"
      "/usr/local/opt/openssl@3/lib/pkgconfig"
      "/opt/homebrew/lib/pkgconfig"
      "/opt/homebrew/opt/libpq/lib/pkgconfig"
      "/opt/homebrew/opt/net-snmp/lib/pkgconfig"
      "/opt/homebrew/opt/openssl@3/lib/pkgconfig"
    )
    dyld_candidates=(
      "/usr/local/opt/libpq/lib"
      "/usr/local/opt/net-snmp/lib"
      "/usr/local/opt/openssl@3/lib"
      "/opt/homebrew/opt/libpq/lib"
      "/opt/homebrew/opt/net-snmp/lib"
      "/opt/homebrew/opt/openssl@3/lib"
    )
  else
    path_candidates=(
      "/usr/local/sbin"
      "/usr/local/bin"
      "${HOME}/.local/bin"
    )
    pkg_candidates=(
      "/usr/lib/pkgconfig"
      "/usr/lib/x86_64-linux-gnu/pkgconfig"
      "/usr/lib/aarch64-linux-gnu/pkgconfig"
      "/usr/local/lib/pkgconfig"
    )
  fi

  local dir
  for dir in "${path_candidates[@]}"; do
    new_path="$(_env_preflight_prepend_unique "${new_path}" "${dir}")"
  done
  for dir in "${pkg_candidates[@]}"; do
    new_pkg_config="$(_env_preflight_prepend_unique "${new_pkg_config}" "${dir}")"
  done
  for dir in "${dyld_candidates[@]}"; do
    new_dyld="$(_env_preflight_prepend_unique "${new_dyld}" "${dir}")"
  done

  export PATH="${new_path}"
  if [[ -n "${new_pkg_config}" ]]; then
    export PKG_CONFIG_PATH="${new_pkg_config}"
  fi
  if [[ -n "${new_dyld}" ]]; then
    export DYLD_LIBRARY_PATH="${new_dyld}"
  fi
}

_env_preflight_print_exports() {
  printf 'export PATH=%q\n' "${PATH}"
  if [[ -n "${PKG_CONFIG_PATH:-}" ]]; then
    printf 'export PKG_CONFIG_PATH=%q\n' "${PKG_CONFIG_PATH}"
  fi
  if [[ -n "${DYLD_LIBRARY_PATH:-}" ]]; then
    printf 'export DYLD_LIBRARY_PATH=%q\n' "${DYLD_LIBRARY_PATH}"
  fi
}

_env_preflight_usage() {
  cat <<'EOF'
Usage:
  source env_preflight.sh
  env_preflight.sh [--print] [--help]

Options:
  --print   Print shell-escaped export statements for PATH, PKG_CONFIG_PATH, and DYLD_LIBRARY_PATH.
  --help    Show this help message.
EOF
}

if _env_preflight_is_sourced; then
  _env_preflight_build_env
else
  set -euo pipefail
  mode="${1:---print}"
  case "${mode}" in
    --print|-p)
      _env_preflight_build_env
      _env_preflight_print_exports
      ;;
    --help|-h)
      _env_preflight_usage
      ;;
    *)
      printf 'Unknown option: %s\n' "${mode}" >&2
      _env_preflight_usage >&2
      exit 2
      ;;
  esac
fi
