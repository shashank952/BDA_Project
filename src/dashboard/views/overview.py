"""Overview page: headline KPIs, monthly trend, top delayed airlines."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.dashboard import theme


def render(client) -> None:
    summary = client.summary()
    totals = summary["totals"]
    rates = summary["rates"]
    averages = summary["averages"]
    period = summary["period"]

    st.subheader("Network overview")
    st.caption(
        f"Dataset period {period['from']} to {period['to']} - "
        f"{totals['total_flights']:,} flight records. Delay threshold is 15 minutes."
    )

    columns = st.columns(5)
    columns[0].metric("Total flights", f"{totals['total_flights']:,}")
    columns[1].metric("Avg departure delay", f"{theme.number(averages['departure_delay_minutes'])} min")
    columns[2].metric("Avg arrival delay", f"{theme.number(averages['arrival_delay_minutes'])} min")
    columns[3].metric(
        "Arrival-delay rate",
        theme.percent(rates["arrival_delay_rate"]),
        help=f"{totals['arrival_delayed_flights']:,} flights delayed 15+ min out of "
        f"{totals['valid_arrival_flights']:,} with a valid arrival measurement",
    )
    columns[4].metric(
        "Cancellation rate",
        theme.percent(rates["cancellation_rate"]),
        help=f"{totals['cancelled_flights']:,} cancelled flights out of {totals['total_flights']:,} records",
    )

    monthly = pd.DataFrame(client.monthly()["data"])
    if monthly.empty:
        theme.empty_state("No monthly data available.")
    else:
        monthly = monthly.sort_values(["flight_year", "flight_month"])
        monthly["period"] = theme.months_label(monthly)
        figure = make_subplots(specs=[[{"secondary_y": True}]])
        figure.add_trace(
            go.Bar(
                x=monthly["period"],
                y=monthly["avg_arrival_delay"],
                name="Avg arrival delay (min)",
                marker_color=theme.PRIMARY,
                hovertemplate="%{x}<br>Avg arrival delay %{y:.2f} min<extra></extra>",
            ),
            secondary_y=False,
        )
        figure.add_trace(
            go.Scatter(
                x=monthly["period"],
                y=monthly["arrival_delay_rate"],
                name="Arrival-delay rate (%)",
                mode="lines+markers",
                line=dict(color=theme.ACCENT, width=2),
                hovertemplate="%{x}<br>Delay rate %{y:.2f}%<extra></extra>",
            ),
            secondary_y=True,
        )
        theme.style(figure, "Monthly arrival delay and delay rate", height=380)
        figure.update_yaxes(title_text="Avg arrival delay (min)", secondary_y=False, gridcolor=theme.GRID)
        figure.update_yaxes(title_text="Delay rate (%)", secondary_y=True, showgrid=False)
        st.plotly_chart(figure, width="stretch", config=theme.CHART_CONFIG)

    top_airlines = pd.DataFrame(client.airlines(limit=10, sort="arrival_delay_rate")["data"])
    st.markdown("##### Highest arrival-delay rates by airline")
    if top_airlines.empty:
        theme.empty_state("No airline data available.")
        return

    top_airlines = top_airlines.sort_values("arrival_delay_rate")
    figure = go.Figure(
        go.Bar(
            x=top_airlines["arrival_delay_rate"],
            y=top_airlines["airline_name"],
            orientation="h",
            marker_color=theme.PRIMARY,
            customdata=top_airlines[["total_flights", "valid_arrival_flights", "avg_arrival_delay"]].to_numpy(),
            hovertemplate=(
                "%{y}<br>Delay rate %{x:.2f}%"
                "<br>Flights %{customdata[0]:,}"
                "<br>Valid arrival measurements %{customdata[1]:,}"
                "<br>Avg arrival delay %{customdata[2]:.2f} min<extra></extra>"
            ),
        )
    )
    theme.style(figure, None, height=380, x_title="Arrival-delay rate (%)", y_title=None)
    st.plotly_chart(figure, width="stretch", config=theme.CHART_CONFIG)

    table = theme.display_table(
        top_airlines[
            [
                "airline_code",
                "airline_name",
                "total_flights",
                "valid_arrival_flights",
                "avg_arrival_delay",
                "arrival_delay_rate",
                "cancellation_rate",
            ]
        ].sort_values("arrival_delay_rate", ascending=False),
        percent_columns=["arrival_delay_rate", "cancellation_rate"],
        number_columns={"avg_arrival_delay": 2},
    )
    st.dataframe(table, width="stretch", hide_index=True)
    theme.download_button("Download airline table (CSV)", top_airlines, "top_airlines.csv", "overview_airlines")
