#!/usr/bin/env python3
"""Concurrent browser sweep over every state without an adapter.

The sequential version took over half an hour and gave no visibility. This one
runs several pages at once, caps every wait, and appends each result to a JSONL
file as it lands so progress is observable and a crash loses nothing.

    .venv/bin/python Scripts/browse_probe.py [out.jsonl]
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import DOMAINS, UA  # noqa: E402

PATHS = ["/scratch-offs", "/scratchers", "/games/scratch-offs", "/scratch"]
CONCURRENCY = 4
NAV_TIMEOUT = 20000
IDLE_TIMEOUT = 5000
SETTLE_MS = 700
GOOD_ENOUGH = 60


def score(html: str) -> dict:
    remaining = len(re.findall(r"remaining|unclaimed", html, re.I))
    tables = html.lower().count("<table")
    money = len(re.findall(r"\$[\d,]{3,}", html))
    links = len(
        set(re.findall(r'href="[^"]*(?:scratch|instant|game)[^"]*[/=]\d+', html, re.I))
    )
    return {
        "remaining": remaining,
        "tables": tables,
        "money": money,
        "links": links,
        "score": remaining * 2 + tables * 5 + min(money, 200) // 10 + links,
    }


async def probe_path(context, url):
    page = await context.new_page()
    try:
        await page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        try:
            await page.wait_for_load_state("networkidle", timeout=IDLE_TIMEOUT)
        except Exception:  # noqa: BLE001 - idle is best-effort
            pass
        await page.wait_for_timeout(SETTLE_MS)
        html = await page.content()
        stats = score(html)
        stats.update(url=url, kb=len(html) // 1024)
        return stats
    except Exception as exc:  # noqa: BLE001 - a probe must never kill the sweep
        return {"url": url, "error": type(exc).__name__, "score": -1}
    finally:
        await page.close()


async def probe_state(browser, code, host, out, lock):
    context = await browser.new_context(
        user_agent=UA, viewport={"width": 1400, "height": 1600}, locale="en-US"
    )
    await context.route(
        re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
        lambda route: asyncio.ensure_future(route.abort()),
    )
    best = {"score": -1, "url": None}
    errors = []
    try:
        for path in PATHS:
            result = await probe_path(context, f"https://{host}{path}")
            if result.get("error"):
                errors.append(f"{path}:{result['error']}")
                continue
            if result["score"] > best["score"]:
                best = result
            if result["score"] >= GOOD_ENOUGH:
                break
    finally:
        await context.close()

    record = {"state": code, "host": host, "errors": errors, **best}
    async with lock:
        with open(out, "a") as handle:
            handle.write(json.dumps(record) + "\n")
    print(
        f"{code}: score={record['score']:>4} {record.get('url') or ''} "
        f"{'errs=' + ','.join(errors) if errors else ''}",
        file=sys.stderr,
        flush=True,
    )
    return record


async def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "probe_results.jsonl")
    out.write_text("")
    lock = asyncio.Lock()
    gate = asyncio.Semaphore(CONCURRENCY)

    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)

        async def guarded(code, host):
            async with gate:
                return await probe_state(browser, code, host, out, lock)

        results = await asyncio.gather(
            *(guarded(code, host) for code, host in DOMAINS.items())
        )
        await browser.close()

    results.sort(key=lambda r: r["score"], reverse=True)
    print(f"\n{'ST':<4}{'score':>7}{'tbl':>5}{'rem':>6}{'lnk':>5}  url")
    for r in results:
        print(
            f"{r['state']:<4}{r['score']:>7}{r.get('tables', 0):>5}"
            f"{r.get('remaining', 0):>6}{r.get('links', 0):>5}  "
            f"{r.get('url') or '(nothing reachable)'}"
        )


if __name__ == "__main__":
    asyncio.run(main())
