#!/bin/bash
# Network Monitor Launcher
# Shell script wrapper to launch the Python application

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTENTS_DIR="$(dirname "$SCRIPT_DIR")"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

# Verify Resources directory exists
if [ ! -d "${RESOURCES_DIR}" ]; then
    echo "Error: Resources directory not found at ${RESOURCES_DIR}" >&2
    exit 1
fi

# Set up environment
export PYTHONPATH="${RESOURCES_DIR}"

# Change to resources directory
cd "${RESOURCES_DIR}" || exit 1

# Find Python 3.10 (try common locations)
PYTHON_PATHS=(
    "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3"
    "/usr/local/bin/python3.10"
    "/opt/homebrew/bin/python3.10"
    "$(which python3.10)"
    "$(which python3)"
)

PYTHON_CMD=""
for path in "${PYTHON_PATHS[@]}"; do
    if [ -f "$path" ] && [ -x "$path" ]; then
        PYTHON_CMD="$path"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "Error: Could not find Python 3.10" >&2
    exit 1
fi

# Execute Python
exec "$PYTHON_CMD" -m netmonitor "$@"

