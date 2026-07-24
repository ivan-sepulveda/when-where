"""
Builds an interactive, hoverable version of the "peak tourism indicator by
country and month" scatterplot (see notebooks/peak_tourism_months_exploration.ipynb
for the static matplotlib original) as a single self-contained HTML file:
data/processed/peak_tourism_interactive_chart.html.

Unlike the notebook (one fixed encoding per chart), the HTML output lets
the viewer pick, live in the browser:
- **Size by:** number of passengers/visitors (this project's per-country
  volume signal, sqrt-scaled, fixed size for Costa Rica/Canada/Brazil --
  see SIGNAL_LABELS), Michelin-starred restaurant count, the peak tourism
  ratio itself (0-1), or USD purchasing power.
- **Order countries by:** alphabetical, capital latitude, or USD
  purchasing power -- each ascending or descending.
Color always encodes PEAK_RATIO, hover always shows all four metrics
regardless of which one is currently driving marker size.

All four size arrays and three ordering arrays are precomputed in Python
and embedded as plain JSON; the dropdowns just call Plotly.restyle() /
Plotly.relayout() against whichever array was picked -- no recomputation
happens in the browser. Renders via Plotly.js loaded from a CDN rather
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
COUNTRY_ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
MICHELIN_PATH = PROCESSED_DIR / "multiple" / "michelin_restaurants.csv"
USD_PP_PATH = PROCESSED_DIR / "usd_purchasing_power_by_country.csv"
OUTPUT_PATH = PROCESSED_DIR / "peak_tourism_interactive_chart.html"

NAME_ALIASES = {"Türkiye": "Turkey"}

# Same three countries the notebook draws at one fixed marker size, since
# their PASSENGERS column isn't a real headcount.
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

SIZE_LABELS = {
    "passengers": "number of passengers/visitors (fixed size for Costa Rica, Canada & Brazil)",
    "michelin": "Michelin-starred restaurant count",
    "peak_ratio": "peak tourism indicator (0-1)",
    "purchasing_power": "USD purchasing power ($1 US-equivalent)",
}
ORDER_LABELS = {
    "alphabetical": "alphabetical",
    "latitude": "capital latitude",
    "purchasing_power": "USD purchasing power",
}


def load_capital_lat(country_names) -> dict:
    """Country name -> capital latitude (most populous 'primary'-tagged
    capital per country, NAME_ALIASES bridge for name mismatches)."""
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

    capital_lat = {}
    for country_name in country_names:
        lookup_name = NAME_ALIASES.get(country_name, country_name)
        capital = capitals_by_country.get(lookup_name)
        capital_lat[country_name] = capital["lat"] if capital else None

    missing = [name for name, lat in capital_lat.items() if lat is None]
    if missing:
        print(f"WARNING: no capital latitude found for: {missing} -- sorted last (treated as lat=-90).")

    return capital_lat


def load_michelin_starred_counts() -> pd.Series:
    """Country iso2 -> count of Michelin-STARRED restaurants only (Award
    contains 'Star', so '1/2/3 Star(s)' but not 'Bib Gourmand' or
    'Selected Restaurants') -- a narrower, more literal reading of
    "Michelin star restaurants" than the notebook's all-award-tiers count."""
    michelin = pd.read_csv(MICHELIN_PATH)
    starred = michelin[michelin["Award"].str.contains("Star", na=False)].copy()

    with open(COUNTRY_ALIASES_PATH, encoding="utf-8") as f:
        country_aliases = json.load(f)["countries"]
    alias_to_iso2 = {alias: entry["iso2"] for entry in country_aliases.values() for alias in entry["aliases"]}
    starred["iso2"] = starred["location_country"].str.strip().str.casefold().map(alias_to_iso2)

    return starred.groupby("iso2").size()


def sqrt_scale(values: pd.Series) -> pd.Series:
    """Sqrt-scale a Series into [MIN_DIAMETER, MAX_DIAMETER] -- area should
    scale with volume, not radius, same reasoning as the notebook's
    MARKER_SIZE/MICHELIN_MARKER_SIZE columns."""
    sqrt_values = np.sqrt(values.astype(float))
    lo, hi = sqrt_values.min(), sqrt_values.max()
    if hi == lo:
        return pd.Series(MIN_DIAMETER, index=values.index)
    return MIN_DIAMETER + (sqrt_values - lo) / (hi - lo) * (MAX_DIAMETER - MIN_DIAMETER)


