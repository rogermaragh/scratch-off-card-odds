#!/usr/bin/env python3
"""Load many pages at once.

The scraper drives one browser page at a time, which is fine for a state with
two URLs and painful for the per-game states: forty pages, each waiting on
network idle plus a settle delay, is over ten minutes of mostly sitting still.
None of those loads depend on each other, so they have no business being
sequential.

Playwright's sync API cannot drive pages concurrently in one thread, so this
runs the async API on its own event loop in its own thread and hands back a
plain dict. Callers stay synchronous and unaware.
"""

from __future__ import annotations

import asyncio
import threading

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


async def _evaluate_one(browser, url, script, settle_ms, gate, results):
    async with gate:
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 1400, "height": 1600}, locale="en-US")
        page = await context.new_page()
        try:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(settle_ms)
            results[url] = await page.evaluate(script)
        except Exception:  # noqa: BLE001 - one bad page must not sink the batch
            results[url] = None
        finally:
            await page.close()
            await context.close()


async def _run(urls, script, settle_ms, concurrency):
    from playwright.async_api import async_playwright

    results = {}
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(concurrency)
        await asyncio.gather(*(
            _evaluate_one(browser, url, script, settle_ms, gate, results)
            for url in urls))
        await browser.close()
    return results


def evaluate_many(urls, script, settle_ms=6000, concurrency=6):
    """Run one script against many URLs, returning {url: result_or_None}.

    Runs on a private thread so it cannot collide with the sync Playwright
    browser the rest of the scraper keeps open.
    """
    urls = list(dict.fromkeys(urls))          # dedupe, keep order
    results: dict = {}

    def runner():
        results.update(asyncio.run(_run(urls, script, settle_ms, concurrency)))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    return results
