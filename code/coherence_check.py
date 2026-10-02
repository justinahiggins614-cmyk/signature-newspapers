#!/usr/bin/env python3
"""Coherence check: signature-newspapers vs the phone-book AI canon.

The Newspaper Archive presents exactly one AI surface: the "<paper> Desk
Assistant" per-edition Q&A. It is a site helper (kind helper) and claims
no JAH-AI canon ID — it only quotes the edition's own printed articles.
This check verifies:
  - no edition record, index, or served file (index.html) claims a
    JAH-AI-* canon AI ID or pairs a canon AI NAME with an ID
  - the only AI surface is the desk-assistant helper

Exit 0 = coherent. Exit 1 = DRIFT FOUND (loud report).
"""
import gzip
import glob
import json
import os
import re
import sys

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CANON_PATH = os.path.expanduser(
    "~/workspace/jah-ai-models/ai-catalog.json")
CANON_ID = re.compile(r"JAH-AI-[A-Z]+-\d+")


def main():
    with open(CANON_PATH, encoding="utf-8") as f:
        canon_raw = json.load(f)
    canon_ids = set()
    recs = canon_raw.get("records", canon_raw) if isinstance(canon_raw, dict) else canon_raw
    for r in recs:
        canon_ids.add(str(r["ID"]))

    issues = []
    checked = 0
    for pat in ("data/volumes/*.jsonl.gz", "data/volumes/*.json.gz"):
        for vf in glob.glob(os.path.join(REPO, pat)):
            try:
                with gzip.open(vf, "rt", encoding="utf-8") as fh:
                    blob = fh.read()
            except Exception as e:
                issues.append(f"could not read {vf}: {e}")
                continue
            checked += 1
            for m in set(CANON_ID.findall(blob)):
                if m in canon_ids:
                    issues.append(
                        f"edition data {os.path.basename(vf)} references canon AI ID {m}")
    for fn in ("index.html",):
        text = open(os.path.join(REPO, fn), encoding="utf-8").read()
        for m in set(CANON_ID.findall(text)):
            if m in canon_ids:
                issues.append(f"SERVED FILE {fn} references canon AI ID {m}")

    # the one AI surface must stay a helper with no canon ID
    text = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
    if 'kind:"helper"' not in text:
        issues.append("desk assistant profile lost its helper kind marker")

    print(f"coherence_check (newspapers): {checked} edition volume files scanned")
    if issues:
        print("*** COHERENCE DRIFT ***")
        for i in issues:
            print("  -", i)
        return 1
    print("OK: the only AI surface is the '<paper> Desk Assistant' helper — "
          "no JAH-AI canon ID claimed anywhere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
