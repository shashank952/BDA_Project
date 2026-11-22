"""Delay causes and cancellation analysis page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import theme

CAUSE_CODE_COLUMNS = {
    "cancelled_carrier": "Carrier",
    "cancelled_weather": "Weather",
    "cancelled_nas": "National Aviation System",
    "cancelled_security": "Security",
}


def render(client) -> None:
    st.subheader("Delay causes and cancellations")
    st.caption(
        "Recorded cause minutes, not causal inference: the dataset attributes delay minutes reported "
        "by carriers, so the categories explain reported attribution rather than proving a mechanism."
    )

    causes = pd.DataFrame(client.delay_causes()["data"])
    if causes.empty:
        st.info("Delay-cause analysis is unavailable for this dataset.")
    else:
        ordered = causes.sort_values("delay_minutes")
        figure = go.Figure(
            go.Bar(
                x=ordered["delay_minutes"],
                y=ordered["cause"],
                orientation="h",
                marker_color=theme.PRIMARY,
                customdata=ordered[["share_pct", "flights_with_cause"]].to_numpy(),
                text=[f"{value:.1f}%" for value in ordered["share_pct"]],
                textposition="outside",
                hovertemplate=(
                    "%{y}<br>Reported minutes %{x:,.0f}"
                    "<br>Share of recorded minutes %{customdata[0]:.2f}%"
                    "<br>Flights with this cause reported %{customdata[1]:,}<extra></extra>"
                ),
            )
        )
        theme.style(figure, "Recorded delay minutes by attributed cause", height=380, x_title="Minutes")
        st.plotly_chart(figure, width="stretch", config=theme.CHART_CONFIG)

        with st.expander("How to read the delay-cause figures"):
            st.markdown(
                "- BTS populates the five cause fields only for flights with an arrival delay of at least 15 minutes.\n"
                "- A missing cause means *not reported*, never zero minutes, so shares are computed over recorded "
                "cause minutes only.\n"
                "- Recorded minutes can exceed the delay itself when a carrier attributes the same delay to several "
                "causes, so the five shares are read as an attribution mix, not a budget."
            )
        table = theme.display_table(
            causes[["cause", "delay_minutes", "flights_with_cause", "share_pct"]],
            percent_columns=["share_pct"],
            number_columns={"delay_minutes": 0},
        )
        st.dataframe(table, width="stretch", hide_index=True)
        theme.download_button("Download delay-cause table (CSV)", causes, "delay_causes.csv", "causes_download")

    st.divider()
    st.markdown("##### Cancellations by airline and month")

    cancellations = pd.DataFrame(client.cancellations(limit=500)["data"])
    if cancellations.empty:
        theme.empty_state("No cancellation data available.")
        return

    controls = st.columns([2, 1, 1])
    labels = {
        row["airline_code"]: f"{row['airline_code']} - {row['airline_name']}"
        for _, row in cancellations.drop_duplicates("airline_code").iterrows()
    }
    selected = controls[0].multiselect("Airlines", options=list(labels), format_func=lambda code: labels[code])
    years = sorted(cancellations["flight_year"].astype(int).unique())
    year = controls[1].selectbox("Year", options=[None, *years], format_func=lambda value: "All years" if value is None else str(value))
    months = list(range(1, 13))
    month = controls[2].selectbox("Month", options=[None, *months], format_func=lambda value: "All months" if value is None else str(value))

    payload = client.cancellations(airline=selected or None, year=year, month=month, limit=500)
    filtered = pd.DataFrame(payload["data"])
    if filtered.empty:
        theme.empty_state()
    else:
        highest = filtered.sort_values("cancellations", ascending=False).head(15)
        figure = go.Figure(
            go.Bar(
                x=highest["airline_name"],
                y=highest["cancellations"],
                marker_color=theme.ACCENT,
                customdata=highest[["cancellation_rate", "total_flights"]].to_numpy(),
                hovertemplate=(
                    "%{x}<br>Cancellations %{y:,}"
                    "<br>Rate %{customdata[0]:.2f}%"
                    "<br>Flights %{customdata[1]:,}<extra></extra>"
                ),
            )
        )
        theme.style(figure, "Highest cancellation counts", height=340, y_title="Cancelled flights")
        st.plotly_chart(figure, width="stretch", config=theme.CHART_CONFIG)

        table = theme.display_table(
            filtered[["airline_code", "airline_name", "flight_year", "flight_month", "total_flights", "cancellations", "cancellation_rate"]],
            percent_columns=["cancellation_rate"],
        )
        st.dataframe(table, width="stretch", hide_index=True)
        theme.download_button("Download cancellation table (CSV)", filtered, "cancellations.csv", "cancellations_download")

    st.markdown("##### Cancellation reasons by airport")
    airports = pd.DataFrame(client.cancellation_airports(year=year, month=month, limit=500)["data"])
    if airports.empty:
        theme.empty_state("No airport-level cancellation data for this filter.")
        return

    top = airports.sort_values("cancellations", ascending=False).head(20)
    figure = go.Figure()
    for column, label in CAUSE_CODE_COLUMNS.items():
        figure.add_trace(
            go.Bar(
                x=top["origin_airport"],
                y=top[column],
                name=label,
                hovertemplate="%{x}<br>" + label + ": %{y:,} cancellations<extra></extra>",
            )
        )
    figure.update_layout(barmode="stack")
    theme.style(figure, "Cancellations by origin airport and reason code", height=380, y_title="Cancelled flights")
    st.plotly_chart(figure, width="stretch", config=theme.CHART_CONFIG)
    st.caption("Reason codes: A carrier, B weather, C national aviation system, D security.")

    table = theme.display_table(
        top[
            [
                "origin_airport",
                "flight_year",
                "flight_month",
                "total_flights",
                "cancellations",
                "cancellation_rate",
                "cancelled_carrier",
                "cancelled_weather",
                "cancelled_nas",
                "cancelled_security",
            ]
        ],
        percent_columns=["cancellation_rate"],
    )
    st.dataframe(table, width="stretch", hide_index=True)
    theme.download_button("Download airport cancellation table (CSV)", airports, "cancellation_airports.csv", "cancel_airports_download")
