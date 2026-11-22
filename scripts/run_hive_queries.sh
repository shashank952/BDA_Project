#!/usr/bin/env bash
# Thin wrapper for Linux/macOS. Requires HIVE_HOME and a reachable HDFS.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m src.hive.run_queries "$@"
