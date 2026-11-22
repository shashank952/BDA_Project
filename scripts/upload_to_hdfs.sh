#!/usr/bin/env bash
# Thin wrapper for Linux/macOS: HDFS layout, raw and cleaned uploads, verification.
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/hdfs_ops.py "$@"
