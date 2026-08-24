#!/usr/bin/env python3
"""Find each state's per-game result pages, and prove they carry a real draw.

The first version of this script only asked "does a group of numbers appear
here", which was enough to spot the pattern and not nearly enough to trust it:
it happily reported Vermont's number generator and a 404 page rendering "404"
as three balls. It now runs the scraper's own detector and applies the
scraper's own rules -- no generator widgets, no undated rows, no sequences --
so anything it prints is something an adapter could actually publish.

Two parallel passes: find the game links, then open them.

    .venv/bin/python Scripts/pergame.py [ST ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parallel  # noqa: E402
import scrape  # noqa: E402

HOSTS = {
    "AR": "www.arkansasscholarshiplottery.com", "CT": "www.ctlottery.org",
    "DC": "dclottery.com", "DE": "www.lottery.delaware.gov",
    "IA": "ialottery.com", "ID": "www.idaholottery.com",
    "IN": "www.hoosierlottery.com", "KS": "playonkansas.com",
    "KY": "www.kylottery.com", "LA": "louisianalottery.com",
    "MN": "www.mnlottery.com", "MO": "www.molottery.com",
    "MS": "www.mslotteryhome.com", "MT": "montanalottery.com",
    "ND": "www.lottery.nd.gov/public", "NE": "nelottery.com/homeapp/landing",
    "NM": "www.nmlottery.com", "OR": "www.oregonlottery.org",
    "RI": "www.rilot.com", "SD": "lottery.sd.gov", "TN": "www.tnlottery.com",
    "VA": "www.valottery.com", "WV": "wvlottery.com", "VT": "vtlottery.com",
}

# Game names worth opening. The multi-state games are already covered
# everywhere, so a page that only proves Powerball works proves nothing.
WANTED = ("pick", "cash", "daily", "match", "fantasy", "lotto", "megabucks",
          "gimme", "badger", "supercash", "rolling", "classic", "triple",
          "weekly", "wild money", "hit 5", "bonus", "multi", "cowboy", "2by2",
          "win 4", "take 5", "money", "keno", "lucky", "all or nothing",
          "palmetto", "hoosier", "natural state", "show me", "treasure")
SKIP = ("powerball", "mega millions", "lucky for life", "cash4life",
        "lotto america", "scratch", "instant", "how to", "rules", "odds")

LINKS = """
() => [...document.querySelectorAll('a')]
  .map(a => ({href: a.href, text: (a.textContent||'').replace(/\\s+/g,' ').trim()}))
  .filter(l => l.href && /game|draw|number/i.test(l.href))
  .slice(0, 400)
"""


def candidate_links(links):
    out, seen = [], set()
    for link in links or []:
        text = (link.get("text") or "").lower()
        if not text or len(text) > 40 or any(s in text for s in SKIP):
            continue
        if any(word in text for word in WANTED) and link["href"] not in seen:
            seen.add(link["href"])
            out.append(link)
    return out[:8]


def usable_rows(rows):
    """Rows the scraper's own rules would accept: real, dated, not generated."""
    good = []
    for row in rows or []:
        numbers = [int(n) for n in row["nums"]]
        if scrape.GENERATOR_RE.search(row.get("cls") or ""):
            continue
        if scrape._is_sequence(numbers):
            continue
        date = next((found for text in row.get("texts") or []
                     if (found := scrape.date_from_text(text))), None)
        if date:
            good.append({"nums": numbers, "date": date,
                         "cls": (row.get("cls") or "")[:40]})
    return good


def main():
    wanted = [c.upper() for c in sys.argv[1:]] or list(HOSTS)

    print(f"pass 1: game links for {len(wanted)} states", file=sys.stderr)
    indexes = {code: f"https://{HOSTS[code]}/" for code in wanted}
    found = parallel.evaluate_many(indexes.values(), LINKS, settle_ms=3500,
                                   concurrency=8)

    targets = {}   # url -> (state, game name)
    for code, index_url in indexes.items():
        for link in candidate_links(found.get(index_url)):
            targets.setdefault(link["href"], (code, link["text"]))
    print(f"pass 2: {len(targets)} game pages", file=sys.stderr)

    pages = parallel.evaluate_many(targets, scrape.BALLS_SCRIPT, settle_ms=5500,
                                   concurrency=8)

    results = {}
    for url, (code, name) in targets.items():
        rows = usable_rows(pages.get(url))
        if rows:
            results.setdefault(code, []).append(
                {"game": name, "url": url, "rows": rows[:2]})

    Path("pergame.json").write_text(json.dumps(results, indent=1))
    print(f"\n{'ST':<4}{'game':<26} {'date':<12} numbers")
    for code in sorted(results, key=lambda c: -len(results[c])):
        for hit in results[code]:
            row = hit["rows"][0]
            print(f"{code:<4}{hit['game'][:24]:<26} {row['date']:<12} {row['nums']}")
    print(f"\n{len(results)} states with a usable in-state result",
          file=sys.stderr)


if __name__ == "__main__":
    main()
