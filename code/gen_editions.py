#!/usr/bin/env python3
"""
The Signature Global Newspaper Archive - deterministic edition generator.

Usage:
    python3 code/gen_editions.py --backfill   # seed ~365 past days x 6 papers
    python3 code/gen_editions.py --daily       # cron: add today's editions (idempotent)
    python3 code/gen_editions.py --rebuild     # rebuild index/sitemap/api only
    python3 code/gen_editions.py --eco-rebuild  # replace ECO_START..today with
                                              # real-ecosystem editions, then rebuild

Determinism: edition content is seeded by SALT + paper + date, so re-running
never changes an existing edition. IDs (JAH-ED-######) are assigned in
chronological order; data/state.json tracks next_index and last_date.

CONTENT HONESTY, TWO ERAS:
  * 2025-10-03 .. 2026-09-27: retired Signature-world fiction editions. All
    people, places, teams, and events invented; kept in the archive and
    clearly labeled, never presented as fact.
  * 2026-09-28 onward: real Signature-ecosystem news editions. Every story
    is grounded in the 27 websites' own data (drip milestones, fixes
    shipped, launches, records) via code/eco_events.py. Never real-world
    news, never real persons' names, drafts never called filed patents.

Layout: weekly gz chunks data/volumes/editions-wNNNNN.jsonl.gz (7 days x 6
papers = 42 editions/chunk). Compact search index data/index/editions.idx.json.gz
rows: [id, date, paper_idx, n_articles, chunk, headlines+ledes joined, coverage].
"""
import argparse, gzip, hashlib, json, os, random, re, sys, datetime
import record_std  # permanent record standard: IDs, hashes, fictionality
import eco_events
import eco_stories

ECO_START = datetime.date(2026, 9, 28)  # first day of real ecosystem coverage


def local_today():
    """Today in America/New_York — the network's timezone (the VM runs UTC)."""
    import zoneinfo
    return datetime.datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
VOL = os.path.join(DATA, "volumes")
IDX = os.path.join(DATA, "index")
STATE_F = os.path.join(DATA, "state.json")
SALT = 20261002
SITE = "https://justinahiggins614-cmyk.github.io/signature-newspapers/"

EPOCH_START = datetime.date(2025, 10, 3)   # backfill begins here (365 days before 2026-10-02)

PAPERS = [
    {"name": "The Signature Daily Globe", "region": "the Signature world",
     "tagline": "All the world's Signature news, every morning",
     "founded": "2024-01-15"},
    {"name": "The Meridian Herald", "region": "Meridia",
     "tagline": "Meridia's morning voice since the first printing",
     "founded": "2024-02-01"},
    {"name": "The Argent Post", "region": "Argentia",
     "tagline": "Argentia, reported straight",
     "founded": "2024-03-10"},
    {"name": "The Northlight Times", "region": "Borealia",
     "tagline": "News from under the northern lights",
     "founded": "2024-04-22"},
    {"name": "The Sunspire Gazette", "region": "Solara",
     "tagline": "Solara's sunlit record of the day",
     "founded": "2024-06-05"},
    {"name": "The Tidewater Chronicle", "region": "Pelagia",
     "tagline": "Pelagia's paper of record, tide in tide out",
     "founded": "2024-07-19"},
]

CITIES = ["Meridian City", "Argent Falls", "Borealia Harbor", "Solara Heights",
          "Pelagia Bay", "Vesper Crossing", "Lumenport", "Cadence Vale",
          "Halcyon Reach", "Juniper Quay", "Emberline", "Frostgate",
          "Glimmerwick", "Stonebridge", "Aldermere", "Cinderwick", "Marlowe Bay",
          "Quillhaven", "Tarnwick", "Opal Shores"]

PEOPLE = ["Wren Halloway", "Casper Vane", "Tamsin Cole", "Joren Pax",
          "Mira Solen", "Dorian Fenn", "Isolde Marr", "Kellan Drisc",
          "Odette Lorr", "Silas Quill", "Nadia Vex", "Percival Odd",
          "Rosalind Pryce", "Edmund Sable", "Vivienne Lark", "Cornelius Thade",
          "Beatrix Wold", "Alistair Fenwick", "Cordelia Vane", "Thaddeus Morn",
          "Elowen Marsh", "Barnaby Slate", "Imogen Starr", "Rupert Candle",
          "Sable Quinn", "Horace Pill", "Mabel Drummond", "Felix Arkwright"]

ORGS = ["the Signature Council", "the Lumen Exchange", "the Meridian Transit Authority",
        "the Halloway Institute", "the Cartographers' Guild", "the Harmonic Society",
        "the Guild of Makers", "the Observatory at Frostgate", "the Tidewater Port Authority",
        "the Solar Conservatory", "the Archive of Weights and Measures",
        "the Fellowship of Printers"]

TEAMS = ["Meridian Comets", "Argent Kestrels", "Solara Lanterns",
         "Pelagia Tides", "Borealia Auroras", "Vesper Foxes"]

PROJECTS = ["The New Skybridge Arc", "The Grand Concourse Extension",
            "The Harbor Light-Rail Loop", "The Civic Athenaeum",
            "The Riverside Promenade", "The Night-Market Halls",
            "The Observatory Dome Restoration", "The Great Bell Tower",
            "The Underground Archive Vaults", "The Festival Green",
            "The Wind-Harbor Piers", "The Lantern District Renewal"]

THINGS = ["a pocket observatory", "a hand-crank printing press",
          "a tide-powered lantern", "a whisper-quiet courier drone",
          "a modular bookshelf engine", "a pocket planetarium",
          "a self-inking survey compass", "a fold-flat market stall",
          "a rain-chime array", "a solar tea kettle",
          "a clockwork message runner", "a harbor fog bell"]

EVENTS = ["Lantern Festival", "Harvest of Inks", "the Long Light Fair",
          "Founders' Week", "the Tide Gala", "the Paper & Press Parade",
          "the Starwatch Nights", "the Makers' Jubilee"]

