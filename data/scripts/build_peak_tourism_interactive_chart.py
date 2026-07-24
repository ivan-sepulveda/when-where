"""
Builds an interactive, hoverable version of the "peak tourism indicator by
country and month" scatterplot (see notebooks/peak_tourism_months_exploration.ipynb
for the static matplotlib original) as a single self-contained HTML file:
data/processed/peak_tourism_interactive_chart.html.

Reproduces the same encoding as the notebook -- countries on the Y axis
sorted north-to-south by capital latitude (data/reference/tourist_cities.json),
month on the X axis, marker color for PEAK_RATIO, marker size (sqrt-scaled)
for each row's underlying volume signal, and each country's actual peak
month (PEAK_RATIO == 1.0) outlined. Hovering a point shows its country,
month, peak ratio, and the raw underlying value with a label describing
what that source actually measures (air passengers, hotel occupancy %,
overnight stays, etc. -- see data/README.md for the full per-country
breakdown), since PASSENGERS means something different per country.

Renders via Plotly.js loaded from a CDN inside the output HTML, rather
than the `plotly` Python package -- this script only needs pandas/numpy
(already project dependencies), and the resulting HTML file is fully
portable: open it in any browser, no Python required, no new entry needed
in requirements.txt.

Usage:
    python build_peak_tourism_interactive_chart.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
PEAK_TOURISM_PATH = PROCESSED_DIR / "PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv"
TOURIST_CITIES_PATH = REFERENCE_DIR / "tourist_cities.json"
OUTPUT_PATH = PROCESSED_DIR / "peak_tourism_interactive_chart.html"

NAME_ALIASES = {"Türkiye": "Turkey"}

# Same three countries the notebook draws at one fixed marker size, since
# their PASSENGERS column isn't a real headcount (see build_marker_sizes).
FIXED_SIZE_COUNTRIES = {"Costa Rica", "Canada", "Brazil"}
MIN_DIAMETER, MAX_DIAMETER = 8, 42
FIXED_DIAMETER = 22

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# What each country's PASSENGERS column actually measures, for hover text --
# see data/README.md's per-country breakdown. Everything not listed here is
# a Eurostat country and uses the default (air passengers, full history).
SIGNAL_LABELS = {
    "Australia": "Short-term visitor arrivals",
    "New Zealand": "Visitor arrivals",
    "Japan": "Border entries",
    "Costa Rica": "Hotel occupancy",
    "Canada": "Transborder aircraft movements",
    "Chile": "Overnight stays",
    "Mexico": "International air passengers",
    "Maldives": "Tourist arrivals",
    "Indonesia": "Foreign tourist visits",
    "Brazil": "Share of annual visits",
    "Colombia": "Foreign visitor entries",
    "Paraguay": "Foreign visitor entries",
}
DEFAULT_SIGNAL_LABEL = "Air passengers"
PERCENT_COUNTRIES = {"Costa Rica", "Brazil"}


def load_capital_lat() -> dict:
    """Country name -> capital latitude, same lookup the notebook uses (most
    populous 'primary'-tagged capital per country, NAME_ALIASES bridge)."""
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)["cities"]

    capitals_by_country = {}
    for city in cities:
        if city.get("capital") != "primary":
            continue
        country = city["country"]
        current = capitals_by_country.get(country)
        if current is None or (city["population"] or 0) > (current["population"] or 0):
            capitals_by_country[country] = city

    return capitals_by_country


def sort_countries(df: pd.DataFrame) -> list:
    """Return country names ordered bottom-to-top (south-to-north) for the
    Y axis, matching the notebook's convention."""
    capitals_by_country = load_capital_lat()

    capital_lat = {}
    for country_name in df["COUNTRY_NAME"].unique():
        lookup_name = NAME_ALIASES.get(country_name, country_name)
        capital = capitals_by_country.get(lookup_name)
        capital_lat[country_name] = capital["lat"] if capital else None

    top_to_bottom = sorted(
        capital_lat, key=lambda c: capital_lat[c] if capital_lat[c] is not None else -90, reverse=True
    )
    return list(reversed(top_to_bottom))


