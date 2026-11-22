"""HTTP client for the airline-delay API.

The dashboard never computes metrics itself: it renders whatever the API
returns. Every call is cached for a short TTL so page switches do not hammer the
API, and every failure is translated into a user-safe ApiError.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import requests
import streamlit as st

from src.common.config import load_settings

SETTINGS = load_settings()
DEFAULT_BASE_URL = SETTINGS.api_url
CACHE_TTL = int(SETTINGS.get("dashboard.cache_ttl_seconds", 60))
TIMEOUT_SECONDS = 10


@dataclass
class ApiError(Exception):
    message: str
    status: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _cached_get(base_url: str, path: str, params: tuple[tuple[str, str], ...]) -> dict:
    query = dict(params)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = requests.get(f"{base_url.rstrip('/')}{path}", params=query, timeout=TIMEOUT_SECONDS)
            if response.status_code == 503:
                payload = response.json().get("error", {})
                raise ApiError(payload.get("message", "Analysis unavailable"), status=503)
            if response.status_code == 400:
                payload = response.json().get("error", {})
                raise ApiError(payload.get("message", "Invalid request"), status=400)
            response.raise_for_status()
            return response.json()
        except ApiError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.4)
    raise ApiError(
        f"Cannot reach the analytics API at {base_url}. Start it with: python -m src.backend.app"
    ) from last_error


class AnalyticsClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or DEFAULT_BASE_URL

    def _get(self, path: str, **params: Any) -> dict:
        clean = {key: str(value) for key, value in params.items() if value not in (None, "")}
        return _cached_get(self.base_url, path, tuple(sorted(clean.items())))

    def health(self) -> dict:
        return self._get("/api/health")

    def metadata(self) -> dict:
        return self._get("/api/metadata")

    def summary(self) -> dict:
        return self._get("/api/summary")

    def airlines(self, airline: list[str] | None = None, limit: int = 500, sort: str | None = None, order: str = "desc") -> dict:
        return self._get(
            "/api/airlines",
            airline=",".join(airline) if airline else None,
            limit=limit,
            sort=sort,
            order=order,
        )

    def airports(self, role: str | None = None, min_flights: int = 0, limit: int = 500, sort: str | None = None) -> dict:
        return self._get("/api/airports", role=role, min_flights=min_flights, limit=limit, sort=sort, order="desc")

    def routes(
        self,
        origin: str | None = None,
        destination: str | None = None,
        min_flights: int | None = None,
        limit: int = 500,
        sort: str | None = None,
    ) -> dict:
        return self._get(
            "/api/routes",
            origin=origin,
            destination=destination,
            min_flights=min_flights,
            limit=limit,
            sort=sort,
            order="desc",
        )

    def monthly(self, year_from: int | None = None, year_to: int | None = None) -> dict:
        return self._get("/api/trends/monthly", year_from=year_from, year_to=year_to, limit=500)

    def day_of_week(self) -> dict:
        return self._get("/api/trends/day-of-week")

    def delay_causes(self) -> dict:
        return self._get("/api/delay-causes")

    def delay_categories(self) -> dict:
        return self._get("/api/delay-categories")

    def cancellations(self, airline: list[str] | None = None, year: int | None = None, month: int | None = None, limit: int = 500) -> dict:
        return self._get(
            "/api/cancellations",
            airline=",".join(airline) if airline else None,
            year=year,
            month=month,
            limit=limit,
        )

    def cancellation_airports(self, year: int | None = None, month: int | None = None, limit: int = 500) -> dict:
        return self._get("/api/cancellations/airports", year=year, month=month, limit=limit)


def clear_cache() -> None:
    _cached_get.clear()
