# data/raw/museums/

One TSV per country, named `<ISO2>.tsv`. These files are the **source of
truth** for `data/processed/multiple/worldwide_museums.json` --
`data/scripts/multiple/build_worldwide_museums.py` does nothing but glob
this directory and concatenate the rows. To add a country, add a TSV. To
correct a museum, edit its row.

## Format

Tab-separated, UTF-8, with a header line naming the columns. Every file
must use exactly these columns, in this order:

`name`, `category`, `kind`, `description`, `location_raw`, `city`, `lat`,
`lng`, `gallery_space_m2`, `gallery_space_sqft`, `year_established`,
`year_established_raw`

The country code is not a column -- it comes from the filename.

An **empty field means null**: the source did not record a value. It does
not mean empty string, and it must never be a guess. `lat`/`lng` are
empty in every file today; geocoding is a future step.

Rows are not deduplicated by name, by design. Some names legitimately
collide between distinct museums -- Japan has two Idemitsu Museum of Arts
branches (Tokyo and Kitakyushu) and two National Museums of Modern Art
(Tokyo and Kyoto), whose names are truncated identically in the source.
Collapsing those would delete real places.

## Coverage

Coverage is uneven by country and **no country should be assumed
exhaustive**. Known gaps worth keeping in mind:

- **ES** -- the bulk of these rows come from a scrape of a Wikipedia
  "List of museums in Spain", which is very thin on Madrid: only one row
  is tagged to the Community of Madrid. Nationally famous Madrid museums
  are largely absent despite being real. They have not been written in by
  hand.
- **FR** -- likewise, the bulk come from a scrape of a Wikipedia "List of
  museums in France": all museum types, `location_raw` is a commune name,
  no per-museum type. Generic names repeat legitimately across communes
  (21 separate `Musée des Beaux-Arts`, 9 `Musée archéologique`, and so
  on) -- these are distinct municipal museums, not duplicates, and no two
  rows share both a name and a location.
- **JP** -- from a national tourism directory filtered to art museums, so
  it is art museums only, not all Japanese museums. Around ten names and
  descriptions are truncated with a trailing `...` exactly as the source
  rendered them; none were completed by guessing.
- **Most countries** are covered from two Wikipedia lists, "List of art
  museums" and "List of science museums". Both are curated selections,
  not surveys -- a country with three rows has three *recorded* museums,
  not three museums. Their entries are tagged `art_museum` /
  `science_museum` because that is each source page's own premise; a few
  are archaeological or decorative-arts museums those pages chose to
  include, and that tagging was not second-guessed per venue.
- Some countries additionally hold a handful of the world's largest art
  museums by gallery space, which are the rows carrying
  `gallery_space_m2`.
- **Cross-source near-duplicates exist and have not been auto-merged.**
  The same museum can appear under two names from two sources ("Louvre"
  and "Musée du Louvre"; "Hermitage" and "State Hermitage Museum").
  Deduplication here is by exact name plus location only -- collapsing
  name variants automatically would delete real distinct museums that
  merely share words, so those merges are left for a human.

`category` and `kind` reflect what a source actually recorded. Where a
source was a general museum list with no reliable per-museum type, both
are null rather than inferred -- which is why most ES rows are
uncategorized while JP rows carry a type.

## Attribution

- **JP**: Japan National Tourism Organization (JNTO) travel directory,
  <https://www.japan.travel>.
- **ES / FR** (most rows): Wikipedia contributors, "List of museums in
  Spain" and "List of museums in France", CC BY-SA.
- **Most countries**: Wikipedia contributors, "List of art museums" and
  "List of science museums", CC BY-SA. Those pages group Armenia,
  Azerbaijan, Russia and Turkey under Europe; that grouping was followed
  rather than re-litigated here. Hong Kong, Macau and Puerto Rico are
  filed under their own ISO codes (HK, MO, PR) rather than under the
  country whose section listed them.
- **Largest-art-museum rows across all countries** (those carrying
  `gallery_space_m2`): a public dataset of the world's largest art
  museums by gallery space. License unresolved -- see `data/README.md`.
