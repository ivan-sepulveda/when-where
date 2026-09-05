import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { API_BASE_URL } from "../lib/apiBaseUrl";

// Trips by departure month, every year stacked into one twelve-point profile.
//
// A LINE, NOT BARS. The question is the SHAPE of the year -- where the peaks
// and troughs sit and how steep the run between them is -- and months are an
// ordered, cyclical scale, so a line reads that shape directly. Bars would
// invite reading each month as an independent magnitude to compare pairwise,
// which is the wrong question.
//
// ONE SERIES, SO NO LEGEND. The title says what is plotted; a legend box
// holding a single swatch is furniture. A second series (the
// layover-excluded count) is available as a toggle rather than a second line,
// because the two differ by 4 rows out of 2,474 and would render as one line
// with a slightly thick edge -- two indistinguishable lines is worse than a
// switch that says which number you are looking at.
//
// COLOR: #3987e5 measures 5.20:1 against this app's #0d1117 chart surface,
// comfortably over the 3:1 floor. The app's own #2563eb only reaches 3.66:1 --
// fine for a small chip, thin for a 2px line.

const SERIES = "#3987e5";
const SURFACE = "#0d1117";
const GRID = "#20262e";
const TEXT_MUTED = "#9aa4b1";

interface MonthTripCount {
  month: number;
  name: string;
  short_name: string;
  trips: number;
  trips_excluding_layovers: number;
}

interface TripsByMonthResponse {
  available: boolean;
  total_trips: number;
  first_year: number | null;
  last_year: number | null;
  months: MonthTripCount[];
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; payload: TripsByMonthResponse };

function Chart({
  months,
  valueKey,
}: {
  months: MonthTripCount[];
  valueKey: "trips" | "trips_excluding_layovers";
}) {
  // The chart is a picture of numbers that are also in the table below it,
  // so the label gives the SHAPE -- which months are the peak and the low --
  // rather than reading twelve values a screen reader user can already reach.
  const peak = months.reduce((a, b) => (b[valueKey] > a[valueKey] ? b : a), months[0]);
  const low = months.reduce((a, b) => (b[valueKey] < a[valueKey] ? b : a), months[0]);

  return (
    <div
      className="flights-by-month-chart"
      role="img"
      aria-label={
        months.length
          ? `Line chart of trips by month, January to December. Busiest is ${peak.name} at ${peak[valueKey].toLocaleString()} trips; quietest is ${low.name} at ${low[valueKey].toLocaleString()}. Exact values for every month are in the table below.`
          : "Line chart of trips by month. No data loaded."
      }
    >
      <ResponsiveContainer width="100%" height={380}>
        <LineChart data={months} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
          {/* Recessive: hairline, solid, one step off the surface. Horizontal
              only -- the x scale is twelve labelled categories and does not
              need rules to read against. */}
          <CartesianGrid stroke={GRID} strokeWidth={1} vertical={false} />
          <XAxis
            dataKey="short_name"
            tick={{ fill: TEXT_MUTED, fontSize: 12 }}
            stroke={GRID}
            tickLine={false}
          />
          {/* Not zero-based, deliberately: the counts sit between ~140 and
              ~275, and a zero baseline would flatten the whole seasonal
              signal into a band at the top of the frame. This is a shape
              chart, not a magnitude comparison -- the y axis is labelled and
              the table below carries the exact numbers. */}
          <YAxis
            tick={{ fill: TEXT_MUTED, fontSize: 12 }}
            stroke={GRID}
            tickLine={false}
            width={56}
            domain={["dataMin - 20", "dataMax + 20"]}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ stroke: TEXT_MUTED, strokeWidth: 1 }}
            contentStyle={{
              background: SURFACE,
              border: "1px solid #3a3f47",
              borderRadius: 6,
              fontSize: 13,
            }}
            labelStyle={{ color: "#e6edf3" }}
            itemStyle={{ color: TEXT_MUTED }}
            formatter={(value: number) => [value.toLocaleString(), "Trips"]}
            labelFormatter={(_, entries) => entries?.[0]?.payload?.name ?? ""}
          />
          <Line
            type="linear"
            dataKey={valueKey}
            stroke={SERIES}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            /* r=4 gives an 8px marker; the 2px surface-coloured ring keeps it
               legible where it sits on the line. */
            dot={{ r: 4, fill: SERIES, stroke: SURFACE, strokeWidth: 2 }}
            activeDot={{ r: 6, fill: SERIES, stroke: SURFACE, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function FlightsByMonth() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [excludeLayovers, setExcludeLayovers] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/trips/by-month`)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
        return res.json() as Promise<TripsByMonthResponse>;
      })
      .then((payload) => {
        if (!cancelled) setState({ status: "loaded", payload });
      })
      .catch((err) => {
        if (!cancelled)
          setState({
            status: "error",
            message: err instanceof Error ? err.message : "Unknown error",
          });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const valueKey = excludeLayovers ? "trips_excluding_layovers" : "trips";
  const months = state.status === "loaded" ? state.payload.months : [];

  const summary = useMemo(() => {
    if (months.length === 0) return null;
    const values = months.map((m) => m[valueKey]);
    const peak = months[values.indexOf(Math.max(...values))];
    const trough = months[values.indexOf(Math.min(...values))];
    const total = values.reduce((a, b) => a + b, 0);
    return { peak, trough, total, peakValue: Math.max(...values), troughValue: Math.min(...values) };
  }, [months, valueKey]);

  return (
    <main className="page">
      <h1>Flights by month</h1>

      {state.status === "loading" && <p className="tagline">Loading trips...</p>}

      {state.status === "error" && (
        <p className="tagline" role="alert">
          Couldn't load trips ({state.message}). Is the API running at {API_BASE_URL}?
        </p>
      )}

      {state.status === "loaded" && !state.payload.available && (
        <p className="tagline">
          No traveler data in this checkout. Run{" "}
          <code>data/scripts/multiple/build_travelers.py</code>.
        </p>
      )}

      {state.status === "loaded" && state.payload.available && summary && (
        <>
          <p className="tagline">
            {summary.total.toLocaleString()} trips departing in each calendar month, every year
            from {state.payload.first_year} to {state.payload.last_year} counted together.{" "}
            {summary.peak.name} is the busiest ({summary.peakValue.toLocaleString()}),{" "}
            {summary.trough.name} the quietest ({summary.troughValue.toLocaleString()}).
          </p>

          <label className="flights-by-month-toggle">
            <input
              type="checkbox"
              checked={excludeLayovers}
              onChange={(event) => setExcludeLayovers(event.target.checked)}
            />
            Exclude layover legs
          </label>

          <Chart months={months} valueKey={valueKey} />

          {/* The table is the accessibility path and the exact-value path:
              the chart answers "what shape", this answers "what number". */}
          <h2>By the numbers</h2>
          <table className="flights-by-month-table">
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">Trips</th>
                <th scope="col">Share</th>
              </tr>
            </thead>
            <tbody>
              {months.map((m) => (
                <tr key={m.month}>
                  <th scope="row">{m.name}</th>
                  <td>{m[valueKey].toLocaleString()}</td>
                  <td>{((m[valueKey] / summary.total) * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </main>
  );
}
