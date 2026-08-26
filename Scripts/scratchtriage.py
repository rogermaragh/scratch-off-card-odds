#!/usr/bin/env python3
"""Work out *why* a state's scratch-off prizes cannot be read, not just that.

The previous probe answered one question -- did `tiers_from_table` return
anything -- and collapsed every kind of failure into the same zero. That is
useless for deciding what to do next, because the failures are not alike:

  TABLELESS   the counts are on the page, in divs or list items rather than a
              <table>. The reader is table-only, so it sees nothing. Fixing
              this fixes every state in the category at once.
  PDF         the counts are published as a document, usually called something
              like "remaining prizes". Nothing to scrape until it is read.
  API         the page fetches its prizes as JSON. The Florida shape.
  TOP-ONLY    the state publishes only its top prizes remaining, with no
              original counts. Genuinely unrankable -- there is nothing to
              divide, and no amount of parsing invents it.
  NO-GAME     we never reached a game page, so nothing has been learned about
              the state at all. A probe fault, not a state fault.

The distinction that matters most is the last one. Three times now a sweep has
reported that most states publish nothing, and three times the sweep was what
was broken.

    .venv/bin/python Scripts/scratchtriage.py [ST ...]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scrape  # noqa: E402
from parallel import UA  # noqa: E402

HOSTS = {
    "AR": "www.arkansasscholarshiplottery.com", "CO": "www.coloradolottery.com",
    "DE": "www.lottery.delaware.gov", "FL": "floridalottery.com",
    "GA": "www.galottery.com", "IA": "ialottery.com",
    "ID": "www.idaholottery.com", "IL": "www.illinoislottery.com",
    "KS": "playonkansas.com", "KY": "www.kylottery.com",
    "MA": "www.masslottery.com", "ME": "www.mainelottery.com",
    "MN": "www.mnlottery.com", "MT": "montanalottery.com",
    "ND": "www.lottery.nd.gov", "NE": "nelottery.com",
    "NH": "www.nhlottery.com", "NJ": "www.njlottery.com",
    "NY": "nylottery.ny.gov", "OH": "www.ohiolottery.com",
    "OR": "www.oregonlottery.org", "PA": "www.palottery.pa.gov",
    "SD": "lottery.sd.gov", "TN": "www.tnlottery.com",
    "TX": "www.texaslottery.com", "VT": "vtlottery.com",
    "WI": "wilottery.com", "WV": "wvlottery.com", "WY": "wyolotto.com",
}

INDEX = re.compile(r"scratch|instant", re.I)
SKIP = re.compile(r"signup|sign-?in|login|register|forum|responsible|how-?to|"
                  r"faq|winner|news|espanol|/draw|promotion|second-?chance", re.I)
REMAINING = re.compile(r"remaining|unclaimed|prizes left|left to win", re.I)
PRIZEISH = re.compile(r'"(?:\w*)(?:prize|remaining|unclaimed|tier)\w*"\s*:', re.I)
NOISE = re.compile(r"(google|facebook|doubleclick|analytics|gtm|hotjar|adobe|"
                   r"onetrust|recaptcha|fonts\.|\.css|\.png|\.jpe?g|\.svg|"
                   r"\.woff|\.gif|cookie|sentry|\.js(\?|$))", re.I)

SURVEY = """
() => {
  const text = (document.body.innerText || '').replace(/\\s+/g, ' ');
  const pdfs = [...document.querySelectorAll('a')]
    .map(a => a.href || '')
    .filter(h => /\\.pdf/i.test(h) &&
                 /remain|unclaim|prize|odds|inventory/i.test(h))
    .slice(0, 4);
  // How many numbers sit next to the word "remaining" outside any table --
  // the signature of counts rendered as divs.
  const cells = [...document.querySelectorAll('div,li,span,dd,td')]
    .filter(e => e.children.length === 0 &&
                 /^\\$?[\\d,]{1,12}$/.test((e.textContent || '').trim())).length;
  return {
    tables: [...document.querySelectorAll('table')]
              .map(t => t.outerHTML).join('\\n').slice(0, 160000),
    tableCount: document.querySelectorAll('table').length,
    text: text.slice(0, 6000),
    hasRemaining: /remaining|unclaimed|prizes left/i.test(text),
    numericCells: cells,
    pdfs: pdfs,
    h1: [...document.querySelectorAll('h1')]
          .map(e => (e.textContent || '').trim().slice(0, 60)).slice(0, 4),
    url: location.href
  };
}
"""

LINKS = """
() => [...document.querySelectorAll('a')].map(a => a.href)
  .filter(h => h && h.startsWith('http')).slice(0, 600)
