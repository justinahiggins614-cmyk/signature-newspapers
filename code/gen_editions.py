#!/usr/bin/env python3
"""
The Signature Global Newspaper Archive - deterministic edition generator.

Usage:
    python3 code/gen_editions.py --backfill   # seed ~365 past days x 6 papers
    python3 code/gen_editions.py --daily       # cron: add today's editions (idempotent)
    python3 code/gen_editions.py --rebuild     # rebuild index/sitemap/api only

Determinism: edition content is seeded by SALT + paper + date, so re-running
never changes an existing edition. IDs (JAH-ED-######) are assigned in
chronological order; data/state.json tracks next_index and last_date.

CONTENT HONESTY: every edition is original Signature-world reporting. All
people, places, teams, and events are invented. Never real-world news, never
real people's names, never copies of real mastheads. Each edition carries an
honesty banner stating this.

Layout: weekly gz chunks data/volumes/editions-wNNNNN.jsonl.gz (7 days x 6
papers = 42 editions/chunk). Compact search index data/index/editions.idx.json.gz
rows: [id, date, paper_idx, n_articles, chunk, headlines+ledes joined].
"""
import argparse, gzip, json, os, random, re, sys, datetime

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
    """Assign IDs, append into weekly chunks. ed_list: [(paper_idx, date)] oldest-first."""
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
            e = make_edition(pi, d)
            e["id"] = eid(state["next_index"])
            state["next_index"] += 1
            state["total_articles"] += len(e["articles"])
            existing.append(e)
        existing.sort(key=lambda e: (e["date"], e["paper"]))
        write_chunk(wi, existing)
    if ed_list:
        state["last_date"] = max(d for _, d in ed_list).isoformat()
    save_state(state)

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
    latest = meta[-1][1]
    todays = [m for m in meta if m[1] == latest][:6]
    parts = []
    for eid_, date, pi, n, wi, iss in todays:
        e = next(x for x in read_chunk(wi) if x["id"] == eid_)
        heads = "".join("<li>%s</li>" % h for h in
                        [a["h"].replace("&", "&amp;").replace("<", "&lt;") for a in e["articles"][:3]])
        parts.append(
            '<p><b><a href="?edition=%s">%s</a></b> — %s, Vol. %d Issue %d<ul>%s</ul></p>' %
            (eid_, PAPERS[pi]["name"], date, e["volume"], e["issue"], heads))
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

def build_all():
    meta = all_editions_meta()
    # --- compact search index: [id, date, paper, n_art, week, headlines+ledes] ---
    cache = {}
    def _ed(wi, eid_):
        if wi not in cache:
            cache[wi] = {x["id"]: x for x in read_chunk(wi)}
        return cache[wi][eid_]
    rows = []
    for eid_, date, pi, n, wi, iss in meta:
        e = _ed(wi, eid_)
        txt = " ‖ ".join(a["h"] + " — " + a["body"][0] for a in e["articles"])
        rows.append([eid_, date, pi, n, wi, txt])
    with gzip.open(os.path.join(IDX, "editions.idx.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    # --- sitemap.xml ---
    urls = [SITE] + [SITE + "?edition=" + eid_ for eid_, _, _, _, _, _ in meta]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.smaps.org/schemas/sitemap/0.9">'.replace("smaps", "sitemaps")]
    for u in urls:
        sm.append("<url><loc>%s</loc></url>" % u)
    sm.append("</urlset>")
    with open(os.path.join(ROOT, "sitemap.xml"), "w") as f:
        f.write("\n".join(sm))
    # --- api.json (root + data/index) ---
    dates = sorted({d for _, d, _, _, _, _ in meta})
    api = {
        "site": "The Signature Global Newspaper Archive",
        "site_url": SITE,
        "title_provisional": True,
        "description": ("Original generated newspapers of the Signature world: daily editions "
                        "from six regional papers across past dates, updated daily. All people, "
                        "places, and events are invented; no real-world news."),
        "updated": datetime.date.today().isoformat(),
        "counts": {"editions": len(meta),
                   "articles": sum(n for _, _, _, n, _, _ in meta),
                   "papers": len(PAPERS)},
        "papers": [{"name": p["name"], "region": p["region"], "tagline": p["tagline"],
                    "founded": p["founded"]} for p in PAPERS],
        "date_range": [dates[0], dates[-1]] if dates else [None, None],
        "deep_link_pattern": SITE + "?edition=JAH-ED-000001",
        "index": "data/index/editions.idx.json.gz",
        "honesty": HONESTY,
    }
    with open(os.path.join(ROOT, "api.json"), "w") as f:
        json.dump(api, f, indent=1)
    with open(os.path.join(IDX, "api.json"), "w") as f:
        json.dump(api, f, indent=1)
    # --- robots.txt ---
    with open(os.path.join(ROOT, "robots.txt"), "w") as f:
        f.write("User-agent: *\nAllow: /\nSitemap: %ssitemap.xml\n" % SITE)
    # --- static latest-editions stamp (crawler/no-JS friendly) ---
    stamp_static()
    # --- data size guard ---
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fns in os.walk(DATA) for f in fns)
    print("DATA bytes: %d (guard 800MB: %s)" % (total, "TRIPPED" if total > 800 * 1024 * 1024 else "ok"))
    print("editions: %d articles: %d" % (len(meta), sum(n for _, _, _, n, _, _ in meta)))

def cmd_backfill(days=365):
    state = load_state()
    today = datetime.date.today()
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
    today = datetime.date.today()
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
    a = ap.parse_args()
    if a.backfill:
        cmd_backfill(a.days)
    elif a.daily:
        cmd_daily()
    elif a.rebuild:
        build_all()
    else:
        ap.print_help()
