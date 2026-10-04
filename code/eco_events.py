#!/usr/bin/env python3
"""Site-14: real Signature-ecosystem event harvest for the newspaper.

Every story the paper prints about the ecosystem is grounded here — real
dated events from Manon's 27 website repos: drip commits, fixes shipped,
features, launches, shard moves, and dated totals from drip logs.

Nothing here is invented: headlines and bodies are built from real commit
subjects and real dated log lines. Numbers appear only when extracted from
a real source.

Usage:
    events_for_date(date) -> list of event dicts, ranked (best first).
    Each event: {site_key, site_name, beat, date, kind, subject,
                 added (int|None), total (int|None), noun}
"""
import datetime
import json
import os
import re
import subprocess

WS = os.path.expanduser("~/workspace")
HERE = os.path.dirname(os.path.abspath(__file__))

# (key, official site name, repo dir under ~/workspace, beat, record noun,
#  one-line factual description)
SITES = [
    ("math", "Signature Math", "signature-math", "builders", "math documents",
     "The deterministic math grid foundation — the 12x12 grid carrying the network's signature mark, with binary overlays and conversion documents."),
    ("calculator", "Signature Universal Paradox Immune Calculator", "jah-calculator", "builders", "solved equation records",
     "The all-modes calculator — Basic, Scientific, Ask Anything, Paradox Check and more — with a safe hand-written parser and read-aloud on every tab."),
    ("dictionary", "The Signature Dictionary", "jah-dictionary", "culture", "dictionary entries",
     "The dictionary: headwords with original definitions, phonetic respellings, word programs and an AI teacher."),
    ("jahwiki", "JAH Wiki", "jah-wiki", "catalogs", "articles",
     "The Wikipedia-like encyclopedia written over all of the network's data."),
    ("leaks", "Wiki Leaks", "jah-n-wiki-leaks", "catalogs", "dossiers",
     "The network's own declassified internal archive, publishing its own files."),
    ("llama", "Signature Llama", "sigllama", "ai", "model builds",
     "The network's own Llama — the chat engine behind every AI on every site."),
    ("phonebook", "The Signature AI Phone Book", "jah-ai-models", "ai", "AI profiles",
     "Every Signature AI with its own 11-digit phone number, dial pad and three-way calling."),
    ("patents", "Globally Rejustered Patent Catalog", "cyber-patent-catalog", "catalogs", "patent records",
     "Real harvested public patent records across every field of invention."),
    ("specs", "Signature Spec Catalog Pending Patents", "signature-one-archive", "catalogs", "draft specs",
     "Original draft patent specs, marching toward one million."),
    ("pc", "The Signature PC System Depository", "jah-computer-systems", "ai", "PC systems",
     "Every computer system from historic to predicted, each with demos and downloads."),
    ("books", "The Signature Book Depository", "signature-books", "culture", "books",
     "Finished books, library artifacts and magazines — all original."),
    ("comics", "The Signature Comic Store", "signature-comics", "culture", "comic issues",
     "The original Signature comics universe."),
    ("news", "The Signature Global Newspaper Archive", "signature-newspapers", "culture", "editions",
     "This very paper — daily editions covering the Signature ecosystem."),
    ("lab", "The Signature AI Mad Scientist Creation Lab", "signature-backend", "ai", "creations",
     "The mix-and-match creation lab, also serving the network's backend API."),
    ("generators", "The Signature Boundless Generator Archive", "signature-boundless-generators", "builders", "generator outputs",
     "Signature-line generators for every field — every output fully solved, no assumptions."),
    ("mixlab", "The Signature AI Mix Lab", "signature-ai-mixlab", "ai", "hybrids",
     "The hybrid forge: mix-and-match Signature AIs."),
    ("olypics", "AI Olypics", "signature-ai-olypics", "ai", "battles",
     "The battle dome where Signature AIs compete in Olympic-style events."),
    ("chips", "The Signature Computer Chip Maker and Archive", "signature-chip-maker", "builders", "chip designs",
     "Chip designs for any chip type, with full specs and board images."),
    ("apps", "The Signature App Archive", "signature-app-archive", "builders", "apps",
     "Signature versions of every phone and PC app."),
    ("robots", "The Signature AI Robot Matcher", "signature-ai-robot-matcher", "ai", "pairs",
     "Matches Signature AIs with Signature robot bodies."),
    ("experiments", "The Signature Experiment Solver", "signature-experiment-solver", "builders", "solved experiments",
     "Enter any experiment — the Universal Matrix runs it full-scale."),
    ("pixel", "Signature AI Pixel", "signature-ai-image-video-maker", "culture", "goods",
     "Free unlimited client-side image and video generation, plus the goods catalog."),
    ("music", "Signature Music Studio", "signature-ai-song-maker", "culture", "songs",
     "The full music studio — beat maker, song writer, vocal synth and the song archive."),
    ("fixit", "The Signature Mr Fix-It", "signature-fixit", "builders", "fixes",
     "Describe any problem — get step-by-step fixes with images and graphs."),
    ("university", "The Signature University", "signature-university", "culture", "courses",
     "The network's university."),
    ("mall", "The Signature Cyber Mega-Mall", "signature-cyber-mega-mall", "markets", "products",
     "The software mega-mall, '80s-'90s mall experience."),
    ("print3d", "The Signature 3D Print Depository", "signature-3d-print", "markets", "print designs",
     "The tangible wing — 3D-printable keepsake emblems for the records."),
]

