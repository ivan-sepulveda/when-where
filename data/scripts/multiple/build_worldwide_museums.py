"""
Builds data/processed/multiple/worldwide_museums.json from a manually
exported PDF of the Japan National Tourism Organization (JNTO) travel
directory's "Art Museum" category (https://www.japan.travel, 96 results).
Fills a gap in build_city_attractions.py's art_museum category (IMLS-only,
US) and art_museums_by_country.json (only the ~112 largest worldwide).

Data source: manual PDF export, transcribed by hand. Not an API pull --
no automated re-fetch yet.

Schema mirrors osm_zoos_and_gardens.json ({name, category, kind, iso2,
lat, lng, ...}) so a future loader can match load_osm_places() in
build_city_attractions.py. "kind" is JNTO's own directory tag (e.g. "Art
Museum", "Modern Architecture"), not a normalized taxonomy. lat/lng are
null -- this source has no coordinates; geocoding is a future step. No
source-specific id field is kept -- JNTO's own page reference showed up
for some JP entries, but that's Japan-only and wouldn't generalize to
other countries' directory sources.

Transcription rule: names/descriptions are copied exactly as the PDF
rendered them, including a trailing "..." where the source text was cut
off -- none of the ~10 truncated names were completed by guessing.
location_raw is kept as one raw string (not split into city/prefecture)
since a few entries show only one segment.

Filtering ("only Museums or Galleries"): excluded 3 of 96 results that
name a park/complex or aren't a venue at all -- see EXCLUDED_NON_MUSEUM
below for which and why.

Usage: python build_worldwide_museums.py
"""

import json
from datetime import date
from pathlib import Path

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
OUTPUT_PATH = PROCESSED_DIR / "worldwide_museums.json"

