#!/usr/bin/env python3
"""Build the compact article-BODY search index for the newspaper archive.

articles.search.json.gz rows:
    [article_id, edition_id, paper_idx, date, section, headline, body_text]

Bodies are small (~350 chars/article), so the whole archive's article text
fits in one lazy-loaded blob (~1.5-2MB gz). The frontend fetches it ONLY when
the user searches with scope "article text" / "both" — boot is untouched.

Called by code/gen_editions.py build_all() on every drip so the index never
goes stale. Idempotent: rebuilds from the volume chunks every time.
"""
import gzip
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..")
IDX = os.path.join(REPO, "data", "index")
VOL = os.path.join(REPO, "data", "volumes")


def read_chunk(wi):
    path = os.path.join(VOL, "editions-w%05d.jsonl.gz" % wi)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def all_editions():
    out = []
    for fn in sorted(os.listdir(VOL)):
        if fn.startswith("editions-w") and fn.endswith(".jsonl.gz"):
            wi = int(fn[len("editions-w"):len("editions-w") + 5])
            out.extend(read_chunk(wi))
    out.sort(key=lambda e: e["id"])
    return out


def build():
    editions = all_editions()
    rows = []
    for e in editions:
        for a in e["articles"]:
            rows.append([
                a["id"], e["id"], e["paper"], e["date"], a["sec"],
                a["h"], " ".join(a["body"]),
            ])
    gz_path = os.path.join(IDX, "articles.search.json.gz")
    with gzip.open(gz_path, "wt", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    plain_path = os.path.join(IDX, "articles.search.json")
    with open(plain_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    print("articles.search: %d rows -> %s (%d bytes gz)" %
          (len(rows), gz_path, os.path.getsize(gz_path)))
    return len(rows)


if __name__ == "__main__":
    build()
