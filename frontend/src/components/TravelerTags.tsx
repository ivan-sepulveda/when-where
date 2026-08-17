import { airlineColor } from "../lib/airlineColors";
import { describeTag, tagCarriers } from "../lib/travelerTags";
import type { TravelerTag } from "../lib/travelers";

// The computed labels on a traveler, drawn as a row of chips. Used on both
// the /rec-sys card grid and the traveler detail page, so a person's tags
// read identically wherever you meet them.
//
// WHAT A CHIP MEANS: a fact about this traveler as recorded, produced by
// data/scripts/multiple/compute_traveler_tags.py -- not something the
// dataset's author asserted. Two travelers written as United loyalists fly
// routes United doesn't serve and get no loyalist chip; that gap is the
// point.
//
// THE DOTS ARE THE AIRLINES' OWN COLORS, from the same lib the "Airlines
// flown" bar uses. Delta's chip carries Delta red on both pages and inside
// the chart on one of them -- lib/airlineColors.ts fixes color to the ENTITY
// rather than to a slot precisely so this holds across components.
//
// A tag can name more than one airline: "Multi Hub" draws a dot per airline
// that hubs in the traveler's home city, which is what makes a Chicago chip
// (United, American) visibly different from a New York one (United, Delta,
// American) without spending any more of a 180px card on text. A tag about
// no airline draws no dots rather than a grey one, so a dot always means
// "this color identifies that airline".
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
      {tags.map((tag) => {
        const carriers = tagCarriers(tag);
        return (
          <li key={tag.tag_id} className="traveler-tag" title={describeTag(tag)}>
            {carriers.length > 0 && (
              <span className="traveler-tag-dots" aria-hidden="true">
                {carriers.map((carrier) => (
                  <span
                    key={carrier}
                    className="traveler-tag-dot"
                    style={{ background: airlineColor(carrier) }}
                  />
                ))}
              </span>
            )}
            {tag.label}
          </li>
        );
      })}
    </ul>
  );
}