# (name, kind, description, location_raw) -- transcribed in directory order
# from the PDF, one tuple per JNTO "Art Museum" result kept after the
# park/city-profile exclusions described above.
JAPAN_PLACES = [
    ("Rantokaku Art Museum", "Art Museum", "The buildings that make up the Rantokaku Museum are jus...", None),
    ("Oita Art Museum", "Art Museum", "Treasured works by regional artists", "Oita-shi, Oita-ken"),
    ("Kushiro Art Museum Hokkaido", "Art Museum", None, "Kushiro-shi, Hokkaido"),
    ("Mori Art Museum", "Art Museum", "One of Roppongi's most iconic museums for contemporary ...", None),
    ("Rokuzan Art Museum", "Art Museum", None, "Azumino-shi, Nagano-…"),
    ("Tokugawa Art Museum", "Art Museum", "Top museum of samurai art and culture", None),
    ("Shimane Art Museum", "Art Museum", None, "Matsue-shi, Shimane-k…"),
    ("Sagawa Art Museum", "Modern Architecture", "The floating museum", "Moriyama-shi, Shiga-ken"),
    ("Fukuoka Asian Art Museum", "Art Museum", "A Museum Featuring Modern and Contemporary Asian Art", None),
    ("Nagasaki Prefectural Art Museum", "Art Museum", "An art lovers dream", None),
    ("Oita Prefectural Art Museum", "Modern Architecture", "An open treasure trove of locally and globally signific...", None),
    ("Tokyo Photographic Art Museum", "Art Museum", "A stunning collection of still and moving images", None),
    ("Hiroshima Prefectural Art Museum", "Art Museum", "There are a number of art", None),
    ("Itchiku Kubota Art Museum", "Art Museum", "Magnificent collection of one-of-a-kind kimono designed...", None),
    ("Nagoya City Art Museum", "Art Museum", None, "Nagoya-shi, Aichi-ken"),
    ("Mie Prefectural Art Museum", "Art Museum", "Take a pleasant outing for art away from Japan's big ci...", None),
    ("Tokyo Metropolitan Teien Art Museum", "Art Museum", "Decor to explore", "Tokyo-to"),
    ("The Omiya Bonsai Art Museum, Saitama", "Bonsai", "The Best Bonsai in the ...", None),
    ("The Museum Of Modern Art, Saitama", "Art Museum", "A modern art museum for...", None),
    ("21st Century Museum Of Contemporary...", "Art Museum", "A contemporary art", None),
    ("The National Art Center, Tokyo", "Modern Architecture", "Japan's only national art museum that focuses on collec...", None),
    ("Ichihara Lakeside Museum", "Art Museum", "Ichihara Lakeside Museum is modern art museum located n...", None),
    ("Museum Of Modern Art, Wakayama", "Art Museum", "Cleanse your Cultural Palate", None),
    ("Shoji Ueda Museum", "Art Museum", "World-class photography in local settings", "Saihaku-gun, Tottori-k…"),
    ("Adachi Museum Of Art", "Art Museum", "Famous for its gardens as well as its art", None),
    ("Hirayama Ikuo Museum Of Art", "Art Museum", "See the works of Hiroshima's most famous and controvers...", None),
    # Distinct from the Idemitsu Museum Of Arts entry further down (Tokyo,
    # "70 years of collector's passion") -- this card's own blurb names it
    # as the Kitakyushu branch, so both are kept as separate real places
    # rather than deduped into one.
    ("Idemitsu Museum Of Arts", "Art Museum", "The Kitakyushu Branch of the famous Tokyo Idemistu Muse...", None),
    ("Saga Prefectural Museum", "Art Museum", "A collection of Saga's history, culture, and art", None),
    ("Yatsugatake Museum Of Art", "Art Museum", None, "Suwa-gun, Nagano-ken"),
    ("Kumamoto Prefectural Museum Of Art", "Art Museum", None, "Kumamoto-shi, Kuma…"),
    ("Fukushima Prefectural Museum Of Art", "Art Museum", "A Mixture of Japanese,", None),
    ("Asakura Museum Of Sculpture", "Art Museum", "A park that honors Japan's most influential sculptor", None),
    ("Yokohama Museum Of Art", "Art Museum", "A treasure trove of Western and Japanese art", None),
    ("Hishikawa Moronobu Memorial Museum", "Art Museum", None, "Awa-gun, Chiba-ken"),
    ("House Of Light", "Art Museum", "Spend the night in a meditative masterpiece", "Tokamachi-shi, Niigata…"),
    ("Kitakyushu Municipal Museum Of Art", "Art Museum", None, "Kitakyushu-shi, Fukuo…"),
    ("Ohara Museum Of Art", "Art Museum", "Located in the heart of the Bikan Historical District i...", None),
    ("Matsumoto City Museum Of Art", "Art Museum", "Immerse yourself in the art of one of the world's leadi...", None),
    ("Ishikawa Museum Of Traditional Arts...", "Art Museum", None, "Kanazawa-shi, Ishikaw…"),
    ("Sesshu Memorial Museum", "Art Museum", "Delightful and contemplative space devoted to one of t...", None),
    ("Izumo Museum Of Quilt Art", "Art Museum", "The only museum of quilt art in Japan", None),
    ("Teiko Shiotani Memorial Photo Galle...", "Art Museum", "A charming museum", None),
    ("Enoura Observatory, Odawara Art Fou...", "Art Museum", "An art complex with", None),
    ("Hokkaido Museum Of Modern Art", "Art Museum", "Cultural Treasures from Home and Abroad", None),
    ("Migishi Kotaro Museum Of Art Hokkai...", "Art Museum", "Kotaro Migishi, a pioneer", None),
    ("Hakodate Museum Of Art, Hokkaido", "Art Museum", None, "Hakodate-shi, Hokkaido"),
    ("Aomori Museum Of Art", "Modern Architecture", "World-class design and Aomori culture", None),
    ("Towada Art Center", "Art Museum", "Amazing new art center concept, and the beautiful Towad...", None),
    ("Akita Museum Of Art", "Art Museum", "A stunning structure showcasing the work of local artis...", None),
    ("Iwate Museum Of Art", "Art Museum", "Sculptures, paintings and pottery by Iwate's greatest a...", None),
    ("Ken Domon Museum Of Photography", "Art Museum", "A Museum of an Un-", None),
    ("Morohashi Museum Of Modern Art", "Art Museum", "A world-class collection of modern western art in the m...", None),
    ("21_21 DESIGN SIGHT", "Art Museum", "21_21 Design Site is the ultimate design lover's fantas...", None),
    ("Mitsuo Aida Museum", "Art Museum", "Calligraphy of the soul", "Tokyo-to"),
    ("Idemitsu Museum Of Arts", "Art Museum", "70 years of collector's passion", None),
    ("Suntory Museum Of Art", "Art Museum", "The museum dedicated to the beauty of the 'everyday'", None),
    ("Museum Of Contemporary Art Tokyo", "Art Museum", "Japan's largest museum", None),
    ("The Sumida Hokusai Museum", "Modern Architecture", "Sumida's tribute to its most famous artist", None),
    ("Nezu Museum", "Art Museum", "Tea houses, traditional gardens, and an extensive colle...", None),
    ("The Hakone Open-Air Museum", "Sculpture", "Explore an open-air museum where art and nature merge", None),
    ("Chiba Prefectural Museum Of Art", "Art Museum", None, "Chiba-shi, Chiba-ken"),
    ("Hoki Museum", "Modern Architecture", "Japan's first dedicated space to realism art", "Chiba-shi, Chiba-ken"),
    ("Hyogo Prefectural Museum Of Art", "Art Museum", None, "Kobe-shi, Hyogo-ken"),
    ("Museum Of Modern Art Gunma", "Art Museum", None, "Takasaki-shi, Gunma-k…"),
    ("Ceramic Art Messe Mashiko", "Art Museum", "View a town through the lens of pottery", None),
    ("Mashiko Sankokan Museum", "Art Museum", None, "Haga-gun, Tochigi-ken"),
    ("Tochigi Prefectural Museum Of Fine ...", "Art Museum", None, "Utsunomiya-shi, Tochi…"),
    ("Art Tower Mito", "Art Museum", None, "Mito-shi, Ibaraki-ken"),
    ("Niigata Prefectural Museum Of Moder...", "Art Museum", None, "Nagaoka-shi, Niigata-k…"),
    ("Toyama Prefectural Museum Of Art An...", "Art Museum", "An impressive new", None),
    ("Ishikawa Prefectural Museum Of Art", "Art Museum", "Explore the regional arts", None),
    ("Japan Ukiyoe Museum", "Art Museum", "Pictures from the floating world", None),
    ("Utsukushigahara Open-Air Museum", "Art Museum", "City Meets Country, Bubble Era Style", None),
    ("Hokusai Museum", "Art Museum", "A collection from the floating world of Hokusai", "Kamitakai-gun, Nagan…"),
    ("Hirayama Ikuo Silk Road Museum", "Art Museum", "Hirayama Ikuo was a Japanese artists with an obsession ...", None),
    ("Kiyosato Museum Of Photographic Art...", "Art Museum", "The Kiyosato Musuem of", None),
    ("Nakamura Keith Haring Collection", "Art Museum", "The Nakamura Keith Haring Collection is dedicated to ho...", None),
    ("Yamanashi Prefectural Museum Of Art", "Art Museum", "Works by some of the", None),
    ("Shizuoka Prefectural Museum Of Art", "Art Museum", "A treasure house of", None),
    ("Okayama Prefectural Museum Of Art", "Art Museum", None, "Okayama-shi, Okayam…"),
    ("MOA Museum Of Art", "Art Museum", "Ten centuries of Japanese and Chinese art treasures in ...", None),
    ("Raku Museum", "Art Museum", "A family tradition", "Kyoto-shi, Kyoto-fu"),
    ("Koryo Museum Of Art", "Art Museum", "See art and artifacts from Korea's ancient dynasties", None),
    ("Shiga Museum Of Art", "Art Museum", None, "Otsu-shi, Shiga-ken"),
    ("Miho Museum", "Art Museum", "Shangri-La for art and architecture lovers", "Koka-shi, Shiga-ken"),
    ("The National Museum Of Western Art", "National Art Museum", "World-class architecture", None),
    ("The National Film Archive Of Japan", "National Art Museum", "The one and only national institution of films in Japan", None),
    # Two distinct real branches (Tokyo and Kyoto both operate a "National
    # Museum of Modern Art"); the PDF's card text distinguishes them
    # ("near the Imperial" vs "with a collection") but truncates both
    # names identically, so both are kept, in source order, rather than
    # guessing which city suffix belongs to which.
    ("The National Museum Of Modern Art, ...", "National Art Museum", "Museum near the Imperial", None),
    ("The National Museum Of Modern Art, ...", "National Art Museum", "Museum with a collection", None),
    ("The National Museum Of Art, Osaka", "National Art Museum", "High culture from across", None),
    ("Sand Museum", "Attraction", "A world-class sand art installation overlooking Tottori...", None),
    ("Nima Sand Museum", "Attraction", 'This unique museum inspired by "singing sands" is also ...', None),
    ("National Crafts Museum", "Art & Design", "The National Crafts Museum Houses Modern Japanese and O...", None),
]

