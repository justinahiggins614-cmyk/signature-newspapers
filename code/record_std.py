#!/usr/bin/env python3
"""Site-14: the permanent newspaper record standard (shared by generator + QA).

Record identity:
  edition: JAH-ED-######  | article: JAH-ARTICLE-###### | paper: JAH-PAPER-######

Fictionality statuses:
  FICTIONAL_GENERATED = retired Signature-world fiction editions
      (2025-10-03 .. 2026-09-27) — invented people/places/events, kept in
      the archive and clearly labeled, never presented as fact.
  ECOSYSTEM_REPORTED = real Signature-ecosystem news editions
      (2026-09-28 onward) — every story grounded in the 27 websites' own
      data: drip milestones, fixes shipped, launches, records.

Every edition/article carries: fictionality_status (one of the above),
creation_mode, version, status (editions), content_hash (SHA-256 over the
canonical JSON of the record minus the hash field itself), canonical_url.
"""
import hashlib
import json

SITE = "https://justinahiggins614-cmyk.github.io/signature-newspapers/"
FICTIONALITY = "FICTIONAL_GENERATED"
ECO_FICTIONALITY = "ECOSYSTEM_REPORTED"
VALID_FICTIONALITY = (FICTIONALITY, ECO_FICTIONALITY)
SCHEMA_VERSION = "JAH-NEWSPAPER-RECORD/1.0"
CREATION_MODES = ("GENERATED", "HUMAN_WRITTEN", "HUMAN_EDITED", "HYBRID", "IMPORTED")

PAPERS = [
    {"paper_id": "JAH-PAPER-000001", "name": "The Signature Daily Globe",
     "region_id": "JAH-REGION-000001", "region": "the Signature ecosystem",
     "tagline": "All the ecosystem's news, every morning", "founded": "2024-01-15"},
    {"paper_id": "JAH-PAPER-000002", "name": "The Meridian Herald",
     "region_id": "JAH-REGION-000002", "region": "Catalogs & Records",
     "tagline": "Patents, specs, wikis and dossiers, reported daily", "founded": "2024-02-01"},
    {"paper_id": "JAH-PAPER-000003", "name": "The Argent Post",
     "region_id": "JAH-REGION-000003", "region": "AI & Systems",
     "tagline": "The AI fleet: models, phones, robots and systems", "founded": "2024-03-10"},
    {"paper_id": "JAH-PAPER-000004", "name": "The Northlight Times",
     "region_id": "JAH-REGION-000004", "region": "Builders & Labs",
     "tagline": "Generators, chips, apps, experiments and fixes", "founded": "2024-04-22"},
    {"paper_id": "JAH-PAPER-000005", "name": "The Sunspire Gazette",
     "region_id": "JAH-REGION-000005", "region": "Library & Culture",
     "tagline": "Books, comics, music, images and learning", "founded": "2024-06-05"},
    {"paper_id": "JAH-PAPER-000006", "name": "The Tidewater Chronicle",
     "region_id": "JAH-REGION-000006", "region": "Markets",
     "tagline": "The mega-malls, where the ecosystem shops", "founded": "2024-07-19"},
]


def eid(n):
    return "JAH-ED-%06d" % n


def aid(n):
    return "JAH-ARTICLE-%06d" % n


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def stamp_article(a, article_id, edition_id, fictionality=FICTIONALITY):
    a["id"] = article_id
    a["edition_id"] = edition_id
    a["fictionality_status"] = fictionality
    a.setdefault("creation_mode", "GENERATED")
    a.setdefault("version", "1.0")
    a["canonical_url"] = SITE + "?article=" + article_id
    body = {k: v for k, v in a.items() if k != "content_hash"}
    a["content_hash"] = sha256_hex(canon(body))
    return a


def stamp_edition(e, next_article, fictionality=FICTIONALITY):
    """Stamp the permanent record standard onto an edition dict (id already set).
    Returns the next free article index."""
    p = PAPERS[e["paper"]]
    e["paper_id"] = p["paper_id"]
    e["fictionality_status"] = fictionality
    e.setdefault("creation_mode", "GENERATED")
    e.setdefault("version", "1.0")
    e.setdefault("status", "PUBLISHED")
    e.setdefault("created", e["date"])
    e["updated"] = e["date"]
    e["canonical_url"] = SITE + "?edition=" + e["id"]
    arts = []
    for a in e["articles"]:
        article_id = aid(next_article)
        next_article += 1
        arts.append(stamp_article(a, article_id, e["id"], fictionality))
    e["articles"] = arts
    e["article_count"] = len(arts)
    e["article_ids"] = [a["id"] for a in arts]
    body = {k: v for k, v in e.items() if k != "content_hash"}
    e["content_hash"] = sha256_hex(canon(body))
    return next_article


def _check_fictionality(v):
    return v in VALID_FICTIONALITY


def verify_article(a, edition_id):
    errs = []
    if not a.get("id", "").startswith("JAH-ARTICLE-"):
        errs.append("bad article id %r" % a.get("id"))
    if a.get("edition_id") != edition_id:
        errs.append("article %s edition link broken" % a.get("id"))
    if not _check_fictionality(a.get("fictionality_status")):
        errs.append("article %s missing fictionality" % a.get("id"))
    if a.get("creation_mode") not in CREATION_MODES:
        errs.append("article %s bad creation_mode" % a.get("id"))
    if not a.get("h") or not a.get("body"):
        errs.append("article %s missing headline/body" % a.get("id"))
    body = {k: v for k, v in a.items() if k != "content_hash"}
    if a.get("content_hash") != sha256_hex(canon(body)):
        errs.append("article %s hash mismatch" % a.get("id"))
    return errs


def verify_edition(e):
    errs = []
    if not e.get("id", "").startswith("JAH-ED-"):
        errs.append("bad edition id %r" % e.get("id"))
    if not _check_fictionality(e.get("fictionality_status")):
        errs.append("edition %s missing fictionality" % e.get("id"))
    if e.get("creation_mode") not in CREATION_MODES:
        errs.append("edition %s bad creation_mode" % e.get("id"))
    if e.get("status") not in ("PUBLISHED", "CORRECTED", "WITHDRAWN"):
        errs.append("edition %s bad status" % e.get("id"))
    if not e.get("honesty"):
        errs.append("edition %s missing honesty banner" % e.get("id"))
    for a in e.get("articles", []):
        errs.extend(verify_article(a, e["id"]))
    if e.get("article_ids") != [a["id"] for a in e.get("articles", [])]:
        errs.append("edition %s article_ids disagree" % e.get("id"))
    body = {k: v for k, v in e.items() if k != "content_hash"}
    if e.get("content_hash") != sha256_hex(canon(body)):
        errs.append("edition %s hash mismatch" % e.get("id"))
    return errs
