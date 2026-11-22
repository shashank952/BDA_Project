"""Airline performance page: ranking, scatter and exportable table."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import theme

SORT_OPTIONS = {
    "Arrival-delay rate": "arrival_delay_rate",
    "Average arrival delay": "avg_arrival_delay",
    "Flight volume": "total_flights",
    "Cancellations": "cancellations",
}


def render(client) -> None:
    st.subheader("Airline performance")
    st.caption(
        "Average delay and delay rates per reporting carrier. Rates use flights with a valid "
        "arrival measurement as the denominator; cancellations use all flight records."
    )

    everything = pd.DataFrame(client.airlines(limit=500)["data"])
    if everything.empty:
        theme.empty_state("No airline data available.")
        return

    labels = {
        row["airline_code"]: f"{row['airline_code']} - {row['airline_name']}"
        for _, row in everything.iterrows()
    }

    controls = st.columns([2, 1, 1])
    selected = controls[0].multiselect(
        "Airlines",
        options=list(labels),
        format_func=lambda code: labels[code],
        default=[],
        help="Leave empty to include every carrier.",
    )
    sort_label = controls[1].selectbox("Sort by", options=list(SORT_OPTIONS), index=0)
    order = controls[2].radio("Order", options=["Descending", "Ascending"], horizontal=True)

    payload = client.airlines(
        airline=selected or None,
        limit=500,
        sort=SORT_OPTIONS[sort_label],
        order="desc" if order == "Descending" else "asc",
    )
    frame = pd.DataFrame(payload["data"])
    if frame.empty:
        theme.empty_state()
        return

    st.caption(f"{payload['pagination']['total']} carriers shown")

    chart_columns = st.columns(2)
    ordered = frame.sort_values("avg_arrival_delay")
    bar = go.Figure(
        go.Bar(
            x=ordered["avg_arrival_delay"],
            y=ordered["airline_name"],
            orientation="h",
            marker_color=theme.PRIMARY,
            customdata=ordered[["valid_arrival_flights", "arrival_delay_rate"]].to_numpy(),
            hovertemplate=(
                "%{y}<br>Avg arrival delay %{x:.2f} min"
                "<br>Valid measurements %{customdata[0]:,}"
                "<br>Delay rate %{customdata[1]:.2f}%<extra></extra>"
            ),
        )
    )
    theme.style(bar, "Average arrival delay by airline", height=420, x_title="Minutes")
    chart_columns[0].plotly_chart(bar, width="stretch", config=theme.CHART_CONFIG)

    scatter = go.Figure(
        go.Scatter(
            x=frame["total_flights"],
            y=frame["arrival_delay_rate"],
            mode="markers",
            marker=dict(
                size=(frame["valid_arrival_flights"].fillna(0) / max(frame["valid_arrival_flights"].max(), 1) * 34 + 8),
                color=theme.ACCENT,
                opacity=0.75,
                line=dict(color=theme.SURFACE, width=1),
            ),
            text=frame["airline_name"],
            customdata=frame[["avg_arrival_delay", "total_flights"]].to_numpy(),
            hovertemplate=(
                "%{text}<br>Delay rate %{y:.2f}%"
                "<br>Flights %{customdata[1]:,}"
                "<br>Avg arrival delay %{customdata[0]:.2f} min<extra></extra>"
            ),
        )
    )
    theme.style(scatter, "Delay rate versus flight volume", height=420, x_title="Flight records", y_title="Arrival-delay rate (%)")
    chart_columns[1].plotly_chart(scatter, width="stretch", config=theme.CHART_CONFIG)

    table = theme.display_table(
        frame[
            [
                "airline_code",
                "airline_name",
                "total_flights",
                "valid_arrival_flights",
                "avg_arrival_delay",
                "delayed_arrivals",
                "arrival_delay_rate",
                "cancellations",
                "cancellation_rate",
            ]
        ],
        percent_columns=["arrival_delay_rate", "cancellation_rate"],
        number_columns={"avg_arrival_delay": 2},
    )
    st.dataframe(table, width="stretch", hide_index=True)
    theme.download_button("Download filtered airline table (CSV)", frame, "airline_performance.csv", "airline_download")
