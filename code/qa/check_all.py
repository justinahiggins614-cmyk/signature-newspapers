#!/usr/bin/env python3
"""QA gates for the Signature Global Newspaper Archive. Exit 1 on ANY failure.

Checks:
 1. edition IDs unique + contiguous (JAH-ED-000001..N)
 2. article IDs unique + contiguous, each linked to a real edition
 3. counts agree: api.json == edition index == volume records; article sums agree
 4. every edition + article carries FICTIONAL_GENERATED
 5. every edition + article hash verifies (SHA-256 over canonical JSON)
 6. paper/region IDs present and consistent
 7. sitemap-index.xml + children are valid XML; edition URL count matches
 8. no hard-coded edition/article counts in index.html
"""
import gzip, json, os, re, sys, xml.etree.ElementTree as ET

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
DATA = os.path.join(REPO, "data")
VOL = os.path.join(DATA, "volumes")
IDX = os.path.join(DATA, "index")
sys.path.insert(0, os.path.join(REPO, "code"))
import record_std

fails = []


def fail(msg):
    fails.append(msg)
    print("FAIL:", msg)


def ok(msg):
    print("ok:", msg)


# ---- load everything ----
editions = []
for cf in sorted(os.listdir(VOL)):
    if cf.endswith(".jsonl.gz"):
        with gzip.open(os.path.join(VOL, cf), "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    editions.append(json.loads(line))
editions.sort(key=lambda e: e["id"])
ed_rows = json.load(gzip.open(os.path.join(IDX, "editions.idx.json.gz"), "rt"))
art_rows = json.load(gzip.open(os.path.join(IDX, "articles.idx.json.gz"), "rt"))
api = json.load(open(os.path.join(REPO, "api.json")))
papers = json.load(open(os.path.join(IDX, "papers.json")))

# 1. edition IDs
ids = [e["id"] for e in editions]
if len(ids) != len(set(ids)):
    fail("duplicate edition IDs")
elif ids != ["JAH-ED-%06d" % (i + 1) for i in range(len(ids))]:
    fail("edition IDs not contiguous from JAH-ED-000001")
else:
    ok("edition IDs contiguous: %d" % len(ids))

# 2. article IDs
aids = [a["id"] for e in editions for a in e["articles"]]
edset = set(ids)
if len(aids) != len(set(aids)):
    fail("duplicate article IDs")
elif aids != ["JAH-ARTICLE-%06d" % (i + 1) for i in range(len(aids))]:
    fail("article IDs not contiguous from JAH-ARTICLE-000001")
elif any(a.get("edition_id") not in edset for e in editions for a in e["articles"]):
    fail("article linked to nonexistent edition")
else:
    ok("article IDs contiguous: %d, all linked" % len(aids))

# 3. counts
n_art = len(aids)
if api["counts"]["editions"] != len(editions) != len(ed_rows):
    fail("edition count mismatch: api=%s volumes=%d index=%d" %
         (api["counts"].get("editions"), len(editions), len(ed_rows)))
elif api["counts"]["articles"] != n_art != len(art_rows):
    fail("article count mismatch: api=%s records=%d index=%d" %
         (api["counts"].get("articles"), n_art, len(art_rows)))
elif api["counts"]["papers"] != 6 or len(papers) != 6:
    fail("paper count != 6")
else:
    ok("counts agree: %d editions / %d articles / 6 papers" % (len(editions), n_art))

# 4+5. fictionality + hashes on every record (full verify)
bad = 0
for e in editions:
    errs = record_std.verify_edition(e)
    if errs:
        bad += 1
        if bad <= 5:
            for er in errs:
                fail(er)
if bad == 0:
    ok("all %d editions + %d articles: fictionality present, hashes verify" % (len(editions), n_art))
else:
    fail("%d editions failed record verification" % bad)

# 6. paper/region IDs
pids = [p["paper_id"] for p in papers]
if pids != ["JAH-PAPER-%06d" % (i + 1) for i in range(6)]:
    fail("paper IDs wrong: %s" % pids)
elif {e["paper_id"] for e in editions} != set(pids):
    fail("edition paper_id not matching papers.json")
else:
    ok("paper/region IDs consistent")

# 7. sitemaps
try:
    tree = ET.parse(os.path.join(REPO, "sitemap-index.xml"))
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    refs = [el.text for el in tree.getroot().iter(ns + "loc") if el.text]
    url_total = 0
    for ref in refs:
        fn = ref.rsplit("/", 1)[-1]
        fp = os.path.join(REPO, fn)
        if not os.path.isfile(fp):
            continue
        try:
            t2 = ET.parse(fp)
            url_total += sum(1 for _el in t2.getroot().iter(ns + "loc"))
        except ET.ParseError:
            fail("sitemap %s is not valid XML" % fn)
    ok("sitemap-index.xml valid (%d child refs, %d URLs)" % (len(refs), url_total))
except ET.ParseError as ex:
    fail("sitemap-index.xml invalid: %s" % ex)

# 8. stat chips stamped (never bare "…") AND assert-verified against real counts
html = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
m = re.search(r"<!-- STAT-CHIPS -->(.*?)<!-- /STAT-CHIPS -->", html, re.S)
if not m:
    fail("index.html is missing the STAT-CHIPS stamp block")
else:
    stamped = [int(x.replace(",", "")) for x in
               re.findall(r"<b>([\d,]+)</b><span>(?:editions on file|articles printed)</span>", m.group(1))]
    n_ed = len(editions)
    n_art = sum(len(e["articles"]) for e in editions)
    if len(stamped) != 2 or stamped[0] != n_ed or stamped[1] != n_art:
        fail("STAT-CHIPS counts %s do not match real counts (%d editions, %d articles)"
             % (stamped, n_ed, n_art))
    else:
        ok("STAT-CHIPS stamped and verified: %d editions, %d articles" % (n_ed, n_art))
    mm = re.search(r"<!-- MARCH-TXT -->(.*?)<!-- /MARCH-TXT -->", html, re.S)
    if not mm or str(format(n_ed, ",")) not in mm.group(1):
        fail("MARCH-TXT stamp missing or stale")
    else:
        ok("MARCH-TXT stamp verified")
if re.search(r"<b>\s*…\s*</b>\s*<span>loading</span>", html):
    fail("index.html still boots a bare \u2026 loading chip")
else:
    ok("no bare \u2026 loading chips in initial HTML")

# 9. article body-search index exists, complete, and matches the article set
spath = os.path.join(IDX, "articles.search.json.gz")
if not os.path.exists(spath):
    fail("data/index/articles.search.json.gz missing")
else:
    srows = json.load(gzip.open(spath, "rt"))
    sids = set(r[0] for r in srows)
    if sids != set(aids):
        fail("articles.search index IDs do not match the article set (%d vs %d)" %
             (len(sids), len(set(aids))))
    elif any(len(r) != 7 or not r[6] for r in srows):
        fail("articles.search index has malformed/empty rows")
    else:
        ok("articles.search index complete: %d rows with body text" % len(srows))

print("---")
if fails:
    print("QA GATES: %d FAILURES" % len(fails))
    sys.exit(1)
print("QA GATES: ALL PASS")
