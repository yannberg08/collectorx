#!/usr/bin/env bash
# Run the repository validation suite.

set -euo pipefail

PYTHON_BIN="${PYTHON:-python3}"

"$PYTHON_BIN" tools/validate_project.py
