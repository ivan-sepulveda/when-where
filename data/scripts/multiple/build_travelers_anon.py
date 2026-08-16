"""
Builds data/processed/multiple/travelers_anon.json from
data/processed/multiple/travelers.json (see build_travelers.py): the same
travelers, the same trips, but every generic sample name ("John Smith",
"Ken Tanaka") replaced by a real, DECEASED author of the same nationality and
gender -- Nobel laureates and the most widely-read names first.

Why: the source dataset's names are filler, and filler names make a page of
124 cards unreadable -- half of them are some permutation of Smith/Lee/Kim, and
two cards apart are indistinguishable at a glance. Swapping in Hemingway,
Woolf, Kawabata and Alice Munro makes each card memorable, which is what a demo
page of traveler profiles actually needs. The trips, dates, costs, ages and
nationalities are all untouched: only who the trips are attributed to changes.

Rules this follows, in order:
  1. Same nationality, same gender as the traveler being replaced.
  2. Deceased. Every name in ROSTER below is a writer who has died -- no
     living author is put in someone else's shoes, and it keeps the list
     stable (a roster of living people would need re-checking).
  3. Best-known first. Each nationality's list is ordered roughly by
     recognition, Nobel laureates at the front, so the most-travelled
     travelers (travelers.json is sorted most-trips-first, and this script
     assigns in that order) get the most recognizable names.
  4. Each author is used at most once, so no two cards share a name.

traveler_id becomes the plain slug of the author's name -- "jane-austen", not
"jane-austen-british". The nationality suffix existed in build_travelers.py to
disambiguate two different sample travelers who happened to share a name; real
author names don't collide, and rule 4 guarantees it.

WHERE THIS IS NECESSARILY IMPERFECT, since it should be visible rather than
buried:
  - A few nationalities in this dataset have a thin published record of
    deceased authors (Emirati, Cambodian, Singaporean). Where a nationality's
    roster runs out, REGION_FALLBACK supplies an author from the same broad
    literary region instead, and that traveler is marked
    `persona_match: "region"` -- so a nationality mismatch is recorded in the
    data, not silently papered over. `persona_match: "nationality"` is an
    exact match; `"unmapped"` (name left alone) means neither had anyone left.
  - "Nationality" for an author is often contested (Kafka, Nabokov, Eliot).
    Where this project had to pick, it picked the one the writer is most
    commonly filed under, and left a comment.
  - Hand-authored travelers (see build_synthetic_trips.py) are passed through
    untouched, keeping their own name and traveler_id and marked
    `persona_match: "authored"` -- they were written with the name they're
    meant to have.
  - This is a swap of one set of names for another in sample data, not real
    anonymization of real people. The source is fictional to begin with (see
    fetch_traveler_trips.py) -- nothing here protects anyone's privacy, and
    it shouldn't be described as if it does.

The mapping is printed to stdout on every run but deliberately NOT written
into the output file: the point is a file that stands on its own.

Usage:
    python build_travelers_anon.py
    python build_travelers_anon.py --quiet    # skip the per-traveler mapping printout
"""

import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the roster is the whole substance of this script.
# ---------------------------------------------------------------------------

# Nationality strings in the source are inconsistent -- it carries "Brazil"
# and "Brazilian", "USA" and "American", "Korean" / "South Korea" /
# "South Korean" -- so everything is normalized through this before lookup.
# Keys are lowercased; anything not listed falls through to itself.
NATIONALITY_ALIASES = {
    "usa": "american",
    "united states": "american",
    "us": "american",
    "uk": "british",
    "united kingdom": "british",
    "england": "british",
    "english": "british",
    "great britain": "british",
    "canada": "canadian",
    "japan": "japanese",
    "korea": "korean",
    "south korea": "korean",
    "south korean": "korean",
    "china": "chinese",
    "taiwan": "taiwanese",
    "hong kong": "hongkonger",
    "hongkong": "hongkonger",
    "spain": "spanish",
    "italy": "italian",
    "germany": "german",
    "greece": "greek",
    "france": "french",
    "brazil": "brazilian",
    "mexico": "mexican",
    "india": "indian",
    "vietnam": "vietnamese",
    "indonesia": "indonesian",
    "australia": "australian",
    "new zealand": "new zealander",
    "netherlands": "dutch",
    "holland": "dutch",
    "scotland": "scottish",
    "singapore": "singaporean",
    "cambodia": "cambodian",
    "morocco": "moroccan",
    "south africa": "south african",
    "united arab emirates": "emirati",
    "uae": "emirati",
    "russia": "russian",
    "ireland": "irish",
    "portugal": "portuguese",
    "poland": "polish",
    "sweden": "swedish",
    "norway": "norwegian",
    "turkey": "turkish",
    "thailand": "thai",
    "egypt": "egyptian",
    "nigeria": "nigerian",
    "argentina": "argentinian",
    "argentine": "argentinian",
    "chile": "chilean",
    "colombia": "colombian",
    "peru": "peruvian",
    "philippines": "filipino",
    "malaysia": "malaysian",
    "pakistan": "pakistani",
    "israel": "israeli",
    "austria": "austrian",
    "switzerland": "swiss",
    "denmark": "danish",
    "finland": "finnish",
    "czech republic": "czech",
    "hungary": "hungarian",
    "cuba": "cuban",
}

