#!/usr/bin/env python3
"""Work out each state's game-link pattern instead of guessing it.

Guessed regexes matched nothing for most states, which said more about the
guesses than the sites. This renders each index, groups every link by its
*shape* (digits -> #, slugs -> *), then actually opens a candidate of each
promising shape and checks whether a complete prize table comes back.

Output is per state: the winning URL pattern, or the reason there isn't one.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import Counter
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import UA  # noqa: E402
from scrape import tiers_from_table  # noqa: E402

INDEXES = {
    "AZ": "https://www.arizonalottery.com/scratch-offs",
    "MD": "https://www.mdlottery.com/scratch-offs",
    "MA": "https://www.masslottery.com/games/instant",
    "MN": "https://www.mnlottery.com/scratch-offs",
    "IL": "https://www.illinoislottery.com/scratch-offs",
    "KS": "https://www.kslottery.com/scratch-offs",
    "MI": "https://www.michiganlottery.com/scratchers",
    "FL": "https://www.flalottery.com/scratch-offs",
    "MT": "https://www.montanalottery.com/scratch",
    "NH": "https://www.nhlottery.com/games/scratch-offs",
    "CO": "https://www.coloradolottery.com/en/games/scratch/",
    "OH": "https://www.ohiolottery.com/games/scratch-offs",
    "CA": "https://www.calottery.com/scratchers",
    "WI": "https://wilottery.com/games/instant-games",
    "WV": "https://wvlottery.com/games/scratch-off/",
    "AR": "https://www.arkansasscholarshiplottery.com/games/scratch-off",
    "KY": "https://www.kylottery.com/scratch-offs",
    "DC": "https://dclottery.com/dc-scratchers",
    "OR": "https://www.oregonlottery.org/scratch-its",
    "CT": "https://www.ctlottery.org/scratch-offs",
}

SHAPE_DIGITS = re.compile(r"\d+")
NOISE = re.compile(
    r"(privacy|terms|contact|about|news|winner|retail|claim|responsib|espanol|"
    r"login|register|sitemap|accessib|faq|help|search|rss|feed|cookie|careers|"
    r"press|media|social|facebook|twitter|instagram|youtube)",
    re.I,
)


def shape(path):
    """/scratchers/1234/lucky-7  ->  /scratchers/#/*"""
    parts = []
    for seg in path.strip("/").split("/"):
        if not seg:
            continue
        if SHAPE_DIGITS.fullmatch(seg):
            parts.append("#")
        elif SHAPE_DIGITS.search(seg) and len(seg) > 3:
            parts.append("~")
        else:
            parts.append(seg if len(seg) <= 14 and "-" not in seg else "*")
    return "/" + "/".join(parts)


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


async def investigate(browser, code, index_url):
    context = await browser.new_context(
        user_agent=UA, viewport={"width": 1400, "height": 1800}, locale="en-US"
    )
    await context.route(
        re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
        lambda route: asyncio.ensure_future(route.abort()),
    )
    out = {"state": code, "index": index_url, "pattern": None, "tiers": 0, "note": ""}
    try:
        html = await load(context, index_url)
        if html.startswith("__ERROR__"):
            out["note"] = f"index {html[9:]}"
            return out

        if tiers_from_table(html):
            out.update(tiers=len(tiers_from_table(html)), pattern="(index page)",
                       note="full table on the index itself")
            return out

        root = re.match(r"https?://[^/]+", index_url).group(0)
        hrefs = re.findall(r'href="([^"#?]+)', html)
        buckets = {}
        for href in hrefs:
            if href.startswith("http") and root not in href:
                continue
            path = re.sub(r"https?://[^/]+", "", href)
            if not path.startswith("/") or NOISE.search(path):
                continue
            if len(path.strip("/").split("/")) < 2:
                continue
            buckets.setdefault(shape(path), []).append(path)

        ranked = sorted(buckets.items(), key=lambda kv: -len(kv[1]))
        # Prefer shapes that look like a game detail and appear many times.
        candidates = [
            (s, paths) for s, paths in ranked
            if len(paths) >= 4 and re.search(r"(scratch|instant|game|ticket)", s, re.I)
        ] or ranked[:3]

        out["shapes"] = [(s, len(p)) for s, p in ranked[:6]]
        for shp, paths in candidates[:3]:
            target = paths[0] if paths[0].startswith("http") else root + paths[0]
            detail = await load(context, target)
            if detail.startswith("__ERROR__"):
                continue
            tiers = tiers_from_table(detail)
            if len(tiers) >= 3:
                out.update(pattern=shp, tiers=len(tiers), note="ok", sample=target)
                return out
            if not out["note"]:
                headers = re.findall(r"<th[^>]*>(.*?)</th>", detail, re.S)[:6]
                out["note"] = (
                    f"{shp}: no tiers ["
                    + " | ".join(re.sub(r"<[^>]+>|\s+", " ", h).strip() for h in headers)[:70]
                    + "]"
                )
        if not out["note"]:
            out["note"] = f"no game-like link shape; saw {out.get('shapes')}"
        return out
    finally:
        await context.close()


async def main():
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(4)

        async def guarded(code, url):
            async with gate:
                res = await investigate(browser, code, url)
                print(f"{res['state']:<3} tiers={res['tiers']:<3} "
                      f"{res['pattern'] or '-':<22} {res['note'][:70]}",
                      file=sys.stderr, flush=True)
                return res

        results = await asyncio.gather(
            *(guarded(code, url) for code, url in INDEXES.items())
        )
        await browser.close()

    usable = [r for r in results if r["tiers"] >= 3]
    Path("linkfind_results.json").write_text(json.dumps(results, indent=1))
    print(f"\nUSABLE ({len(usable)}):")
    for r in usable:
        print(f"  {r['state']}: {r['pattern']} -> {r['tiers']} tiers  {r.get('sample','')}")


if __name__ == "__main__":
    asyncio.run(main())