def compute_size_passengers(df: pd.DataFrame) -> pd.Series:
    scalable = df[~df["COUNTRY_NAME"].isin(FIXED_SIZE_COUNTRIES)]
    sqrt_passengers = np.sqrt(scalable["PASSENGERS"].astype(float))
    lo, hi = sqrt_passengers.min(), sqrt_passengers.max()

    def compute(row):
        if row["COUNTRY_NAME"] in FIXED_SIZE_COUNTRIES:
            return FIXED_DIAMETER
        scaled = (np.sqrt(float(row["PASSENGERS"])) - lo) / (hi - lo)
        return MIN_DIAMETER + scaled * (MAX_DIAMETER - MIN_DIAMETER)

    return df.apply(compute, axis=1)


def compute_size_michelin(df: pd.DataFrame) -> pd.Series:
    starred_counts = load_michelin_starred_counts()
    counts = df["COUNTRY"].map(starred_counts).fillna(0).astype(int)
    return sqrt_scale(counts), counts


def compute_size_peak_ratio(df: pd.DataFrame) -> pd.Series:
    """Linear (not sqrt) scale, since PEAK_RATIO is already a bounded 0-1
    ratio, not a volume that needs area-correct compression."""
    return MIN_DIAMETER + df["PEAK_RATIO"].astype(float) * (MAX_DIAMETER - MIN_DIAMETER)


