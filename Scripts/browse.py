#!/usr/bin/env python3
"""Browser-backed fetching, for states whose prize tables are client-rendered.

Plain HTTP gets roughly a third of US lotteries. The rest either render their
game list with JavaScript or reject non-browser clients outright. This module
drives headless Chromium so those states become reachable, and exposes the same
`render(url) -> html` call the scraper adapters use.

Run directly to re-probe every unbuilt state and report what a browser unlocks.
"""

from __future__ import annotations

import re
import sys
from contextlib import contextmanager

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Candidate paths, most-likely first. Probing stops at the first good score.
PATHS = [
    "/scratch-offs",
    "/scratchers",
    "/games/scratch-offs",
    "/scratch",
    "/games/instant-games",
    "/instant-games",
]

# Every jurisdiction without an adapter yet.
DOMAINS = {
    "AZ": "www.arizonalottery.com",
    "AR": "www.arkansasscholarshiplottery.com",
    "CA": "www.calottery.com",
    "CO": "www.coloradolottery.com",
    "CT": "www.ctlottery.org",
    "DE": "www.lottery.delaware.gov",
    "DC": "dclottery.com",
    "FL": "www.flalottery.com",
    "GA": "www.galottery.com",
    "ID": "www.idaholottery.com",
    "IL": "www.illinoislottery.com",
    "IN": "www.hoosierlottery.com",
    "IA": "ialottery.com",
    "KS": "www.kslottery.com",
    "KY": "www.kylottery.com",
    "ME": "www.mainelottery.com",
    "MD": "www.mdlottery.com",
    "MA": "www.masslottery.com",
    "MI": "www.michiganlottery.com",
    "MN": "www.mnlottery.com",
    "MO": "www.molottery.com",
    "MT": "www.montanalottery.com",
    "NE": "www.nelottery.com",
    "NH": "www.nhlottery.com",
    "NJ": "www.njlottery.com",
    "NY": "nylottery.ny.gov",
    "ND": "www.lottery.nd.gov",
    "OH": "www.ohiolottery.com",
    "OK": "www.lottery.ok.gov",
    "OR": "www.oregonlottery.org",
    "PA": "www.palottery.state.pa.us",
    "RI": "www.rilot.com",
    "SD": "lottery.sd.gov",
    "TN": "www.tnlottery.com",
    "TX": "www.texaslottery.com",
    "VT": "vtlottery.com",
    "VA": "www.valottery.com",
    "WV": "wvlottery.com",
    "WI": "wilottery.com",
    "WY": "wyolotto.com",
}


@contextmanager
def browser_session(headless=True):
    """One Chromium instance reused across many page loads."""
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1400, "height": 1600},
            locale="en-US",
        )
        # Images and fonts double load time and none of them carry prize data.
        context.route(
            re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4)(\?|$)"),
            lambda route: route.abort(),
        )
        try:
            yield context
        finally:
            context.close()
            browser.close()


def render(context, url, wait_for=None, settle_ms=1200, timeout=45000):
    """Load a URL and return the DOM after scripts have run."""
    page = context.new_page()
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=timeout)
            except PWTimeout:
                pass
        else:
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeout:
                pass
        page.wait_for_timeout(settle_ms)
        return page.content()
    finally:
        page.close()


def render_clicking(context, url, click_selector=None, settle_ms=1800, timeout=45000):
    """Load a URL, optionally click one control, and return the resulting DOM.

    Some states paginate entirely client-side — their page links are not
    addressable by URL — so the only way to reach page 2 is to press it.
    """
    page = context.new_page()
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except PWTimeout:
            pass
        page.wait_for_timeout(800)
        if click_selector:
            try:
                page.click(click_selector, timeout=12000)
                page.wait_for_timeout(settle_ms)
            except PWTimeout:
                return None  # control never appeared; caller decides what that means
        else:
            page.wait_for_timeout(settle_ms)
        return page.content()
    finally:
        page.close()


def capture_json(context, page_url, url_contains, settle_ms=3000, timeout=40000):
    """Load a page and return the body of the first JSON response whose URL
    contains `url_contains`.

    Some states put their results behind an API that requires a header the page
    supplies — Florida's is an Azure gateway that 401s without a subscription
    key. Replaying a scraped key is brittle: it rotates, and it is theirs.
    Letting the page make its own request and reading the answer is stable and
    needs no secret.
    """
    page = context.new_page()
    captured = {}

    def on_response(response):
        if url_contains in response.url and not captured:
            try:
                captured["body"] = response.text()
            except Exception:  # noqa: BLE001
                pass

    page.on("response", on_response)
    try:
        page.goto(page_url, timeout=timeout, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except PWTimeout:
            pass
        page.wait_for_timeout(settle_ms)
        return captured.get("body")
    except Exception:  # noqa: BLE001
        return captured.get("body")
    finally:
        page.close()


def score(html):
    """Signals that prize inventory is actually present in the rendered DOM."""
    remaining = len(re.findall(r"remaining|unclaimed", html, re.I))
    tables = html.lower().count("<table")
    money = len(re.findall(r"\$[\d,]{3,}", html))
    links = len(set(re.findall(r'href="[^"]*(?:scratch|instant|game)[^"]*[/=]\d+', html, re.I)))
    return remaining * 2 + tables * 5 + min(money, 200) // 10 + links


def probe_state(context, code, host):
    best = (0, None, 0)
    for path in PATHS:
        url = f"https://{host}{path}"
        try:
            html = render(context, url)
        except Exception as exc:  # noqa: BLE001 - a probe must never abort the sweep
            print(f"  {code} {path}: {type(exc).__name__}", file=sys.stderr)
            continue
        value = score(html)
        if value > best[0]:
            best = (value, url, len(html) // 1024)
        if value >= 60:  # clearly carrying data; stop early
            break
    return best


def main():
    results = []
    with browser_session() as context:
        for code, host in DOMAINS.items():
            value, url, size = probe_state(context, code, host)
            results.append((code, value, url, size))
            print(f"  probed {code}: {value}", file=sys.stderr)

    results.sort(key=lambda r: r[1], reverse=True)
    print(f"\n{'ST':<4}{'score':>7}{'KB':>7}  url")
    for code, value, url, size in results:
        print(f"{code:<4}{value:>7}{size:>7}  {url or '(nothing reachable)'}")


if __name__ == "__main__":
    main()
