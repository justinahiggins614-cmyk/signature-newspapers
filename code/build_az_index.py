#!/usr/bin/env python3
"""Build the A-Z edition archive index for browse.html's "A-Z BY HEADLINE"
section.

Ground truth (never page text):
  * data/index/editions.idx.json.gz -> rows [eid, date, paper_idx, n_articles,
    week_idx, "headline -- body0 || headline -- body0 || ...", era]
    (older rows may have 6 elements without the era field)

Writes (under data/index/az/):
  * <L>.json        one compact JSON array per letter of the edition's LEAD
                    HEADLINE: [edition_id, date, paper_name, lead_headline, era]
                    sorted by headline (then date). Lazy-loaded by browse.html
                    on <details> toggle so phones never pull the whole catalog.
  * manifest.json   {total, built, counts} so the page stamps per-letter counts
                    without loading any letter file

Called by code/gen_editions.py build_all() (after stamp_browse()) — never one
run behind. Safe to re-run any time.
"""
import datetime
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AZ = os.path.join(ROOT, "data", "index", "az")
PAPER_NAMES = (
    "The Signature Daily Globe",
    "The Meridian Herald",
    "The Argent Post",
    "The Northlight Times",
    "The Sunspire Gazette",
    "The Tidewater Chronicle",
)


def letter_of(text):
    m = re.search(r"[A-Za-z]", text or "")
    return m.group(0).upper() if m else "#"


def lead_headline(blob):
    first = (blob or "").split(" || ")[0]
    head = first.split(" — ")[0].strip()
    return head[:160]


def main():
    with gzip.open(os.path.join(ROOT, "data", "index",
                                "editions.idx.json.gz"), "rt",
                   encoding="utf-8") as f:
        rows = json.load(f)
    buckets = {}
    for r in rows:
        eid, date = r[0], r[1]
        pi = r[2] if isinstance(r[2], int) else 0
        paper = PAPER_NAMES[pi] if 0 <= pi < len(PAPER_NAMES) else ""
        era = r[6] if len(r) > 6 else ""
        head = lead_headline(r[5] if len(r) > 5 else "")
        buckets.setdefault(letter_of(head), []).append(
            [eid, date, paper, head, era])
    os.makedirs(AZ, exist_ok=True)
    counts = {}
    for L in sorted(buckets):
        rr = sorted(buckets[L], key=lambda x: (x[3].lower(), x[1]))
        with open(os.path.join(AZ, L + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(rr, f, ensure_ascii=False, separators=(",", ":"))
        counts[L] = len(rr)
    total = sum(counts.values())
    manifest = {"total": total,
                "built": datetime.date.today().isoformat(),
                "counts": counts}
    with open(os.path.join(AZ, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, separators=(",", ":"))
    print("A-Z-ARCHIVE: %d editions -> data/index/az/ (%d letter files)"
          % (total, len(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
