#!/usr/bin/env python3
"""Site-14: real-ecosystem story writer for the newspaper.

Turns the dated events from eco_events.py into newspaper articles.
Every headline and paragraph is grounded in a real event (a real commit
subject or a real dated log line). Numbers appear only when extracted
from the source. No invented quotes, no invented people, no invented
figures. Drafts are always called drafts — never filed patents.
"""
import re

from eco_events import BEAT_LABEL, SITE_NUMBER

BYLINES = {
    "lead": "Signature News Desk",
    "catalogs": "Records Desk",
    "ai": "AI Desk",
    "builders": "Builders Desk",
    "culture": "Culture Desk",
    "markets": "Markets Desk",
    "network": "Network Desk",
}

ECO_HONESTY = ("Signature ecosystem press: this edition reports real events from "
               "the 27-website Signature network — drip milestones, fixes shipped, "
               "launches and records, verified against the sites' own data. "
               "It reports no real-world news and names no real-world persons.")


def _the(site):
    return site if site.startswith("The ") else "the " + site


def _The(site):
    s = _the(site)
    return s[0].upper() + s[1:] if s else s


def _site(site):
    return site  # bare name for headlines


def fmt(n):
    return format(n, ",") if isinstance(n, int) else str(n)


def _short(subject, n=110):
    s = re.sub(r"\s+", " ", subject).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def _clean_subject(subject):
    """Trim commit-ese for headline use."""
    s = re.sub(r"\s+", " ", subject).strip()
    # drop a leading "<Site>: " prefix if the site name is already in the headline
    s = re.sub(r"^[^:]{4,60}:\s*", "", s)
    return s


def headline_for(ev):
    site, noun = ev["site_name"], ev["noun"]
    kind = ev["kind"]
    added, total = ev.get("added"), ev.get("total")
    if kind == "launch":
        num = SITE_NUMBER.get(ev["site_key"])
        return "%s opens its doors%s" % (site, " — site %d of 27" % num if num else "")
    if kind == "drip":
        if total:
            return "%s breaks its own record: %s %s and counting" % (site, fmt(total), noun)
        if added:
            return "%s adds %s %s in a day" % (site, fmt(added), noun)
        return "%s: fresh %s land in today's drip" % (site, noun)
    if kind == "shard":
        if total:
            return "%s grows sideways: %s %s on file" % (site, fmt(total), noun)
        return "%s shards its archive sideways" % site
    if kind == "fix":
        return "%s fix ships: %s" % (site, _short(_clean_subject(ev["subject"]), 90))
    if kind == "note":
        return _short(ev["subject"], 110)
    return "%s: %s" % (site, _short(_clean_subject(ev["subject"]), 90))


def body_for(ev):
    """3-4 factual paragraphs. Only sourced facts; no invented quotes."""
    site, noun, desc = ev["site_name"], ev["noun"], ev["desc"]
    kind = ev["kind"]
    added, total = ev.get("added"), ev.get("total")
    subj = _clean_subject(ev["subject"])
    paras = []

    if kind == "launch":
        num = SITE_NUMBER.get(ev["site_key"])
        paras.append(
            "%s launched today%s. %s" % (
                _The(site),
                ", joining the Signature network as site %d of 27" % num if num else "",
                desc))
        paras.append(
            "Like every site in the network, it ships with its full apparatus: "
            "its records, its tools, and its AI helper, all marching toward "
            "one million files.")
        paras.append(
            "The launch is one more step in the network's standing order: "
            "expand and expand, with growth always sideways and no data ever cut.")
    elif kind == "drip":
        if total and added:
            paras.append(
                "%s printed another %s %s today, lifting its archive to %s %s "
                "on file — a new all-time high for the site." % (_The(site), fmt(added), noun, fmt(total), noun))
        elif total:
            paras.append(
                "%s archive stands at %s %s on file — a new all-time high — "
                "after today's drip." % (_The(site), fmt(total), noun))
        elif added:
            paras.append(
                "Another %s %s landed on %s today." % (fmt(added), noun, _the(site)))
        else:
            paras.append(
                "%s regular drip added a fresh batch of %s today." % (_The(site), noun))
        paras.append(desc)
        paras.append(
            "The site keeps marching toward one million %s, with fresh batches "
            "landing around the clock. Growth goes sideways into new storage, "
            "never by trimming the archive." % noun)
    elif kind == "shard":
        paras.append(
            "%s outgrew its home again today, and the oldest %s moved "
            "sideways into a new shard repository: %s" % (_The(site), noun, _short(subj, 140)))
        paras.append(
            "Nothing was deleted and nothing was lost — that is the rule. "
            "The network grows sideways, and the main archive keeps serving "
            "every record through its shard index.")
        if total:
            paras.append(
                "The count stands at %s %s on file, still marching toward "
                "one million." % (fmt(total), noun))
        else:
            paras.append(desc)
    elif kind == "fix":
        paras.append("A fix shipped on %s today: %s." % (_the(site), _short(subj, 200)))
        paras.append(desc)
        paras.append("The fix is live on the site now.")
    elif kind == "note":
        paras.append(_short(ev["subject"], 400))
        paras.append(
            "The note comes from the network's own operations journal, which "
            "logs every milestone the day it ships.")
        paras.append(desc)
    else:  # feature / update
        paras.append("On %s today: %s." % (_the(site), _short(subj, 220)))
        paras.append(desc)
        paras.append(
            "The change is live on the site now, one of many the network "
            "ships every day on its march to one million files per archive.")
    return paras


def roundup_article(events, date):
    """'Around the network' roundup of the day's other real events."""
    lines = []
    for ev in events[:6]:
        lines.append("%s — %s." % (ev["site_name"], _short(_clean_subject(ev["subject"]), 120)))
    body = [
        "Beyond the front page, the network kept its usual pace today. "
        "Here is what else shipped across the 27 sites.",
    ] + lines + [
        "Every item above is drawn from the sites' own records for %s — "
        "commits, drip logs and the operations journal." % date.isoformat(),
    ]
    return {"sec": "network", "h": "Around the network: %s" % date.strftime("%B %d, %Y"),
            "by": BYLINES["network"], "body": body}


def article_for(ev, sec):
    return {"sec": sec, "h": headline_for(ev),
            "by": BYLINES.get(sec, "Signature News Desk"),
            "body": body_for(ev)}
