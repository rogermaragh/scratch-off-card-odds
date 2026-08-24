#!/usr/bin/env python3
"""Watch what a results page fetches, the way Florida's adapter does.

Nine states render nothing a DOM detector can read. That does not mean they
publish nothing -- Florida looks exactly the same and serves its results from
an Azure gateway that 401s without a subscription key the page itself carries.
Letting the page make its own request and reading the answer needs no key and
no selector.

Two differences from the earlier sweep, which found little and concluded
wrongly. It only kept responses whose content-type declared JSON, and it
loaded one guessed URL per state without checking the URL resolved. This
follows the site's own navigation to its results page, records the HTTP status
so "found nothing" and "never loaded" stay distinguishable, and keeps any
response whose *shape* looks like draws regardless of what it claims to be.

    .venv/bin/python Scripts/netprobe.py [ST ...]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parallel import UA  # noqa: E402

HOSTS = {
    "DE": "www.lottery.delaware.gov", "IA": "ialottery.com",
    "MT": "www.montanalottery.com", "ND": "www.lottery.nd.gov",
    "NM": "www.nmlottery.com", "OR": "www.oregonlottery.org",
    "TN": "www.tnlottery.com", "VA": "www.valottery.com",
    "WV": "wvlottery.com", "KS": "www.kslottery.com",
    "NE": "nelottery.com", "CT": "www.ctlottery.org",
    "LA": "louisianalottery.com", "VT": "vtlottery.com",
}

NAV = re.compile(r"winning\s*numbers|past\s*results|draw\s*results|results", re.I)
NOISE = re.compile(
    r"(google|facebook|doubleclick|analytics|gtm|segment|hotjar|adobe|onetrust|"
    r"recaptcha|fonts\.|\.css|\.png|\.jpe?g|\.svg|\.woff|\.gif|cookie|sentry)", re.I)

# Draw data looks like dates sitting near groups of small integers, whatever
# the keys are called. Scoring on shape rather than on hoped-for key names is
# what lets this find a feed nobody documented.
DATE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}")
ARRAY = re.compile(r"\[\s*\d{1,2}\s*(?:,\s*\d{1,2}\s*){1,19}\]")
KEYS = re.compile(r'"\w*(?:number|ball|digit|pick|result|draw)\w*"\s*:', re.I)


def shape_score(text):
    if not text or len(text) < 120:
        return 0
    return (min(len(DATE.findall(text)), 40)
            + len(ARRAY.findall(text)) * 4
            + min(len(KEYS.findall(text)) * 2, 60))


async def probe(browser, code, host):
    context = await browser.new_context(
        user_agent=UA, viewport={"width": 1400, "height": 1600}, locale="en-US")
    hits = []

    async def on_response(response):
        if NOISE.search(response.url):
            return
        try:
            body = await response.text()
        except Exception:  # noqa: BLE001
            return
        score = shape_score(body)
        if score >= 15:
            hits.append({"url": response.url, "status": response.status,
                         "score": score, "bytes": len(body),
                         "sample": body[:300]})

    context.on("response", lambda r: asyncio.ensure_future(on_response(r)))
    page = await context.new_page()
    out = {"state": code, "status": None, "results_url": None, "hits": []}
    try:
        response = await page.goto(f"https://{host}/", timeout=35000,
                                   wait_until="domcontentloaded")
        out["status"] = response.status if response else None
        try:
            await page.wait_for_load_state("networkidle", timeout=9000)
        except Exception:  # noqa: BLE001
            pass

        target = await page.evaluate(
            """() => {
                 const re = /winning\\s*numbers|past\\s*results|draw\\s*results/i;
                 const a = [...document.querySelectorAll('a')]
                   .find(a => re.test(a.textContent || ''));
                 return a ? a.href : null;
               }""")
        if target:
            out["results_url"] = target
            response = await page.goto(target, timeout=35000,
                                       wait_until="domcontentloaded")
            out["status"] = response.status if response else out["status"]
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(5000)
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
    finally:
        await page.close()
        await context.close()

    seen, unique = set(), []
    for hit in sorted(hits, key=lambda h: -h["score"]):
        key = hit["url"].split("?")[0]
        if key not in seen:
            seen.add(key)
            unique.append(hit)
    out["hits"] = unique[:4]
    return out


async def main():
    from playwright.async_api import async_playwright

    wanted = [c.upper() for c in sys.argv[1:]] or list(HOSTS)
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(6)

        async def guarded(code):
            async with gate:
                out = await probe(browser, code, HOSTS[code])
                print(f"  {code}: status={out['status']} "
                      f"hits={len(out['hits'])} {out.get('error','')}",
                      file=sys.stderr, flush=True)
                return out

        results = await asyncio.gather(*(guarded(c) for c in wanted))
        await browser.close()

    Path("netprobe.json").write_text(json.dumps(results, indent=1))
    print(f"\n{'ST':<4}{'score':>6}{'KB':>6}  endpoint")
    for r in sorted(results, key=lambda r: -(r["hits"][0]["score"] if r["hits"] else 0)):
        if not r["hits"]:
            print(f"{r['state']:<4}{'-':>6}{'':>6}  status={r['status']} "
                  f"{r.get('error', 'nothing matched')}  {r['results_url'] or ''}")
        for hit in r["hits"][:2]:
            print(f"{r['state']:<4}{hit['score']:>6}{hit['bytes']//1024:>6}  "
                  f"{hit['url'][:88]}")


if __name__ == "__main__":
    asyncio.run(main())
