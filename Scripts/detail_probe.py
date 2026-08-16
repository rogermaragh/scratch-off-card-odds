#!/usr/bin/env python3
"""Answer the only question that matters for a candidate state: do its game
pages yield prize tiers?

Renders the index, harvests game links, renders a couple of them, and runs the
shared table parser. Prints what an adapter would actually get.

    .venv/bin/python Scripts/detail_probe.py MT IN MI FL
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browse import browser_session, render  # noqa: E402
from scrape import tiers_from_table  # noqa: E402

CANDIDATES = {
    "VA": "https://www.valottery.com/scratchers",
    "PA": "https://www.palottery.state.pa.us/scratch-offs",
    "MT": "https://www.montanalottery.com/scratch",
    "ID": "https://www.idaholottery.com/games/scratch-offs",
    "IN": "https://www.hoosierlottery.com/scratch-offs",
    "MI": "https://www.michiganlottery.com/scratchers",
    "FL": "https://www.flalottery.com/scratch-offs",
    "NH": "https://www.nhlottery.com/games/scratch-offs",
    "MA": "https://www.masslottery.com/scratch-offs",
    "AZ": "https://www.arizonalottery.com/scratch-offs",
    "MD": "https://www.mdlottery.com/scratch-offs",
    "MN": "https://www.mnlottery.com/scratch-offs",
    "IL": "https://www.illinoislottery.com/scratch-offs",
    "KS": "https://www.kslottery.com/scratch-offs",
    "CO": "https://www.coloradolottery.com/scratch-offs",
    "CT": "https://www.ctlottery.org/scratchers",
}

LINK_RE = re.compile(r'href="([^"]*(?:scratch|instant|game)[^"?#]*)"', re.I)
ASSET_RE = re.compile(r"\.(css|js|png|jpe?g|gif|svg|webp|woff2?|ttf|pdf)(\?|$)", re.I)


def game_links(index_html, index_url):
    """Same-host links that look like individual game pages, not assets."""
    from urllib.parse import urlparse

    host = urlparse(index_url).netloc
    base = index_url.rstrip("/")
    out = []
    for href in LINK_RE.findall(index_html):
        full = urljoin(index_url, href)
        if ASSET_RE.search(full) or urlparse(full).netloc != host:
            continue
        if full.rstrip("/") == base or full in out:
            continue
        # A game page lives deeper than the index it was linked from.
        if len(urlparse(full).path.strip("/").split("/")) <= len(
            urlparse(index_url).path.strip("/").split("/")
        ):
            continue
        out.append(full)
    return out


def main():
    wanted = sys.argv[1:] or list(CANDIDATES)
    with browser_session() as context:
        for code in wanted:
            index_url = CANDIDATES.get(code)
            if not index_url:
                print(f"{code}: no candidate url"); continue
            try:
                index_html = render(context, index_url, settle_ms=1500)
            except Exception as exc:  # noqa: BLE001
                print(f"{code}: index failed ({type(exc).__name__})"); continue

            index_tiers = tiers_from_table(index_html)
            links = game_links(index_html, index_url)

            print(f"\n{code}: {len(links)} game links, "
                  f"{len(index_tiers)} tiers on the index itself")
            if index_tiers:
                print(f"   index sample: {index_tiers[:2]}")

            for link in links[:2]:
                try:
                    html = render(context, link, settle_ms=1500)
                except Exception as exc:  # noqa: BLE001
                    print(f"   {link[:70]} -> {type(exc).__name__}")
                    continue
                tiers = tiers_from_table(html)
                headers = re.findall(r"<th[^>]*>(.*?)</th>", html, re.S)[:6]
                headers = [re.sub(r"<[^>]+>|\s+", " ", h).strip() for h in headers]
                print(f"   {link[:70]}")
                print(f"      tiers={len(tiers)} headers={headers}")
                if tiers:
                    print(f"      sample={tiers[:2]}")


if __name__ == "__main__":
    main()
