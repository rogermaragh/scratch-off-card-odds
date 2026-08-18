#!/usr/bin/env python3
"""A configurable adapter for the common state-lottery shape.

Most remaining states follow the same pattern: an index page listing games,
each linking to a detail page with a prize table. Writing 30 bespoke scrapers
for that is mostly copy-paste, so this expresses the pattern once and takes the
per-state differences as configuration.

A state only needs its own function when it breaks the pattern -- Washington
ships one JSON blob, Mississippi uses a REST API, Virginia paginates via
filters. Those stay hand-written.
"""

from __future__ import annotations

import re
import sys
from html import unescape

PRICE_LABELS = (
    r"ticket price", r"price per play", r"price", r"cost", r"ticket cost",
)
TOP_PRIZE_LABELS = (r"top prize", r"grand prize", r"jackpot")
ODDS_LABELS = (
    r"overall odds", r"odds of winning overall", r"approximate overall odds",
    r"odds",
)


def visible_text(html):
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", body)
    return re.sub(r"[ \t]+", " ", text)


def labelled_value(text, labels, pattern=r"\$?([\d.,]+)"):
    """Find a value near any of `labels`, trying after then before the label.

    States are split roughly evenly between printing the label first and the
    value first, so both orders have to be tried.
    """
    for label in labels:
        after = re.search(rf"{label}\s*:?\s*\n*\s*{pattern}", text, re.I)
        if after:
            return after.group(1)
        before = re.search(rf"{pattern}\s*\n*\s*{label}", text, re.I)
        if before:
            return before.group(1)
    return None


def game_name(html, text, game_id, strip_patterns=()):
    """Prefer <title>: body headings are inconsistent and often mislabelled."""
    title = re.search(r"<title>([^<]*)</title>", html, re.S)
    if title:
        name = unescape(title.group(1))
        for pattern in strip_patterns:
            name = re.sub(pattern, "", name, flags=re.I)
        name = re.split(r"\s*\|", name)[0].strip(" -–—")
        if name:
            return name.strip()
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if heading:
        name = unescape(re.sub(r"<[^>]+>", " ", heading.group(1))).strip()
        if name:
            return re.sub(r"\s+", " ", name)
    return f"Game {game_id}"


def build_adapter(
    code,
    root,
    index_paths,
    link_re,
    *,
    fetch,
    tiers_from_table,
    money,
    title_strip=(),
    expired_re=None,
    limit=None,
):
    """Return a scraper callable for a state that follows the common shape.

    `fetch(url)` should return HTML -- pass the plain-HTTP getter for states
    that serve real markup, or the browser renderer for those that don't.
    """

    def scrape():
        links = []
        seen = set()
        for path in index_paths:
            html = fetch(root + path)
            if not html:
                continue
            for match in re.findall(link_re, html):
                url = match if match.startswith("http") else root + match
                if url not in seen:
                    seen.add(url)
                    links.append(url)
        if limit:
            links = links[:limit]
        print(f"  {code}: {len(links)} games listed", file=sys.stderr)

        games = []
        for url in links:
            html = fetch(url)
            if not html:
                continue
            tiers = tiers_from_table(html)
            if not tiers:
                continue
            text = visible_text(html)
            game_id = (re.search(r"(\d+)(?!.*\d)", url) or [None, url])[1]

            odds_raw = labelled_value(text, ODDS_LABELS, r"1 in\s*([\d.,]+)")
            if not odds_raw:
                odds_raw = labelled_value(text, ODDS_LABELS)

            games.append(
                {
                    "id": f"{code}-{game_id}",
                    "name": game_name(html, text, game_id, title_strip),
                    "number": str(game_id),
                    "price": money(labelled_value(text, PRICE_LABELS)),
                    "topPrize": max(t["value"] for t in tiers),
                    "overallOdds": money(odds_raw) if odds_raw else None,
                    "tiers": tiers,
                    "url": url,
                    "expired": bool(expired_re and re.search(expired_re, html, re.I)),
                }
            )
        print(f"  {code}: {len(games)} games parsed", file=sys.stderr)
        return games

    return scrape