def compute_size_purchasing_power(df: pd.DataFrame) -> pd.Series:
    usd_pp = pd.read_csv(USD_PP_PATH)
    values = df["COUNTRY"].map(usd_pp.set_index("COUNTRY")["USD_PURCHASING_POWER"])
    return sqrt_scale(values), values


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
    michelin_count = int(row["MICHELIN_STARRED_COUNT"])
    pp = row["USD_PURCHASING_POWER"]
    pp_text = f"${pp:.2f}" if pd.notna(pp) else "n/a"
    return (
        f"<b>{row['COUNTRY_NAME']}</b><br>"
        f"{MONTH_NAMES[row['MONTH'] - 1]}<br>"
        f"Peak ratio: {row['PEAK_RATIO']:.0%}<br>"
        f"{label}: {value} ({row['SOURCE_YEAR']})<br>"
        f"Michelin-starred restaurants: {michelin_count}<br>"
        f"USD purchasing power: {pp_text}"
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
  #controls {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 12px; align-items: center; }}
  #controls label {{ font-size: 14px; font-weight: 600; margin-right: 6px; }}
  #controls select {{ font-size: 14px; padding: 4px 8px; }}
  #chart {{ width: 100%; height: 1400px; }}
</style>
</head>
<body>
<div id="controls">
  <div>
    <label for="sizeBy">Size by</label>
    <select id="sizeBy">
      <option value="passengers" selected>Number of passengers</option>
      <option value="michelin">Michelin star restaurants</option>
      <option value="peak_ratio">Peak tourism indicator (0-1)</option>
      <option value="purchasing_power">Purchasing power</option>
    </select>
  </div>
  <div>
    <label for="orderBy">Order countries by</label>
    <select id="orderBy">
      <option value="alphabetical">Alphabetical (A-Z)</option>
      <option value="latitude" selected>Latitude</option>
      <option value="purchasing_power">Purchasing power</option>
    </select>
  </div>
  <div>
    <label for="direction">Direction</label>
    <select id="direction">
      <option value="ascending" selected>Ascending</option>
      <option value="descending">Descending</option>
    </select>
  </div>
</div>
<div id="chart"></div>
<script>
var pointData = {point_data};
var peakData = {peak_data};
var countryOrders = {country_orders};
var sizeLabels = {size_labels};
var orderLabels = {order_labels};

function buildTitle() {{
  var sizeBy = document.getElementById('sizeBy').value;
  var orderBy = document.getElementById('orderBy').value;
  var direction = document.getElementById('direction').value;
  return 'Peak tourism indicator by country and month<br>' +
    '<sub>size = ' + sizeLabels[sizeBy] + ' &mdash; ordered by ' + orderLabels[orderBy] + ' (' + direction + ')</sub>';
}}

function currentCategoryArray() {{
  var orderBy = document.getElementById('orderBy').value;
  var direction = document.getElementById('direction').value;
  var order = countryOrders[orderBy];
  return direction === 'ascending' ? order.slice() : order.slice().reverse();
}}

var allTrace = {{
  x: pointData.x,
  y: pointData.y,
  mode: 'markers',
  type: 'scatter',
  text: pointData.hover,
  hoverinfo: 'text',
  marker: {{
    size: pointData.size.passengers,
    color: pointData.peak_ratio,
    colorscale: 'RdBu',
    reversescale: true,
    line: {{width: 0.6, color: 'black'}},
    colorbar: {{title: 'PEAK_RATIO<br>(0-1)'}},
    opacity: 0.85,
  }},
  name: '',
}};

var peakTrace = {{
  x: peakData.x,
  y: peakData.y,
  mode: 'markers',
  type: 'scatter',
  text: peakData.hover,
  hoverinfo: 'text',
  marker: {{
    size: peakData.size.passengers,
    color: 'rgba(0,0,0,0)',
    line: {{width: 2, color: 'green'}},
  }},
  name: 'Peak month (PEAK_RATIO = 1.0)',
}};

var layout = {{
  title: buildTitle(),
  xaxis: {{
    tickmode: 'array',
    tickvals: [1,2,3,4,5,6,7,8,9,10,11,12],
    ticktext: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    range: [0.5, 12.5],
    title: 'Month',
  }},
  yaxis: {{
    categoryorder: 'array',
    categoryarray: currentCategoryArray(),
    title: 'Country',
    automargin: true,
  }},
  hovermode: 'closest',
  showlegend: true,
  legend: {{orientation: 'h', y: -0.04}},
  margin: {{t: 80, b: 60}},
}};

Plotly.newPlot('chart', [allTrace, peakTrace], layout, {{responsive: true}});

document.getElementById('sizeBy').addEventListener('change', function() {{
  var metric = this.value;
  Plotly.restyle('chart', {{'marker.size': [pointData.size[metric]]}}, [0]);
  Plotly.restyle('chart', {{'marker.size': [peakData.size[metric]]}}, [1]);
  Plotly.relayout('chart', {{title: buildTitle()}});
}});

function applyOrder() {{
  Plotly.relayout('chart', {{'yaxis.categoryarray': currentCategoryArray(), title: buildTitle()}});
}}

document.getElementById('orderBy').addEventListener('change', applyOrder);
document.getElementById('direction').addEventListener('change', applyOrder);
</script>
</body>
</html>
"""


def build_chart_html(df: pd.DataFrame) -> str:
    df = df.copy()

    michelin_counts_scaled, michelin_counts_raw = compute_size_michelin(df)
    pp_scaled, pp_raw = compute_size_purchasing_power(df)

    df["MICHELIN_STARRED_COUNT"] = michelin_counts_raw
    df["USD_PURCHASING_POWER"] = pp_raw
    df["HOVER"] = df.apply(hover_text, axis=1)

    size_arrays = {
        "passengers": compute_size_passengers(df).tolist(),
        "michelin": michelin_counts_scaled.tolist(),
        "peak_ratio": compute_size_peak_ratio(df).tolist(),
        "purchasing_power": pp_scaled.tolist(),
    }

    point_data = {
        "x": df["MONTH"].tolist(),
        "y": df["COUNTRY_NAME"].tolist(),
        "peak_ratio": df["PEAK_RATIO"].tolist(),
        "hover": df["HOVER"].tolist(),
        "size": size_arrays,
    }

    peak_mask = df["PEAK_RATIO"] == 1.0
    peak_df = df[peak_mask]
    peak_data = {
        "x": peak_df["MONTH"].tolist(),
        "y": peak_df["COUNTRY_NAME"].tolist(),
        "hover": peak_df["HOVER"].tolist(),
        "size": {metric: (np.array(arr)[peak_mask.values] + 10).tolist() for metric, arr in size_arrays.items()},
    }

    # Three "ascending" country orderings -- descending is just the JS-side
    # reverse of whichever of these is picked. "Ascending" here means
    # increasing value from the bottom of the chart to the top (standard
    # graph-axis convention), so "Latitude" ascending puts the southernmost
    # capital at the bottom and the northernmost at the top, matching the
    # notebook's default look.
    capital_lat = load_capital_lat(df["COUNTRY_NAME"].unique())
    usd_pp = pd.read_csv(USD_PP_PATH).set_index("COUNTRY_NAME")["USD_PURCHASING_POWER"]

    country_orders = {
        "alphabetical": sorted(df["COUNTRY_NAME"].unique()),
        "latitude": sorted(capital_lat, key=lambda c: capital_lat[c] if capital_lat[c] is not None else -90),
        "purchasing_power": sorted(df["COUNTRY_NAME"].unique(), key=lambda c: usd_pp.get(c, 0)),
    }

    return HTML_TEMPLATE.format(
        point_data=json.dumps(point_data),
        peak_data=json.dumps(peak_data),
        country_orders=json.dumps(country_orders),
        size_labels=json.dumps(SIZE_LABELS),
        order_labels=json.dumps(ORDER_LABELS),
    )


def main():
    df = pd.read_csv(PEAK_TOURISM_PATH)
    html = build_chart_html(df)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {df.shape[0]} rows ({df['COUNTRY_NAME'].nunique()} countries) -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