# ---------------- headline templates per section ----------------
HEADS = {
 "lead": [
    "Council Approves {project} for {city}",
    "{org_cap} Unveils {thing} in {city}",
    "Record Crowds Gather for {event} in {city}",
    "{city} Breaks Ground on {project}",
    "{org_cap} Opens New Chapter With {thing} Debut",
    "{person} Named Steward of {project}",
    "{city} and {city2} Linked by the New {thing_title}",
    "Thousands Turn Out as {event} Opens in {city}",
 ],
 "region": [
    "{city} Market Hall Reopens After Restoration",
    "New Ferry Route Joins {city} to {city2}",
    "{org_cap} Funds {project} Across the Region",
    "{city} Library Extends Hours for Readers",
    "The {thing_title} Finds a Historic Home in {city} Museum",
    "Farmers of {region} Report Bountiful Season",
    "{city} Council Votes to Plant Ten Thousand Trees",
    "Night Trains Return to {city} Station",
 ],
 "science": [
    "{org_cap} Charts a New Comet Over {city}",
    "Halloway Researchers Bottle {thing}",
    "Observatory at Frostgate Spots Distant Light",
    "New Study: {city} Air Sweetest at Dawn",
    "Cartographers Map the Uncharted {place}",
    "{org_cap} Launches Public Starwatch Season",
    "Engineers Tune the Great Bell of {city}",
    "Botanists Catalog Rare Blooms Near {city2}",
 ],
 "culture": [
    "{person} Premieres New Play in {city}",
    "{event} Draws Artists From Across {region}",
    "Museum of {city} Hangs Hundred New Works",
    "{person}'s Latest Novel Tops Local Lists",
    "Street Musicians of {city} Get Their Own Stage",
    "Old Press Hall Becomes Print Museum in {city2}",
    "Poets Laureate Gather for {event}",
    "{city} Choir to Sing the Dawn In",
 ],
 "weather": [
    "Fair Skies Over {city}, Warm Week Ahead",
    "Coastal Breezes Bring Relief to {region}",
    "Morning Mists to Lift Early Across {city2}",
    "Stargazers' Delight: Clear Nights Forecast",
    "Gentle Rains Expected Over {region} Valleys",
    "Crisp Air Settles In Over {city}",
 ],
 "sports": [
    "{team} Edge {team2} in Thrilling Finish",
    "{team} Clinch Playoff Berth Before Home Crowd",
    "{person} Stars as {team} Rout {team2}",
    "{team2} Stun {team} in Late Comeback",
    "Championship Race Tightens as {team} Win Again",
    "{team} Unveil Rookie Sensation {person}",
 ],
 "business": [
    "{org_cap} Posts Record Quarter at the Lumen Exchange",
    "Makers' Guild Opens Hundred New Workshops",
    "Harbor Trade Through {city} Hits New High",
    "{person} Launches Cooperative Bank in {city2}",
    "Print and Paper Stocks Rise on Strong Demand",
 ],
 "opinion": [
    "Editorial: A City Is Its Readers",
    "Editorial: Keep the Night Markets Open Late",
    "Letters: In Praise of the Morning Edition",
    "Editorial: Plant the Trees, Ring the Bells",
    "Opinion: Why Every Town Needs a Print Shop",
 ],
}

# ---------------- body sentence banks per section ----------------
BODIES = {
 "lead": [
    "{city} woke to big news this morning as {org} formally approved {project}, a civic undertaking years in the making.",
    "Councilor {person} called the vote 'a promise kept,' noting that work crews will begin surveying within the fortnight.",
    "Residents interviewed near the old market were broadly in favor, though several asked pointed questions about the timeline.",
    "The plan's backers say {project} will employ hundreds of makers, printers, and engineers over its construction.",
    "Critics on the council asked for quarterly public reports; the measure passed with that amendment attached.",
    "By evening, celebratory lanterns had appeared along the harbor, hung by shopkeepers in anticipation.",
    "A public reading of the full plan is scheduled at the Civic Athenaeum, and printed copies will be sold for a copper.",
    "Historians note this is the largest civic project in {city} since the restoration of the bell tower.",
 ],
 "region": [
    "Life in {city} moved at its usual brisk pace this week, with the markets full and the presses running late.",
    "{person}, who has kept shop on Lantern Row for thirty years, said the neighborhood 'has never felt more alive.'",
    "The regional council confirmed funding for {project}, with the first phase to finish before the {event}.",
    "Travelers passing through {city2} will notice new signage, freshly painted in the guild's deep blue.",
    "Schoolchildren toured the restoration works on Tuesday, each taking home a printed keepsake.",
    "The {org} praised local volunteers, whose weekend work parties have become something of a tradition.",
    "Merchants report strong trade, and the night ferries have added an extra sailing on Fridays.",
    "In a brief ceremony, {person} cut the ribbon and declared the season officially open.",
 ],
 "science": [
    "Researchers at {org} announced the findings on Tuesday, to applause from a packed lecture hall.",
    "{person}, the study's lead, explained the work began as 'a curiosity and became an obsession.'",
    "The team documented every step in the public record, and printed diagrams are available at the institute's front desk.",
    "Independent observers called the results 'careful, patient science of the best kind.'",
    "A second expedition is planned for the autumn, when conditions are expected to be ideal.",
    "The discovery has already found its way into school lessons across {region}.",
    "Funding for the next phase was confirmed by {org2}, ensuring the work continues uninterrupted.",
    "The full paper, set in handsome type, runs to forty pages and is free to any reader who asks.",
 ],
 "culture": [
    "The evening opened to a full house, and by the interval the applause had become rhythmic.",
    "{person} has lived in {city} for a decade, and the work bears the city's fingerprints on every page.",
    "Critics in attendance called it 'the season's essential evening out' and urged readers to book early.",
    "The production will tour to {city2} next month, with two open-air performances planned.",
    "Local printers have already produced a handsome program, which sold out before curtain.",
    "Young artists in the audience were seen sketching throughout, a hopeful sign for the future.",
    "The {org} underwrote the run, continuing its long patronage of the city's stages.",
    "A second run is under discussion; the box office opens to subscribers on Monday.",
 ],
 "weather": [
    "The observatory's forecast desk reports settled conditions across {region} through the weekend.",
    "Morning mists will burn off by mid-morning, giving way to the season's characteristic clear light.",
    "Sailors out of {city} are advised of gentle swells and fair winds for the crossing.",
    "Night skies will favor stargazers, with the observatory opening its dome to the public on Saturday.",
    "Farmers welcomed the outlook, calling it 'exactly what the fields ordered.'",
    "Travelers on the high roads should pack for cool evenings and bright, crisp days.",
 ],
 "sports": [
    "The crowd at the {city} grounds was on its feet for the final minutes of a memorable contest.",
    "{person} was the difference, turning the match with a sequence the papers will recount for weeks.",
    "The {team} bench emptied onto the field at the final whistle as supporters sang long into the evening.",
    "Coaches credited 'discipline and a little luck' in the post-match remarks.",
    "The result tightens the table considerably, with three clubs now separated by a single point.",
    "Tickets for the return fixture go on sale Friday; the club expects another full house.",
    "Veteran watchers called it the finest match seen in {city} in many a season.",
    "The league office confirmed the fixture list for the run-in, setting up a grandstand finish.",
 ],
 "business": [
    "Trading at the Lumen Exchange was brisk, with the print and paper counters leading the advance.",
    "{person}, speaking for {org}, attributed the figures to 'steady hands and honest work.'",
    "Analysts note the fourth consecutive quarter of growth, a run not seen in a decade.",
    "New workshops continue to open along Maker's Row, each flying the guild's blue pennant.",
    "The harbor manifests show cargo up across every category, from ink to timber.",
    "A public dividend was declared, to be paid in the customary printed scrip.",
    "Economists urge cautious optimism but concede the trend lines are encouraging.",
    "The exchange bell rang an extra peal at the close, a tradition reserved for record days.",
 ],
 "opinion": [
    "A city is its readers, and a reader is made one morning at a time, over coffee and these pages.",
    "We have said it before and will say it again: keep the night markets open late, for that is where the city talks to itself.",
    "To the correspondent who praised the morning edition: the praise belongs to the compositors, who rise before the birds.",
    "Plant the trees, ring the bells, and mind the small courtesies; great cities are built of such things.",
    "Every town needs a print shop the way every harbor needs a lighthouse.",
    "The editors welcome letters on any subject under the sun, provided they are civil and brief.",
 ],
}