"""


async def survey(browser, url, script, settle, capture=False):
    context = await browser.new_context(user_agent=UA,
                                        viewport={"width": 1400, "height": 1800})
    payloads = []
    if capture:
        async def on_response(response):
            if NOISE.search(response.url):
                return
            try:
                body = await response.text()
            except Exception:  # noqa: BLE001
                return
            if len(body) > 200 and PRIZEISH.search(body):
                payloads.append({"url": response.url, "bytes": len(body)})
        context.on("response", lambda r: asyncio.ensure_future(on_response(r)))

    page = await context.new_page()
    try:
        await page.goto(url, timeout=40000, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=11000)
        except Exception:  # noqa: BLE001
            pass
        await page.wait_for_timeout(settle)
        result = await page.evaluate(script)
        if isinstance(result, dict):
            result["api"] = payloads[:3]
        return result
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__}
    finally:
        await page.close()
        await context.close()


def classify(page):
    """Which of the five failures this is."""
    if not page or page.get("error"):
        return "NO-GAME", page.get("error", "no result") if page else "no result"

    tiers = scrape.tiers_from_table(page.get("tables") or "")
    usable = [t for t in tiers
              if t.get("total") and t.get("remaining") is not None]
    if usable:
        return "OK", f"{len(usable)} tiers"

    text = page.get("text") or ""
    if page.get("pdfs"):
        return "PDF", page["pdfs"][0][:70]
    if page.get("api"):
        return "API", page["api"][0]["url"][:70]
    if tiers and not usable:
        return "TOP-ONLY", f"{len(tiers)} tiers, no original counts"
    if page.get("hasRemaining") and page.get("numericCells", 0) >= 8:
        return "TABLELESS", f"{page['numericCells']} numeric cells, " \
                            f"{page.get('tableCount', 0)} tables"
    if page.get("hasRemaining"):
        return "TOP-ONLY", "says remaining but few numbers"
    return "NO-GAME", (page.get("h1") or [""])[0][:40] or "no prize wording"


async def main():
    from playwright.async_api import async_playwright

    wanted = [c.upper() for c in sys.argv[1:]] or list(HOSTS)
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(6)

        async def find_game(code):
            """Home → scratch-off index → one game page."""
            async with gate:
                home = await survey(browser, f"https://{HOSTS[code]}/", LINKS, 3500)
                links = home if isinstance(home, list) else []
                indexes = [h for h in links
                           if INDEX.search(h) and not SKIP.search(h)][:2]
                for index_url in indexes:
                    listed = await survey(browser, index_url, LINKS, 5500)
                    if not isinstance(listed, list):
                        continue
                    base = index_url.split("?")[0].split("#")[0].rstrip("/")
                    for href in listed:
                        clean = href.split("?")[0].split("#")[0].rstrip("/")
                        if SKIP.search(clean) or clean == base:
                            continue
                        child = (clean.startswith(base + "/")
                                 and clean[len(base):].count("/") == 1)
                        numbered = re.search(r"/\d{3,6}(?:-|/|$)", clean)
                        if child or (numbered and INDEX.search(clean)):
                            page = await survey(browser, href, SURVEY, 7000,
                                                capture=True)
                            return code, href, page
                return code, indexes[0] if indexes else None, None

        results = await asyncio.gather(*(find_game(c) for c in wanted))
        await browser.close()

    report = {}
    for code, url, page in results:
        kind, detail = classify(page)
        report[code] = {"kind": kind, "detail": detail, "url": url}
        print(f"  {code}: {kind}", file=sys.stderr, flush=True)

    Path("scratchtriage.json").write_text(json.dumps(report, indent=1))

    order = ["OK", "TABLELESS", "API", "PDF", "TOP-ONLY", "NO-GAME"]
    print(f"\n{'ST':<4}{'verdict':<11} detail")
    for kind in order:
        for code, entry in sorted(report.items()):
            if entry["kind"] == kind:
                print(f"{code:<4}{kind:<11} {entry['detail']}")
    counts = {k: sum(1 for e in report.values() if e["kind"] == k) for k in order}
    print("\n" + "  ".join(f"{k}={v}" for k, v in counts.items() if v),
          file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
