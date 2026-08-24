#!/usr/bin/env python3
"""Look for results on each game's own page.

Wyoming's results were not on its winning-numbers page at all — that page is a
ticket checker — but each game's page carries its latest draw. That pattern is
common, and it is simpler than fighting search forms: find the game links, open
one, and look for a group of elements that are all small numbers.

    .venv/bin/python Scripts/pergame.py [ST ...]
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import UA  # noqa: E402

HOSTS = {
    "AR": "www.arkansasscholarshiplottery.com", "CA": "www.calottery.com",
    "CO": "www.coloradolottery.com", "CT": "www.ctlottery.org",
    "DC": "dclottery.com", "ID": "www.idaholottery.com",
    "IN": "www.hoosierlottery.com", "IA": "ialottery.com",
    "KS": "www.kslottery.com", "KY": "www.kylottery.com",
    "LA": "louisianalottery.com", "ME": "www.mainelottery.com",
    "MD": "www.mdlottery.com", "MN": "www.mnlottery.com",
    "MO": "www.molottery.com", "MT": "www.montanalottery.com",
    "MS": "www.mslotteryhome.com", "NE": "nelottery.com",
    "NM": "www.nmlottery.com", "ND": "www.lottery.nd.gov",
    "OR": "www.oregonlottery.org", "PA": "www.palottery.state.pa.us",
    "RI": "www.rilot.com", "SC": "www.sceducationlottery.com",
    "SD": "lottery.sd.gov", "TN": "www.tnlottery.com",
    "TX": "www.texaslottery.com", "VT": "vtlottery.com",
    "VA": "www.valottery.com", "WA": "www.walottery.com",
    "WV": "wvlottery.com", "WI": "wilottery.com", "DE": "www.lottery.delaware.gov",
}

# In-state game names worth opening. Multi-state games are already covered.
GAME_WORDS = (
    "pick", "cash", "daily", "play", "match", "fantasy", "lucky day", "lotto",
    "megabucks", "gimme", "badger", "supercash", "rolling", "classic",
    "triple", "weekly", "wild money", "hit 5", "numbers", "bonus match",
    "multi-match", "cowboy", "2by2", "jackpot", "win 4", "take 5", "money",
)

FIND_LINKS = """
() => [...document.querySelectorAll('a')]
  .map(a => ({href: a.href, text: (a.textContent||'').replace(/\\s+/g,' ').trim()}))
  .filter(l => l.href && /game|draw/i.test(l.href))
  .slice(0, 400)
"""

FIND_BALLS = """
() => {
  const isNum = t => /^\\d{1,2}$/.test((t||'').trim());
  const rows = [];
  document.querySelectorAll('*').forEach(el => {
    const kids = [...el.children];
    if (kids.length < 3 || kids.length > 22) return;
    const nums = kids.filter(k => isNum(k.textContent));
    if (nums.length < 3 || nums.length < kids.length - 1) return;
    rows.push({cls: (el.className||'').toString().slice(0,44),
               nums: nums.map(n => n.textContent.trim())});
  });
  return rows.slice(0, 4);
}
"""


async def load(page, url, settle=4000):
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(settle)
        return True
    except Exception:  # noqa: BLE001
        return False


async def probe(browser, code, host):
    context = await browser.new_context(user_agent=UA,
                                        viewport={"width": 1400, "height": 1400})
    page = await context.new_page()
    out = {"state": code, "hits": []}
    try:
        if not await load(page, f"https://{host}/", settle=2500):
            return out
        links = await page.evaluate(FIND_LINKS) or []

        # Keep links whose text names an in-state game, best guess first.
        candidates, seen = [], set()
        for link in links:
            text = (link["text"] or "").lower()
            if not text or len(text) > 40:
                continue
            if any(word in text for word in GAME_WORDS):
                if link["href"] not in seen:
                    seen.add(link["href"])
                    candidates.append(link)

        for link in candidates[:6]:
            if not await load(page, link["href"]):
                continue
            rows = await page.evaluate(FIND_BALLS) or []
            if rows:
                out["hits"].append({"game": link["text"], "url": link["href"],
                                    "rows": rows})
            if len(out["hits"]) >= 3:
                break
    finally:
        await page.close()
        await context.close()
    return out


async def main():
    from playwright.async_api import async_playwright

    wanted = [c.upper() for c in sys.argv[1:]] or list(HOSTS)
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(4)

        async def guarded(code):
            async with gate:
                out = await probe(browser, code, HOSTS[code])
                print(f"  {code}: {len(out['hits'])} game pages with numbers",
                      file=sys.stderr, flush=True)
                return out

        results = await asyncio.gather(*(guarded(c) for c in wanted))
        await browser.close()

    Path("pergame.json").write_text(json.dumps(results, indent=1))
    print(f"\n{'ST':<4}  game / numbers")
    for r in sorted(results, key=lambda r: -len(r["hits"])):
        for hit in r["hits"][:3]:
            first = hit["rows"][0]
            print(f"{r['state']:<4}  {hit['game'][:26]:<28} {first['nums']}")


if __name__ == "__main__":
    asyncio.run(main())
