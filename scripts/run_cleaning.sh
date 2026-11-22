#!/usr/bin/env bash
# Thin wrapper for Linux/macOS. The Python entry point is identical everywhere.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m src.preprocessing.clean_data "$@"