SECTIONS = ["lead", "region", "science", "culture", "weather", "sports"]
SEC_TITLES = {"lead": "Front Page", "region": "Regional", "science": "Science & Discovery",
              "culture": "Arts & Culture", "weather": "Weather", "sports": "Sport",
              "business": "Business", "opinion": "Opinion"}

HONESTY = ("Signature press: this edition is an original generated newspaper of the "
           "Signature world. All people, places, teams, organizations, and events named "
           "herein are invented. It reports no real-world news and names no real persons.")

def cap_org(s):
    return s[0].upper() + s[1:] if s.startswith("the ") else s

def title_noun(s):
    # "a pocket observatory" -> "Pocket Observatory" (strip leading article, title-case)
    s = re.sub(r"^(a|an|the) ", "", s)
    return " ".join(w.capitalize() for w in s.split())

def fill(tpl, r):
    city = r.choice(CITIES); city2 = r.choice([c for c in CITIES if c != city])
    person = r.choice(PEOPLE); person2 = r.choice([p for p in PEOPLE if p != person])
    org = r.choice(ORGS); org2 = r.choice([o for o in ORGS if o != org])
    team = r.choice(TEAMS); team2 = r.choice([t for t in TEAMS if t != team])
    return tpl.format(
        city=city, city2=city2, person=person, person2=person2,
        org=org, org2=org2, org_cap=cap_org(org),
        team=team, team2=team2,
        project=r.choice(PROJECTS), project_cap=r.choice(PROJECTS).capitalize(),
        thing=r.choice(THINGS), thing_title=title_noun(r.choice(THINGS)),
        event=r.choice(EVENTS), region=r.choice(["Meridia", "Argentia", "Borealia", "Solara", "Pelagia"]),
        place=r.choice(["high vales", "outer isles", "northern reaches", "salt marshes", "ember hills"]),
    )

def make_article(sec, r, byline):
    heads = HEADS[sec]; bodies = BODIES[sec]
    h = fill(r.choice(heads), r)
    npar = 3 if sec in ("weather", "opinion") else r.choice([3, 3, 4])
    paras, used = [], set()
    while len(paras) < npar:
        s = fill(r.choice(bodies), r)
        if s not in used:
            used.add(s); paras.append(s)
    return {"sec": sec, "h": h, "by": byline, "body": paras}

def issue_no(paper, date):
    founded = datetime.date.fromisoformat(paper["founded"])
    return max(1, (date - founded).days + 1)


def make_eco_edition(paper_idx, date):
    """Real-ecosystem edition: 6 articles from that day's real network events.

    Paper 0 (Daily Globe, flagship) leads with the day's biggest story and
    covers one top story per beat. Beat desks lead with their beat's top
    story, then fill from the rest of the day's real events.
    """
    events = eco_events.events_for_date(date)
    beat = eco_events.PAPER_BEAT[paper_idx]
    used = set()
    site_n = {}
    arts = []

    def take(ev):
        if ev is None or ev["subject"] in used:
            return None
        if site_n.get(ev["site_key"], 0) >= 2:
            return None
        used.add(ev["subject"])
        site_n[ev["site_key"]] = site_n.get(ev["site_key"], 0) + 1
        return ev

    def top_of(beats, exclude=()):
        for ev in events:
            if ev["beat"] in beats and ev["subject"] not in used and ev not in exclude:
                return ev
        return None

    others = []  # events not used in articles, for the roundup
    if beat == "all":
        ordered_beats = ["catalogs", "ai", "builders", "culture", "markets"]
        lead = take(events[0]) if events else None
        picks = [lead] if lead else []
        for b in ordered_beats:
            t = take(top_of([b]))
            if t:
                picks.append(t)
        for ev in events:
            if len(picks) >= 5:
                break
            t = take(ev)
            if t:
                picks.append(t)
    else:
        lead = take(top_of([beat])) or (take(events[0]) if events else None)
        picks = [lead] if lead else []
        for ev in events:
            if len(picks) >= 5:
                break
            if ev["beat"] == beat:
                t = take(ev)
                if t:
                    picks.append(t)
        for ev in events:
            if len(picks) >= 5:
                break
            t = take(ev)
            if t:
                picks.append(t)

    picks = picks[:5]  # leave the 6th slot for the roundup
    for i, ev in enumerate(picks):
        sec = "lead" if i == 0 else (ev["beat"] if ev["beat"] in eco_events.BEAT_LABEL else "network")
        arts.append(eco_stories.article_for(ev, sec))
    # final slots: roundup(s) of the day's remaining real events
    rest = [ev for ev in events if ev["subject"] not in used]
    while len(arts) < 6 and rest:
        arts.append(eco_stories.roundup_article(rest, date))
        rest = rest[6:]
    while len(arts) < 6:  # unreachable on real days; keep the 6-article shape
        arts.append(eco_stories.roundup_article(events[len(arts):], date))
    arts = arts[:6]

    paper = PAPERS[paper_idx]
    iss = issue_no(paper, date)
    return {
        "paper": paper_idx,
        "date": date.isoformat(),
        "issue": iss,
        "volume": (date.year - datetime.date.fromisoformat(paper["founded"]).year) + 1,
        "articles": arts,
        "honesty": eco_stories.ECO_HONESTY,
        "coverage": "ecosystem",
    }


def build_edition(pi, d):
    """(edition_dict, fictionality_status) — eco for real dates, fiction before."""
    if d >= ECO_START:
        return make_eco_edition(pi, d), record_std.ECO_FICTIONALITY
    return make_edition(pi, d), record_std.FICTIONALITY


def restamp_rebuilt(e, article_ids):
    """Re-stamp a rebuilt eco edition, preserving its edition + article IDs."""
    e["fictionality_status"] = record_std.ECO_FICTIONALITY
    e["honesty"] = eco_stories.ECO_HONESTY
    e["coverage"] = "ecosystem"
    e["status"] = "PUBLISHED"
    e.setdefault("creation_mode", "GENERATED")
    e.setdefault("version", "1.0")
    e["updated"] = e["date"]
    arts = []
    for a, aid_ in zip(e["articles"], article_ids):
        record_std.stamp_article(a, aid_, e["id"], record_std.ECO_FICTIONALITY)
        arts.append(a)
    e["articles"] = arts
    e["article_ids"] = list(article_ids)
    e["article_count"] = len(arts)
    body = {k: v for k, v in e.items() if k != "content_hash"}
    e["content_hash"] = record_std.sha256_hex(record_std.canon(body))
    return e