# nationality -> gender -> [author name, ...], best-known first. Names only:
# an earlier version carried a one-line claim to fame per author ("Nobel Prize
# in Literature, 1938") and rendered it on the traveler's page, which turned a
# list of travelers into a list of literary credentials -- not what the page is
# for. The ordering still encodes the same judgment, it just isn't stated.
ROSTER = {
    "american": {
        "Male": [
            "Ernest Hemingway",
            "William Faulkner",
            "John Steinbeck",
            "Mark Twain",
            "F. Scott Fitzgerald",
            "Herman Melville",
            "Edgar Allan Poe",
            "Saul Bellow",
            "Sinclair Lewis",
            "Kurt Vonnegut",
            "James Baldwin",
            "Walt Whitman",
            "Robert Frost",
            "Jack London",
            "Ralph Ellison",
            "John Updike",
            "Philip Roth",
            "Ray Bradbury",
        ],
        "Female": [
            "Toni Morrison",
            "Pearl S. Buck",
            "Emily Dickinson",
            "Harper Lee",
            "Maya Angelou",
            "Edith Wharton",
            "Willa Cather",
            "Flannery O'Connor",
            "Ursula K. Le Guin",
            "Zora Neale Hurston",
            "Sylvia Plath",
            "Louisa May Alcott",
        ],
    },
    "british": {
        "Male": [
            "William Shakespeare",
            "Charles Dickens",
            "George Orwell",
            "Rudyard Kipling",
            "William Golding",
            "Harold Pinter",
            "Thomas Hardy",
            "Aldous Huxley",
            "Graham Greene",
            "J. R. R. Tolkien",
        ],
        "Female": [
            "Jane Austen",
            "Virginia Woolf",
            "Doris Lessing",
            "Charlotte Bronte",
            "Emily Bronte",
            "George Eliot",
            "Mary Shelley",
            "Agatha Christie",
            "Daphne du Maurier",
            "Iris Murdoch",
        ],
    },
    "scottish": {
        # Filed separately from British because the source dataset lists
        # "Scottish" as its own nationality -- so a Scottish traveler gets a
        # Scottish writer rather than an English one.
        "Male": [
            "Robert Louis Stevenson",
            "Robert Burns",
            "Walter Scott",
            "Arthur Conan Doyle",
        ],
        "Female": [
            "Muriel Spark",
            "Nan Shepherd",
            "Naomi Mitchison",
        ],
    },
    "canadian": {
        "Male": [
            "Robertson Davies",
            "Mordecai Richler",
            "Leonard Cohen",
            "Stephen Leacock",
            "Timothy Findley",
        ],
        "Female": [
            "Alice Munro",
            "L. M. Montgomery",
            "Margaret Laurence",
            "Mavis Gallant",
            "Carol Shields",
            "Gabrielle Roy",
            "P. K. Page",
            "Marian Engel",
        ],
    },
    "australian": {
        "Male": [
            "Patrick White",
            "Henry Lawson",
            "Banjo Paterson",
        ],
        "Female": [
            "Christina Stead",
            "Miles Franklin",
            "Colleen McCullough",
            "Elizabeth Jolley",
            "Ruth Park",
        ],
    },
    "new zealander": {
        "Male": [
            "Frank Sargeson",
            "James K. Baxter",
            "Hone Tuwhare",
        ],
        "Female": [
            "Katherine Mansfield",
            "Janet Frame",
            "Ngaio Marsh",
        ],
    },
    "japanese": {
        "Male": [
            "Yasunari Kawabata",
            "Kenzaburo Oe",
            "Natsume Soseki",
            "Yukio Mishima",
            "Junichiro Tanizaki",
            "Ryunosuke Akutagawa",
            "Kobo Abe",
            "Osamu Dazai",
        ],
        "Female": [
            "Murasaki Shikibu",
            "Sei Shonagon",
            "Ichiyo Higuchi",
            "Fumiko Enchi",
            "Yuko Tsushima",
        ],
    },
    "korean": {
        "Male": [
            "Yun Dong-ju",
            "Yi Sang",
            "Kim Su-yong",
            "Han Yong-un",
            "Yi Kwang-su",
            "Kim Dong-ni",
            "Choi In-hun",
            "Hyun Jin-geon",
            "Kim Yu-jeong",
            "Jeong Ji-yong",
        ],
        "Female": [
            "Park Kyong-ni",
            "Park Wan-suh",
            "Heo Nanseolheon",
            "Hwang Jini",
            "Na Hye-sok",
            "Kang Kyeong-ae",
            "Shin Saimdang",
            "Kim Myeong-sun",
            "No Cheon-myeong",
            "Kim Il-yeop",
        ],
    },
    "chinese": {
        "Male": [
            "Lu Xun",
            "Lao She",
            "Ba Jin",
            "Shen Congwen",
            "Cao Xueqin",
            "Du Fu",
            "Li Bai",
        ],
        "Female": [
            "Eileen Chang",
            "Bing Xin",
            "Ding Ling",
            "Xiao Hong",
            "Li Qingzhao",
        ],
    },
    "taiwanese": {
        "Male": [
            "Bo Yang",
            "Chung Li-ho",
            "Wang Wen-hsing",
        ],
        "Female": [
            "Sanmao",
            "Lin Hai-yin",
            "Nieh Hualing",
            "Chi Chun",
        ],
    },
    "hongkonger": {
        "Male": [
            "Jin Yong",
            "Liu Yichang",
        ],
        "Female": [
            "Xi Xi",
        ],
    },
    "vietnamese": {
        "Male": [
            "Nguyen Du",
            "Nam Cao",
            "Vu Trong Phung",
            "Nguyen Tuan",
        ],
        "Female": [
            "Ho Xuan Huong",
            "Xuan Quynh",
            "Doan Thi Diem",
        ],
    },
    "indonesian": {
        "Male": [
            "Pramoedya Ananta Toer",
            "Chairil Anwar",
        ],
        "Female": [
            "Nh. Dini",
        ],
    },
    "singaporean": {
        # Thin by necessity -- most of Singapore's best-known writers are
        # still living, and rule 2 rules them out. REGION_FALLBACK covers
        # the overflow.
        "Male": [
            "Arthur Yap",
            "Goh Poh Seng",
        ],
        "Female": [],
    },
    "cambodian": {
        "Male": [
            "Nhok Them",
            "Preah Botumthera Som",
        ],
        "Female": [],
    },
    "thai": {
        "Male": [
            "Sunthorn Phu",
            "Kukrit Pramoj",
        ],
        "Female": [
            "Dokmai Sot",
        ],
    },
    "filipino": {
        "Male": [
            "Jose Rizal",
            "Nick Joaquin",
        ],
        "Female": [
            "Kerima Polotan Tuvera",
        ],
    },
    "indian": {
        "Male": [
            "Rabindranath Tagore",
            "R. K. Narayan",
            "Munshi Premchand",
            "Mulk Raj Anand",
        ],
        "Female": [
            "Mahasweta Devi",
            "Amrita Pritam",
            "Kamala Das",
            "Sarojini Naidu",
            "Ismat Chughtai",
        ],
    },
    "pakistani": {
        "Male": [
            "Saadat Hasan Manto",
            "Faiz Ahmed Faiz",
        ],
        "Female": [
            "Bapsi Sidhwa",
            "Fahmida Riaz",
        ],
    },
    "french": {
        "Male": [
            "Victor Hugo",
            "Albert Camus",
            "Marcel Proust",
            "Gustave Flaubert",
            "Emile Zola",
            "Andre Gide",
            "Alexandre Dumas",
        ],
        "Female": [
            "Simone de Beauvoir",
            "Colette",
            "George Sand",
            "Marguerite Duras",
            "Marguerite Yourcenar",
        ],
    },
    "german": {
        "Male": [
            "Thomas Mann",
            "Johann Wolfgang von Goethe",
            "Hermann Hesse",
            "Gunter Grass",
            "Heinrich Boll",
            "Bertolt Brecht",
        ],
        "Female": [
            "Nelly Sachs",
            "Christa Wolf",
            "Anna Seghers",
        ],
    },
    "austrian": {
        "Male": [
            "Stefan Zweig",
            "Robert Musil",
            "Thomas Bernhard",
        ],
        "Female": [
            "Ingeborg Bachmann",
            "Marie von Ebner-Eschenbach",
        ],
    },
    "italian": {
        "Male": [
            "Dante Alighieri",
            "Italo Calvino",
            "Luigi Pirandello",
            "Umberto Eco",
            "Primo Levi",
            "Eugenio Montale",
        ],
        "Female": [
            "Grazia Deledda",
            "Elsa Morante",
            "Natalia Ginzburg",
            "Oriana Fallaci",
            "Anna Maria Ortese",
        ],
    },
    "spanish": {
        "Male": [
            "Miguel de Cervantes",
            "Federico Garcia Lorca",
            "Camilo Jose Cela",
            "Juan Ramon Jimenez",
            "Antonio Machado",
            "Miguel de Unamuno",
        ],
        "Female": [
            "Emilia Pardo Bazan",
            "Rosalia de Castro",
            "Ana Maria Matute",
            "Carmen Laforet",
            "Carmen Martin Gaite",
            "Maria Zambrano",
            "Gloria Fuertes",
        ],
    },
    "portuguese": {
        "Male": [
            "Jose Saramago",
            "Fernando Pessoa",
            "Eca de Queiros",
        ],
        "Female": [
            "Sophia de Mello Breyner Andresen",
            "Agustina Bessa-Luis",
        ],
    },
    "dutch": {
        # Anne Frank is deliberately not on this list. She fits the criteria
        # on paper and is the most famous Dutch diarist there is, but
        # reassigning a murdered child's name to a fictional tourist taking
        # beach holidays is not a trade this project is going to make.
        "Male": [
            "Harry Mulisch",
            "Willem Frederik Hermans",
            "Gerard Reve",
        ],
        "Female": [
            "Hella Haasse",
            "Annie M. G. Schmidt",
        ],
    },
    "greek": {
        "Male": [
            "Nikos Kazantzakis",
            "George Seferis",
            "Odysseas Elytis",
            "Constantine Cavafy",
        ],
        "Female": [
            "Sappho",
            "Penelope Delta",
            "Kiki Dimoula",
        ],
    },
    "russian": {
        "Male": [
            "Leo Tolstoy",
            "Fyodor Dostoevsky",
            "Anton Chekhov",
            "Alexander Pushkin",
            "Boris Pasternak",
            "Nikolai Gogol",
            "Mikhail Bulgakov",
        ],
        "Female": [
            "Anna Akhmatova",
            "Marina Tsvetaeva",
            "Nadezhda Teffi",
        ],
    },
    "polish": {
        "Male": [
            "Henryk Sienkiewicz",
            "Czeslaw Milosz",
            "Stanislaw Lem",
            "Bruno Schulz",
        ],
        "Female": [
            "Wislawa Szymborska",
            "Zofia Nalkowska",
            "Maria Konopnicka",
        ],
    },
    "irish": {
        "Male": [
            "James Joyce",
            "Samuel Beckett",
            "W. B. Yeats",
            "Oscar Wilde",
            "Seamus Heaney",
        ],
        "Female": [
            "Edna O'Brien",
            "Maeve Binchy",
            "Lady Gregory",
        ],
    },
    "swedish": {
        "Male": [
            "August Strindberg",
            "Par Lagerkvist",
            "Tomas Transtromer",
        ],
        "Female": [
            "Selma Lagerlof",
            "Astrid Lindgren",
            "Karin Boye",
        ],
    },
    "norwegian": {
        "Male": [
            "Henrik Ibsen",
            "Knut Hamsun",
            "Bjornstjerne Bjornson",
        ],
        "Female": [
            "Sigrid Undset",
            "Camilla Collett",
            "Amalie Skram",
        ],
    },
    "danish": {
        "Male": [
            "Hans Christian Andersen",
            "Johannes V. Jensen",
        ],
        "Female": [
            "Karen Blixen",
            "Tove Ditlevsen",
        ],
    },
    "finnish": {
        "Male": [
            "Mika Waltari",
            "F. E. Sillanpaa",
            "Vaino Linna",
        ],
        "Female": [
            "Tove Jansson",
            "Minna Canth",
        ],
    },
    "czech": {
        "Male": [
            "Franz Kafka",  # Prague-born, German-language; filed Czech here
            "Karel Capek",
            "Milan Kundera",
            "Jaroslav Seifert",
        ],
        "Female": [
            "Bozena Nemcova",
        ],
    },
    "hungarian": {
        "Male": [
            "Imre Kertesz",
            "Sandor Marai",
            "Antal Szerb",
        ],
        "Female": [
            "Magda Szabo",
        ],
    },
    "swiss": {
        "Male": [
            "Friedrich Durrenmatt",
            "Max Frisch",
            "Robert Walser",
        ],
        "Female": [
            "Johanna Spyri",
            "Annemarie Schwarzenbach",
        ],
    },
    "turkish": {
        "Male": [
            "Nazim Hikmet",
            "Yasar Kemal",
            "Sait Faik Abasiyanik",
        ],
        "Female": [
            "Halide Edib Adivar",
            "Adalet Agaoglu",
        ],
    },
    "israeli": {
        "Male": [
            "S. Y. Agnon",
            "Amos Oz",
        ],
        "Female": [
            "Leah Goldberg",
        ],
    },
    "brazilian": {
        "Male": [
            "Machado de Assis",
            "Jorge Amado",
            "Carlos Drummond de Andrade",
            "Joao Guimaraes Rosa",
            "Mario de Andrade",
        ],
        "Female": [
            "Clarice Lispector",
            "Cecilia Meireles",
            "Rachel de Queiroz",
        ],
    },
    "mexican": {
        "Male": [
            "Octavio Paz",
            "Juan Rulfo",
            "Carlos Fuentes",
            "Juan Jose Arreola",
        ],
        "Female": [
            "Sor Juana Ines de la Cruz",
            "Rosario Castellanos",
            "Elena Garro",
        ],
    },
    "argentinian": {
        "Male": [
            "Jorge Luis Borges",
            "Julio Cortazar",
            "Ernesto Sabato",
        ],
        "Female": [
            "Alfonsina Storni",
            "Silvina Ocampo",
            "Victoria Ocampo",
        ],
    },
    "chilean": {
        "Male": [
            "Pablo Neruda",
            "Nicanor Parra",
            "Roberto Bolano",
        ],
        "Female": [
            "Gabriela Mistral",
            "Marta Brunet",
        ],
    },
    "colombian": {
        "Male": [
            "Gabriel Garcia Marquez",
            "Jose Eustasio Rivera",
        ],
        "Female": [
            "Marvel Moreno",
            "Soledad Acosta de Samper",
        ],
    },
    "peruvian": {
        "Male": [
            "Mario Vargas Llosa",
            "Cesar Vallejo",
            "Jose Maria Arguedas",
        ],
        "Female": [
            "Blanca Varela",
        ],
    },
    "cuban": {
        "Male": [
            "Jose Marti",
            "Alejo Carpentier",
            "Guillermo Cabrera Infante",
        ],
        "Female": [
            "Dulce Maria Loynaz",
        ],
    },
    "south african": {
        "Male": [
            "Alan Paton",
            "Andre Brink",
            "Es'kia Mphahlele",
        ],
        "Female": [
            "Nadine Gordimer",
            "Bessie Head",
            "Olive Schreiner",
        ],
    },
    "nigerian": {
        "Male": [
            "Chinua Achebe",
            "Amos Tutuola",
            "Ken Saro-Wiwa",
        ],
        "Female": [
            "Buchi Emecheta",
            "Flora Nwapa",
        ],
    },
    "kenyan": {
        "Male": [
            "Ngugi wa Thiong'o",
        ],
        "Female": [
            "Grace Ogot",
        ],
    },
    "egyptian": {
        "Male": [
            "Naguib Mahfouz",
            "Taha Hussein",
        ],
        "Female": [
            "Nawal El Saadawi",
            "Radwa Ashour",
        ],
    },
    "moroccan": {
        "Male": [
            "Mohamed Choukri",
            "Driss Chraibi",
            "Mohammed Khair-Eddine",
        ],
        "Female": [
            "Fatema Mernissi",
        ],
    },
    "emirati": {
        "Male": [
            "Sultan bin Ali Al Owais",
            "Ahmed Rashid Thani",
        ],
        "Female": [
            "Ousha bint Khalifa Al Suwaidi",
        ],
    },
}

