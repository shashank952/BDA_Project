#!/usr/bin/env bash
# Thin wrapper for Linux/macOS. Requires a reachable HDFS and HADOOP_HOME.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m src.mapreduce.run_jobs "$@"
