import { useId } from "react";
import { Bar, BarChart, Cell, Pie, PieChart, Tooltip, YAxis } from "recharts";
import type { PieLabelRenderProps } from "recharts";
import type { BarOfPieData, Slice } from "../lib/travelerCharts";

// A BAR OF PIE: a pie whose last slice ("Other", or "International" on the
// domestic chart) is exploded into a stacked bar beside it, joined by a
// connector wedge. Excel's chart type, drawn here with Recharts for the two
// halves plus one hand-computed SVG for the connector -- Recharts has a Pie
// and a stacked Bar but no notion of a relationship between two charts, so
// the wedge is geometry this file owns.
//
// Everything is laid out at fixed pixel sizes rather than in a
// ResponsiveContainer, because the connector's endpoints have to land
// exactly on the pie's arc: they're computed from the same cx/cy/radius and
// the same cumulative angles Recharts uses to draw the slices, and a
// container that resizes underneath would leave the wedge pointing at
// nothing.

const PIE_SIZE = 220;
const CX = PIE_SIZE / 2;
const CY = PIE_SIZE / 2;
const RADIUS = 88;
const GAP = 60;
const BAR_W = 54;
const BAR_H = 168;
const BAR_X = PIE_SIZE + GAP;
const BAR_Y = (PIE_SIZE - BAR_H) / 2;
const WIDTH = BAR_X + BAR_W;

// Recharts measures angles in degrees counterclockwise from 3 o'clock, and
// a pie is drawn by sweeping 360 degrees CLOCKWISE (start, start - 360) --
// the direction a reader expects a pie to run.
//
// Where that sweep BEGINS is the whole trick of a bar of pie. The exploded
// slice is always the last one drawn, so the start angle is chosen to land
// that slice centered on 3 o'clock, facing the bar: with the slice covering
// the final fraction f of the sweep, start = 360 - 180f puts its midpoint
// at 0 degrees. Start from the top instead and the connector has to reach
// across the face of the pie to get to the bar.
const PLAIN_PIE_START_ANGLE = 90; // no exploded slice: just start at 12 o'clock

function pieStartAngle(otherFraction: number): number {
  return otherFraction > 0 ? 360 - 180 * otherFraction : PLAIN_PIE_START_ANGLE;
}

// The dark-mode categorical palette, in its fixed slot order. Assigned by
// position and never cycled: past the eighth slot categories fold into a
// grey aggregate instead of reusing a hue that already means another
// airline. Validated against this page's card surface (#161b22) -- all
// eight clear the lightness band, chroma floor, adjacent CVD separation
// (worst 8.4), normal-vision floor (worst 19.3) and 3:1 contrast.
const SERIES = [
  "#3987e5", // blue
  "#d95926", // orange
  "#199e70", // aqua
  "#c98500", // yellow
  "#d55181", // magenta
  "#008300", // green
  "#9085e9", // violet
  "#e66767", // red
];

// Deliberately NOT a categorical hue: the aggregate slice/segment isn't an
// entity, and giving it a series color would make "Other" look like just
// another airline.
const AGGREGATE = "#7d7f86";
const SURFACE = "#161b22"; // the card this sits on -- drawn between marks as the 2px gap
const INK = "#f2f2f2";

function pointOnArc(angleDeg: number, radius: number = RADIUS): [number, number] {
  const rad = (angleDeg * Math.PI) / 180;
  return [CX + radius * Math.cos(rad), CY - radius * Math.sin(rad)];
}

// Colors follow the ENTITY's position in the sorted order, so a slice keeps
// its hue whether or not the bar is present.
function pieColors(data: BarOfPieData): string[] {
  return data.pie.map((_, i) =>
    data.hasOtherSlice && i === data.pie.length - 1 ? AGGREGATE : SERIES[i],
  );
}

// The bar continues the pie's slot sequence rather than restarting at slot
// 1 -- restarting would put the pie's blue and the bar's blue on screen
// together meaning different airlines.
function barColors(data: BarOfPieData): string[] {
  const offset = data.pie.length - 1; // the Other slice doesn't consume a hue
  return data.bar.map((slice, i) =>
    slice.label.endsWith(" others") ? AGGREGATE : SERIES[(offset + i) % SERIES.length],
  );
}

function formatPercent(percent: number): string {
  return `${Number.isInteger(percent) ? percent : percent.toFixed(1)}%`;
}

// Below this share a label doesn't fit inside its own slice, so it's left to
// the legend, the tooltip and the table rather than being drawn overflowing
// the wedge it belongs to.
const MIN_LABELLED_SHARE = 8;