def make_edition(paper_idx, date):
    paper = PAPERS[paper_idx]
    seed = SALT + paper_idx * 100003 + (date - EPOCH_START).days * 7919
    r = random.Random(seed)
    secs = list(SECTIONS)
    # some days swap sports/weather for business/opinion for variety
    if r.random() < 0.25:
        secs[4] = "business"
    if r.random() < 0.20:
        secs[5] = "opinion"
    reporters = r.sample(PEOPLE, 6)
    articles = [make_article(s, r, "By %s, %s staff" % (reporters[i], paper["name"].split()[-1]))
                for i, s in enumerate(secs)]
    iss = issue_no(paper, date)
    return {
        "paper": paper_idx,
        "date": date.isoformat(),
        "issue": iss,
        "volume": (date.year - datetime.date.fromisoformat(paper["founded"]).year) + 1,
        "articles": articles,
        "honesty": HONESTY,
    }

# ---------------- storage, index, sitemap, api ----------------
def load_state():
    if os.path.exists(STATE_F):
        with open(STATE_F) as f:
            return json.load(f)
    return {"next_index": 1, "last_date": None, "total_articles": 0}

def save_state(s):
    with open(STATE_F, "w") as f:
        json.dump(s, f)

def week_idx(date):
    return (date - EPOCH_START).days // 7

def chunk_path(wi):
    return os.path.join(VOL, "editions-w%05d.jsonl.gz" % wi)

