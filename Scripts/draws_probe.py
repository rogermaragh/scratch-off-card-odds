#!/usr/bin/env python3
"""Find each state's winning-numbers page and see what it actually carries.

Draw results are a much easier target than scratch-off prize tables: a game
name, a date and a handful of numbers, with no inventory to reconcile. This
sweeps every state without in-state draw coverage, tries plain HTTP first and
falls back to a browser, and reports which in-state games it can see.

    .venv/bin/python Scripts/draws_probe.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import UA  # noqa: E402

# Every jurisdiction except NY (open data) and NC (already scraped).
DOMAINS = {
    "AZ": "www.arizonalottery.com", "AR": "www.arkansasscholarshiplottery.com",
    "CA": "www.calottery.com", "CO": "www.coloradolottery.com",
    "CT": "www.ctlottery.org", "DE": "www.lottery.delaware.gov",
    "DC": "dclottery.com", "FL": "www.flalottery.com", "GA": "www.galottery.com",
    "ID": "www.idaholottery.com", "IL": "www.illinoislottery.com",
    "IN": "www.hoosierlottery.com", "IA": "ialottery.com",
    "KS": "www.kslottery.com", "KY": "www.kylottery.com",
    "LA": "louisianalottery.com", "ME": "www.mainelottery.com",
    "MD": "www.mdlottery.com", "MA": "www.masslottery.com",
    "MI": "www.michiganlottery.com", "MN": "www.mnlottery.com",
    "MS": "www.mslotteryhome.com", "MO": "www.molottery.com",
    "MT": "www.montanalottery.com", "NE": "www.nelottery.com",
    "NH": "www.nhlottery.com", "NJ": "www.njlottery.com",
    "NM": "www.nmlottery.com", "ND": "www.lottery.nd.gov",
    "OH": "www.ohiolottery.com", "OK": "www.lottery.ok.gov",
    "OR": "www.oregonlottery.org", "PA": "www.palottery.state.pa.us",
    "RI": "www.rilot.com", "SC": "www.sceducationlottery.com",
    "SD": "lottery.sd.gov", "TN": "www.tnlottery.com", "TX": "www.texaslottery.com",
    "VT": "vtlottery.com", "VA": "www.valottery.com", "WA": "www.walottery.com",
    "WV": "wvlottery.com", "WI": "wilottery.com", "WY": "wyolotto.com",
}

PATHS = [
    "/winning-numbers", "/results", "/winning-numbers/", "/draw-games",
    "/games/winning-numbers", "/winningnumbers", "/lottery-results",
]

# In-state game families. Multi-state games are excluded: they are already
# covered and would make every page look like a hit.
GAME_RE = re.compile(
    r"\b("
    r"Pick\s?\d|Cash\s?\d|Daily\s?\d|Play\s?\d|Match\s?\d|Fantasy\s?5|"
    r"Lucky\s?Day|Take\s?5|Win\s?4|Big\s?4|Rolling\s?Cash|Classic\s?Lotto|"
    r"Weekly\s?Grand|Bonus\s?Match|Multi-?Match|Triple\s?Play|Super\s?Cash|"
    r"Mega\s?Bucks|Badger\s?5|Gimme\s?5|Wild\s?Money|Quick\s?Draw|Keno|"
    r"Cash\s?Pop|Lotto\s?America|2by2|Hit\s?5|Match\s?6|Numbers\s?Game|"
    r"Lotto\s?47|Fantasy\s?Five|Cash4Life"
    r")\b",
    re.I,
)
EXCLUDE = re.compile(r"powerball|mega\s?millions|millionaire\s?for\s?life", re.I)


def visible(html):
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


def assess(html):
    text = visible(html)
    games = sorted({re.sub(r"\s+", " ", m.group(0)).title() for m in GAME_RE.finditer(text)})
    # Ball markup is a strong hint the numbers are in the DOM, not an image.
    balls = len(re.findall(r'class="[^"]*\b(?:ball|number|winning-number)\b', html, re.I))
    dates = len(re.findall(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+[A-Z][a-z]{2}", text))
    return {
        "games": games,
        "balls": balls,
        "dates": dates,
        "score": len(games) * 4 + min(balls, 60) // 2 + min(dates, 20),
    }


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def probe_http(host):
    best = {"score": -1, "url": None, "games": [], "via": "http"}
    for path in PATHS:
        url = f"https://{host}{path}"
        try:
            html = http_get(url)
        except Exception:  # noqa: BLE001
            continue
        stats = assess(html)
        if stats["score"] > best["score"]:
            best = {**stats, "url": url, "via": "http"}
        if stats["score"] >= 25:
            break
    return best


async def probe_browser(browser, host):
    context = await browser.new_context(
        user_agent=UA, viewport={"width": 1400, "height": 1600}, locale="en-US"
    )
    await context.route(
        re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
        lambda route: asyncio.ensure_future(route.abort()),
    )
    best = {"score": -1, "url": None, "games": [], "via": "browser"}
    try:
        for path in PATHS[:4]:
            page = await context.new_page()
            try:
                await page.goto(f"https://{host}{path}", timeout=20000,
                                wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:  # noqa: BLE001
                    pass
                await page.wait_for_timeout(900)
                stats = assess(await page.content())
                if stats["score"] > best["score"]:
                    best = {**stats, "url": f"https://{host}{path}", "via": "browser"}
                if stats["score"] >= 25:
                    break
            except Exception:  # noqa: BLE001
                continue
            finally:
                await page.close()
    finally:
        await context.close()
    return best


async def main():
    from playwright.async_api import async_playwright

    # Plain HTTP first: it is far cheaper and works for a good share of states.
    http_results = {}
    loop = asyncio.get_running_loop()
    tasks = {
        code: loop.run_in_executor(None, probe_http, host)
        for code, host in DOMAINS.items()
    }
    for code, task in tasks.items():
        http_results[code] = await task
        print(f"  http {code}: {http_results[code]['score']}", file=sys.stderr, flush=True)

    weak = [c for c, r in http_results.items() if r["score"] < 12]
    print(f"\nfalling back to browser for {len(weak)}: {', '.join(weak)}\n",
          file=sys.stderr)

    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(4)

        async def guarded(code):
            async with gate:
                out = await probe_browser(browser, DOMAINS[code])
                print(f"  browser {code}: {out['score']}", file=sys.stderr, flush=True)
                return code, out

        for code, out in await asyncio.gather(*(guarded(c) for c in weak)):
            if out["score"] > http_results[code]["score"]:
                http_results[code] = out
        await browser.close()

    ranked = sorted(http_results.items(), key=lambda kv: -kv[1]["score"])
    Path("draws_probe.json").write_text(json.dumps(dict(ranked), indent=1))

    print(f"\n{'ST':<4}{'score':>6}{'via':>9}  games found")
    for code, r in ranked:
        if r["score"] < 4:
            continue
        print(f"{code:<4}{r['score']:>6}{r['via']:>9}  {', '.join(r['games'][:7])}")
    print(f"\nnothing usable: "
          f"{', '.join(c for c, r in ranked if r['score'] < 4)}")


if __name__ == "__main__":
    asyncio.run(main())
