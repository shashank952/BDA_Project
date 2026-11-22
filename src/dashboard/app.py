"""Streamlit entry point for the airline delay analytics dashboard.

Run:
    streamlit run src/dashboard/app.py

The app talks only to the Flask API (default http://127.0.0.1:5050). It never
runs Hadoop or recomputes a metric locally.

Note on layout: page modules live in `views/` rather than `pages/` because
Streamlit auto-discovers a sibling `pages/` directory and would add its own
navigation next to the explicit sidebar navigation used here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

st.set_page_config(
    page_title="Airline Flight Delay Analysis",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.dashboard import theme  # noqa: E402
from src.dashboard.api_client import AnalyticsClient, ApiError, clear_cache  # noqa: E402
from src.dashboard.views import (  # noqa: E402
    airline_performance,
    airport_routes,
    delay_causes,
    overview,
    time_analysis,
)

PAGES = {
    "Overview": overview,
    "Airline performance": airline_performance,
    "Airport and routes": airport_routes,
    "Time analysis": time_analysis,
    "Delay causes and cancellations": delay_causes,
}

DEFINITIONS = """
**Total flights** - flight records after the documented deduplication rule.

**Average delay** - mean of valid delay measurements in minutes. Negative values are early
departures or arrivals and are kept, not clamped to zero.

**Delay rate** - flights delayed 15 minutes or more divided by flights with a valid
measurement for that metric. Cancelled and most diverted flights have no arrival
measurement and therefore do not enter the arrival-delay denominator.

**Cancellation rate** - cancelled flights divided by all flight records.

**Delay categories** - on time < 15 min, minor 15-29, moderate 30-59, severe 60+ minutes.
These are project-defined bands, not an official aviation standard.

**Delay causes** - minutes attributed by the reporting carrier. BTS reports these only for
flights delayed 15 minutes or more, so a missing entry means "not reported", not zero.
"""


def sidebar(client: AnalyticsClient) -> str:
    with st.sidebar:
        st.title("Airline flight delays")
        st.caption("BTS On-Time Performance · Hadoop HDFS · MapReduce · Hive")
        page = st.radio("Analysis", options=list(PAGES), label_visibility="collapsed")

        st.divider()
        try:
            health = client.health()
            st.success(f"API online - {len(health.get('analytics_available', []))} analyses available")
        except ApiError:
            st.error("API offline")
            st.caption("Start it with: python -m src.backend.app")

        try:
            metadata = client.metadata()
            dataset = metadata.get("dataset", {})
            processing = metadata.get("processing", {})
            st.markdown("**Dataset**")
            st.caption(
                f"Period: {dataset.get('period_from') or 'n/a'} to {dataset.get('period_to') or 'n/a'}\n\n"
                f"Cleaned records: {dataset.get('records_cleaned') or 0:,}\n\n"
                f"Quarantined: {dataset.get('records_quarantined') or 0:,}"
            )
            if processing.get("last_updated"):
                st.caption(f"Last successful processing: {processing['last_updated']}")
        except ApiError:
            st.caption("Metadata unavailable.")

        st.divider()
        st.session_state.setdefault("theme_mode", theme.DEFAULT_MODE)
        choice = st.radio(
            "Appearance",
            options=["Light", "Dark"],
            index=0 if st.session_state["theme_mode"] == "light" else 1,
            horizontal=True,
            key="appearance_choice",
            help="Switches the chart palette and the app chrome. Data tables follow the app base theme.",
        )
        st.session_state["theme_mode"] = choice.lower()

        if st.button("Refresh data", width="stretch"):
            clear_cache()
            st.rerun()

        with st.expander("Metric definitions"):
            st.markdown(DEFINITIONS)

        st.caption("Historical analysis of 2025 flight records; not a real-time tracker.")
    return page


def main() -> None:
    # Read the widget value directly: it is already updated on the rerun that the
    # radio click triggers, whereas the mirrored theme_mode is written later in sidebar().
    mode = str(st.session_state.get("appearance_choice", theme.DEFAULT_MODE)).lower()
    theme.apply_mode(mode)
    st.markdown(theme.css(mode), unsafe_allow_html=True)

    client = AnalyticsClient()
    page = sidebar(client)
    st.title(page)

    try:
        PAGES[page].render(client)
    except ApiError as error:
        st.error(str(error))
        if error.status == 503:
            st.info(
                "Analytical outputs have not been generated yet. Run the pipeline "
                "(cleaning, MapReduce, Hive) or `python scripts/export_results.py`."
            )
        if st.button("Retry", key="retry_button"):
            clear_cache()
            st.rerun()


main()
