"""Airport and route analysis page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.common.config import load_settings
from src.dashboard import theme

SETTINGS = load_settings()
DEFAULT_MIN_ROUTE_FLIGHTS = int(SETTINGS.get("analytics.min_route_flights", 100))


def render(client) -> None:
    st.subheader("Airport and route analysis")
    st.caption(
        "Departure metrics use the origin airport and departure delay; arrival metrics use the "
        "destination airport and arrival delay. The two roles are never combined into one figure."
    )

    role_label = st.radio("Airport role", options=["Departures (origin)", "Arrivals (destination)"], horizontal=True)
    role = "departure" if role_label.startswith("Departures") else "arrival"
    top_n = st.slider("Airports shown in the chart", min_value=5, max_value=40, value=15, step=5)

    airports = pd.DataFrame(client.airports(role=role, limit=500, sort="delay_rate")["data"])
    if airports.empty:
        theme.empty_state("No airport data for this role.")
    else:
        imports = airports.sort_values("delay_rate", ascending=False).head(top_n).sort_values("delay_rate")
        figure = go.Figure(
            go.Bar(
                x=imports["delay_rate"],
                y=imports["airport_code"],
                orientation="h",
                marker_color=theme.PRIMARY,
                customdata=imports[["total_flights", "valid_delay_flights", "avg_delay"]].to_numpy(),
                hovertemplate=(
                    "%{y}<br>Delay rate %{x:.2f}%"
                    "<br>Flights %{customdata[0]:,}"
                    "<br>Valid measurements %{customdata[1]:,}"
                    "<br>Avg delay %{customdata[2]:.2f} min<extra></extra>"
                ),
            )
        )
        theme.style(
            figure,
            f"Top {len(imports)} {role} airports by delay rate",
            height=460,
            x_title="Delay rate (%)",
        )
        st.plotly_chart(figure, width="stretch", config=theme.CHART_CONFIG)

        table = theme.display_table(
            airports,
            percent_columns=["delay_rate"],
            number_columns={"avg_delay": 2},
        )
        st.dataframe(table, width="stretch", hide_index=True)
        theme.download_button(
            f"Download {role} airport table (CSV)", airports, f"airports_{role}.csv", f"airports_{role}_download"
        )

    st.divider()
    st.markdown("##### Route performance")
    st.caption(
        f"Only routes with at least the selected number of flights are shown, so a single unusual "
        f"flight cannot dominate the ranking. Default from configuration: {DEFAULT_MIN_ROUTE_FLIGHTS}."
    )

    filters = st.columns([1, 1, 2])
    origin = filters[0].text_input("Origin airport", placeholder="e.g. JFK").strip().upper() or None
    destination = filters[1].text_input("Destination airport", placeholder="e.g. LAX").strip().upper() or None
    min_flights = filters[2].slider(
        "Minimum flights per route",
        min_value=1,
        max_value=1000,
        value=DEFAULT_MIN_ROUTE_FLIGHTS,
        step=10,
    )

    payload = client.routes(origin=origin, destination=destination, min_flights=min_flights, limit=500)
    routes = pd.DataFrame(payload["data"])
    if routes.empty:
        theme.empty_state("No routes match these filters at this minimum flight count.")
        return

    st.caption(f"{payload['pagination']['total']:,} routes match; showing the first {len(routes):,} ordered by delay rate.")
    table = theme.display_table(
        routes,
        percent_columns=["arrival_delay_rate"],
        number_columns={"avg_arrival_delay": 2},
    )
    st.dataframe(table, width="stretch", hide_index=True)
    theme.download_button("Download filtered route table (CSV)", routes, "routes.csv", "routes_download")