SITE_BY_KEY = {s[0]: s for s in SITES}

# Manon's official 27-site network order (1-based site numbers)
SITE_NUMBER = {
    "math": 1, "calculator": 2, "dictionary": 3, "jahwiki": 4, "leaks": 5,
    "llama": 6, "phonebook": 7, "patents": 8, "specs": 9, "pc": 10,
    "books": 11, "comics": 12, "news": 13, "lab": 14, "generators": 15,
    "mixlab": 16, "olypics": 17, "chips": 18, "apps": 19, "robots": 20,
    "experiments": 21, "pixel": 22, "music": 23, "fixit": 24,
    "university": 25, "mall": 26, "print3d": 27,
}

BEAT_LABEL = {
    "catalogs": "Catalogs & Records",
    "ai": "AI & Systems",
    "builders": "Builders & Labs",
    "culture": "Library & Culture",
    "markets": "Markets",
}

# paper_idx -> beat it covers ("all" for the flagship Daily Globe)
PAPER_BEAT = {0: "all", 1: "catalogs", 2: "ai", 3: "builders", 4: "culture", 5: "markets"}

NUM = re.compile(r"\+([\d,]+)")
TOTAL = re.compile(r"\btotal\s+([\d,]+)", re.I)


def _to_int(s):
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def classify(subject):
    s = subject.lower()
    if re.search(r"\bshard[-\s]?\d+", s):
        return "shard"
    if re.search(r"\bdrip\b|\bharvest\b", s):
        return "drip"
    if re.search(r"\bfix(es|ed)?\b|\brepair\b|\bpatch\b", s):
        return "fix"
    if re.search(r"\btour\b|\bguide\b|\busability\b|\bnav\b", s):
        return "feature"
    if re.search(r"\blaunch\b|\bopens\b|\bnew site\b", s):
        return "feature"
    if re.search(r"\badd\b|\bnew\b|\bintroduc", s):
        return "feature"
    return "update"


LOCAL_TZ = "America/New_York"


_COMMITS_CACHE = {}


def _repo_commits(repo):
    """[(local_date, subject)] for every commit in a repo (cached)."""
    if repo in _COMMITS_CACHE:
        return _COMMITS_CACHE[repo]
    res = []
    try:
        out = subprocess.run(
            ["git", "-C", repo, "log", "--pretty=%cI%x00%s"],
            capture_output=True, text=True, timeout=120)
    except Exception:
        _COMMITS_CACHE[repo] = res
        return res
    if out.returncode == 0:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(LOCAL_TZ)
        for line in out.stdout.splitlines():
            if "\x00" not in line:
                continue
            iso, subj = line.split("\x00", 1)
            subj = subj.strip()
            if not subj:
                continue
            try:
                d = datetime.datetime.fromisoformat(iso)
                res.append((d.astimezone(tz).date(), subj))
            except Exception:
                continue
    _COMMITS_CACHE[repo] = res
    return res


def _git_log(repo, date):
    """[subject] for one repo whose committer date falls on `date`
    in America/New_York (commits are UTC-stamped)."""
    return [s for d, s in _repo_commits(repo) if d == date]


