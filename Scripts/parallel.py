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
import re
import threading

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


async def _evaluate_one(browser, url, script, settle_ms, gate, results,
                        scroll_passes=0):
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
            # Game lists increasingly load on scroll rather than paginate.
            # Oklahoma shows twelve of its forty-odd games until you reach the
            # bottom, and a reader that never scrolls simply reports twelve --
            # which looks like a state with twelve games, not a truncated list.
            for _ in range(scroll_passes):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(900)
            results[url] = await page.evaluate(script)
        except Exception:  # noqa: BLE001 - one bad page must not sink the batch
            results[url] = None
        finally:
            await page.close()
            await context.close()


async def _run(urls, script, settle_ms, concurrency, scroll_passes=0):
    from playwright.async_api import async_playwright

    results = {}
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(concurrency)
        await asyncio.gather(*(
            _evaluate_one(browser, url, script, settle_ms, gate, results,
                          scroll_passes)
            for url in urls))
        await browser.close()
    return results


def evaluate_many(urls, script, settle_ms=6000, concurrency=6,
                  scroll_passes=0):
    """Run one script against many URLs, returning {url: result_or_None}.

    Runs on a private thread so it cannot collide with the sync Playwright
    browser the rest of the scraper keeps open.
    """
    urls = list(dict.fromkeys(urls))          # dedupe, keep order
    results: dict = {}

    def runner():
        results.update(asyncio.run(
            _run(urls, script, settle_ms, concurrency, scroll_passes)))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    return results

async def _capture_one(browser, url, match, settle_ms, gate, results):
    async with gate:
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 1400, "height": 1200}, locale="en-US")
        found = []

        async def on_response(response):
            if match in response.url:
                try:
                    found.append(await response.text())
                except Exception:  # noqa: BLE001
                    pass

        context.on("response", lambda r: asyncio.ensure_future(on_response(r)))
        page = await context.new_page()
        try:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(settle_ms)
        except Exception:  # noqa: BLE001
            pass
        finally:
            await page.close()
            await context.close()
        results[url] = found[0] if found else None


async def _run_capture(urls, match, settle_ms, concurrency):
    from playwright.async_api import async_playwright

    results = {}
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(concurrency)
        await asyncio.gather(*(
            _capture_one(browser, url, match, settle_ms, gate, results)
            for url in urls))
        await browser.close()
    return results


def capture_many(urls, url_contains, settle_ms=4000, concurrency=6):
    """Load many pages and keep the response each one fetches.

    Some states serve their prize data from a gateway that refuses anyone
    without a key the page itself carries -- Florida's answers a direct request
    with "Missing header". Letting each page make its own call and reading the
    answer needs no key and no pretending to be a browser we are not.
    """
    urls = list(dict.fromkeys(urls))
    results: dict = {}

    def runner():
        results.update(asyncio.run(
            _run_capture(urls, url_contains, settle_ms, concurrency)))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    return results

async def _render_one(browser, url, settle_ms, gate, results):
    async with gate:
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 1400, "height": 1600}, locale="en-US")
        # Images and fonts double the load time and carry no prize data.
        await context.route(
            re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
            lambda route: asyncio.ensure_future(route.abort()))
        page = await context.new_page()
        try:
            await page.goto(url, timeout=45000, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=12000)
            except Exception:  # noqa: BLE001
                pass
            await page.wait_for_timeout(settle_ms)
            results[url] = await page.content()
        except Exception:  # noqa: BLE001
            results[url] = None
        finally:
            await page.close()
            await context.close()


async def _run_render(urls, settle_ms, concurrency):
    from playwright.async_api import async_playwright

    results = {}
    async with async_playwright() as play:
        browser = await play.chromium.launch(headless=True)
        gate = asyncio.Semaphore(concurrency)
        await asyncio.gather(*(
            _render_one(browser, url, settle_ms, gate, results) for url in urls))
        await browser.close()
    return results


def render_many(urls, settle_ms=2000, concurrency=6):
    """Rendered HTML for many pages at once, as {url: html_or_None}.

    The same job `render_page` does, without waiting for each page before
    starting the next. Three scratch-off adapters open one browser page per
    game -- Virginia alone is eighty-six -- which is most of the time a full
    scrape spends.
    """
    urls = list(dict.fromkeys(urls))
    results: dict = {}

    def runner():
        results.update(asyncio.run(_run_render(urls, settle_ms, concurrency)))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    return results