// Drawn INSIDE the slice. Recharts' default label sits outside the radius,
// which the fixed-size chart box then clips -- and its own `percent` prop
// (a 0-1 fraction) is shadowed here, because Recharts spreads each data
// entry into the label props and every Slice carries its own `percent`
// field on a 0-100 scale. Reading the value off `payload` instead of the
// top-level prop makes which scale is in play explicit rather than
// depending on that collision.
function renderSliceLabel(props: PieLabelRenderProps) {
  const slice = props.payload as unknown as Slice | undefined;
  if (!slice || slice.percent < MIN_LABELLED_SHARE) return <g />;

  const cx = Number(props.cx);
  const cy = Number(props.cy);
  const outer = Number(props.outerRadius);
  const rad = (-Number(props.midAngle) * Math.PI) / 180;
  const r = outer * 0.68;

  return (
    <text
      x={cx + r * Math.cos(rad)}
      y={cy + r * Math.sin(rad)}
      fill={INK}
      fontSize={12}
      textAnchor="middle"
      dominantBaseline="central"
    >
      {formatPercent(slice.percent)}
    </text>
  );
}

function TooltipContent({ active, payload }: { active?: boolean; payload?: { payload?: Slice }[] }) {
  const slice = active && payload && payload.length ? payload[0].payload : undefined;
  if (!slice) return null;
  return (
    <div className="bar-of-pie-tooltip">
      <strong>{slice.label}</strong>
      <span>
        {formatPercent(slice.percent)} · {slice.value} {slice.value === 1 ? "trip" : "trips"}
      </span>
    </div>
  );
}

export interface BarOfPieChartProps {
  title: string;
  data: BarOfPieData;
  // Rendered under the chart: what the percentages are a share of. The two
  // charts on a traveler page have DIFFERENT denominators (only trips with
  // a recorded airline vs every classifiable trip), so leaving this to the
  // reader to infer would be misleading.
  caption: string;
  // Shown instead of the chart when there's nothing to plot -- the common
  // case, since 124 of 206 travelers have no airline recorded at all.
  emptyMessage: string;
}

