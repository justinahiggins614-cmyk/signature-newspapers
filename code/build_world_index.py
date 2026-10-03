#!/usr/bin/env python3
"""Site-14 fix wave: fictional-world entity index (mined from actual content).

Scans every article for the generator's own entity pools (people, orgs,
cities, teams, projects, things, events) and builds a permanent entity
index. Every entity gets a stable JAH-ENTITY-###### ID with first
appearance, appearance count, and type. NO entities are invented: the
pools come from code/gen_editions.py (the same pools the text was
generated from), and only entities that actually appear in article text
are indexed.

Output: data/index/entities.idx.json.gz (+ uncompressed .json fallback)
Rows: [entity_id, name, type, first_edition, first_date, appearances]
"""
import gzip, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VOL = os.path.join(ROOT, "data", "volumes")
IDX = os.path.join(ROOT, "data", "index")
SITE = "https://justinahiggins614-cmyk.github.io/signature-newspapers/"

POOLS = {
    "person": ["Wren Halloway", "Casper Vane", "Tamsin Cole", "Joren Pax",
               "Mira Solen", "Dorian Fenn", "Isolde Marr", "Kellan Drisc",
               "Odette Lorr", "Silas Quill", "Nadia Vex", "Percival Odd",
               "Rosalind Pryce", "Edmund Sable", "Vivienne Lark", "Cornelius Thade",
               "Beatrix Wold", "Alistair Fenwick", "Cordelia Vane", "Thaddeus Morn",
               "Elowen Marsh", "Barnaby Slate", "Imogen Starr", "Rupert Candle",
               "Sable Quinn", "Horace Pill", "Mabel Drummond", "Felix Arkwright"],
    "organization": ["the Signature Council", "the Lumen Exchange", "the Meridian Transit Authority",
                     "the Halloway Institute", "the Cartographers' Guild", "the Harmonic Society",
                     "the Guild of Makers", "the Observatory at Frostgate", "the Tidewater Port Authority",
                     "the Solar Conservatory", "the Archive of Weights and Measures",
                     "the Fellowship of Printers"],
    "city": ["Meridian City", "Argent Falls", "Borealia Harbor", "Solara Heights",
             "Pelagia Bay", "Vesper Crossing", "Lumenport", "Cadence Vale",
             "Halcyon Reach", "Juniper Quay", "Emberline", "Frostgate",
             "Glimmerwick", "Stonebridge", "Aldermere", "Cinderwick", "Marlowe Bay",
             "Quillhaven", "Tarnwick", "Opal Shores"],
    "team": ["Meridian Comets", "Argent Kestrels", "Solara Lanterns",
             "Pelagia Tides", "Borealia Auroras", "Vesper Foxes"],
    "project": ["The New Skybridge Arc", "The Grand Concourse Extension",
                "The Harbor Light-Rail Loop", "The Civic Athenaeum",
                "The Riverside Promenade", "The Night-Market Halls",
                "The Observatory Dome Restoration", "The Great Bell Tower",
                "The Underground Archive Vaults", "The Festival Green",
                "The Wind-Harbor Piers", "The Lantern District Renewal"],
    "thing": ["a pocket observatory", "a hand-crank printing press",
              "a tide-powered lantern", "a whisper-quiet courier drone",
              "a modular bookshelf engine", "a pocket planetarium",
              "a self-inking survey compass", "a fold-flat market stall",
              "a rain-chime array", "a solar tea kettle",
              "a clockwork message runner", "a harbor fog bell"],
    "event": ["Lantern Festival", "Harvest of Inks", "the Long Light Fair",
              "Founders' Week", "the Tide Gala", "the Paper & Press Parade",
              "the Starwatch Nights", "the Makers' Jubilee"],
}


def main():
    # compile matchers (case-insensitive; strip leading articles for orgs/things/events)
    matchers = []
    for etype, names in POOLS.items():
        for name in names:
            pat = re.sub(r"^(the|a|an) ", "", name)
            matchers.append((etype, name, re.compile(r"\b" + re.escape(pat) + r"\b", re.I)))
    stats = {}  # (etype, name) -> [first_edition, first_date, count]
    editions = []
    for cf in sorted(os.listdir(VOL)):
        if not cf.endswith(".jsonl.gz"):
            continue
        with gzip.open(os.path.join(VOL, cf), "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    editions.append(json.loads(line))
    editions.sort(key=lambda e: e["id"])
    for e in editions:
        text = " ".join(a["h"] + " " + " ".join(a["body"]) for a in e["articles"])
        for etype, name, rx in matchers:
            if rx.search(text):
                k = (etype, name)
                if k not in stats:
                    stats[k] = [e["id"], e["date"], 0]
                stats[k][2] += 1
    rows = []
    for i, ((etype, name), (fe, fd, n)) in enumerate(sorted(stats.items()), 1):
        eid_ = "JAH-ENTITY-%06d" % i
        rows.append([eid_, name, etype, fe, fd, n,
                     SITE + "?entity=" + eid_])
    with gzip.open(os.path.join(IDX, "entities.idx.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    with open(os.path.join(IDX, "entities.idx.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    by_type = {}
    for r in rows:
        by_type[r[2]] = by_type.get(r[2], 0) + 1
    print("entities indexed: %d  (%s)" % (len(rows), by_type))


if __name__ == "__main__":
    main()
