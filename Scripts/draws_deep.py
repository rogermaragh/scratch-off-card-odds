#!/usr/bin/env python3
"""A results sweep that does not assume how a state serves its data.

The previous pass looked only at network responses whose content-type was
JSON, and loaded one guessed URL per state without checking it resolved. Both
limits were real: Washington's working adapter reads JSON embedded in the page
HTML, which that pass could not see by construction, and several of the URLs
almost certainly 404'd so no request ever fired.

This one:
  * follows the site's own nav to the results page instead of guessing once
  * records the HTTP status, so "nothing found" and "page never loaded" differ
  * captures every response, not only declared JSON
  * scans rendered HTML for embedded JSON blobs (the Washington shape)
  * scores on the actual shape of results -- date near a group of numbers --
    rather than on hoped-for key names

    .venv/bin/python Scripts/draws_deep.py [ST ...]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import UA  # noqa: E402

HOSTS = {
    "AR": "www.arkansasscholarshiplottery.com", "CA": "www.calottery.com",
    "CO": "www.coloradolottery.com", "CT": "www.ctlottery.org",
    "DE": "www.lottery.delaware.gov", "DC": "dclottery.com",
    "GA": "www.galottery.com", "ID": "www.idaholottery.com",
    "IL": "www.illinoislottery.com", "IN": "www.hoosierlottery.com",
    "IA": "ialottery.com", "KS": "www.kslottery.com", "KY": "www.kylottery.com",
    "LA": "louisianalottery.com", "ME": "www.mainelottery.com",
    "MD": "www.mdlottery.com", "MN": "www.mnlottery.com",
    "MS": "www.mslotteryhome.com", "MO": "www.molottery.com",
    "MT": "www.montanalottery.com", "NE": "www.nelottery.com",
    "NH": "www.nhlottery.com", "NJ": "www.njlottery.com",
    "NM": "www.nmlottery.com", "ND": "www.lottery.nd.gov",
    "OH": "www.ohiolottery.com", "OK": "www.lottery.ok.gov",
    "OR": "www.oregonlottery.org", "PA": "www.palottery.state.pa.us",
    "RI": "www.rilot.com", "SC": "www.sceducationlottery.com",
    "SD": "lottery.sd.gov", "TN": "www.tnlottery.com", "TX": "www.texaslottery.com",
    "VT": "vtlottery.com", "VA": "www.valottery.com", "WV": "wvlottery.com",
    "WI": "wilottery.com", "WY": "wyolotto.com",
}

# Link text that leads to a results page on almost every lottery site.
NAV_RE = re.compile(r"winning\s*numbers|past\s*results|draw\s*results|results", re.I)

NOISE = re.compile(
    r"(google|facebook|doubleclick|analytics|gtm|segment|hotjar|adobe|onetrust|"
    r"recaptcha|fonts\.|\.css|\.png|\.jpe?g|\.svg|\.woff|\.gif|cookie)", re.I)

# A results payload looks like dates sitting near groups of small integers.
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")
NUMS_RE = re.compile(r"\[\s*\d{1,2}\s*(?:,\s*\d{1,2}\s*){1,19}\]")
PAIR_RE = re.compile(r'"(?:\w*)(?:number|ball|digit|pick|result)\w*"\s*:', re.I)


def shape_score(text: str) -> int:
    """How much this looks like draw results, independent of key names."""
    if not text or len(text) < 120:
        return 0
    dates = len(DATE_RE.findall(text))
    arrays = len(NUMS_RE.findall(text))
    keys = len(PAIR_RE.findall(text))
    return min(dates, 40) + arrays * 4 + keys * 2


def embedded_blobs(html: str):
    """JSON assigned into the page — the shape Washington uses."""
    out = []
    for match in re.finditer(r"JSON\.parse\(\s*'(.{200,}?)'\s*\)", html, re.S):
        try:
            out.append(match.group(1).encode().decode("unicode_escape"))
        except Exception:  # noqa: BLE001
            out.append(match.group(1))
    for match in re.finditer(
        r"(?:window\.[\w.]+|var\s+\w+|const\s+\w+|let\s+\w+)\s*=\s*(\[.{200,}?\]|\{.{200,}?\})\s*[;\n]",
        html, re.S,
    ):
        out.append(match.group(1))
    for match in re.finditer(
        r'<script[^>]+type="application/json"[^>]*>(.{200,}?)</script>', html, re.S
    ):
        out.append(match.group(1))
    return out


async def sweep(browser, code, host):
    context = await browser.new_context(
        user_agent=UA, viewport={"width": 1400, "height": 1600}, locale="en-US")
    await context.route(
        re.compile(r"\.(png|jpe?g|gif|webp|woff2?|ttf|mp4)(\?|$)"),
        lambda route: asyncio.ensure_future(route.abort()))

    found = []

    async def on_response(response):
        url = response.url
        if NOISE.search(url):
            return
        try:
            body = await response.text()
        except Exception:  # noqa: BLE001
            return
        score = shape_score(body)
        if score >= 12:
            found.append({"kind": "network", "url": url, "score": score,
                          "bytes": len(body), "sample": body[:220]})

    context.on("response", lambda r: asyncio.ensure_future(on_response(r)))
    page = await context.new_page()
    out = {"state": code, "status": None, "results_url": None, "hits": []}

    try:
        response = await page.goto(f"https://{host}/", timeout=30000,
                                   wait_until="domcontentloaded")
        out["status"] = response.status if response else None
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:  # noqa: BLE001
            pass

        # Follow the site's own link to results rather than guessing a path.
        target = None
        for link in await page.locator("a").all():
            try:
                text = (await link.inner_text(timeout=500) or "").strip()
                href = await link.get_attribute("href")
            except Exception:  # noqa: BLE001
                continue
            if href and NAV_RE.search(text or ""):
                target = href if href.startswith("http") else f"https://{host}{href}"
                break

        if target:
            out["results_url"] = target
            response = await page.goto(target, timeout=30000,
                                       wait_until="domcontentloaded")
            out["status"] = response.status if response else out["status"]
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(3000)

        html = await page.content()
        for blob in embedded_blobs(html):
            score = shape_score(blob)
            if score >= 12:
                found.append({"kind": "embedded", "url": out["results_url"],
                              "score": score, "bytes": len(blob),
                              "sample": blob[:220]})
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
    finally:
        await page.close()
        await context.close()

    found.sort(key=lambda f: -f["score"])
    out["hits"] = found[:3]
    return out


async def main():
    from playwright.async_api import async_playwright

    wanted = [c.upper() for c in sys.argv[1:]] or list(HOSTS)
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(4)

        async def guarded(code):
            async with gate:
                out = await sweep(browser, code, HOSTS[code])
                top = out["hits"][0]["score"] if out["hits"] else 0
                print(f"  {code}: status={out['status']} best={top} "
                      f"{out.get('error','')}", file=sys.stderr, flush=True)
                return out

        results = await asyncio.gather(*(guarded(c) for c in wanted))
        await browser.close()

    Path("draws_deep.json").write_text(json.dumps(results, indent=1))
    print(f"\n{'ST':<4}{'score':>6}  {'kind':<9} source")
    for r in sorted(results, key=lambda r: -(r["hits"][0]["score"] if r["hits"] else 0)):
        if not r["hits"]:
            print(f"{r['state']:<4}{'-':>6}  status={r['status']} {r.get('error','')}")
            continue
        hit = r["hits"][0]
        print(f"{r['state']:<4}{hit['score']:>6}  {hit['kind']:<9} {(hit['url'] or '')[:78]}")


if __name__ == "__main__":
    asyncio.run(main())