def marker_diameter(df: pd.DataFrame) -> pd.Series:
    """Sqrt-scaled marker diameter (pixels) from PASSENGERS, fixed for
    FIXED_SIZE_COUNTRIES. Diameter, not area, since Plotly's marker.size is
    a diameter -- separate scaling from the matplotlib notebook's area-based
    MARKER_SIZE, tuned to look comparable at Plotly's default marker scale."""
    scalable = df[~df["COUNTRY_NAME"].isin(FIXED_SIZE_COUNTRIES)]
    sqrt_passengers = np.sqrt(scalable["PASSENGERS"].astype(float))
    lo, hi = sqrt_passengers.min(), sqrt_passengers.max()

    def compute(row):
        if row["COUNTRY_NAME"] in FIXED_SIZE_COUNTRIES:
            return FIXED_DIAMETER
        scaled = (np.sqrt(float(row["PASSENGERS"])) - lo) / (hi - lo)
        return MIN_DIAMETER + scaled * (MAX_DIAMETER - MIN_DIAMETER)

    return df.apply(compute, axis=1)


def format_value(country_name: str, value: float) -> str:
    if country_name in PERCENT_COUNTRIES:
        return f"{value:.2f}%" if not float(value).is_integer() else f"{value:.1f}%"
    if float(value).is_integer():
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def hover_text(row: pd.Series) -> str:
    label = SIGNAL_LABELS.get(row["COUNTRY_NAME"], DEFAULT_SIGNAL_LABEL)
    value = format_value(row["COUNTRY_NAME"], float(row["PASSENGERS"]))
    peak_note = "<br><b>Peak month</b>" if row["PEAK_RATIO"] == 1.0 else ""
    return (
        f"<b>{row['COUNTRY_NAME']}</b><br>"
        f"{MONTH_NAMES[row['MONTH'] - 1]}<br>"
        f"Peak ratio: {row['PEAK_RATIO']:.0%}<br>"
        f"{label}: {value} ({row['SOURCE_YEAR']})"
        f"{peak_note}"
    )


HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Peak tourism indicator by country and month</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 0; padding: 16px; }}
  #chart {{ width: 100%; height: 1400px; }}
</style>
</head>
<body>
<div id="chart"></div>
<script>
var allTrace = {all_trace};
var peakTrace = {peak_trace};
var layout = {layout};
Plotly.newPlot('chart', [allTrace, peakTrace], layout, {{responsive: true}});
</script>
</body>
</html>
"""


def build_chart_html(df: pd.DataFrame) -> str:
    countries_bottom_to_top = sort_countries(df)
    df = df.copy()
    df["DIAMETER"] = marker_diameter(df)
    df["HOVER"] = df.apply(hover_text, axis=1)

    all_trace = {
        "x": df["MONTH"].tolist(),
        "y": df["COUNTRY_NAME"].tolist(),
        "mode": "markers",
        "type": "scatter",
        "text": df["HOVER"].tolist(),
        "hoverinfo": "text",
        "marker": {
            "size": df["DIAMETER"].tolist(),
            "color": df["PEAK_RATIO"].tolist(),
            "colorscale": "RdBu",
            "reversescale": True,
            "line": {"width": 0.6, "color": "black"},
            "colorbar": {"title": "PEAK_RATIO<br>(0-1)"},
            "opacity": 0.85,
        },
        "name": "",
    }

    peak_rows = df[df["PEAK_RATIO"] == 1.0]
    peak_trace = {
        "x": peak_rows["MONTH"].tolist(),
        "y": peak_rows["COUNTRY_NAME"].tolist(),
        "mode": "markers",
        "type": "scatter",
        "text": peak_rows["HOVER"].tolist(),
        "hoverinfo": "text",
        "marker": {
            "size": (peak_rows["DIAMETER"] + 10).tolist(),
            "color": "rgba(0,0,0,0)",
            "line": {"width": 2, "color": "green"},
        },
        "name": "Peak month (PEAK_RATIO = 1.0)",
    }

    layout = {
        "title": "Peak tourism indicator by country and month<br><sub>size = underlying volume signal, fixed size for Costa Rica, Canada &amp; Brazil</sub>",
        "xaxis": {
            "tickmode": "array",
            "tickvals": list(range(1, 13)),
            "ticktext": MONTH_NAMES,
            "range": [0.5, 12.5],
            "title": "Month",
        },
        "yaxis": {
            "categoryorder": "array",
            "categoryarray": countries_bottom_to_top,
            "title": "Country",
            "automargin": True,
        },
        "hovermode": "closest",
        "showlegend": True,
        "legend": {"orientation": "h", "y": -0.04},
        "margin": {"t": 80, "b": 60},
    }

    return HTML_TEMPLATE.format(
        all_trace=json.dumps(all_trace),
        peak_trace=json.dumps(peak_trace),
        layout=json.dumps(layout),
    )


def main():
    df = pd.read_csv(PEAK_TOURISM_PATH)
    html = build_chart_html(df)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {df.shape[0]} rows ({df['COUNTRY_NAME'].nunique()} countries) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