EXCLUDED_NON_MUSEUM = [
    {"name": "Arita Porcelain Park", "kind": "Park", "reason": "a themed village/park, not a single museum or gallery"},
    {"name": "Sapporo Art Park", "kind": "Art Museum", "reason": "a multi-facility park (sculpture garden, workshops, theatre), not itself one museum"},
    {"name": "Kanazawa", "kind": "Culture", "reason": "a city profile card in the directory, not a venue at all"},
]


def build():
    places = []
    for name, kind, description, location_raw in JAPAN_PLACES:
        places.append(
            {
                "name": name,
                "category": "art_museum",
                "kind": kind,
                "iso2": "JP",
                "description": description,
                "location_raw": location_raw,
                "lat": None,
                "lng": None,
            }
        )

    kind_counts: dict[str, int] = {}
    for p in places:
        kind_counts[p["kind"]] = kind_counts.get(p["kind"], 0) + 1

    payload = {
        "source": (
            "Japan National Tourism Organization (JNTO) official travel directory, "
            "'Art Museum' content-type filter (https://www.japan.travel). Manually "
            "exported to PDF and transcribed by hand -- not an API pull, no automated "
            "re-fetch yet."
        ),
        "attribution": "Japan National Tourism Organization (JNTO)",
        "generated": date.today().isoformat(),
        "countries_covered": ["JP"],
        "total_places": len(places),
        "places_by_kind": kind_counts,
        "excluded_non_museum": EXCLUDED_NON_MUSEUM,
        "note": (
            "Data source: manual PDF export, transcribed by hand -- not exhaustive, "
            "only the 'Art Museum' filter's 96 results (93 kept, 3 excluded, see "
            "excluded_non_museum). lat/lng are null; this source has no coordinates."
        ),
        "places": places,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"Wrote {len(places)} places ({OUTPUT_PATH.stat().st_size} bytes) -> {OUTPUT_PATH}")
    print("places_by_kind:", kind_counts)
    print("excluded:", [e["name"] for e in EXCLUDED_NON_MUSEUM])


if __name__ == "__main__":
    build()
