#!/usr/bin/env bash
set -euo pipefail

DEFAULT_PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
PYTHON_BIN="${DEFAULT_PYTHON}"
SOURCE_DIR=""
EZSNMP_SPEC=""

usage() {
    cat <<'EOF'
Usage: update_local_desktop.sh --source-dir <worktree_or_repo> [options]

Install ezsnmp_data_logger non-editably into macOS Framework Python 3.13,
clean local build artifacts from --source-dir, and run smoke tests.

Options:
  --source-dir <path>    Path to the ezsnmp_data_logger repo or worktree (required).
  --ezsnmp-spec <spec>   Optional ezsnmp pip requirement or wheel path to install first.
  --python <path>        Override target Python executable
                         (default: /Library/Frameworks/Python.framework/Versions/3.13/bin/python3).
  -h, --help             Show this help message and exit.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source-dir)
            [[ $# -ge 2 ]] || { echo "Error: --source-dir requires a value" >&2; exit 2; }
            SOURCE_DIR="$2"
            shift 2
            ;;
        --ezsnmp-spec)
            [[ $# -ge 2 ]] || { echo "Error: --ezsnmp-spec requires a value" >&2; exit 2; }
            EZSNMP_SPEC="$2"
            shift 2
            ;;
        --python)
            [[ $# -ge 2 ]] || { echo "Error: --python requires a value" >&2; exit 2; }
            PYTHON_BIN="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "${SOURCE_DIR}" ]]; then
    echo "Error: --source-dir is required." >&2
    usage >&2
    exit 2
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
    echo "Error: --source-dir does not exist: ${SOURCE_DIR}" >&2
    exit 1
fi

SOURCE_DIR="$(cd "${SOURCE_DIR}" && pwd)"

if [[ ! -f "${SOURCE_DIR}/pyproject.toml" && ! -f "${SOURCE_DIR}/setup.py" && ! -f "${SOURCE_DIR}/setup.cfg" ]]; then
    echo "Error: --source-dir does not appear to be a Python package root: ${SOURCE_DIR}" >&2
    exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Error: Target Python executable not found or not executable: ${PYTHON_BIN}" >&2
    exit 1
fi

clean_build_artifacts() {
    rm -rf "${SOURCE_DIR}/build"
    find "${SOURCE_DIR}" -maxdepth 2 -name "*.egg-info" -exec rm -rf {} +
}

echo "Cleaning pre-existing build artifacts in ${SOURCE_DIR}..."
clean_build_artifacts

if [[ -n "${EZSNMP_SPEC}" ]]; then
    echo "Installing ezsnmp spec (${EZSNMP_SPEC}) into ${PYTHON_BIN}..."
    "${PYTHON_BIN}" -m pip install --upgrade --force-reinstall "${EZSNMP_SPEC}"
fi

echo "Installing ${SOURCE_DIR} non-editably into ${PYTHON_BIN}..."
"${PYTHON_BIN}" -m pip install --no-build-isolation --force-reinstall --no-deps "${SOURCE_DIR}"

echo "Cleaning post-install build artifacts in ${SOURCE_DIR}..."
clean_build_artifacts

PYTHON_BIN_DIR="$(dirname "${PYTHON_BIN}")"
CLI_BIN="${PYTHON_BIN_DIR}/ezsnmp-data-logger"

echo "Running smoke test: version --json..."
if [[ -x "${CLI_BIN}" ]]; then
    "${CLI_BIN}" version --json
else
    "${PYTHON_BIN}" -m ezsnmp_data_logger version --json
fi

echo "Running smoke test: ezsnmp_data_logger.gui import..."
"${PYTHON_BIN}" -c "import ezsnmp_data_logger.gui; print('GUI import OK:', ezsnmp_data_logger.gui.__file__)"

echo "Local desktop update and smoke tests completed successfully."
