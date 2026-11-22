"""Shared pytest fixtures. Puts the repository root on sys.path so modules
import as `src.*` regardless of where pytest is invoked from."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_csv() -> Path:
    return FIXTURES / "sample_flights.csv"


@pytest.fixture(scope="session")
def cleaned_fixture(tmp_path_factory, fixture_csv) -> "object":
    """Clean the committed fixture once and share the DataFrame."""
    from src.common.config import load_settings
    from src.preprocessing.clean_data import clean_dataframe, read_source

    settings = load_settings()
    frame = read_source(fixture_csv)
    cleaned, quarantine, rejections, duplicates = clean_dataframe(frame, settings)
    return {
        "cleaned": cleaned,
        "quarantine": quarantine,
        "rejections": rejections,
        "duplicates": duplicates,
    }
