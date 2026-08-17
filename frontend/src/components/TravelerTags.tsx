import { airlineColor } from "../lib/airlineColors";
import { describeTag } from "../lib/travelerTags";
import type { TravelerTag } from "../lib/travelers";

// The computed labels on a traveler, drawn as a row of chips. Used on both
// the /rec-sys card grid and the traveler detail page, so a person's tags
// read identically wherever you meet them.
//
// WHAT A CHIP MEANS: a fact about this traveler's trips as recorded, produced
// by data/scripts/multiple/compute_traveler_tags.py -- not something the
// dataset's author asserted. Two travelers written as United loyalists fly
// routes United doesn't serve and get no chip; that gap is the point.
//
// THE DOT IS THE AIRLINE'S OWN COLOR, from the same lib the "Airlines flown"
// bar uses. Delta's chip carries Delta red on both pages and inside the chart
// on one of them -- lib/airlineColors.ts fixes color to the ENTITY rather
// than to a slot precisely so this holds across components. Tags with no
// carrier get no dot rather than a grey one, so the dot always means "this
// color identifies that airline".
export default function TravelerTags({
  tags,
  className,
}: {
  tags: TravelerTag[] | undefined;
  className?: string;
}) {
  // No chips and no empty container: an untagged traveler should look like a
  // traveler, not like a traveler missing something.
  if (!tags || tags.length === 0) return null;

  return (
    <ul className={["traveler-tags", className].filter(Boolean).join(" ")}>
      {tags.map((tag) => (
        <li key={tag.tag_id} className="traveler-tag" title={describeTag(tag)}>
          {tag.carrier_name && (
            <span
              className="traveler-tag-dot"
              style={{ background: airlineColor(tag.carrier_name) }}
              aria-hidden="true"
            />
          )}
          {tag.label}
        </li>
      ))}
    </ul>
  );
}
