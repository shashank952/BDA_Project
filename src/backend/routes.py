"""HTTP routes for the analytics API.

Response shape (all list endpoints):
    {
      "data": [ {..row..}, ... ],
      "pagination": {"total": n, "limit": n, "offset": n, "returned": n},
      "filters": {..echoed filters..},
      "generated_at": "UTC ISO-8601"
    }

Parameter validation is explicit: bad input returns 400 with a message that
names the offending parameter, and no internal filesystem detail is ever echoed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from src.backend import services

api = Blueprint("api", __name__, url_prefix="/api")

MAX_LIMIT_KEY = "api.max_limit"


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _max_limit() -> int:
    return int(services.load_settings_value(MAX_LIMIT_KEY))


def _int_param(name: str, default=None, minimum=None, maximum=None):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiError(f"Query parameter '{name}' must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ApiError(f"Query parameter '{name}' must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ApiError(f"Query parameter '{name}' must be <= {maximum}")
    return value


def _limit_offset() -> tuple[int, int]:
    default = int(services.load_settings_value("api.default_limit"))
    limit = _int_param("limit", default, minimum=1, maximum=_max_limit())
    offset = _int_param("offset", 0, minimum=0)
    return limit, offset


def _order() -> str:
    order = (request.args.get("order") or "desc").lower()
    if order not in {"asc", "desc"}:
        raise ApiError("Query parameter 'order' must be 'asc' or 'desc'")
    return order


def _list_param(name: str) -> list[str]:
    values: list[str] = []
    for raw in request.args.getlist(name):
        values.extend(part.strip().upper() for part in raw.split(",") if part.strip())
    return values


def _envelope(frame, pagination, **extra):
    payload = {
        "data": services.records(frame),
        "pagination": pagination,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    payload.update(extra)
    return jsonify(payload)


@api.get("/health")
def health():
    analytics = services.paths().analytics
    try:
        available = sorted(path.stem for path in analytics.glob("*.csv"))
    except OSError:
        available = []
    return jsonify(
        {
            "status": "ok",
            "service": "airline-delay-api",
            "version": services.load_settings_value("project.version"),
            "analytics_available": available,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )


@api.get("/summary")
def summary():
    payload = services.summary()
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return jsonify(payload)


@api.get("/airlines")
def airlines():
    limit, offset = _limit_offset()
    frame, pagination = services.airlines(
        _list_param("airline"), limit, offset, request.args.get("sort"), _order()
    )
    return _envelope(frame, pagination, filters={"airline": _list_param("airline")})


@api.get("/airports")
def airports():
    limit, offset = _limit_offset()
    role = request.args.get("role")
    if role and role not in {"departure", "arrival"}:
        raise ApiError("Query parameter 'role' must be 'departure' or 'arrival'")
    min_flights = _int_param("min_flights", 0, minimum=0)
    frame, pagination = services.airports(
        role, _list_param("airport"), min_flights, limit, offset, request.args.get("sort"), _order()
    )
    return _envelope(
        frame, pagination, filters={"role": role, "airport": _list_param("airport"), "min_flights": min_flights}
    )


@api.get("/routes")
def routes():
    limit, offset = _limit_offset()
    min_flights = _int_param("min_flights", None, minimum=0)
    if min_flights is None:
        min_flights = int(services.load_settings_value("analytics.min_route_flights"))
    frame, pagination = services.routes(
        request.args.get("origin"),
        request.args.get("destination"),
        min_flights,
        limit,
        offset,
        request.args.get("sort"),
        _order(),
    )
    return _envelope(
        frame,
        pagination,
        filters={
            "origin": request.args.get("origin"),
            "destination": request.args.get("destination"),
            "min_flights": min_flights,
        },
    )


@api.get("/trends/monthly")
def monthly_trends():
    limit, offset = _limit_offset()
    year_from = _int_param("year_from", None, minimum=1987, maximum=2100)
    year_to = _int_param("year_to", None, minimum=1987, maximum=2100)
    if year_from and year_to and year_from > year_to:
        raise ApiError("'year_from' must be <= 'year_to'")
    frame, pagination = services.monthly(year_from, year_to, limit, offset)
    return _envelope(frame, pagination, filters={"year_from": year_from, "year_to": year_to})


@api.get("/trends/day-of-week")
def day_of_week():
    return _envelope(services.day_of_week(), {"total": 7, "limit": 7, "offset": 0, "returned": 7})


@api.get("/delay-causes")
def delay_causes():
    frame = services.delay_causes()
    return _envelope(frame, {"total": len(frame), "limit": len(frame), "offset": 0, "returned": len(frame)})


@api.get("/delay-categories")
def delay_categories():
    frame = services.delay_categories()
    return _envelope(frame, {"total": len(frame), "limit": len(frame), "offset": 0, "returned": len(frame)})


@api.get("/cancellations")
def cancellations():
    limit, offset = _limit_offset()
    year = _int_param("year", None, minimum=1987, maximum=2100)
    month = _int_param("month", None, minimum=1, maximum=12)
    frame, pagination = services.cancellations(_list_param("airline"), year, month, limit, offset)
    return _envelope(frame, pagination, filters={"airline": _list_param("airline"), "year": year, "month": month})


@api.get("/cancellations/airports")
def cancellation_airports():
    limit, offset = _limit_offset()
    year = _int_param("year", None, minimum=1987, maximum=2100)
    month = _int_param("month", None, minimum=1, maximum=12)
    frame, pagination = services.cancellation_airports(year, month, limit, offset)
    return _envelope(frame, pagination, filters={"year": year, "month": month})


@api.get("/metadata")
def metadata():
    return jsonify(services.metadata())
