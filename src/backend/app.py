"""Flask application factory for the airline delay analytics API.

Run:
    python -m src.backend.app
    (or) flask --app src.backend.app:create_app run --port 5000
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.backend import services  # noqa: E402
from src.backend.routes import ApiError, api  # noqa: E402
from src.common.config import load_settings  # noqa: E402


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(TESTING=False, JSON_SORT_KEYS=False)
    if test_config:
        app.config.update(test_config)
    app.register_blueprint(api)

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify({"error": {"type": "invalid_request", "message": error.message}}), error.status

    @app.errorhandler(services.InvalidParameter)
    def handle_invalid_parameter(error: services.InvalidParameter):
        return jsonify({"error": {"type": "invalid_request", "message": str(error)}}), 400

    @app.errorhandler(services.OutputUnavailable)
    def handle_unavailable(error: services.OutputUnavailable):
        return (
            jsonify({"error": {"type": "analysis_unavailable", "message": str(error)}}),
            503,
        )

    @app.errorhandler(404)
    def handle_not_found(_error):
        return jsonify({"error": {"type": "not_found", "message": "Unknown endpoint"}}), 404

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        return (
            jsonify({"error": {"type": error.name.lower().replace(" ", "_"), "message": error.description}}),
            error.code,
        )

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        app.logger.exception("Unhandled API error")
        return (
            jsonify(
                {
                    "error": {
                        "type": "internal_error",
                        "message": "The server could not complete the request. Check the API logs for details.",
                    }
                }
            ),
            500,
        )

    @app.get("/")
    def index():
        return jsonify(
            {
                "service": "airline-delay-api",
                "endpoints": [
                    "/api/health",
                    "/api/summary",
                    "/api/airlines",
                    "/api/airports",
                    "/api/routes",
                    "/api/trends/monthly",
                    "/api/trends/day-of-week",
                    "/api/delay-causes",
                    "/api/delay-categories",
                    "/api/cancellations",
                    "/api/cancellations/airports",
                    "/api/metadata",
                ],
            }
        )

    return app


def main() -> None:
    settings = load_settings()
    host = os.environ.get("AIRLINE_API_HOST", settings.get("api.host", "127.0.0.1"))
    port = int(os.environ.get("AIRLINE_API_PORT", settings.get("api.port", 5000)))
    app = create_app()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