def read_chunk(wi):
    p = chunk_path(wi)
    if not os.path.exists(p):
        return []
    out = []
    with gzip.open(p, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def write_chunk(wi, editions):
    with gzip.open(chunk_path(wi), "wt", encoding="utf-8") as f:
        for e in editions:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

def eid(n):
    return "JAH-ED-%06d" % n

def add_editions(ed_list, state):
    """Assign IDs, append into weekly chunks. ed_list: [(paper_idx, date)] oldest-first.
    Dates before ECO_START get fiction editions; ECO_START onward get real
    ecosystem editions. Existing (paper, date) pairs are never duplicated."""
    by_week = {}
    for pi, d in ed_list:
        wi = week_idx(d)
        by_week.setdefault(wi, []).append((pi, d))
    for wi in sorted(by_week):
        existing = read_chunk(wi)
        have = {(e["paper"], e["date"]) for e in existing}
        for pi, d in by_week[wi]:
            if (pi, d.isoformat()) in have:
                continue
            e, fic = build_edition(pi, d)
            e["id"] = eid(state["next_index"])
            state["next_index"] += 1
            # stamp the permanent record standard: paper/article IDs, hashes, fictionality
            state["next_article_index"] = record_std.stamp_edition(
                e, state.get("next_article_index", 1), fic)
            state["total_articles"] = state.get("total_articles", 0) + len(e["articles"])
            existing.append(e)
        existing.sort(key=lambda e: (e["date"], e["paper"]))
        write_chunk(wi, existing)
    if ed_list:
        state["last_date"] = max(d for _, d in ed_list).isoformat()
    save_state(state)


def cmd_eco_rebuild():
    """Replace every edition from ECO_START..today with real-ecosystem
    editions, preserving edition + article IDs (positional, 6 articles each).
    Missing (paper, date) pairs are appended with fresh IDs. Then rebuild."""
    state = load_state()
    today = local_today()
    # map (paper, date) -> (week_idx, edition)
    loc = {}
    weeks = {}
    for fn in sorted(os.listdir(VOL)):
        if not fn.startswith("editions-w") or not fn.endswith(".jsonl.gz"):
            continue
        wi = int(fn[len("editions-w"):len("editions-w") + 5])
        eds = read_chunk(wi)
        weeks[wi] = eds
        for e in eds:
            loc[(e["paper"], e["date"])] = (wi, e)
    missing = []
    replaced = 0
    dirty = set()
    d = ECO_START
    while d <= today:
        for pi in range(len(PAPERS)):
            key = (pi, d.isoformat())
            e, fic = build_edition(pi, d)
            assert fic == record_std.ECO_FICTIONALITY
            if key in loc:
                wi, old = loc[key]
                assert len(old["articles"]) == 6, "unexpected article count in %s" % old["id"]
                aids = [a["id"] for a in old["articles"]]
                e["id"] = old["id"]
                e["paper_id"] = old.get("paper_id", record_std.PAPERS[pi]["paper_id"])
                e["created"] = old.get("created", e["date"])
                restamp_rebuilt(e, aids)
                # swap into the week's list, preserving order
                wl = weeks[wi]
                for i, x in enumerate(wl):
                    if x["id"] == old["id"]:
                        wl[i] = e
                        break
                replaced += 1
                dirty.add(wi)
            else:
                missing.append((pi, d))
        d += datetime.timedelta(days=1)
    for wi in sorted(dirty):
        eds = weeks[wi]
        eds.sort(key=lambda e: (e["date"], e["paper"]))
        write_chunk(wi, eds)
    print("eco-rebuild: replaced %d editions, %d missing pairs to append" % (replaced, len(missing)))
    if missing:
        add_editions(sorted(missing, key=lambda t: (t[1], t[0])), state)
    build_all()

def all_editions_meta():
    """Lightweight scan: (id, date, paper, n_articles, week) for every edition."""
    out = []
    for fn in sorted(os.listdir(VOL)):
        if not fn.startswith("editions-w") or not fn.endswith(".jsonl.gz"):
            continue
        wi = int(fn[len("editions-w"):len("editions-w") + 5])
        with gzip.open(os.path.join(VOL, fn), "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                out.append((e["id"], e["date"], e["paper"], len(e["articles"]), wi, e["issue"]))
    out.sort(key=lambda t: t[0])
    return out

def stamp_static():
    """Bake the latest editions' headlines into index.html for crawlers/no-JS."""
    meta = all_editions_meta()
    if not meta:
        return
    latest = max(m[1] for m in meta)
    todays = [m for m in meta if m[1] == latest][:6]
    parts = []
    for eid_, date, pi, n, wi, iss in todays:
        e = next(x for x in read_chunk(wi) if x["id"] == eid_)
        heads = "".join("<li>%s</li>" % h for h in
                        [a["h"].replace("&", "&amp;").replace("<", "&lt;") for a in e["articles"][:3]])
        parts.append(
            '<p itemscope itemtype="https://schema.org/NewsArticle"><b><a itemprop="url" href="?edition=%s"><span itemprop="headline">%s</span></a></b> — <time itemprop="datePublished" datetime="%s">%s</time>, Vol. %d Issue %d<ul>%s</ul></p>' %
            (eid_, PAPERS[pi]["name"], date, date, e["volume"], e["issue"], heads))
    html = "\n".join(parts)
    p = os.path.join(ROOT, "index.html")
    with open(p, encoding="utf-8") as f:
        src = f.read()
    start = src.index("<!-- LATEST-EDITIONS -->") + len("<!-- LATEST-EDITIONS -->")
    end = src.index("<!-- /LATEST-EDITIONS -->")
    src = src[:start] + "\n" + html + "\n" + src[end:]
    with open(p, "w", encoding="utf-8") as f:
        f.write(src)
    print("stamped latest editions into index.html")


def stamp_stats():
    """Stamp the last-known real counts into the hero stat chips (initial HTML
    content — the drip re-stamps every run; JS overwrites live on boot).
    Chips must NEVER boot as bare "…" (usability wave rule)."""
    meta = all_editions_meta()
    n_ed = len(meta)
    n_art = 0
    for eid_, date, pi, n, wi, iss in meta:
        n_art += n
    dates = sorted(set(m[1] for m in meta))
    first = dates[0] if dates else ""
    fill = min(100.0, n_ed / 10000.0)
    march = "%s / 1,000,000 EDITIONS \u00b7 %s ARTICLES" % (
        format(n_ed, ","), format(n_art, ","))
    chips = (
        '<div class="stat"><b>%s</b><span>editions on file</span></div>'
        '<div class="stat"><b>%s</b><span>articles printed</span></div>'
        '<div class="stat"><b>6</b><span>regional papers</span></div>'
        '<div class="stat"><b>%s</b><span>archive begins</span></div>'
        % (format(n_ed, ","), format(n_art, ","), first))
    p = os.path.join(ROOT, "index.html")
    with open(p, encoding="utf-8") as f:
        src = f.read()
    start = src.index("<!-- STAT-CHIPS -->") + len("<!-- STAT-CHIPS -->")
    end = src.index("<!-- /STAT-CHIPS -->")
    src = src[:start] + "\n" + chips + "\n" + src[end:]
    start2 = src.index("<!-- MARCH-TXT -->") + len("<!-- MARCH-TXT -->")
    end2 = src.index("<!-- /MARCH-TXT -->")
    src = src[:start2] + march + src[end2:]
    src = re.sub(r'<div class="fill" id="marchfill" style="width:[^"]*">',
                 '<div class="fill" id="marchfill" style="width:%.2f%%">' % fill,
                 src)
    with open(p, "w", encoding="utf-8") as f:
        f.write(src)
    print("stamped stat chips into index.html (%d editions, %d articles)" % (n_ed, n_art))


def stamp_browse():
    """Stamp the real counts + latest editions into browse.html (runs inside
    build_all, AFTER the new edition flushes — never one run behind).
    The drip re-stamps every run; browse.html JS overwrites live on boot."""
    meta = all_editions_meta()
    n_ed = len(meta)
    n_art = sum(n for _, _, _, n, _, _ in meta)
    n_eco = sum(1 for _, d, _, _, _, _ in meta if d >= ECO_START.isoformat())
    n_fic = n_ed - n_eco
    latest = max(m[1] for m in meta)
    todays = [m for m in meta if m[1] == latest][:6]
    parts = []
    for eid_, date, pi, n, wi, iss in todays:
        e = next(x for x in read_chunk(wi) if x["id"] == eid_)
        heads = "".join("<li>%s</li>" % h for h in
                        [a["h"].replace("&", "&amp;").replace("<", "&lt;") for a in e["articles"][:3]])
        parts.append(
            '<p itemscope itemtype="https://schema.org/NewsArticle"><b><a itemprop="url" href="?edition=%s"><span itemprop="headline">%s</span></a></b> — <time itemprop="datePublished" datetime="%s">%s</time>, Vol. %d Issue %d<ul>%s</ul></p>' %
            (eid_, PAPERS[pi]["name"], date, date, e["volume"], e["issue"], heads))
    chips = (
        '<div class="stat"><b>%s</b><span>editions on file</span></div>'
        '<div class="stat"><b>%s</b><span>articles printed</span></div>'
        '<div class="stat"><b>%s</b><span>real-news editions</span></div>'
        '<div class="stat"><b>%s</b><span>fiction-archive editions</span></div>'
        % (format(n_ed, ","), format(n_art, ","), format(n_eco, ","), format(n_fic, ",")))
    p = os.path.join(ROOT, "browse.html")
    with open(p, encoding="utf-8") as f:
        src = f.read()
    start = src.index("<!-- BROWSE-STATS -->") + len("<!-- BROWSE-STATS -->")
    end = src.index("<!-- /BROWSE-STATS -->")
    src = src[:start] + "\n" + chips + "\n" + src[end:]
    start2 = src.index("<!-- BROWSE-LATEST -->") + len("<!-- BROWSE-LATEST -->")
    end2 = src.index("<!-- /BROWSE-LATEST -->")
    src = src[:start2] + "\n" + "\n".join(parts) + "\n" + src[end2:]
    with open(p, "w", encoding="utf-8") as f:
        f.write(src)
    print("stamped browse.html (%d editions, %d articles)" % (n_ed, n_art))


# ---------------- Site-14 diagnostic: feed, sub-sitemaps, static archive ------
def build_catalog_feed(meta):
    """data/index/newspapers-catalog.json: standardized machine-readable edition feed."""
    return [{"id": eid_, "date": date, "paper": PAPERS[pi]["name"],
             "paper_idx": pi, "issue": iss, "url": SITE + "?edition=" + eid_}
            for eid_, date, pi, n, wi, iss in meta]

def write_sitemap(path, urls):
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append("<url><loc>%s</loc></url>" % u)
    sm.append("</urlset>")
    with open(path, "w") as f:
        f.write("\n".join(sm))

def build_sub_sitemaps(meta, week_pages):
    """Per-paper (regional) + per-year (chronological) sitemap sub-indexes plus a
    sitemap-index.xml tying them together. sitemap.xml stays flat for compat.
    Article URLs (one per JAH-ARTICLE) + entity URLs get their own shards."""
    refs = []
    for pi in range(len(PAPERS)):
        urls = [SITE + "?edition=" + eid_ for (eid_, d, ppi, n, wi, iss) in meta if ppi == pi]
        fn = "sitemap-paper-%d.xml" % pi
        write_sitemap(os.path.join(ROOT, fn), urls)
        refs.append((fn, len(urls)))
    for y in sorted({d[:4] for _, d, _, _, _, _ in meta}):
        urls = [SITE + "?edition=" + eid_ for (eid_, d, ppi, n, wi, iss) in meta if d.startswith(y)]
        fn = "sitemap-year-%s.xml" % y
        write_sitemap(os.path.join(ROOT, fn), urls)
        refs.append((fn, len(urls)))
    # article shards, one per year (JAH-ARTICLE deep links)
    art_rows = json.load(gzip.open(os.path.join(IDX, "articles.idx.json.gz"), "rt"))
    for y in sorted({r[3][:4] for r in art_rows}):
        urls = [SITE + "?article=" + r[0] for r in art_rows if r[3].startswith(y)]
        fn = "sitemap-articles-%s.xml" % y
        write_sitemap(os.path.join(ROOT, fn), urls)
        refs.append((fn, len(urls)))
    # entity shard (fictional-world entities, mined from content)
    try:
        ent_rows = json.load(gzip.open(os.path.join(IDX, "entities.idx.json.gz"), "rt"))
        urls = [r[6] for r in ent_rows]
        write_sitemap(os.path.join(ROOT, "sitemap-entities.xml"), urls)
        refs.append(("sitemap-entities.xml", len(urls)))
    except OSError:
        pass
    for d0, fn, items in week_pages:
        refs.append(("archive/" + fn, len(items)))
    idx = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for fn, n in refs:
        idx.append("<sitemap><loc>%s%s</loc></sitemap>" % (SITE, fn))
    idx.append("</sitemapindex>")
    with open(os.path.join(ROOT, "sitemap-index.xml"), "w") as f:
        f.write("\n".join(idx))
    return refs

WEEK_CSS = ("body{margin:0;background:#f6f1e2;color:#1c1a15;font-family:Georgia,serif}"
 ".wrap{max-width:860px;margin:0 auto;padding:0 14px}"
 "header{border-bottom:4px double #2b2820;padding:18px 0;text-align:center}"
 "h1{font-size:1.6em;text-transform:uppercase;margin:.2em 0}"
 ".hon{background:#fff8e1;border-top:3px double #2b2820;border-bottom:3px double #2b2820;"
 "padding:8px 12px;font-size:.85em;text-align:center;font-family:Arial,sans-serif}"
 "article.ed{background:#fffdf4;border:1px solid #c9bfa4;margin:22px 0;padding:20px 24px}"
 ".emast{font-size:1.4em;font-weight:900;text-transform:uppercase;border-bottom:4px double #2b2820;"
 "padding-bottom:8px;text-align:center}.edate{text-align:center;color:#6b6353;font-size:.85em;"
 "font-family:Arial,sans-serif;margin:6px 0 12px}h3{font-size:1.15em;margin:1em 0 .2em}"
 ".byline{font-size:.82em;color:#6b6353;font-style:italic}p{line-height:1.65}"
 ".back{font-family:Arial,sans-serif;font-size:.85em;margin:18px 0}"
 "ul.weeks{line-height:2;font-family:Arial,sans-serif}"
 ".ficlabel{background:#1c1a15;color:#f6f1e2;font-family:Arial,sans-serif;font-weight:700;"
 "font-size:.78em;letter-spacing:.14em;text-align:center;padding:8px 10px;margin:0 0 4px;"
 "text-transform:uppercase}"
 ".pp0{color:#9c2b2b}.pp1{color:#1f3a6e}.pp2{color:#2e6b34}"
 ".pp3{color:#5b2a86}.pp4{color:#b06a00}.pp5{color:#0f6b6e}"
 ".artid{font-family:Arial,sans-serif;font-size:.72em;color:#6b6353;letter-spacing:.06em}")

def edition_jsonld(e, paper_name):
    lead = e["articles"][0]["h"] if e["articles"] else paper_name
    secs = sorted({a["sec"] for a in e["articles"]})
    return {"@context": "https://schema.org", "@type": "NewsArticle",
            "headline": lead, "datePublished": e["date"],
            "author": {"@type": "Person", "name": "Justin Addam Higgins"},
            "isPartOf": {"@type": "Periodical", "name": paper_name},
            "identifier": e["id"], "url": SITE + "?edition=" + e["id"],
            "articleSection": secs}

def esc_h(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _week_is_eco(d0):
    return d0 >= ECO_START.isoformat()


def write_week_digest(adir, d0, fn, items, chunk_of):
    """Static weekly digest: headline summaries + full transcript blocks for every
    edition in the week. Crawler / no-JS friendly."""
    eco = _week_is_eco(d0)
    fic_tag = "Signature ecosystem news" if eco else "Fictional Signature world"
    parts = []
    for eid_, date, pi, n, wi, iss in sorted(items, key=lambda t: (t[1], t[2])):
        e = chunk_of(wi, eid_)
        p = PAPERS[pi]
        arts = []
        for i, a in enumerate(e["articles"]):
            arts.append('<div class="artid">%s-A%d &middot; %s</div>'
                        '<h3 itemprop="headline">%s</h3><div class="byline">%s</div>%s' % (
                eid_, i + 1, fic_tag, esc_h(a["h"]), esc_h(a["by"]),
                "".join("<p>%s</p>" % esc_h(par) for par in a["body"])))
        ld = json.dumps(edition_jsonld(e, p["name"]), ensure_ascii=False)
        fic_label = ("Signature ecosystem news &mdash; real events from the 27-site network"
                     if eco else "Fictional Signature world &mdash; not real-world news")
        parts.append(
            '<article class="ed" itemscope itemtype="https://schema.org/NewsArticle">'
            '<div class="emast pp%d">%s</div>'
            '<div class="ficlabel">%s</div>'
            '<div class="edate"><time itemprop="datePublished" datetime="%s">%s</time>'
            ' &middot; Vol. %d, Issue %d &middot; <span itemprop="identifier">%s</span></div>'
            '<div class="hon">Signature press: %s</div>'
            '<script type="application/ld+json">%s</script>%s'
            '<p><a href="%s?edition=%s">Read the interactive edition &rarr;</a></p>'
            '</article>' % (pi, esc_h(p["name"]), fic_label, date, date, e["volume"], e["issue"],
                             eid_, esc_h(e["honesty"]), ld, "".join(arts), SITE, eid_))
    hon_div = ("""<div class="hon"><b>Signature press.</b> Every edition below reports real """
               """events from the 27-website Signature network &mdash; drip milestones, fixes """
               """shipped, launches and records, verified from the sites' own data.</div>"""
               if eco else
               """<div class="hon"><b>Signature press.</b> Every edition below is a retired """
               """Signature-world fiction edition &mdash; all people, places, teams, """
               """organizations, and events are invented. It reports no real-world news and names """
               """no real persons.</div>""")
    meta_desc = ("Static digest of Signature-ecosystem newspaper editions for the week of %s. "
                 "Real events from the 27-website network."
                 if eco else
                 "Static digest of retired Signature-world fiction newspaper editions for the "
                 "week of %s. All people, places, and events are invented.")
    html = ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Signature press digest &mdash; week of %s</title>"
            "<meta name=\"description\" content=\"%s\">"
            "<link rel=\"canonical\" href=\"%sarchive/%s\">"
            "<style>%s</style></head><body><div class=\"wrap\">"
            "<header><h1>The Signature Global Newspaper Archive</h1>"
            "<p>Static press digest &mdash; week of %s</p></header>"
            "%s"
            "%s<p class=\"back\"><a href=\"%s\">&larr; Back to the Newspaper Archive</a>"
            " &middot; <a href=\"%sarchive/\">All digest weeks</a></p>"
            "</div></body></html>" % (d0, meta_desc % d0, SITE, fn, WEEK_CSS, d0, hon_div,
                                      "".join(parts), SITE, SITE))
    with open(os.path.join(adir, fn), "w", encoding="utf-8") as f:
        f.write(html)

def build_static_archive(meta):
    """Weekly digest pages + archive index. Returns [(week_start, filename, items)]."""
    adir = os.path.join(ROOT, "archive")
    os.makedirs(adir, exist_ok=True)
    by_week = {}
    for t in meta:
        by_week.setdefault(t[4], []).append(t)
    cache = {}
    def chunk_of(wi, eid_):
        if wi not in cache:
            cache[wi] = {x["id"]: x for x in read_chunk(wi)}
        return cache[wi][eid_]
    weeks = []
    for wi in sorted(by_week):
        d0 = (EPOCH_START + datetime.timedelta(days=wi * 7)).isoformat()
        fn = "week-%s.html" % d0
        weeks.append((d0, fn, by_week[wi]))
        write_week_digest(adir, d0, fn, by_week[wi], chunk_of)
    lis = "".join('<li><a href="%s">Week of %s</a> &mdash; %d editions</li>' % (
        fn, d0, len(items)) for d0, fn, items in weeks)
    idx_html = ("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Static press digests &mdash; The Signature Global Newspaper Archive</title>"
        "<style>%s</style></head><body><div class=\"wrap\">"
        "<header><h1>The Signature Global Newspaper Archive</h1>"
        "<p>Static press digests &mdash; every edition, plain HTML</p></header>"
        "<div class=\"hon\"><b>Signature press.</b> Editions from 2026-09-28 onward report real "
        "events from the 27-website Signature network. Earlier editions are retired "
        "Signature-world fiction — invented people, places and events — and are labeled "
        "as such on their pages. No real-world news.</div>"
        "<ul class=\"weeks\">%s</ul>"
        "<p class=\"back\"><a href=\"%s\">&larr; Back to the Newspaper Archive</a></p>"
        "</div></body></html>" % (WEEK_CSS, lis, SITE))
    with open(os.path.join(adir, "index.html"), "w", encoding="utf-8") as f:
        f.write(idx_html)
    want = {fn for _, fn, _ in weeks} | {"index.html"}
    for fn in os.listdir(adir):
        if fn.startswith("week-") and fn.endswith(".html") and fn not in want:
            os.remove(os.path.join(adir, fn))
    return weeks

def build_all():
    meta = all_editions_meta()
    # --- compact search indexes -------------------------------------------
    # editions: [id, date, paper, n_art, week, headlines+ledes, coverage]
    # articles: [article_id, edition_id, paper, date, section, week]
    cache = {}
    def _ed(wi, eid_):
        if wi not in cache:
            cache[wi] = {x["id"]: x for x in read_chunk(wi)}
        return cache[wi][eid_]
    rows, arows = [], []
    for eid_, date, pi, n, wi, iss in meta:
        e = _ed(wi, eid_)
        txt = " ‖ ".join(a["h"] + " — " + a["body"][0] for a in e["articles"])
        cov = "ecosystem" if date >= ECO_START.isoformat() else "fiction-archive"
        rows.append([eid_, date, pi, n, wi, txt, cov])
        for a in e["articles"]:
            arows.append([a["id"], eid_, pi, date, a["sec"], wi])
    with gzip.open(os.path.join(IDX, "editions.idx.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    with gzip.open(os.path.join(IDX, "articles.idx.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(arows, f, ensure_ascii=False)
    # uncompressed fallbacks for readers that cannot handle application/gzip
    with open(os.path.join(IDX, "editions.idx.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    with open(os.path.join(IDX, "articles.idx.json"), "w", encoding="utf-8") as f:
        json.dump(arows, f, ensure_ascii=False)
    # --- compact article-BODY search index (lazy-loaded by the frontend only
    #     when the user searches article text; keeps boot untouched) ---------
    import build_body_search_index
    build_body_search_index.build()
    # --- papers + regions (recomputed from the data) -----------------------
    papers, regions = [], []
    for i, p in enumerate(record_std.PAPERS):
        mine = [t for t in meta if t[2] == i]
        papers.append({
            "paper_id": p["paper_id"], "name": p["name"],
            "region_id": p["region_id"], "region": p["region"],
            "tagline": p["tagline"], "description": p["tagline"],
            "founded": p["founded"], "status": "ACTIVE",
            "edition_count": len(mine),
            "first_edition": mine[0][0] if mine else None,
            "latest_edition": mine[-1][0] if mine else None,
            "editorial_model": "generated-daily",
            "creation_mode": "GENERATED", "version": "1.0",
            "fictionality_status": record_std.FICTIONALITY,
            "canonical_url": SITE + "?paper=" + p["paper_id"],
            "created": p["founded"], "updated": local_today().isoformat(),
        })
        regions.append({
            "region_id": p["region_id"], "name": p["region"],
            "papers": [p["paper_id"]],
            "fictionality_status": record_std.FICTIONALITY,
            "note": ("News desk beat, not a place: this paper covers one beat of "
                     "the Signature website network (catalogs, AI, builders, "
                     "culture, markets) plus the flagship all-network edition."),
        })
    with open(os.path.join(IDX, "papers.json"), "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=1, ensure_ascii=False)
    with open(os.path.join(IDX, "regions.json"), "w", encoding="utf-8") as f:
        json.dump(regions, f, indent=1, ensure_ascii=False)
    # --- world entities (mined from actual article content; never invented) -
    import build_world_index
    build_world_index.main()
    # --- hash manifest over every index file --------------------------------
    hashes = {}
    for fn in sorted(os.listdir(IDX)):
        fp = os.path.join(IDX, fn)
        if os.path.isfile(fp):
            h = hashlib.sha256()
            with open(fp, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b)
            hashes[fn] = h.hexdigest()
    with open(os.path.join(IDX, "hash-manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": local_today().isoformat(), "algorithm": "SHA-256",
                   "files": hashes}, f, indent=1)
    # --- sitemap.xml (flat: home + catalog browse page + every edition) ---
    urls = [SITE, SITE + "browse.html"] + [SITE + "?edition=" + eid_ for eid_, _, _, _, _, _ in meta]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.smaps.org/schemas/sitemap/0.9">'.replace("smaps", "sitemaps")]
    for u in urls:
        sm.append("<url><loc>%s</loc></url>" % u)
    sm.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w") as f:
        f.write("\n".join(sm))
    # --- api.json (root + data/index) ---
    dates = sorted({d for _, d, _, _, _, _ in meta})
    n_ed, n_art = len(meta), sum(n for _, _, _, n, _, _ in meta)
    api = {
        "site": "The Signature Global Newspaper Archive",
        "site_url": SITE,
        "title_provisional": True,
        "description": ("Real Signature-ecosystem news: daily editions from six papers "
                        "covering the 27-website Signature network — drip milestones, fixes shipped, "
                        "launches and records, verified from the sites' own data. "
                        "Editions before 2026-09-28 are retired Signature-world fiction, clearly labeled."),
        "updated": local_today().isoformat(),
        "counts": {"editions": n_ed, "articles": n_art,
                   "papers": len(PAPERS), "regions": len(PAPERS)},
        "schema_version": record_std.SCHEMA_VERSION,
        "catalog_version": local_today().isoformat(),
        "archive_version": local_today().isoformat(),
        "papers": [{"paper_id": p["paper_id"], "name": p["name"],
                    "region_id": p["region_id"], "region": p["region"],
                    "tagline": p["tagline"], "founded": p["founded"]} for p in record_std.PAPERS],
        "date_range": [dates[0], dates[-1]] if dates else [None, None],
        "deep_links": {
            "edition": SITE + "?edition=JAH-ED-000001",
            "article": SITE + "?article=JAH-ARTICLE-000001",
            "paper": SITE + "?paper=JAH-PAPER-000001",
            "verify": SITE + "?verify=JAH-ED-000001",
            "browse": SITE + "browse.html",
        },
        "index": {"editions_gz": "data/index/editions.idx.json.gz",
                  "editions": "data/index/editions.idx.json",
                  "articles_gz": "data/index/articles.idx.json.gz",
                  "articles": "data/index/articles.idx.json",
                  "articles_search_gz": "data/index/articles.search.json.gz",
                  "articles_search": "data/index/articles.search.json",
                  "entities_gz": "data/index/entities.idx.json.gz",
                  "entities": "data/index/entities.idx.json",
                  "hash_manifest": "data/index/hash-manifest.json"},
        "feed": "data/index/newspapers-catalog.json",
        "sitemap_index": "sitemap-index.xml",
        "static_archive": "archive/index.html",
        "honesty": ("Two-era archive. New editions (2026-09-28 onward) report real events from "
                    "the 27-website Signature network, verified from the sites' own data. Earlier "
                    "editions are retired Signature-world fiction, clearly labeled. "
                    "No real-world news, no real persons named."),
        "fictionality_status": record_std.FICTIONALITY,
    }
    with open(os.path.join(ROOT, "api.json"), "w") as f:
        json.dump(api, f, indent=1)
    with open(os.path.join(IDX, "api.json"), "w") as f:
        json.dump(api, f, indent=1)
    # --- master manifest ----------------------------------------------------
    ents = json.load(gzip.open(os.path.join(IDX, "entities.idx.json.gz"), "rt"))
    manifest = {
        "site_id": "SIGNATURE-GLOBAL-NEWSPAPER-ARCHIVE",
        "site_name": "The Signature Global Newspaper Archive",
        "site_version": "1.0",
        "archive_version": local_today().isoformat(),
        "total_editions": n_ed, "total_articles": n_art,
        "total_papers": 6, "total_regions": 6, "total_entities": len(ents),
        "earliest_date": dates[0] if dates else None,
        "latest_date": dates[-1] if dates else None,
        "goal": "1,000,000 editions + articles",
        "schema_version": record_std.SCHEMA_VERSION,
        "index_version": "1.0",
        "index_hash": hashes.get("editions.idx.json.gz"),
        "generator_version": "code/gen_editions.py (SALT 20261002)",
        "fictionality_status": record_std.FICTIONALITY,
        "fictionality_note": ("Two-era archive. Editions dated 2026-09-28 onward carry "
            "ECOSYSTEM_REPORTED: real news from the 27-website Signature network, every "
            "story grounded in the sites' own data. Editions before 2026-09-28 carry "
            "FICTIONAL_GENERATED: retired Signature-world fiction — invented people, "
            "places and events — kept in the archive and clearly labeled, never "
            "presented as fact. No real-world news, no real persons named."),
        "license": "Original Signature-generated content. Read, copy and download freely from this archive.",
        "created": "2025-10-03",
        "updated": local_today().isoformat(),
        "canonical_url": SITE,
        "records": {"edition_id": "JAH-ED-######", "article_id": "JAH-ARTICLE-######",
                    "paper_id": "JAH-PAPER-######", "region_id": "JAH-REGION-######",
                    "entity_id": "JAH-ENTITY-######"},
        "indexes": {"editions_gz": "data/index/editions.idx.json.gz",
                    "editions": "data/index/editions.idx.json",
                    "articles_gz": "data/index/articles.idx.json.gz",
                    "articles": "data/index/articles.idx.json",
                    "entities_gz": "data/index/entities.idx.json.gz",
                    "entities": "data/index/entities.idx.json",
                    "papers": "data/index/papers.json",
                    "regions": "data/index/regions.json",
                    "hash_manifest": "data/index/hash-manifest.json"},
        "schemas": "data/schemas/",
        "papers": [{"paper_id": p["paper_id"], "name": p["name"],
                    "region_id": p["region_id"], "region": p["region"],
                    "edition_count": p["edition_count"],
                    "first_edition": p["first_edition"],
                    "latest_edition": p["latest_edition"]} for p in papers],
    }
    with open(os.path.join(ROOT, "newspaper-manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    # --- robots.txt ---
    with open(os.path.join(ROOT, "robots.txt"), "w") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\nSitemap: %ssitemap-index.xml\n" % (SITE, SITE))
    # --- newspapers-catalog.json feed (AI-USER fix 2) ---
    with open(os.path.join(IDX, "newspapers-catalog.json"), "w", encoding="utf-8") as f:
        json.dump(build_catalog_feed(meta), f, ensure_ascii=False)
    # --- static weekly digest archive: headlines + transcripts (AI-USER fix 3) ---
    week_pages = build_static_archive(meta)
    # --- sitemap sub-indexes: per-paper + per-year + digest weeks (AI-USER fix 2) ---
    build_sub_sitemaps(meta, week_pages)
    # --- static latest-editions stamp (crawler/no-JS friendly) ---
    stamp_static()
    # --- static stat-chip stamp (no bare "…" chips on first paint) ---
    stamp_stats()
    # --- browse.html catalog stamp (after the flush — never one run behind) ---
    stamp_browse()
    # --- A-Z headline archive index (browse.html "A-Z by headline") -----------
    # never one run behind: rebuilds data/index/az/<L>.json + manifest.json
    try:
        import build_az_index
        build_az_index.main()
    except Exception as e:
        print("A-Z archive index skipped: %s" % e)
    # --- data size guard ---
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fns in os.walk(DATA) for f in fns)
    print("DATA bytes: %d (guard 800MB: %s)" % (total, "TRIPPED" if total > 800 * 1024 * 1024 else "ok"))
    print("editions: %d articles: %d" % (n_ed, n_art))
    # --- QA gates: fail the build LOUDLY on any integrity problem -----------
    import subprocess
    qa = os.path.join(HERE, "qa", "run_all.sh")
    r = subprocess.run(["bash", qa], cwd=ROOT)
    if r.returncode != 0:
        print("*** BUILD GATES FAILED — not publishing ***")
        sys.exit(1)
    print("build gates: PASS")

def cmd_backfill(days=365):
    state = load_state()
    today = local_today()
    start = today - datetime.timedelta(days=days)
    if start < EPOCH_START:
        start = EPOCH_START
    end = today - datetime.timedelta(days=1)
    work = []
    d = start
    while d <= end:
        for pi in range(len(PAPERS)):
            work.append((pi, d))
        d += datetime.timedelta(days=1)
    print("backfill: %d editions (%d days x %d papers)" % (len(work), (end - start).days + 1, len(PAPERS)))
    add_editions(work, state)
    build_all()

def cmd_daily():
    state = load_state()
    today = local_today()
    if state.get("last_date") == today.isoformat():
        print("daily: today's editions already on file; nothing to do")
        return
    work = [(pi, today) for pi in range(len(PAPERS))]
    print("daily: adding %d editions for %s" % (len(work), today.isoformat()))
    add_editions(work, state)
    build_all()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--eco-rebuild", action="store_true",
                    help="replace ECO_START..today editions with real-ecosystem editions, then rebuild")
    a = ap.parse_args()
    if a.backfill:
        cmd_backfill(a.days)
    elif a.daily:
        cmd_daily()
    elif a.rebuild:
        build_all()
    elif a.eco_rebuild:
        cmd_eco_rebuild()
    else:
        ap.print_help()