# Used only when a nationality's own list is exhausted (or empty). Keyed by
# region; a traveler filled from here is marked persona_match: "region" so the
# imperfect match is recorded in the data rather than hidden. Names here are
# deliberately NOT duplicated from ROSTER -- an author already used anywhere
# is skipped, so rule 4 (each author at most once) still holds.
REGION_FALLBACK = {
    "arab": {
        "Male": [
            "Mahmoud Darwish",
            "Nizar Qabbani",
            "Ghassan Kanafani",
            "Khalil Gibran",
        ],
        "Female": [
            "Fadwa Tuqan",
            "May Ziadeh",
            "Nazik al-Malaika",
        ],
    },
    "east asia": {
        "Male": [
            "Wang Wei",
            "Su Shi",
        ],
        "Female": [
            "Qiu Jin",
            "Yu Xuanji",
        ],
    },
    "southeast asia": {
        "Male": [
            "Usman Awang",
            "Sitor Situmorang",
        ],
        # No female entry: the deceased Southeast Asian women writers this
        # project could confirm are already in ROSTER by nationality, and a
        # fallback pool that reaches outside the region would defeat the point
        # of having one. A traveler who needs this ends up "unmapped", which
        # the script reports so the roster can be extended.
        "Female": [],
    },
}

# Which fallback pool each nationality draws on when its own list runs dry.
# Anything not listed here gets no fallback -- it's left unmapped rather than
# handed an author from an unrelated literary tradition.
REGION_BY_NATIONALITY = {
    "emirati": "arab",
    "moroccan": "arab",
    "egyptian": "arab",
    "hongkonger": "east asia",
    "taiwanese": "east asia",
    "chinese": "east asia",
    "singaporean": "southeast asia",
    "cambodian": "southeast asia",
    "indonesian": "southeast asia",
    "filipino": "southeast asia",
    "thai": "southeast asia",
    "malaysian": "southeast asia",
}

# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
TRAVELERS_PATH = PROCESSED_DIR / "travelers.json"
OUTPUT_PATH = PROCESSED_DIR / "travelers_anon.json"


def normalize_nationality(nationality: str | None) -> str:
    if not nationality:
        return ""
    key = " ".join(str(nationality).strip().lower().split())
    return NATIONALITY_ALIASES.get(key, key)


def slugify(text: str) -> str:
    """"Gabriel Garcia Marquez" -> "gabriel-garcia-marquez". Same normalization
    as build_travelers.py's slugify() -- this is what /rec-sys/travelers/:id
    routes on, so it has to survive a URL round trip."""
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")
    return slug or "traveler"


class AuthorPool:
    """Hands out each author exactly once, nationality first and region
    second. Stateful on purpose: assignment order is the order travelers
    appear in travelers.json (most trips first), so the most-travelled
    travelers get the front of each list -- the best-known names."""

    def __init__(self):
        self.used: set[str] = set()

    def _take(self, entries) -> str | None:
        for name in entries:
            if name not in self.used:
                self.used.add(name)
                return name
        return None

    def assign(self, nationality: str | None, gender: str | None) -> tuple[str | None, str]:
        """(name, match) where match is "nationality", "region" or
        "unmapped" (in which case name is None)."""
        key = normalize_nationality(nationality)
        # A traveler with no gender recorded (or an unexpected value) falls
        # back to whichever list still has someone, rather than being left
        # unmapped over a missing field.
        genders = [gender] if gender in ("Male", "Female") else ["Female", "Male"]

        by_gender = ROSTER.get(key, {})
        for g in genders:
            taken = self._take(by_gender.get(g, []))
            if taken:
                return taken, "nationality"

        region = REGION_BY_NATIONALITY.get(key)
        if region:
            by_gender = REGION_FALLBACK.get(region, {})
            for g in genders:
                taken = self._take(by_gender.get(g, []))
                if taken:
                    return taken, "region"

        return None, "unmapped"


