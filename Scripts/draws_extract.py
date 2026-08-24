#!/usr/bin/env python3
"""Extract real draw results, or prove a state doesn't publish them usably.

The first probe scored game-name mentions, which every nav menu inflates:
Louisiana looked like the best state in the country on the strength of its
menu bar. This asks a stricter question -- are there groups of ball-marked
elements, each near a game name and a date? -- and prints an actual sample so
the answer can be eyed rather than trusted.

    .venv/bin/python Scripts/draws_extract.py [ST ...]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import UA  # noqa: E402

# Elements whose class marks them as a drawn number.
BALL_RE = re.compile(
    r'<[a-z]+[^>]*class="[^"]*\b(?:ball|winning-number|number|result-number|'
    r'draw-number|num)\b[^"]*"[^>]*>\s*([0-9]{1,2})\s*<',
    re.I,
)
GAME_RE = re.compile(
    r"\b(Pick\s?\d|Cash\s?\d|Daily\s?\d|Play\s?\d|Match\s?\d|Fantasy\s?5|"
    r"Lucky\s?Day|Take\s?5|Win\s?4|Rolling\s?Cash|Classic\s?Lotto|Lotto\s?America|"
    r"Bonus\s?Match\s?5|Multi-?Match|Triple\s?Play|Super\s?Cash|Mega\s?Bucks|"
    r"Badger\s?5|Gimme\s?5|Wild\s?Money|Cash\s?Pop|Hit\s?5|Match\s?6|Lotto\s?47|"
    r"Easy\s?5|Lotto|Keno|Numbers|Big\s?4|Cash\s?5)\b",
    re.I,
)
DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+[A-Z][a-z]{2,8}\.?\s+\d{1,2}|"
    r"[A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4})\b"
)


def extract(html):
    """Group consecutive ball elements and label each group from nearby text."""
    matches = list(BALL_RE.finditer(html))
    groups, current = [], []
    for index, match in enumerate(matches):
        if current and match.start() - matches[index - 1].end() > 400:
            groups.append(current)
            current = []
        current.append(match)
    if current:
        groups.append(current)

    results = []
    for group in groups:
        if not 2 <= len(group) <= 20:
            continue
        numbers = [int(m.group(1)) for m in group]
        # Look back from the group for the game it belongs to, and a date.
        lead = html[max(0, group[0].start() - 1200):group[0].start()]
        lead_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", lead))
        game = None
        for m in GAME_RE.finditer(lead_text):
            game = m.group(0)
        date = None
        for m in DATE_RE.finditer(lead_text):
            date = m.group(0)
        if game:
            results.append({"game": re.sub(r"\s+", " ", game).title(),
                            "date": date, "numbers": numbers})
    return results


async def load(context, url, settle=1500):
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


async def main():
    from playwright.async_api import async_playwright

    probe = json.loads(Path("draws_probe.json").read_text())
    wanted = [c.upper() for c in sys.argv[1:]] or [
        c for c, r in probe.items() if r.get("url") and r.get("score", 0) >= 10
    ]

    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(4)
        out = {}

        async def run(code):
            async with gate:
                url = probe[code]["url"]
                context = await browser.new_context(
                    user_agent=UA, viewport={"width": 1400, "height": 1800}
                )
                await context.route(
                    re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
                    lambda route: asyncio.ensure_future(route.abort()),
                )
                try:
                    html = await load(context, url)
                    if html.startswith("__ERROR__"):
                        return code, {"url": url, "error": html[9:], "results": []}
                    found = extract(html)
                    return code, {"url": url, "results": found}
                finally:
                    await context.close()

        for code, data in await asyncio.gather(*(run(c) for c in wanted)):
            out[code] = data
            games = sorted({r["game"] for r in data["results"]})
            print(f"  {code}: {len(data['results'])} groups, games={games[:6]}"
                  f"{' ERR=' + data['error'] if data.get('error') else ''}",
                  file=sys.stderr, flush=True)
        await browser.close()

    Path("draws_extract.json").write_text(json.dumps(out, indent=1))

    print(f"\n{'ST':<4}{'draws':>6}  sample")
    usable = []
    for code, data in sorted(out.items(), key=lambda kv: -len(kv[1]["results"])):
        results = data["results"]
        if not results:
            continue
        usable.append(code)
        first = results[0]
        print(f"{code:<4}{len(results):>6}  {first['game']} "
              f"[{first['date'] or 'no date'}] {first['numbers']}")
    print(f"\nusable ({len(usable)}): {', '.join(usable)}")
    print(f"no extractable results: "
          f"{', '.join(c for c, d in out.items() if not d['results'])}")


if __name__ == "__main__":
    asyncio.run(main())
