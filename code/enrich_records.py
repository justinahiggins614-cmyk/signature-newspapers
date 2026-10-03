#!/usr/bin/env python3
"""Site-14 fix wave: permanent IDs, hashes, record standards (one-time migration).

Enriches every edition volume record with the permanent record standard:
  id (JAH-ED-######, already present), paper_id (JAH-PAPER-######),
  fictionality_status, creation_mode, version, status, created/updated,
  canonical_url, content_hash (SHA-256 over the canonical record),
and every article with: id (JAH-ARTICLE-######), fictionality_status,
  creation_mode, version, content_hash, canonical_url.

Article IDs are deterministic and permanent: editions in chronological order,
article position within the edition -> JAH-ARTICLE-000001..NNNNNN.

Also rebuilds:
  data/index/editions.idx.json.gz  (compact edition rows, unchanged layout)
  data/index/articles.idx.json.gz  (NEW compact article rows)
  data/index/editions.idx.json     (NEW uncompressed fallback, same rows)
  data/index/articles.idx.json     (NEW uncompressed fallback, same rows)
  data/index/papers.json           (NEW paper + region records)
  data/index/hash-manifest.json    (NEW SHA-256 of every index file)
  data/index/api.json + api.json   (counts computed from the data itself)

Deterministic: re-running on already-enriched data is a no-op for content
(article/edition text untouched); hashes verify stable.
"""
import gzip, hashlib, json, os, datetime
import record_std  # idempotent stamping: content_hash excluded before hashing
from record_std import FICTIONALITY, SCHEMA_VERSION, PAPERS, SITE, eid, aid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
VOL = os.path.join(DATA, "volumes")
IDX = os.path.join(DATA, "index")
SITE = "https://justinahiggins614-cmyk.github.io/signature-newspapers/"

PAPERS = [
    {"paper_id": "JAH-PAPER-000001", "name": "The Signature Daily Globe",
     "region_id": "JAH-REGION-000001", "region": "the Signature world",
     "tagline": "All the world's Signature news, every morning", "founded": "2024-01-15"},
    {"paper_id": "JAH-PAPER-000002", "name": "The Meridian Herald",
     "region_id": "JAH-REGION-000002", "region": "Meridia",
     "tagline": "Meridia's morning voice since the first printing", "founded": "2024-02-01"},
    {"paper_id": "JAH-PAPER-000003", "name": "The Argent Post",
     "region_id": "JAH-REGION-000003", "region": "Argentia",
     "tagline": "Argentia, reported straight", "founded": "2024-03-10"},
    {"paper_id": "JAH-PAPER-000004", "name": "The Northlight Times",
     "region_id": "JAH-REGION-000004", "region": "Borealia",
     "tagline": "News from under the northern lights", "founded": "2024-04-22"},
    {"paper_id": "JAH-PAPER-000005", "name": "The Sunspire Gazette",
     "region_id": "JAH-REGION-000005", "region": "Solara",
     "tagline": "Solara's sunlit record of the day", "founded": "2024-06-05"},
    {"paper_id": "JAH-PAPER-000006", "name": "The Tidewater Chronicle",
     "region_id": "JAH-REGION-000006", "region": "Pelagia",
     "tagline": "Pelagia's paper of record, tide in tide out", "founded": "2024-07-19"},
]

FICTIONALITY = "FICTIONAL_GENERATED"
SCHEMA_VERSION = "JAH-NEWSPAPER-RECORD/1.0"
ARCHIVE_VERSION = "2026-10-03"