def build_anon_travelers(travelers: list[dict]) -> tuple[list[dict], list[tuple[str, str, str]]]:
    pool = AuthorPool()
    used_ids: set[str] = set()
    result: list[dict] = []
    mapping: list[tuple[str, str, str]] = []  # (original name, new name, match) -- printed, never written

    for traveler in travelers:
        # Hand-authored travelers (build_synthetic_trips.py) already carry the
        # name they're meant to have -- Frank Lloyd Wright IS the persona, not
        # a filler name waiting to be replaced. Renaming him would undo the
        # thing that made him worth authoring.
        if traveler.get("synthetic"):
            anon = dict(traveler)
            # The name is kept, but the id is re-slugged from it like every
            # other entry here: build_travelers.py appends the nationality to
            # disambiguate sample travelers who share a name
            # ("joaquin-sorolla-american"), and this file's whole
            # convention is bare-name ids ("jane-austen").
            traveler_id = slugify(traveler["name"])
            suffix = 2
            while traveler_id in used_ids:
                traveler_id = f"{slugify(traveler['name'])}-{suffix}"
                suffix += 1
            used_ids.add(traveler_id)

            anon["traveler_id"] = traveler_id
            anon["persona_match"] = "authored"
            mapping.append((traveler["name"], traveler["name"], "authored"))
            result.append(anon)
            continue

        name, match = pool.assign(traveler.get("nationality"), traveler.get("gender"))

        if name is None:
            # Nothing left for this nationality/gender: keep the original
            # traveler untouched (including its id) rather than inventing
            # something. Reported at the end so the roster can be extended.
            anon = dict(traveler)
            anon["persona_match"] = "unmapped"
            mapping.append((traveler["name"], traveler["name"], "unmapped"))
            result.append(anon)
            continue

        traveler_id = slugify(name)
        suffix = 2
        while traveler_id in used_ids:
            # Can't happen while rule 4 holds (each author once), but a
            # duplicate id would make one traveler unreachable by URL, so
            # don't leave it to chance.
            traveler_id = f"{slugify(name)}-{suffix}"
            suffix += 1
        used_ids.add(traveler_id)

        anon = dict(traveler)
        anon["traveler_id"] = traveler_id
        anon["name"] = name
        anon["persona_match"] = match
        result.append(anon)
        mapping.append((traveler["name"], name, match))

    return result, mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quiet", action="store_true", help="Don't print the per-traveler mapping.")
    args = parser.parse_args()

    if not TRAVELERS_PATH.exists():
        raise FileNotFoundError(
            f"{TRAVELERS_PATH} not found -- run scripts/multiple/build_travelers.py first."
        )
    with open(TRAVELERS_PATH, encoding="utf-8") as f:
        source = json.load(f)

    travelers, mapping = build_anon_travelers(source["travelers"])

    by_match: dict[str, int] = {}
    for _, _, match in mapping:
        by_match[match] = by_match.get(match, 0) + 1

    payload = {
        "source": (
            "travelers.json with each sample name replaced by a deceased author of the same "
            "nationality and gender -- see build_travelers_anon.py and data/README.md"
        ),
        "generated": date.today().isoformat(),
        "note": (
            "Trips, dates, costs, ages, genders and nationalities are unchanged from travelers.json; "
            "only the traveler_id and name differ. persona_match records how good the nationality "
            "match is: 'nationality' exact, 'region' an author from the same broad literary region "
            "(used where a nationality has too few deceased authors on record), 'unmapped' left as "
            "the original name. This is a name swap in fictional sample data, not anonymization of "
            "real people."
        ),
        "total_travelers": len(travelers),
        "total_trips": sum(t["trip_count"] for t in travelers),
        "persona_match_counts": by_match,
        "travelers": travelers,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    if not args.quiet:
        print("mapping (printed only -- deliberately not written into the output file):")
        for original, new, match in mapping:
            flag = "" if match == "nationality" else f"   [{match}]"
            print(f"  {original:<28} -> {new}{flag}")

    print(f"\nWrote {len(travelers)} travelers -> {OUTPUT_PATH}")
    print(f"  match quality: {by_match}")
    unmapped = [original for original, _, match in mapping if match == "unmapped"]
    if unmapped:
        print(f"  {len(unmapped)} traveler(s) had no author available and kept their original name: {unmapped}")
        print("  -> add deceased authors of that nationality/gender to ROSTER and re-run.")


if __name__ == "__main__":
    main()
