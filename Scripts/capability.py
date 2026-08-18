#!/usr/bin/env python3
"""Ask the only question that decides whether a state is usable.

Reaching a page is not the same as the page carrying what the ranking needs.
The value ratio requires, per prize tier, both the original number of prizes
and the number still unclaimed. Plenty of states publish only "top prizes
remaining", which looks like data and is useless for this.

For each state this follows one game link and reports how many complete tiers
come back.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import UA  # noqa: E402
from scrape import tiers_from_table  # noqa: E402

# state -> (index url, regex for a game link)
TARGETS = {
    "PA": ("https://www.palottery.state.pa.us/Scratch-Offs/Active-Games.aspx",
           r'href="(/Scratch-Offs/View-Scratch-Off\.aspx\?id=\d+)"'),
    "MT": ("https://www.montanalottery.com/en/view/games/scratch",
           r'href="(/en/view/games/scratch/[^"]+)"'),
    "ID": ("https://www.idaholottery.com/games/scratch-offs",
           r'href="(/games/scratch[^"]*/\d+[^"]*)"'),
    "NH": ("https://www.nhlottery.com/games/scratch-offs",
           r'href="(/games/scratch[^"]*/[^"]+)"'),
    "MI": ("https://www.michiganlottery.com/scratchers",
           r'href="(/scratch[^"]*/\d+[^"]*)"'),
    "FL": ("https://www.flalottery.com/scratch-offs",
           r'href="([^"]*scratch[^"]*game[^"]*\d+[^"]*)"'),
    "KS": ("https://www.kslottery.com/scratch-offs",
           r'href="([^"]*(?:instant|scratch)[^"]*/[^"]+)"'),
    "AZ": ("https://www.arizonalottery.com/scratch-offs",
           r'href="([^"]*scratch[^"]*/\d+[^"]*)"'),
    "MD": ("https://www.mdlottery.com/scratch-offs",
           r'href="([^"]*scratch-off[^"]*/[^"]+)"'),
    "MA": ("https://www.masslottery.com/games/instant",
           r'href="([^"]*instant[^"]*/[^"]+)"'),
    "MN": ("https://www.mnlottery.com/scratch-offs",
           r'href="([^"]*scratch[^"]*/[^"]+)"'),
    "IL": ("https://www.illinoislottery.com/scratch-offs",
           r'href="([^"]*scratch[^"]*/[^"]+)"'),
    "CO": ("https://www.coloradolottery.com/en/games/scratch/",
           r'href="(/en/games/scratch/[^"]+)"'),
    "OK": ("https://www.lottery.ok.gov/scratchers",
           r'href="([^"]*scratcher[^"]*/[^"]+)"'),
    "WV": ("https://wvlottery.com/games/scratch-off/",
           r'href="([^"]*scratch[^"]*/[^"]+)"'),
}


async def load(context, url, settle=1800):
    page = await context.new_page()
    try:
        await page.goto(url, timeout=25000, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(settle)
        return await page.content()
    except Exception as exc:  # noqa: BLE001
        return f"__ERROR__{type(exc).__name__}"
    finally:
        await page.close()


async def check(browser, code, index_url, link_re):
    context = await browser.new_context(
        user_agent=UA, viewport={"width": 1400, "height": 1400}, locale="en-US"
    )
    await context.route(
        re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
        lambda route: asyncio.ensure_future(route.abort()),
    )
    result = {"state": code, "tiers": 0, "note": ""}
    try:
        index = await load(context, index_url)
        if index.startswith("__ERROR__"):
            result["note"] = f"index {index[9:]}"
            return result

        # Some states put the full table on the index itself.
        index_tiers = tiers_from_table(index)
        if index_tiers:
            result.update(tiers=len(index_tiers), note="on index page")
            return result

        root = re.match(r"https?://[^/]+", index_url).group(0)
        links = re.findall(link_re, index)
        if not links:
            result["note"] = "no game links matched"
            return result

        target = links[0] if links[0].startswith("http") else root + links[0]
        detail = await load(context, target)
        if detail.startswith("__ERROR__"):
            result["note"] = f"detail {detail[9:]}"
            return result

        tiers = tiers_from_table(detail)
        headers = re.findall(r"<th[^>]*>(.*?)</th>", detail, re.S)[:6]
        result.update(
            tiers=len(tiers),
            note=("ok" if tiers else "no complete tiers: "
                  + " | ".join(re.sub(r"<[^>]+>|\s+", " ", h).strip() for h in headers)[:90]),
            sample=target,
        )
        return result
    finally:
        await context.close()


async def main():
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(4)

        async def guarded(code, cfg):
            async with gate:
                out = await check(browser, code, *cfg)
                print(f"{out['state']:<3} tiers={out['tiers']:<3} {out['note']}",
                      file=sys.stderr, flush=True)
                return out

        results = await asyncio.gather(
            *(guarded(code, cfg) for code, cfg in TARGETS.items())
        )
        await browser.close()

    usable = [r for r in results if r["tiers"] >= 3]
    print(json.dumps(results, indent=1))
    print(f"\nusable ({len(usable)}): {', '.join(r['state'] for r in usable)}")


if __name__ == "__main__":
    asyncio.run(main())
