"""Central configuration loader.

Everything downstream (cleaning, MapReduce jobs, Hive DDL, API, dashboard)
reads the *same* settings and schema mapping from here so that column names,
thresholds and metric definitions cannot drift between layers.

Environment overrides (optional, for other machines):

    AIRLINE_HADOOP_HOME   override hdfs.hadoop_home
    AIRLINE_JAVA_HOME     override hdfs.java_home
    AIRLINE_HDFS_URI      override hdfs.uri
    AIRLINE_API_URL       override dashboard.api_url
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
SCHEMA_PATH = CONFIG_DIR / "schema_mapping.yaml"
AIRLINES_PATH = CONFIG_DIR / "airlines.csv"


class ConfigurationError(RuntimeError):
    """Raised when a project configuration file is missing or invalid."""


class Settings:
    """Read-only view over settings.yaml with repository-relative paths resolved."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    def section(self, name: str) -> dict[str, Any]:
        try:
            return dict(self._raw[name])
        except KeyError as exc:  # pragma: no cover - configuration guard
            raise ConfigurationError(f"Missing configuration section: {name}") from exc

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self._raw
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def path(self, key: str) -> Path:
        """Resolve a path declared under the `paths` section against REPO_ROOT."""
        value = self.get(f"paths.{key}")
        if value is None:
            raise ConfigurationError(f"Unknown path key: {key}")
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (REPO_ROOT / candidate)

    @property
    def hdfs_base(self) -> str:
        return str(self.get("hdfs.base"))

    @property
    def hadoop_home(self) -> Path:
        return Path(os.environ.get("AIRLINE_HADOOP_HOME") or self.get("hdfs.hadoop_home"))

    @property
    def java_home(self) -> Path:
        return Path(os.environ.get("AIRLINE_JAVA_HOME") or self.get("hdfs.java_home"))

    @property
    def hdfs_uri(self) -> str:
        return os.environ.get("AIRLINE_HDFS_URI") or str(self.get("hdfs.uri"))

    @property
    def mapreduce_framework(self) -> str:
        return str(os.environ.get("AIRLINE_MR_FRAMEWORK") or self.get("hdfs.framework", "local"))

    @property
    def api_url(self) -> str:
        return os.environ.get("AIRLINE_API_URL") or str(self.get("dashboard.api_url"))

    def ensure_directories(self) -> None:
        """Create every local output directory the pipeline writes to."""
        for key in (
            "data_raw",
            "data_processed",
            "data_quarantine",
            "data_sample",
            "outputs",
            "analytics_outputs",
            "reports",
            "logs",
        ):
            self.path(key).mkdir(parents=True, exist_ok=True)


def load_settings(path: Path | None = None) -> Settings:
    path = path or SETTINGS_PATH
    if not path.exists():
        raise ConfigurationError(f"Settings file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return Settings(raw)


def load_schema_mapping(path: Path | None = None) -> dict[str, Any]:
    path = path or SCHEMA_PATH
    if not path.exists():
        raise ConfigurationError(f"Schema mapping not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        mapping = yaml.safe_load(handle) or {}
    if "fields" not in mapping or "cleaned_column_order" not in mapping:
        raise ConfigurationError("schema_mapping.yaml must define `fields` and `cleaned_column_order`")
    return mapping


def field_specs(mapping: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    mapping = mapping or load_schema_mapping()
    return list(mapping["fields"])


def required_source_columns(mapping: dict[str, Any] | None = None) -> list[str]:
    return [spec["source"] for spec in field_specs(mapping) if spec.get("required")]


def optional_source_columns(mapping: dict[str, Any] | None = None) -> list[str]:
    return [spec["source"] for spec in field_specs(mapping) if not spec.get("required")]


def cleaned_columns(mapping: dict[str, Any] | None = None) -> list[str]:
    mapping = mapping or load_schema_mapping()
    return list(mapping["cleaned_column_order"])


def load_airlines(path: Path | None = None) -> dict[str, str]:
    path = path or AIRLINES_PATH
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["code"]: row["name"] for row in csv.DictReader(handle)}
