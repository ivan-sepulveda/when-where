import { useId } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ShareBreakdown, Slice } from "../lib/travelerCharts";

// A 100% STACKED HORIZONTAL BAR: one bar, segments sized by share, always
// filling the full width. The question each answers is "what proportion of
// this person's flying is X", so the bar is the whole and the segments are
// the parts -- there is no axis to read, which is why the scale is hidden
// and the values are carried by labels, the legend and the table instead.
//
// Drawn with Recharts (layout="vertical", one data row, every segment
// sharing a stackId) rather than by hand, so hover and the tooltip come
// from the same library as anything else charted later.

const BAR_HEIGHT = 44;

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

// Deliberately NOT a categorical hue: the aggregate isn't an entity, and
// giving it a series color would make "6 others" look like one more airline.
const AGGREGATE = "#7d7f86";
const SURFACE = "#161b22"; // the card this sits on -- drawn between segments as the 2px gap
const INK_ON_DARK = "#f2f2f2";
const INK_ON_LIGHT = "#0b0f14";

// Label ink has to follow the FILL, not the page. Most segments are dark
// enough for the page's near-white ink, but not all: American's color is its
// brand GREY (#A5B5BE), and white on that measures about 1.7:1 -- the label
// was rendering, and was unreadable. Choosing ink per segment keeps every
// label legible whatever color an airline brings.
function relativeLuminance(hex: string): number {
  const h = hex.replace("#", "");
  const channels = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function inkOn(fill: string): string {
  // 0.32 is roughly where the two inks swap which one has more contrast
  // against the fill.
  return relativeLuminance(fill) > 0.32 ? INK_ON_LIGHT : INK_ON_DARK;
}

// Label fitting. Segment width is known at draw time, so rather than
// guessing from the percentage alone the renderer measures: it tries
// "American 11%", falls back to "11%", and draws nothing if even that would
// overflow. CHAR_PX is a conservative average advance for 12px system-ui --
// erring wide, because a label that overflows its segment is worse than one
// that was dropped to the legend.
const CHAR_PX = 6.4;
const LABEL_PADDING_PX = 10;

function fits(text: string, width: number): boolean {
  return text.length * CHAR_PX + LABEL_PADDING_PX <= width;
}

// Two coloring modes.
//
// `colorOf` is supplied for the airlines bar, where each segment's color
// comes from the AIRLINE, not from its position -- so Delta is Delta red
// whether it's the biggest slice or the smallest, on every traveler's page.
// Without it the bar falls back to the validated categorical palette,
// assigned by position, which is what the domestic/international bar wants
// since "Domestic" has no brand of its own.
function segmentColors(data: ShareBreakdown, colorOf?: (label: string) => string): string[] {
  return data.segments.map((slice, i) => {
    if (data.hasAggregate && i === data.segments.length - 1) return AGGREGATE;
    return colorOf ? colorOf(slice.label) : SERIES[i];
  });
}

function formatPercent(percent: number): string {
  return `${Number.isInteger(percent) ? percent : percent.toFixed(1)}%`;
}

function formatTrips(value: number): string {
  return `${value} ${value === 1 ? "trip" : "trips"}`;
}

function TooltipContent({ active, payload }: { active?: boolean; payload?: { payload?: Slice }[] }) {
  const slice = active && payload && payload.length ? payload[0].payload : undefined;
  if (!slice) return null;
  return (
    <div className="share-bar-tooltip">
      <strong>{slice.label}</strong>
      <span>
        {formatPercent(slice.percent)} · {formatTrips(slice.value)}
      </span>
    </div>
  );
}

export interface StackedShareBarProps {
  title: string;
  data: ShareBreakdown;
  // Optional per-category color, keyed on the segment's label. Supplied for
  // airlines (brand colors); omitted elsewhere to use the categorical palette.
  colorOf?: (label: string) => string;
  // Optional short form of a segment's label, drawn inside the segment when
  // it fits. On the airlines bar this is doing real work: brand colors are
  // not distinguishable enough to carry identity by themselves -- Delta and
  // American are visually the same red -- so the text is what actually tells
  // the segments apart. See lib/airlineColors.ts.
  shortLabelOf?: (label: string) => string;
  // Rendered under the bar: what the percentages are a share of. The two
  // charts on a traveler page have DIFFERENT denominators (only trips with
  // a recorded airline vs every classifiable trip), so leaving this to the
  // reader to infer would be misleading.
  caption: string;
  // Shown instead of the bar when there's nothing to plot -- the common
  // case, since 124 of 206 travelers have no airline recorded at all.
  emptyMessage: string;
}

export default function StackedShareBar({
  title,
  data,
  caption,
  emptyMessage,
  colorOf,
  shortLabelOf,
}: StackedShareBarProps) {
  const titleId = useId();

  if (data.total === 0 || data.segments.length === 0) {
    return (
      <section className="share-bar" aria-labelledby={titleId}>
        <h3 id={titleId} className="share-bar-title">{title}</h3>
        <p className="share-bar-empty">{emptyMessage}</p>
      </section>
    );
  }

  const colors = segmentColors(data, colorOf);

  // One row, one key per segment. Recharts stacks in declaration order and
  // this layout runs left-to-right, so segment 0 (the largest) lands on the
  // left -- the same order as the legend and the table.
  const row: Record<string, number> = Object.fromEntries(
    data.segments.map((slice, i) => [`s${i}`, slice.percent]),
  );

  return (
    <section className="share-bar" aria-labelledby={titleId}>
      <h3 id={titleId} className="share-bar-title">{title}</h3>

      <div
        className="share-bar-figure"
        role="img"
        aria-label={`${title}. ${data.segments
          .map((s) => `${s.label} ${formatPercent(s.percent)}`)
          .join(", ")}.`}
      >
        <ResponsiveContainer width="100%" height={BAR_HEIGHT}>
          <BarChart layout="vertical" data={[row]} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            {/* Fixed 0-100 domain, not derived from the data: this is a
                percent-of-whole bar, and letting Recharts fit the domain to
                the values would silently rescale a bar that must always
                mean "all of it". */}
            <XAxis type="number" domain={[0, 100]} hide />
            <YAxis type="category" hide />
            <Tooltip
              // ONE SEGMENT, NOT THE WHOLE STACK. Recharts' default is an
              // axis-shared tooltip: every segment of the stack comes back
              // in `payload` on any hover, in series order, so reading
              // payload[0] showed the FIRST segment wherever the pointer
              // was -- "Domestic" while hovering International. shared
              // makes the hovered item the only one in the payload.
              shared={false}
              cursor={false}
              content={({ active, payload }) => (
                <TooltipContent
                  active={active}
                  payload={payload?.map((p) => ({
                    payload: data.segments[Number(String(p.dataKey).slice(1))],
                  }))}
                />
              )}
            />
            {data.segments.map((slice, i) => (
              <Bar
                key={slice.label}
                dataKey={`s${i}`}
                stackId="share"
                fill={colors[i]}
                // The 2px surface gap between fills, per the mark spec --
                // separation by a gap rather than by a drawn border. A lone
                // segment gets none: a stroke on a full-width bar draws
                // edges that read as a second, empty category.
                stroke={data.segments.length > 1 ? SURFACE : "none"}
                strokeWidth={data.segments.length > 1 ? 2 : 0}
                isAnimationActive={false}
                // 4px rounded data-ends on the two ends of the bar only;
                // interior segments stay square so the stack reads as one bar.
                radius={
                  data.segments.length === 1
                    ? 4
                    : i === 0
                      ? [4, 0, 0, 4]
                      : i === data.segments.length - 1
                        ? [0, 4, 4, 0]
                        : undefined
                }
                label={(props: { x?: number; y?: number; width?: number; height?: number }) => {
                  const width = Number(props.width ?? 0);
                  const short = shortLabelOf?.(slice.label);
                  const pct = formatPercent(slice.percent);
                  // Fallback order matters. When both fit, show both. When
                  // only one does, the NAME wins over the number: the number
                  // is also in the legend, the tooltip and the table, whereas
                  // the name is the only thing distinguishing two segments
                  // that share a color -- which on the airlines bar is
                  // common (Delta, American, Envoy and Air Canada are all
                  // the same red). A bare "14%" on an unidentifiable red
                  // block is the failure mode this whole label exists to
                  // prevent.
                  const candidates = short ? [`${short} ${pct}`, short, pct] : [pct];
                  const text = candidates.find((c) => fits(c, width)) ?? null;
                  // Nothing fits -- the legend, tooltip and table still carry
                  // this segment's identity and value.
                  if (!text) return <g />;
                  return (
                    <text
                      x={Number(props.x ?? 0) + width / 2}
                      y={Number(props.y ?? 0) + Number(props.height ?? 0) / 2}
                      fill={inkOn(colors[i])}
                      fontSize={12}
                      textAnchor="middle"
                      dominantBaseline="central"
                      // The label sits ON TOP of its segment, so without
                      // this it eats the pointer events the segment needs
                      // to raise the tooltip -- the tooltip vanished in a
                      // band across the middle of every labelled segment,
                      // which is exactly where a pointer lands.
                      pointerEvents="none"
                    >
                      {text}
                    </text>
                  );
                }}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Always present, including for a single segment: the chart title
          says "Airlines flown", not which airline, so without the legend a
          loyalist's 100% bar would be an unlabelled blue rectangle. */}
      <ul className="share-bar-legend">
        {data.segments.map((slice, i) => (
          <li key={slice.label}>
            <span className="share-bar-swatch" style={{ background: colors[i] }} aria-hidden="true" />
            <span className="share-bar-legend-label">{slice.label}</span>
            <span className="share-bar-legend-value">{formatPercent(slice.percent)}</span>
          </li>
        ))}
      </ul>

      <p className="share-bar-caption">{caption}</p>

      {/* The table twin: every value the bar encodes, reachable without
          color, hover, or a pointer. */}
      <details className="share-bar-table">
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
            {data.segments.map((slice) => (
              <tr key={slice.label}>
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
