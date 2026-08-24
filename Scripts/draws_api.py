#!/usr/bin/env python3
"""Watch what a winning-numbers page fetches, and look for a JSON results API.

DOM scraping failed across the board: markup differs everywhere and the useful
signal (a game name beside a group of numbers) is drowned out by nav menus.
But these pages render client-side, which means the numbers arrive over the
wire as data. Catching that request gives a stable endpoint instead of a
brittle selector -- and if several states share a vendor, one find covers many.

    .venv/bin/python Scripts/draws_api.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import UA  # noqa: E402

TARGETS = {
    "MI": "https://www.michiganlottery.com/results",
    "FL": "https://www.flalottery.com/winning-numbers",
    "MD": "https://www.mdlottery.com/winning-numbers",
    "SC": "https://www.sceducationlottery.com/winning-numbers",
    "VA": "https://www.valottery.com/results",
    "LA": "https://louisianalottery.com/winning-numbers",
    "ME": "https://www.mainelottery.com/lottery-results",
    "CO": "https://www.coloradolottery.com/en/winning-numbers/",
    "AZ": "https://www.arizonalottery.com/winning-numbers",
    "OH": "https://www.ohiolottery.com/winning-numbers",
    "IN": "https://www.hoosierlottery.com/winning-numbers",
    "KY": "https://www.kylottery.com/winning-numbers",
    "WA": "https://www.walottery.com/WinningNumbers",
    "MN": "https://www.mnlottery.com/winning-numbers",
    "DC": "https://dclottery.com/winning-numbers",
    "CT": "https://www.ctlottery.org/winning-numbers",
}

# Requests that clearly aren't results data.
NOISE = re.compile(
    r"(google|facebook|doubleclick|analytics|gtm|segment|hotjar|adobe|"
    r"cloudflare|recaptcha|fonts|\.css|\.js($|\?)|\.png|\.jpg|\.svg|\.woff)",
    re.I,
)
INTERESTING = re.compile(r"(draw|winning|number|result|game|jackpot)", re.I)


async def probe(browser, code, url):
    context = await browser.new_context(user_agent=UA,
                                        viewport={"width": 1400, "height": 1600})
    seen = []

    async def on_response(response):
        req_url = response.url
        if NOISE.search(req_url):
            return
        ctype = (response.headers or {}).get("content-type", "")
        if "json" not in ctype.lower():
            return
        try:
            body = await response.text()
        except Exception:  # noqa: BLE001
            return
        # Keep payloads that look like they carry drawn numbers.
        if len(body) < 60:
            return
        score = len(re.findall(r'"(?:numbers?|winningNumbers|drawDate|balls?)"',
                               body, re.I))
        if score or INTERESTING.search(req_url):
            seen.append({"url": req_url, "bytes": len(body), "hits": score,
                         "sample": body[:200]})

    context.on("response", lambda r: asyncio.ensure_future(on_response(r)))

    page = await context.new_page()
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(2500)
    except Exception as exc:  # noqa: BLE001
        return code, {"url": url, "error": type(exc).__name__, "apis": []}
    finally:
        await page.close()
        await context.close()

    seen.sort(key=lambda s: -s["hits"])
    return code, {"url": url, "apis": seen[:4]}


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(3)

        async def guarded(code, url):
            async with gate:
                code, data = await probe(browser, code, url)
                best = data["apis"][0]["hits"] if data.get("apis") else 0
                print(f"  {code}: {len(data.get('apis', []))} json responses, "
                      f"best hits={best}"
                      f"{' ERR=' + data['error'] if data.get('error') else ''}",
                      file=sys.stderr, flush=True)
                return code, data

        results = dict(await asyncio.gather(
            *(guarded(c, u) for c, u in TARGETS.items())
        ))
        await browser.close()

    Path("draws_api.json").write_text(json.dumps(results, indent=1))
    print(f"\n{'ST':<4}{'hits':>5}  endpoint")
    for code, data in sorted(results.items(),
                             key=lambda kv: -(kv[1]["apis"][0]["hits"]
                                              if kv[1].get("apis") else 0)):
        for api in data.get("apis", [])[:2]:
            if api["hits"]:
                print(f"{code:<4}{api['hits']:>5}  {api['url'][:96]}")


if __name__ == "__main__":
    asyncio.run(main())