export default function BarOfPieChart({ title, data, caption, emptyMessage }: BarOfPieChartProps) {
  const titleId = useId();

  if (data.total === 0 || data.pie.length === 0) {
    return (
      <section className="bar-of-pie" aria-labelledby={titleId}>
        <h3 id={titleId} className="bar-of-pie-title">{title}</h3>
        <p className="bar-of-pie-empty">{emptyMessage}</p>
      </section>
    );
  }

  const sliceColors = pieColors(data);
  const segmentColors = barColors(data);
  const barTotal = data.bar.reduce((sum, s) => sum + s.value, 0);

  // The exploded slice is the last one drawn, so it runs from
  // start - 360(1 - f) clockwise to start - 360. With the start angle
  // chosen above, those two endpoints straddle 3 o'clock and the connector
  // reaches the bar without crossing the pie.
  const otherFraction = data.hasOtherSlice
    ? data.pie[data.pie.length - 1].value / data.total
    : 0;
  const startAngle = pieStartAngle(otherFraction);
  const [wedgeTopX, wedgeTopY] = pointOnArc(startAngle - 360 * (1 - otherFraction));
  const [wedgeBottomX, wedgeBottomY] = pointOnArc(startAngle - 360);
  // SVG arc flags for the connector's pie-side edge. An exploded slice
  // bigger than half the pie spans more than 180 degrees, which is the
  // major arc (large-arc-flag 1); getting this wrong doesn't error, it just
  // quietly traces the *other* side of the circle and wraps the wedge
  // around the wrong half of the chart. Sweep 0 because the edge runs from
  // the lower endpoint up through 3 o'clock, which is counterclockwise once
  // SVG's flipped y-axis is accounted for.
  const largeArcFlag = otherFraction > 0.5 ? 1 : 0;

  // One row per category, both halves, for the table view. A chart is never
  // the only way to read these numbers.
  const rows: { slice: Slice; color: string; where: string }[] = [
    ...data.pie.map((slice, i) => ({ slice, color: sliceColors[i], where: "Pie" })),
    ...data.bar.map((slice, i) => ({ slice, color: segmentColors[i], where: "Bar" })),
  ];

  return (
    <section className="bar-of-pie" aria-labelledby={titleId}>
      <h3 id={titleId} className="bar-of-pie-title">{title}</h3>

      <div className="bar-of-pie-figure" style={{ width: WIDTH, height: PIE_SIZE }} role="img"
           aria-label={`${title}. ${rows.map((r) => `${r.slice.label} ${formatPercent(r.slice.percent)}`).join(", ")}.`}>
        {/* Connector first so it sits behind both charts. pointer-events
            none keeps it from stealing the pie's hover targets. */}
        {data.hasOtherSlice && data.bar.length > 0 && (
          <svg className="bar-of-pie-connector" width={WIDTH} height={PIE_SIZE} aria-hidden="true">
            {/* The pie-side edge follows the arc of the exploded slice
                rather than chording straight across it -- a chord would cut
                through the face of the pie, and the fill would read as a
                slab behind the chart instead of a wedge leaving a slice.
                Kept faint: this is a pointer between two marks, not a mark. */}
            <path
              d={
                `M ${wedgeTopX} ${wedgeTopY} L ${BAR_X} ${BAR_Y} L ${BAR_X} ${BAR_Y + BAR_H} ` +
                `L ${wedgeBottomX} ${wedgeBottomY} A ${RADIUS} ${RADIUS} 0 ${largeArcFlag} 0 ${wedgeTopX} ${wedgeTopY} Z`
              }
              fill={AGGREGATE}
              fillOpacity={0.12}
              stroke={AGGREGATE}
              strokeOpacity={0.35}
              strokeWidth={1}
            />
          </svg>
        )}

        <div className="bar-of-pie-pie">
          <PieChart width={PIE_SIZE} height={PIE_SIZE}>
            <Pie
              data={data.pie}
              dataKey="value"
              nameKey="label"
              cx={CX}
              cy={CY}
              outerRadius={RADIUS}
              startAngle={startAngle}
              endAngle={startAngle - 360}
              // The 2px surface gap between fills, per the mark spec --
              // separation by a gap rather than by a drawn border. A lone
              // slice gets neither: a gap and a stroke on a full circle draw
              // a seam at 12 o'clock that reads as a second, empty category.
              paddingAngle={data.pie.length > 1 ? 1.2 : 0}
              stroke={data.pie.length > 1 ? SURFACE : "none"}
              strokeWidth={data.pie.length > 1 ? 2 : 0}
              isAnimationActive={false}
              // Direct labels, but selectively -- see renderSliceLabel.
              label={renderSliceLabel}
              labelLine={false}
            >
              {data.pie.map((slice, i) => (
                <Cell key={slice.label} fill={sliceColors[i]} />
              ))}
            </Pie>
            <Tooltip content={<TooltipContent />} />
          </PieChart>
        </div>

        {data.bar.length > 0 && (
          <div className="bar-of-pie-bar" style={{ left: BAR_X, top: BAR_Y }}>
            <BarChart
              width={BAR_W}
              height={BAR_H}
              data={[Object.fromEntries(data.bar.map((s, i) => [`s${i}`, s.value]))]}
              margin={{ top: 0, right: 0, bottom: 0, left: 0 }}
            >
              {/* Fixed domain so the stack always fills the bar: the bar's
                  height means "the Other slice", and its segments are that
                  slice's composition. */}
              <YAxis hide domain={[0, barTotal]} />
              <Tooltip
                cursor={false}
                content={({ active, payload }) => (
                  <TooltipContent
                    active={active}
                    payload={payload?.map((p) => ({
                      payload: data.bar[Number(String(p.dataKey).slice(1))],
                    }))}
                  />
                )}
              />
              {/* Declared smallest-first because Recharts stacks the first
                  Bar at the BOTTOM -- which puts the largest segment on top,
                  so the bar reads top-to-bottom in the same descending order
                  as the legend and the pie. */}
              {data.bar
                .map((slice, i) => ({ slice, i }))
                .reverse()
                .map(({ slice, i }, position) => (
                  <Bar
                    key={slice.label}
                    dataKey={`s${i}`}
                    stackId="other"
                    fill={segmentColors[i]}
                    stroke={SURFACE}
                    strokeWidth={2}
                    barSize={BAR_W}
                    isAnimationActive={false}
                    // 4px rounded data-ends on the two ends of the stack
                    // only; interior segments stay square so the stack reads
                    // as one bar.
                    radius={
                      position === data.bar.length - 1
                        ? [4, 4, 0, 0]
                        : position === 0
                          ? [0, 0, 4, 4]
                          : undefined
                    }
                  />
                ))}
            </BarChart>
          </div>
        )}
      </div>

      {/* Always present, including for a single category: the chart title
          says "Airlines flown", not which airline, so without the legend a
          loyalist's 100% slice would be an unlabelled blue circle. */}
      {rows.length > 0 && (
        <ul className="bar-of-pie-legend">
          {rows.map(({ slice, color }) => (
            <li key={`${slice.label}-${slice.value}`}>
              <span className="bar-of-pie-swatch" style={{ background: color }} aria-hidden="true" />
              <span className="bar-of-pie-legend-label">{slice.label}</span>
              <span className="bar-of-pie-legend-value">{formatPercent(slice.percent)}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="bar-of-pie-caption">{caption}</p>

      {/* The table twin: every value the chart encodes, reachable without
          color, hover, or a pointer. */}
      <details className="bar-of-pie-table">
        <summary>View as table</summary>
        <table>
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">Trips</th>
              <th scope="col">Share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ slice, where }) => (
              <tr key={`${where}-${slice.label}`}>
                <th scope="row">{slice.label}</th>
                <td>{slice.value}</td>
                <td>{formatPercent(slice.percent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}
