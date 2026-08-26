import { useId } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { PreferenceAxis } from "../lib/travelerCharts";

// A traveler's DESTINATION PREFERENCE PROFILE as a radar/spider chart: one
// axis per scored dimension (UNESCO, Michelin, weather today -- see
// preferenceAxes), each 0-1, plotted as a single filled polygon.
//
// Reuses the .share-bar* classes from StackedShareBar.tsx rather than a
// parallel set of near-identical rules -- this card sits in the same
// .traveler-charts grid and should look like the same family of chart, not
// a different one that happens to be next to it.
//
// Unlike StackedShareBar, there's only ONE series here (a single Radar for
// "value"), so the axis-shared-tooltip bug that bit the stacked bars
// (payload[0] always being the FIRST stacked segment) doesn't apply: each
// hover targets one row of `axes` and Recharts hands back that row's own
// payload, not every axis at once.
//
// MIN_RADAR_AXES = 3 -- found by looking at the picture, not guessed at.
// weather_score is null far more often than unesco_score/michelin_score
// (only 1,770 of 3,069 cities have weather normals), so a common real case
// is exactly 2 present axes. Two points 180 degrees apart don't draw a
// polygon at all -- Recharts renders a single vertical LINE through the
// center, which reads as a broken chart, not a small one. Below three axes
// this falls back to plain stat rows instead, the same call EntropyBlock
// already makes on this page ("two numbers, not a chart: ... a one-bar bar
// chart would be a stat tile wearing a costume") -- the values themselves
// are just as real with two dimensions as with three, only the shape stops
// being meaningful.
const MIN_RADAR_AXES = 3;

const RADAR_HEIGHT = 260;
const STROKE = "#3987e5"; // same blue as the first slot in the categorical palette
const GRID_STROKE = "#3a3f47"; // matches .share-bar's border color
const AXIS_INK = "#c8ccd4";

function formatPercent01(value: number): string {
  const pct = value * 100;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(1)}%`;
}

function formatTrips(value: number): string {
  return `${value} ${value === 1 ? "trip" : "trips"}`;
}

function TooltipContent({ active, payload }: { active?: boolean; payload?: { payload?: PreferenceAxis }[] }) {
  const axis = active && payload && payload.length ? payload[0].payload : undefined;
  if (!axis) return null;
  return (
    <div className="share-bar-tooltip">
      <strong>{axis.label}</strong>
      <span>
        {formatPercent01(axis.value)} · avg over {formatTrips(axis.trips)}
      </span>
    </div>
  );
}

export interface PreferenceRadarChartProps {
  title: string;
  axes: PreferenceAxis[];
  // What the values are and how they were built -- same role as
  // StackedShareBar's caption, since this chart's scale (0-1, a rescaled
  // mean of 0-10 trip scores) isn't self-explanatory either.
  caption: string;
  // Shown instead of the chart when no dimension has a single scored trip
  // -- a Kaggle-sourced traveler whose one trip matched no city record, for
  // instance.
  emptyMessage: string;
}

export default function PreferenceRadarChart({ title, axes, caption, emptyMessage }: PreferenceRadarChartProps) {
  const titleId = useId();

  if (axes.length === 0) {
    return (
      <section className="share-bar" aria-labelledby={titleId}>
        <h3 id={titleId} className="share-bar-title">{title}</h3>
        <p className="share-bar-empty">{emptyMessage}</p>
      </section>
    );
  }

  // Too few axes for the shape to mean anything (see MIN_RADAR_AXES) --
  // show what IS known as plain rows, styled like StackedShareBar's own
  // legend, rather than a chart that would draw a bare line through the
  // center.
  if (axes.length < MIN_RADAR_AXES) {
    return (
      <section className="share-bar" aria-labelledby={titleId}>
        <h3 id={titleId} className="share-bar-title">{title}</h3>
        <ul className="share-bar-legend">
          {axes.map((axis) => (
            <li key={axis.key}>
              <span className="share-bar-legend-label">{axis.label}</span>
              <span className="share-bar-legend-value">{formatPercent01(axis.value)}</span>
            </li>
          ))}
        </ul>
        <p className="share-bar-caption">
          Only {axes.length} of 3 dimensions have a scored trip to average, too few to draw a shape. {caption}
        </p>
      </section>
    );
  }

  return (
    <section className="share-bar" aria-labelledby={titleId}>
      <h3 id={titleId} className="share-bar-title">{title}</h3>

      <div
        className="share-bar-figure"
        role="img"
        aria-label={`${title}. ${axes.map((a) => `${a.label} ${formatPercent01(a.value)}`).join(", ")}.`}
      >
        <ResponsiveContainer width="100%" height={RADAR_HEIGHT}>
          <RadarChart data={axes} outerRadius="70%">
            <PolarGrid stroke={GRID_STROKE} />
            <PolarAngleAxis dataKey="label" tick={{ fill: AXIS_INK, fontSize: 12 }} />
            {/* Fixed 0-1 domain, not derived from the data -- same reasoning
                as StackedShareBar's pinned XAxis domain: these values are a
                rescaled 0-1 share, and letting Recharts fit the domain to
                whatever this traveler's own max happens to be would make one
                traveler's "0.4" look as full as another's "1.0". */}
            <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} tickCount={5} />
            <Radar
              dataKey="value"
              stroke={STROKE}
              fill={STROKE}
              fillOpacity={0.35}
              isAnimationActive={false}
            />
            <Tooltip
              content={({ active, payload }) => (
                <TooltipContent
                  active={active}
                  payload={payload?.map((p) => ({ payload: p.payload as PreferenceAxis }))}
                />
              )}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      <p className="share-bar-caption">{caption}</p>
    </section>
  );
}
