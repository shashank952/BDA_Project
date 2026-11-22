"""Time-based analysis page: monthly trend, day of week, delay categories."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.dashboard import theme


def render(client) -> None:
    st.subheader("Time-based analysis")
    st.caption("Seasonality is measured on arrival delay, the passenger-visible outcome of a flight.")

    monthly = pd.DataFrame(client.monthly()["data"])
    if monthly.empty:
        theme.empty_state("No monthly data available.")
        return

    years = sorted(monthly["flight_year"].astype(int).unique())
    controls = st.columns([1, 1, 2])
    year_from = controls[0].selectbox("From year", options=years, index=0)
    year_to = controls[1].selectbox("To year", options=years, index=len(years) - 1)
    if year_from > year_to:
        st.warning("The start year is after the end year; showing the full period instead.")
        year_from, year_to = years[0], years[-1]

    filtered = pd.DataFrame(client.monthly(year_from=year_from, year_to=year_to)["data"])
    filtered = filtered.sort_values(["flight_year", "flight_month"])
    filtered["period"] = theme.months_label(filtered)

    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Scatter(
            x=filtered["period"],
            y=filtered["avg_arrival_delay"],
            name="Avg arrival delay (min)",
            mode="lines+markers",
            line=dict(color=theme.PRIMARY, width=2),
            hovertemplate="%{x}<br>Avg arrival delay %{y:.2f} min<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Bar(
            x=filtered["period"],
            y=filtered["cancellation_rate"],
            name="Cancellation rate (%)",
            marker_color=theme.GRID,
            hovertemplate="%{x}<br>Cancellation rate %{y:.2f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    theme.style(figure, "Monthly average arrival delay and cancellation rate", height=380)
    figure.update_yaxes(title_text="Minutes", secondary_y=False, gridcolor=theme.GRID)
    figure.update_yaxes(title_text="Cancellation rate (%)", secondary_y=True, showgrid=False)
    st.plotly_chart(figure, width="stretch", config=theme.CHART_CONFIG)

    columns = st.columns(2)
    weekday = pd.DataFrame(client.day_of_week()["data"])
    if weekday.empty:
        columns[0].info("No day-of-week data available.")
    else:
        weekday = weekday.sort_values("day_of_week")
        chart = go.Figure(
            go.Bar(
                x=weekday["day_name"],
                y=weekday["avg_arrival_delay"],
                marker_color=theme.PRIMARY,
                customdata=weekday[["arrival_delay_rate", "total_flights"]].to_numpy(),
                hovertemplate=(
                    "%{x}<br>Avg arrival delay %{y:.2f} min"
                    "<br>Delay rate %{customdata[0]:.2f}%"
                    "<br>Flights %{customdata[1]:,}<extra></extra>"
                ),
            )
        )
        theme.style(chart, "Average arrival delay by day of week", height=360, y_title="Minutes")
        columns[0].plotly_chart(chart, width="stretch", config=theme.CHART_CONFIG)

    categories = pd.DataFrame(client.delay_categories()["data"])
    if categories.empty:
        columns[1].info("No delay-category data available.")
    else:
        chart = go.Figure(
            go.Pie(
                labels=categories["category_label"],
                values=categories["flights"],
                hole=0.55,
                marker=dict(colors=theme.SERIES, line=dict(color=theme.SURFACE, width=2)),
                hovertemplate="%{label}<br>%{value:,} flights<br>%{percent}<extra></extra>",
                textinfo="percent",
                sort=False,
            )
        )
        theme.style(chart, "Arrival-delay categories", height=360)
        chart.update_layout(legend=dict(orientation="v", y=0.5, x=1.02))
        columns[1].plotly_chart(chart, width="stretch", config=theme.CHART_CONFIG)

    st.caption(
        "Categories are project-defined: on time < 15 min, minor 15-29, moderate 30-59, severe 60+ minutes. "
        "Flights without an arrival measurement (cancelled or diverted) are reported as unknown."
    )

    table = theme.display_table(
        categories[["delay_category", "category_label", "flights", "share_pct"]],
        percent_columns=["share_pct"],
    )
    st.dataframe(table, width="stretch", hide_index=True)
    theme.download_button("Download delay-category table (CSV)", categories, "delay_categories.csv", "categories_download")
