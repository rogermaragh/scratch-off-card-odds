#!/usr/bin/env python3
"""Ask each state whether its scratch-off prizes can actually be ranked.

The ranking needs one thing: for each prize tier, how many were printed and how
many are left. The print run cancels out of the ratio, so odds and ticket
counts are optional -- but without both counts per tier there is nothing to
divide, and a state that publishes only "top prizes remaining" cannot be ranked
at all, however much it looks like it can.

So this does not guess from the page's appearance. It runs the scraper's own
`tiers_from_table` over whatever tables the page has and reports what came
back, which is exactly what an adapter would get.

    .venv/bin/python Scripts/scratchprobe.py [ST ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import parallel  # noqa: E402
import scrape  # noqa: E402

# Every state without a scratch-off adapter. Hosts are the current ones --
# several moved during the draw-game work, and a stale domain looks exactly
# like a state that publishes nothing.
HOSTS = {
    "AR": "www.arkansasscholarshiplottery.com", "AZ": "www.arizonalottery.com",
    "CO": "www.coloradolottery.com", "CT": "ctlottery.com",
    "DC": "dclottery.com", "DE": "www.lottery.delaware.gov",
    "FL": "www.flalottery.com", "GA": "www.galottery.com",
    "IA": "ialottery.com", "ID": "www.idaholottery.com",
    "IL": "www.illinoislottery.com", "KS": "playonkansas.com",
    "KY": "www.kylottery.com", "MA": "www.masslottery.com",
    "ME": "www.mainelottery.com", "MI": "www.michiganlottery.com",
    "MN": "www.mnlottery.com", "MO": "www.molottery.com",
    "MT": "montanalottery.com", "ND": "www.lottery.nd.gov",
    "NE": "nelottery.com", "NH": "www.nhlottery.com",
    "NJ": "www.njlottery.com", "NY": "nylottery.ny.gov",
    "OH": "www.ohiolottery.com", "OR": "www.oregonlottery.org",
    "PA": "www.palottery.pa.gov", "SD": "lottery.sd.gov",
    "TN": "www.tnlottery.com", "TX": "www.texaslottery.com",
    "VT": "vtlottery.com", "WI": "wilottery.com",
    "WV": "wvlottery.com", "WY": "wyolotto.com",
}

INDEX_HINT = re.compile(r"scratch|instant|e-?instant", re.I)
# Anything but the host's own nav. The first pass at this matched any href
# containing "game", which collected menu links and a lottery forum and
# concluded that thirty-three states publish nothing -- the same mistake as
# the first draw-game sweep, and the same lesson: when a sweep says almost
# everyone fails, suspect the sweep.
SKIP_HINT = re.compile(r"signup|sign-in|login|register|forum|responsible|"
                       r"how-to|faq|winners|news|espanol|/draw", re.I)

LINKS = """
() => [...document.querySelectorAll('a')]
  .map(a => ({href: a.href, text: (a.textContent||'').replace(/\\s+/g,' ').trim()}))
  .filter(l => l.href && l.href.startsWith('http'))
  .slice(0, 500)
"""

# Only the tables and a slice of text: the parser wants markup, and shipping a
# whole page back for seventy pages is a lot of memory for nothing.
TABLES = """
() => ({
  tables: [...document.querySelectorAll('table')]
            .map(t => t.outerHTML).join('\\n').slice(0, 200000),
  text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 3000),
  title: (document.title || '').slice(0, 80)
})
"""


def pick(links, pattern, limit):
    out, seen = [], set()
    for link in links or []:
        blob = f"{link.get('href','')} {link.get('text','')}"
        if SKIP_HINT.search(blob):
            continue
        if pattern.search(blob) and link["href"] not in seen:
            seen.add(link["href"])
            out.append(link["href"])
    return out[:limit]


def children_of(index_url, links, limit):
    """Links that go *below* the index page.

    A game's prize table lives on the game's own page, and those pages sit
    under the scratch-off index -- /scratch-offs/1234, /scratchers/50x-the-
    money. Selecting on the path rather than on the word "game" is what
    separates a game from the menu item pointing at the list of them.
    """
    base = index_url.split("?")[0].split("#")[0].rstrip("/")
    out, seen = [], set()
    for link in links or []:
        href = (link.get("href") or "").split("?")[0].split("#")[0].rstrip("/")
        if href in seen or href == base or SKIP_HINT.search(href):
            continue
        deeper = href.startswith(base + "/") and href[len(base):].count("/") == 1
        # Or a sibling carrying a game id, which is how several sites number
        # their scratch-offs without nesting them.
        numbered = (bool(re.search(r"/\d{3,6}(?:/|$)", href))
                    and INDEX_HINT.search(href) is not None)
        if deeper or numbered:
            seen.add(href)
            out.append(link["href"])
    return out[:limit]


def main():
    wanted = [c.upper() for c in sys.argv[1:]] or list(HOSTS)

    print(f"pass 1: scratch-off sections for {len(wanted)} states", file=sys.stderr)
    homes = {code: f"https://{HOSTS[code]}/" for code in wanted}
    found = parallel.evaluate_many(homes.values(), LINKS, settle_ms=3500,
                                   concurrency=8)

    indexes = {}
    for code, home in homes.items():
        for url in pick(found.get(home), INDEX_HINT, 2):
            indexes[url] = code
    print(f"pass 2: {len(indexes)} candidate index pages", file=sys.stderr)

    listed = parallel.evaluate_many(indexes, LINKS, settle_ms=5000, concurrency=8)

    games = {}
    per_state = {}
    for url, code in indexes.items():
        for game_url in children_of(url, listed.get(url), 4):
            if per_state.get(code, 0) >= 4 or game_url in games:
                continue
            games[game_url] = code
            per_state[code] = per_state.get(code, 0) + 1
    print(f"pass 3: {len(games)} game pages", file=sys.stderr)

    pages = parallel.evaluate_many(games, TABLES, settle_ms=6000, concurrency=8)

    report = {}
    for url, code in games.items():
        payload = pages.get(url) or {}
        tiers = scrape.tiers_from_table(payload.get("tables") or "")
        # Rankable means every tier carries both counts; a tier list with only
        # remaining counts parses to nothing, which is the honest answer.
        usable = [t for t in tiers if t.get("total") and t.get("remaining") is not None]
        entry = report.setdefault(code, {"best": 0, "pages": []})
        entry["pages"].append({"url": url, "tiers": len(tiers),
                               "usable": len(usable),
                               "title": payload.get("title") or ""})
        entry["best"] = max(entry["best"], len(usable))

    Path("scratchprobe.json").write_text(json.dumps(report, indent=1))

    print(f"\n{'ST':<4}{'tiers':>6}  page")
    ranked = sorted(report.items(), key=lambda kv: -kv[1]["best"])
    for code, entry in ranked:
        best = max(entry["pages"], key=lambda p: p["usable"])
        mark = "✓" if entry["best"] >= 3 else " "
        print(f"{code:<4}{entry['best']:>6} {mark} {best['url'][:78]}")
    winners = [c for c, e in report.items() if e["best"] >= 3]
    print(f"\n{len(winners)} states with a usable prize table: "
          f"{' '.join(sorted(winners))}", file=sys.stderr)


if __name__ == "__main__":
    main()