def _norm_subject(s):
    s = s.lower()
    s = NUM.sub("+N", s)
    s = TOTAL.sub("total T", s)
    s = re.sub(r"jah-[a-z]+-[0-9]+(\.\.[0-9]+)?", "ID", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _first_commit_date(repo):
    """First commit's local (America/New_York) date, or None."""
    commits = _repo_commits(repo)
    if not commits:
        return None
    return min(d for d, _ in commits)


def _spec_drip_totals(date):
    """Dated totals from the spec drip log: {added, total} or None."""
    p = os.path.join(WS, "signature-one-archive", "code", "specs", "drip.log")
    if not os.path.exists(p):
        return None
    ds = date.isoformat()
    best = None
    with open(p, errors="replace") as f:
        for line in f:
            if ds not in line:
                continue
            m_add = re.search(r"\+([\d,]+)\s+(?:new|solved)", line)
            m_tot = re.search(r"([\d,]+)\s+total\s+specs", line)
            if m_tot:
                best = {"added": _to_int(m_add.group(1)) if m_add else None,
                        "total": _to_int(m_tot.group(1))}
    return best


def _pending_notes(date):
    """Dated notes from the updates-pending journal (cleared periodically)."""
    p = os.path.join(WS, "hidden_files", "updates_pending.jsonl")
    if not os.path.exists(p):
        return []
    ds = date.isoformat()
    out = []
    with open(p, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or ds not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("date") == ds and obj.get("note"):
                out.append(obj["note"])
    return out


def _rank(ev):
    kind = ev["kind"]
    base = {"launch": 100, "shard": 85, "fix": 70, "drip": 55,
            "feature": 40, "update": 10, "note": 45}.get(kind, 10)
    boost = 0
    if ev.get("total"):
        boost = min(20, ev["total"] // 50000)
    if ev.get("added"):
        boost += min(10, ev["added"] // 2000)
    return base + boost


def events_for_date(date):
    """All real ecosystem events for a date, best-first."""
    events = []
    seen_norm = set()
    for key, name, repo_dir, beat, noun, desc in SITES:
        repo = os.path.join(WS, repo_dir)
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        # launch event on the repo's first-commit day
        if _first_commit_date(repo) == date:
            events.append({
                "site_key": key, "site_name": name, "beat": beat, "noun": noun,
                "desc": desc, "date": date, "kind": "launch",
                "subject": "%s launches" % name,
                "added": None, "total": None,
            })
        subjects = _git_log(repo, date)
        # aggregate identical drips (sum the +N across batches)
        agg = {}
        for s in subjects:
            norm = _norm_subject(s)
            k = (key, norm)
            if k in agg:
                agg[k]["n"] += 1
                a = _to_int(NUM.search(s).group(1)) if NUM.search(s) else None
                if a:
                    agg[k]["added"] = (agg[k]["added"] or 0) + a
            else:
                agg[k] = {"subject": s, "n": 1,
                          "added": (_to_int(NUM.search(s).group(1)) if NUM.search(s) else None)}
        for (k2, norm), a in agg.items():
            if (k2, norm) in seen_norm:
                continue
            seen_norm.add((k2, norm))
            kind = classify(a["subject"])
            ev = {
                "site_key": key, "site_name": name, "beat": beat, "noun": noun,
                "desc": desc, "date": date, "kind": kind,
                "subject": a["subject"],
                "added": a["added"],
                "total": _to_int(TOTAL.search(a["subject"]).group(1)) if TOTAL.search(a["subject"]) else None,
                "batches": a["n"],
            }
            # spec drip totals come from the dated drip log (authoritative)
            if key == "specs" and kind == "drip":
                dt = _spec_drip_totals(date)
                if dt:
                    ev["added"] = dt["added"] or ev["added"]
                    ev["total"] = dt["total"] or ev["total"]
            events.append(ev)
    # pending-journal notes for the date become short news notes
    for note in _pending_notes(date):
        events.append({
            "site_key": "network", "site_name": "The Signature Network",
            "beat": "network", "noun": "updates",
            "desc": "The 27-site Signature website network.",
            "date": date, "kind": "note", "subject": note,
            "added": None,
            "total": _to_int(TOTAL.search(note).group(1)) if TOTAL.search(note) else None,
        })
    for ev in events:
        ev["rank"] = _rank(ev)
    events.sort(key=lambda e: (-e["rank"], e["site_name"]))
    return events
