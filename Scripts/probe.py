#!/usr/bin/env python3
"""Score candidate state lottery sites for scrapeability.

Reports whether an index page is reachable, whether it exposes per-game links,
and whether the raw HTML already carries prize/remaining data (meaning no
headless browser is needed).
"""

import concurrent.futures
import re
import sys
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

CANDIDATES = {
    "AZ": "https://www.arizonalottery.com/scratchers/",
    "CO": "https://www.coloradolottery.com/en/games/scratch/",
    "CT": "https://www.ctlottery.org/ScratchGames",
    "DC": "https://dclottery.com/dc-scratchers",
    "IA": "https://ialottery.com/Pages/ScratchGames/ScratchGames.aspx",
    "ID": "https://www.idcholottery.com/games/scratch",
    "KY": "https://www.kylottery.com/apps/scratch_offs/index.html",
    "ME": "https://www.mainelottery.com/games/instant_games.html",
    "MN": "https://www.mnlottery.com/games/scratch-games",
    "NE": "https://nelottery.com/homeapp/ScratchGames",
    "NH": "https://www.nhlottery.com/Scratch-Tickets",
    "NJ": "https://www.njlottery.com/en-us/scratch-offs.html",
    "NM": "https://www.nmlottery.com/games/scratchers/",
    "OK": "https://www.lottery.ok.gov/scratchers",
    "OR": "https://www.oregonlottery.org/scratch-its/",
    "RI": "https://www.rilot.com/en/games/instant-games.html",
    "SC": "https://www.sceducationlottery.com/Games/InstantGames",
    "TN": "https://www.tnlottery.com/instant-games/",
    "VT": "https://vtlottery.com/games/scratch",
    "WA": "https://www.walottery.com/ScratchGames/",
    "WV": "https://wvlottery.com/games/scratch-offs/",
    "WI": "https://wilottery.com/games/scratch-games",
}


def probe(item):
    code, url = item
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        return code, f"HTTP {exc.code}", 0, 0, 0
    except Exception as exc:  # noqa: BLE001 - probe should never crash the run
        return code, type(exc).__name__, 0, 0, 0

    # Signals that the payload already contains game data server-side.
    links = len(set(re.findall(r'href="[^"]*(?:scratch|instant|game)[^"]*/\d+', html, re.I)))
    remaining = len(re.findall(r"remaining", html, re.I))
    tables = html.lower().count("<table")
    return code, f"HTTP {status} {len(html)//1024}KB", links, remaining, tables


def main():
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for result in pool.map(probe, CANDIDATES.items()):
            rows.append(result)

    rows.sort(key=lambda r: (r[3] + r[4] * 5 + r[2] * 2), reverse=True)
    print(f"{'ST':<4}{'status':<18}{'links':>6}{'remaining':>11}{'tables':>8}")
    for code, status, links, remaining, tables in rows:
        print(f"{code:<4}{status:<18}{links:>6}{remaining:>11}{tables:>8}")
    print("\nHigh 'remaining' or 'tables' with HTTP 200 = worth a real look.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
