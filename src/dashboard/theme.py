"""Shared visual language for the dashboard: palette, Plotly layout, formatting.

Two appearances are supported. `apply_mode()` rebinds the module-level palette and the
Plotly layout, so every view that reads `theme.PRIMARY` / calls `theme.style()` at render
time switches automatically without passing a mode through five modules.

Streamlit resolves its base theme from `.streamlit/config.toml` at startup and has no
runtime theme API, so the dark appearance styles the app chrome with a scoped stylesheet
and the charts with a Plotly layout. Data tables are rendered by Streamlit's canvas grid,
which keeps the configured light base theme; they are presented as bordered cards so the
contrast reads as intentional rather than broken.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

CHART_CONFIG = {"displayModeBar": False, "responsive": True}

LIGHT = {
    "template": "plotly_white",
    "ink": "#16202c",
    "muted": "#5b6675",
    "grid": "#e6e9ef",
    "surface": "#ffffff",
    "primary": "#1f3a5f",
    "accent": "#c8871a",
    "series": ["#1f3a5f", "#3f6f9f", "#c8871a", "#8a9bb0", "#5c4a35", "#2f6f5e"],
}

DARK = {
    "template": "plotly_dark",
    "ink": "#e8edf3",
    "muted": "#9aa8b8",
    "grid": "#26313f",
    "surface": "#101821",
    "primary": "#74a8dc",
    "accent": "#e8a63a",
    "series": ["#74a8dc", "#4b82b8", "#e8a63a", "#8ea0b5", "#c9b49a", "#5fa890"],
}

MODES = {"light": LIGHT, "dark": DARK}
DEFAULT_MODE = "light"

current_mode = DEFAULT_MODE

INK = LIGHT["ink"]
MUTED = LIGHT["muted"]
GRID = LIGHT["grid"]
SURFACE = LIGHT["surface"]
PRIMARY = LIGHT["primary"]
ACCENT = LIGHT["accent"]
SERIES = LIGHT["series"]

BASE_LAYOUT = dict(
    template=LIGHT["template"],
    colorway=SERIES,
    font=dict(family="Segoe UI, Helvetica, Arial, sans-serif", size=12, color=INK),
    margin=dict(l=48, r=24, t=48, b=48),
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    hoverlabel=dict(bgcolor=SURFACE, font_size=12, font_color=INK, bordercolor=GRID),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)


def apply_mode(mode: str | None) -> str:
    """Rebind the palette for this render. Returns the mode actually applied."""
    global current_mode, INK, MUTED, GRID, SURFACE, PRIMARY, ACCENT, SERIES, BASE_LAYOUT

    resolved = (mode or DEFAULT_MODE).lower()
    if resolved not in MODES:
        resolved = DEFAULT_MODE
    spec = MODES[resolved]

    current_mode = resolved
    INK = spec["ink"]
    MUTED = spec["muted"]
    GRID = spec["grid"]
    SURFACE = spec["surface"]
    PRIMARY = spec["primary"]
    ACCENT = spec["accent"]
    SERIES = spec["series"]
    BASE_LAYOUT = dict(
        template=spec["template"],
        colorway=SERIES,
        font=dict(family="Segoe UI, Helvetica, Arial, sans-serif", size=12, color=INK),
        margin=dict(l=48, r=24, t=48, b=48),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        hoverlabel=dict(bgcolor=SURFACE, font_size=12, font_color=INK, bordercolor=GRID),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return resolved


def css(mode: str | None = None) -> str:
    """Scoped stylesheet for the app chrome. Light mode relies on config.toml alone."""
    resolved = (mode or current_mode).lower()
    if resolved != "dark":
        return ""

    spec = DARK
    return f"""
<style>
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background-color: {spec['surface']} !important; }}
  [data-testid="stHeader"] {{ background-color: transparent; }}
  [data-testid="stSidebar"] {{ background-color: #131c27 !important; border-right: 1px solid {spec['grid']}; }}
  h1, h2, h3, h4, h5, h6 {{ color: {spec['ink']} !important; }}
  p, li, [data-testid="stMarkdownContainer"] p {{ color: {spec['ink']} !important; }}
  [data-testid="stWidgetLabel"] label, [data-testid="stWidgetLabel"] p {{ color: #c9d4e0; }}
  [data-testid="stMetricValue"] {{ color: {spec['ink']}; }}
  [data-testid="stMetricLabel"] {{ color: {spec['muted']}; }}
  [data-testid="stMetric"] {{
    background-color: #16202c; border: 1px solid {spec['grid']};
    border-radius: 8px; padding: 12px 14px;
  }}
  [data-testid="stExpander"] details {{
    background-color: #16202c; border: 1px solid {spec['grid']}; border-radius: 8px;
  }}
  [data-testid="stAlert"]:not([data-baseweb]) {{ background-color: #1b2735; }}
  [data-testid="stDataFrame"] {{
    border: 1px solid {spec['grid']}; border-radius: 8px; overflow: hidden;
  }}
  hr {{ border-color: {spec['grid']}; }}
  [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ color: #c9d4e0; }}
</style>
"""


def style(fig: go.Figure, title: str | None = None, height: int = 360, y_title: str | None = None, x_title: str | None = None) -> go.Figure:
    fig.update_layout(**BASE_LAYOUT, height=height, title=dict(text=title or "", x=0, font=dict(size=14, color=INK)))
    fig.update_xaxes(title_text=x_title, showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID, zeroline=False)
    fig.update_yaxes(title_text=y_title, gridcolor=GRID, zeroline=False)
    return fig


def months_label(frame: pd.DataFrame) -> pd.Series:
    return frame["flight_year"].astype(str) + "-" + frame["flight_month"].astype(int).astype(str).str.zfill(2)


def percent(value: float | None) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:.2f}%"


def number(value: float | None, decimals: int = 1) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:,.{decimals}f}"


def integer(value: float | None) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{int(value):,}"


def display_table(frame: pd.DataFrame, percent_columns: list[str], number_columns: dict[str, int] | None = None) -> pd.DataFrame:
    """Copy of the frame with presentation formatting; the raw frame is used for CSV."""
    view = frame.copy()
    for column in percent_columns:
        if column in view:
            view[column] = view[column].map(percent)
    for column, decimals in (number_columns or {}).items():
        if column in view:
            view[column] = view[column].map(lambda value, d=decimals: number(value, d))
    return view


def download_button(label: str, frame: pd.DataFrame, filename: str, key: str) -> None:
    import streamlit as st

    st.download_button(
        label=label,
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        key=key,
    )


def empty_state(message: str = "No records match these filters.") -> None:
    import streamlit as st

    st.info(message)