def canon(obj):
    """Canonical JSON for hashing: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def eid(n):
    return "JAH-ED-%06d" % n


def aid(n):
    return "JAH-ARTICLE-%06d" % n


def enrich_article(a, article_id, edition_id):
    a["id"] = article_id
    a["edition_id"] = edition_id
    a["fictionality_status"] = FICTIONALITY
    a["creation_mode"] = "GENERATED"
    a["version"] = "1.0"
    a["canonical_url"] = SITE + "?article=" + article_id
    body = dict(a)
    a["content_hash"] = sha256_hex(canon(body))
    return a


def enrich_edition(e, next_article):
    p = PAPERS[e["paper"]]
    e["paper_id"] = p["paper_id"]
    e["fictionality_status"] = FICTIONALITY
    e["creation_mode"] = "GENERATED"
    e["version"] = "1.0"
    e["status"] = "PUBLISHED"
    e["created"] = e["date"]
    e["updated"] = e["date"]
    e["canonical_url"] = SITE + "?edition=" + e["id"]
    arts = []
    for i, a in enumerate(e["articles"]):
        article_id = aid(next_article + i)
        arts.append(enrich_article(a, article_id, e["id"]))
    e["articles"] = arts
    e["article_count"] = len(arts)
    e["article_ids"] = [a["id"] for a in arts]
    body = dict(e)
    e["content_hash"] = sha256_hex(canon(body))
    return e, next_article + len(arts)


def main():
    chunks = sorted(f for f in os.listdir(VOL) if f.endswith(".jsonl.gz"))
    all_editions = []
    for cf in chunks:
        with gzip.open(os.path.join(VOL, cf), "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_editions.append((cf, json.loads(line)))
    # chronological order = edition ID order (IDs assigned chronologically)
    all_editions.sort(key=lambda t: t[1]["id"])
    ids = [e["id"] for _, e in all_editions]
    assert len(ids) == len(set(ids)), "duplicate edition IDs"
    assert ids == [eid(i + 1) for i in range(len(ids))], "edition IDs not contiguous"

    next_article = 1
    by_chunk = {}
    for cf, e in all_editions:
        # idempotent: record_std excludes content_hash before hashing
        next_article = record_std.stamp_edition(e, next_article)
        by_chunk.setdefault(cf, []).append(e)
    total_articles = next_article - 1

    # rewrite chunks (content untouched; metadata fields added)
    for cf, eds in by_chunk.items():
        tmp = os.path.join(VOL, cf + ".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            for e in eds:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp, os.path.join(VOL, cf))

    # compact indexes
    ed_rows, art_rows = [], []
    for cf, e in all_editions:
        wi = int(cf[10:15])
        txt = " ‖ ".join(a["h"] + " — " + a["body"][0] for a in e["articles"])
        ed_rows.append([e["id"], e["date"], e["paper"], len(e["articles"]), wi, txt])
        for a in e["articles"]:
            art_rows.append([a["id"], e["id"], e["paper"], e["date"], a["sec"], wi])

    with gzip.open(os.path.join(IDX, "editions.idx.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(ed_rows, f, ensure_ascii=False)
    with gzip.open(os.path.join(IDX, "articles.idx.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(art_rows, f, ensure_ascii=False)
    # uncompressed fallbacks (same rows, plain JSON)
    with open(os.path.join(IDX, "editions.idx.json"), "w", encoding="utf-8") as f:
        json.dump(ed_rows, f, ensure_ascii=False)
    with open(os.path.join(IDX, "articles.idx.json"), "w", encoding="utf-8") as f:
        json.dump(art_rows, f, ensure_ascii=False)

    # paper + region records
    papers = []
    for i, p in enumerate(PAPERS):
        first = min(e["id"] for _, e in all_editions if e["paper"] == i)
        last = max(e["id"] for _, e in all_editions if e["paper"] == i)
        n = sum(1 for _, e in all_editions if e["paper"] == i)
        papers.append({
            "paper_id": p["paper_id"], "name": p["name"],
            "region_id": p["region_id"], "region": p["region"],
            "tagline": p["tagline"], "description": p["tagline"],
            "founded": p["founded"], "status": "ACTIVE",
            "edition_count": n, "first_edition": first, "latest_edition": last,
            "editorial_model": "generated-daily",
            "creation_mode": "GENERATED", "version": "1.0",
            "fictionality_status": FICTIONALITY,
            "canonical_url": SITE + "?paper=" + p["paper_id"],
            "created": p["founded"], "updated": ARCHIVE_VERSION,
        })
    with open(os.path.join(IDX, "papers.json"), "w", encoding="utf-8") as f:
        json.dump(papers, f, indent=1, ensure_ascii=False)

    regions = [{"region_id": p["region_id"], "name": p["region"],
                "papers": [p["paper_id"]],
                "fictionality_status": FICTIONALITY,
                "note": "Fictional Signature-world region. Geography beyond the name is "
                        "not defined in the archive; no real-world place is implied."}
               for p in PAPERS]
    with open(os.path.join(IDX, "regions.json"), "w", encoding="utf-8") as f:
        json.dump(regions, f, indent=1, ensure_ascii=False)

    # hash manifest over every index file
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
        json.dump({"generated": ARCHIVE_VERSION, "algorithm": "SHA-256",
                   "files": hashes}, f, indent=1)

    dates = sorted({e["date"] for _, e in all_editions})
    api = {
        "site": "The Signature Global Newspaper Archive",
        "site_url": SITE,
        "title_provisional": True,
        "description": ("Original generated newspapers of the Signature world: daily editions "
                        "from six regional papers across past dates, updated daily. All people, "
                        "places, and events are invented; no real-world news."),
        "updated": datetime.date.today().isoformat(),
        "counts": {"editions": len(all_editions), "articles": total_articles,
                   "papers": len(PAPERS), "regions": len(regions)},
        "schema_version": SCHEMA_VERSION,
        "catalog_version": ARCHIVE_VERSION,
        "archive_version": ARCHIVE_VERSION,
        "papers": [{"paper_id": p["paper_id"], "name": p["name"], "region_id": p["region_id"],
                    "region": p["region"], "tagline": p["tagline"], "founded": p["founded"]}
                   for p in PAPERS],
        "date_range": [dates[0], dates[-1]],
        "deep_links": {
            "edition": SITE + "?edition=JAH-ED-000001",
            "article": SITE + "?article=JAH-ARTICLE-000001",
            "paper": SITE + "?paper=JAH-PAPER-000001",
            "verify": SITE + "?verify=JAH-ED-000001",
        },
        "index": {"editions_gz": "data/index/editions.idx.json.gz",
                  "editions": "data/index/editions.idx.json",
                  "articles_gz": "data/index/articles.idx.json.gz",
                  "articles": "data/index/articles.idx.json",
                  "hash_manifest": "data/index/hash-manifest.json"},
        "feed": "data/index/newspapers-catalog.json",
        "sitemap_index": "sitemap-index.xml",
        "static_archive": "archive/index.html",
        "honesty": ("Signature press: this edition is an original generated newspaper of the "
                    "Signature world. All people, places, teams, organizations, and events named "
                    "herein are invented. It reports no real-world news and names no real persons."),
        "fictionality_status": FICTIONALITY,
    }
    with open(os.path.join(ROOT, "api.json"), "w", encoding="utf-8") as f:
        json.dump(api, f, indent=1, ensure_ascii=False)
    with open(os.path.join(IDX, "api.json"), "w", encoding="utf-8") as f:
        json.dump(api, f, indent=1, ensure_ascii=False)

    # state: track the article sequence for the daily drip
    sp = os.path.join(DATA, "state.json")
    st = json.load(open(sp))
    st["next_article_index"] = total_articles + 1
    st["total_articles"] = total_articles
    json.dump(st, open(sp, "w"), indent=0)
    print("editions: %d  articles: %d  next_article_index: %d" %
          (len(all_editions), total_articles, total_articles + 1))


if __name__ == "__main__":
    main()
