#!/usr/bin/env python3
"""Fetch lottery data and emit the normalized JSON bundle the app reads.

Draw games come from New York's open-data SODA endpoints (no key required).
Scratch-off inventories are scraped per state; each state needs its own
adapter because no two lottery sites agree on anything.
"""

import argparse
import functools
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import parallel
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from html import unescape
from pathlib import Path

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
OUT = Path(__file__).resolve().parent.parent / "Data" / "lottery.json"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def get(url, tries=3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
            _ = exc
    return ""


def money(text):
    """'$5,000,000' -> 5000000. Returns None when there is no number.

    Reads the FIRST number rather than stripping every non-digit. Stripping
    concatenates across separators, so a footnote marker turns "$5" plus a
    dangling "1" into 51 -- which is exactly how California's $5 tier became a
    nonexistent $51 prize at 1-in-13 odds and inflated the game's payout to
    139%. Prize tables are full of asterisks, footnotes and trailing notes.
    """
    match = re.search(r"\d[\d,]*(?:\.\d+)?", text or "")
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def odds_after_in(text):
    """'1 in 3.01' -> 3.01. Falls back to the first number if there is no 'in'."""
    if not text:
        return None
    match = re.search(r"1\s+in\s+([\d.,]+)", text, re.I)
    return money(match.group(1)) if match else money(text)


# ------------------------------------------------------------ browser support

# Adapters for client-rendered states call render_page(). The browser is opened
# once, lazily, and only if such a state is actually being scraped -- so a run
# limited to plain-HTTP states never pays the startup cost.
_BROWSER = {"ctx": None, "stack": None, "unavailable": False, "pages": 0}

# A single Chromium context degrades over a long run -- past a few hundred page
# loads it starts refusing navigations and eventually dies. Recycling it keeps
# the later states in the run as healthy as the first.
BROWSER_RECYCLE_AFTER = 120


def _start_browser():
    """Open a browser context. Returns False only if Playwright itself is absent."""
    try:
        from contextlib import ExitStack

        from browse import browser_session

        stack = ExitStack()
        _BROWSER["ctx"] = stack.enter_context(browser_session())
        _BROWSER["stack"] = stack
        _BROWSER["pages"] = 0
        return True
    except ImportError as exc:
        print(f"  Playwright not installed ({exc}); client-rendered states "
              "will be skipped", file=sys.stderr)
        _BROWSER["unavailable"] = True
        return False
    except Exception as exc:  # noqa: BLE001
        # A wiped browser cache used to fail silently: every client-rendered
        # state returned zero games and only the validator caught it. Install
        # the browser once and retry rather than shipping empty states.
        if "Executable doesn't exist" in str(exc) and not _BROWSER.get("installed"):
            _BROWSER["installed"] = True
            print("  browser binary missing; running 'playwright install chromium'",
                  file=sys.stderr)
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=False,
            )
            return _start_browser()
        print(f"  browser launch failed ({type(exc).__name__})", file=sys.stderr)
        return False


def _restart_browser():
    close_browser()
    return _start_browser()


def render_page(url, wait_for=None, settle_ms=1200):
    """Return a URL's DOM after its scripts have run, or None if unavailable.

    A crashed browser is recovered rather than latched: an earlier version set
    a permanent "failed" flag on the first hiccup, which silently skipped every
    remaining browser-backed state in the run.
    """
    if _BROWSER["unavailable"]:
        return None
    if _BROWSER["ctx"] is None and not _start_browser():
        return None
    if _BROWSER["pages"] >= BROWSER_RECYCLE_AFTER:
        _restart_browser()

    from browse import render

    for attempt in range(2):
        try:
            _BROWSER["pages"] += 1
            return render(_BROWSER["ctx"], url, wait_for=wait_for, settle_ms=settle_ms)
        except Exception as exc:  # noqa: BLE001
            print(f"  render failed for {url}: {type(exc).__name__}"
                  f"{' — restarting browser' if attempt == 0 else ''}", file=sys.stderr)
            if attempt == 0 and not _restart_browser():
                return None
    return None


def render_page_click(url, click_selector, settle_ms=1800):
    """Load a page, press one control, and return the DOM that results."""
    if _BROWSER["unavailable"]:
        return None
    if _BROWSER["ctx"] is None and render_page(url) is None:
        return None
    try:
        from browse import render_clicking

        return render_clicking(
            _BROWSER["ctx"], url, click_selector=click_selector, settle_ms=settle_ms
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  click render failed for {url}: {type(exc).__name__}", file=sys.stderr)
        return None


def capture_json_pages(page_url, url_contains, settle_ms=4000):
    """All matching JSON responses a page fetches."""
    if _BROWSER["unavailable"]:
        return []
    if _BROWSER["ctx"] is None and not _start_browser():
        return []
    try:
        from browse import capture_json_all

        return capture_json_all(_BROWSER["ctx"], page_url, url_contains,
                                settle_ms=settle_ms)
    except Exception as exc:  # noqa: BLE001
        print(f"  capture failed for {page_url}: {type(exc).__name__}",
              file=sys.stderr)
        return []


def fetch_json_via_browser(url):
    """GET a JSON URL using the browser, for hosts that refuse plain clients."""
    if _BROWSER["unavailable"]:
        return None
    if _BROWSER["ctx"] is None and not _start_browser():
        return None
    try:
        from browse import fetch_json

        return fetch_json(_BROWSER["ctx"], url)
    except Exception as exc:  # noqa: BLE001
        print(f"  browser fetch failed for {url}: {type(exc).__name__}",
              file=sys.stderr)
        return None


def evaluate_page(url, script, settle_ms=5000):
    """Run JS against a page and return the result, or None."""
    if _BROWSER["unavailable"]:
        return None
    if _BROWSER["ctx"] is None and not _start_browser():
        return None
    try:
        from browse import evaluate

        return evaluate(_BROWSER["ctx"], url, script, settle_ms=settle_ms)
    except Exception as exc:  # noqa: BLE001
        print(f"  evaluate failed for {url}: {type(exc).__name__}", file=sys.stderr)
        return None


def capture_json_page(page_url, url_contains, settle_ms=3000):
    """Read a JSON response the page itself fetched (for header-gated APIs)."""
    if _BROWSER["unavailable"]:
        return None
    if _BROWSER["ctx"] is None and not _start_browser():
        return None
    try:
        from browse import capture_json

        return capture_json(_BROWSER["ctx"], page_url, url_contains,
                            settle_ms=settle_ms)
    except Exception as exc:  # noqa: BLE001
        print(f"  capture failed for {page_url}: {type(exc).__name__}",
              file=sys.stderr)
        return None


def close_browser():
    if _BROWSER["stack"] is not None:
        _BROWSER["stack"].close()
        _BROWSER["ctx"] = None
        _BROWSER["stack"] = None


# ------------------------------------------------------------ table parsing


def tiers_from_table(html, value_kw=("prize", "value", "amount"),
                     total_kw=("total", "original", "at start", "start",
                               "number of prizes", "winning tickets", "printed",
                               "in game"),
                     left_kw=("remaining", "unclaimed", "left"),
                     odds_kw=("odds",)):
    """Pull prize tiers out of whichever table carries them.

    Columns are located by matching header text, never by position: layouts
    differ between states and even between games within one state.
    """

    def header_index(headers, keywords, exclude=()):
        for index, header in enumerate(headers):
            low = header.lower()
            if any(k in low for k in keywords) and not any(x in low for x in exclude):
                return index
        return None

    best = []
    for table in re.findall(r"<table.*?</table>", html, re.S):
        headers = [
            unescape(re.sub(r"<[^>]+>", " ", h)).strip()
            for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)
        ]
        if not headers:
            continue
        # "Remaining" must not also match the value column, and vice versa.
        v_col = header_index(headers, value_kw, exclude=("remain", "unclaim", "odds"))
        t_col = header_index(headers, total_kw, exclude=("remain", "unclaim"))
        l_col = header_index(headers, left_kw)
        o_col = header_index(headers, odds_kw)
        if v_col is None or l_col is None:
            continue
        # California writes remaining and total into one cell ("55 of 105"),
        # so a missing total column is not automatically a dead end.
        combined = t_col is None
        if combined and v_col == l_col:
            continue

        tiers = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = [
                unescape(re.sub(r"<[^>]+>", " ", c)).strip()
                for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            needed = [v_col, l_col] + ([] if combined else [t_col])
            if len(cells) <= max(needed):
                continue
            value = money(cells[v_col])
            if combined:
                pair = re.search(
                    r"([\d,]+)\s*(?:of|/)\s*([\d,]+)", cells[l_col], re.I
                )
                if not pair:
                    continue
                left, total = money(pair.group(1)), money(pair.group(2))
            else:
                total, left = money(cells[t_col]), money(cells[l_col])
            if value is None or total is None or left is None or total <= 0:
                continue
            odds = None
            if o_col is not None and len(cells) > o_col:
                match = re.search(r"1 in ([\d.,]+)", cells[o_col]) or re.search(
                    r"([\d.,]+)", cells[o_col]
                )
                odds = money(match.group(1)) if match else None
            tiers.append(
                {
                    "value": value,
                    "odds": odds,
                    "total": int(total),
                    "remaining": int(left),
                }
            )
        if len(tiers) > len(best):
            best = tiers
    return best


# ---------------------------------------------------------------- draw games

# Millionaire for Life replaced BOTH Cash4Life and Lucky for Life in Feb 2026.
# Those two are retired: their feeds still resolve but stopped updating, so
# publishing either would have shown months-old numbers as current.
MFL_STATES = [
    "AR", "CO", "CT", "DE", "DC", "GA", "ID", "IN", "IA", "KS", "KY", "ME",
    "MA", "MS", "MI", "MT", "NE", "NH", "NJ", "NY", "NC", "ND", "OH", "OK",
    "PA", "RI", "SD", "TN", "VT", "VA", "WY",
]


def _split(text):
    return [int(n) for n in re.findall(r"\d+", text or "")]


def _digits(text):
    """'558' -> [5, 5, 8]; daily-number games publish a single digit string."""
    return [int(c) for c in re.sub(r"\D", "", text or "")]


def parse_main_plus_special(row, special_key):
    nums = _split(row.get("winning_numbers"))
    special = row.get(special_key)
    if not nums:
        return []
    return [{"numbers": nums, "special": int(special) if special else None}]


def parse_powerball(row):
    nums = _split(row.get("winning_numbers"))
    if len(nums) < 6:
        return []
    return [{"numbers": nums[:5], "special": nums[5],
             "multiplier": row.get("multiplier")}]


def parse_two_a_day(row, midday_key, evening_key, digits=False):
    """Games drawn twice daily publish both draws on one row."""
    out = []
    for label, key in (("Midday", midday_key), ("Evening", evening_key)):
        raw = row.get(key)
        nums = _digits(raw) if digits else _split(raw)
        if nums:
            out.append({"numbers": nums, "special": None, "label": label})
    return out


SODA = {
    "powerball": {
        "resource": "d6yy-54nr",
        "name": "Powerball",
        "special_label": "Powerball",
        "parser": parse_powerball,
        "states": None,  # sold everywhere
    },
    "megamillions": {
        "resource": "5xaw-6ayf",
        "name": "Mega Millions",
        "special_label": "Mega Ball",
        "parser": lambda row: parse_main_plus_special(row, "mega_ball"),
        "states": None,
    },
    "millionaireforlife": {
        "resource": "a4w9-a3tp",
        "name": "Millionaire for Life",
        "special_label": "Millionaire Ball",
        "parser": lambda row: parse_main_plus_special(row, "mill_ball"),
        "states": MFL_STATES,
    },
    # New York publishes its in-state games as open data too, which makes NY
    # the best-covered state without scraping anything.
    "nylotto": {
        "resource": "6nbc-h7bj",
        "name": "New York Lotto",
        "special_label": "Bonus",
        "parser": lambda row: parse_main_plus_special(row, "bonus"),
        "states": ["NY"],
    },
    "nytake5": {
        "resource": "dg63-4siq",
        "name": "Take 5",
        "special_label": None,
        "parser": lambda row: parse_two_a_day(
            row, "midday_winning_numbers", "evening_winning_numbers"),
        "states": ["NY"],
    },
    "nynumbers": {
        "resource": "hsys-3def",
        "name": "Numbers",
        "special_label": None,
        "parser": lambda row: parse_two_a_day(
            row, "midday_daily", "evening_daily", digits=True),
        "states": ["NY"],
    },
    "nywin4": {
        "resource": "hsys-3def",
        "name": "Win 4",
        "special_label": None,
        "parser": lambda row: parse_two_a_day(
            row, "midday_win_4", "evening_win_4", digits=True),
        "states": ["NY"],
    },
    "nypick10": {
        "resource": "bycu-cw7c",
        "name": "Pick 10",
        "special_label": None,
        "parser": lambda row: parse_main_plus_special(row, "__none__"),
        "states": ["NY"],
    },
}


def fetch_draw_game(key, cfg, limit=8):
    url = (
        f"https://data.ny.gov/resource/{cfg['resource']}.json"
        f"?$limit={limit}&$order=draw_date%20DESC"
    )
    rows = json.loads(get(url))
    draws = []
    for row in rows:
        date = (row.get("draw_date") or "")[:10]
        if not date:
            continue
        for parsed in cfg["parser"](row):
            draws.append({
                "date": date,
                "numbers": parsed["numbers"],
                "special": parsed.get("special"),
                "multiplier": parsed.get("multiplier"),
                "label": parsed.get("label"),
            })
    return {
        "id": key,
        "name": cfg["name"],
        "specialLabel": cfg["special_label"],
        "states": cfg["states"],
        "draws": draws,
    }


# ------------------------------------------------------- NC scratch-off state

NC_ROOT = "https://www.nclottery.com"


def nc_game_urls():
    html = get(f"{NC_ROOT}/scratch-off")
    paths = re.findall(r'href="(/scratch-off/\d+/[^"]+)"', html)
    seen, ordered = set(), []
    for path in paths:
        if path not in seen:
            seen.add(path)
            ordered.append(NC_ROOT + path)
    return ordered


def nc_parse_game(url):
    html = get(url)

    def label(name):
        # Detail pages render each stat as <span>Label</span><span>Value</span>.
        match = re.search(
            rf"{name}\s*</\w+>\s*<[^>]*>\s*([^<]+)", html, re.I
        )
        return unescape(match.group(1)).strip() if match else None

    # <span class="title">200X The Cash <span>#24</span></span>
    title_match = re.search(r'<span class="title">(.*?)</span>\s*</span>', html, re.S)
    if not title_match:
        return None
    raw_title = title_match.group(1)
    number_match = re.search(r"#(\d+)", raw_title)
    game_name = unescape(re.sub(r"<[^>]+>|#\d+", "", raw_title)).strip()
    if not game_name:
        return None
    tiers = []
    rows = re.findall(r"<tr>(.*?)</tr>", html, re.S)
    for row in rows:
        value = re.search(r'class="PrizeValue"[^>]*>([^<]+)', row)
        odds = re.search(r'class="OriginalOdds"[^>]*>([^<]+)', row)
        total = re.search(r'class="PrizeCount"[^>]*>([^<]+)', row)
        left = re.search(r'class="PrizeCountRemaining"[^>]*>([^<]+)', row)
        if not (value and total and left):
            continue
        v, t, r = money(value.group(1)), money(total.group(1)), money(left.group(1))
        if v is None or t is None or r is None or t <= 0:
            continue
        tiers.append(
            {
                "value": v,
                "odds": money(odds.group(1)) if odds else None,
                "total": int(t),
                "remaining": int(r),
            }
        )

    if not tiers:
        return None

    return {
        "id": f"NC-{number_match.group(1) if number_match else game_name}",
        "name": game_name,
        "number": number_match.group(1) if number_match else None,
        "price": money(label("Ticket Price")),
        "topPrize": money(label("Top Prize")),
        # "1 in 3.01" -- take the figure after "in". money() reads the first
        # number, which here is the literal 1, so every NC game reported odds
        # of 1 in 1.0.
        "overallOdds": odds_after_in(label("Overall Odds")),
        "tiers": tiers,
        "url": url,
    }


def scrape_nc():
    urls = nc_game_urls()
    print(f"  NC: {len(urls)} games listed", file=sys.stderr)
    games = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(nc_parse_game, urls):
            if result:
                games.append(result)
    print(f"  NC: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------------------ analytics


def enrich(game):
    """Estimate tickets left and how the game's payout has drifted.

    A tier's original odds imply the print run: odds x prizes at that tier.
    We take the median implied run to blunt rounding in published odds, then
    assume tickets sell in proportion to prizes claimed, which is the standard
    approximation every remaining-prize tracker makes.
    """
    tiers = game["tiers"]
    total_prizes = sum(t["total"] for t in tiers)
    left_prizes = sum(t["remaining"] for t in tiers)
    if total_prizes <= 0:
        return None

    frac_left = left_prizes / total_prizes
    value_start = sum(t["value"] * t["total"] for t in tiers)
    value_left = sum(t["value"] * t["remaining"] for t in tiers)
    if frac_left <= 0 or value_start <= 0:
        return None

    # The print run cancels out of the ratio:
    #   ratio = (value_left / (printed * frac_left)) / (value_start / printed)
    #         =  value_left / (frac_left * value_start)
    # So a state publishing only prize counts can still be ranked. The run is
    # needed solely for the absolute figures below.
    game["pctPrizesRemaining"] = round(frac_left * 100, 1)
    game["ratio"] = round(value_left / (frac_left * value_start), 3)

    # Some states publish the print run outright; prefer that over inferring it.
    printed = None
    if game.get("ticketsPrintedActual"):
        printed = float(game.pop("ticketsPrintedActual"))
        game["printRunSource"] = "published"
    else:
        runs = sorted(t["odds"] * t["total"] for t in tiers if t["odds"])
        if runs:
            printed = runs[len(runs) // 2]
            game["printRunSource"] = "tier-odds"
        elif game.get("overallOdds"):
            printed = total_prizes * game["overallOdds"]
            game["printRunSource"] = "overall-odds"
        else:
            game["printRunSource"] = None

    price = game.get("price") or 0
    if printed:
        tickets_left = printed * frac_left
        ev_start = value_start / printed
        ev_now = value_left / tickets_left if tickets_left else 0
        game["ticketsPrinted"] = round(printed)
        game["ticketsRemaining"] = round(tickets_left)
        game["evStart"] = round(ev_start, 4)
        game["evNow"] = round(ev_now, 4)
        game["returnPct"] = round(ev_now / price * 100, 1) if price else None
    else:
        game["ticketsPrinted"] = None
        game["ticketsRemaining"] = None
        game["evStart"] = None
        game["evNow"] = None
        game["returnPct"] = None
    game["topPrizesRemaining"] = sum(
        t["remaining"] for t in tiers if t["value"] == max(x["value"] for x in tiers)
    )
    # Below a few percent inventory the proportional-sales assumption stops
    # holding and the ratio swings wildly, so flag it rather than trust it.
    game["endingSoon"] = frac_left < 0.05
    game["partialTiers"] = bool(game.get("partialTiers"))

    # Win estimates.
    #
    # A "current odds of winning anything" figure is deliberately NOT published
    # here. Tickets remaining is estimated as proportional to prizes claimed,
    # so tickets_left / prizes_left reduces to printed / total_prizes -- the
    # published odds exactly, every time. It would look like a live number and
    # be nothing of the sort. Only the state's own figure is shown.
    #
    # Expected value does move, because the *mix* of remaining prizes changes
    # even when the count ratio does not: claim the top prize and every
    # remaining ticket is worth less, while the odds of winning something at
    # all are unchanged.
    # Always present, even when it cannot be computed: the neighbouring fields
    # are set to None explicitly, and a key that sometimes vanishes makes every
    # consumer guard for two shapes instead of one.
    game["netPerTicket"] = None
    if price and game.get("evNow"):
        # What a ticket is worth against what it costs. Essentially always
        # negative -- that is how lotteries work -- but the size varies a lot.
        game["netPerTicket"] = round(game["evNow"] - price, 2)
    return game


# id, display name, path, per-draw link token, special label, main ball count.
#
# Every NC page also renders other games' results, so a result block is only
# accepted when it contains that game's own "<Token>-Draw?dn=" detail link.
# Cash 5 and Lucky for Life are deliberately absent: their blocks carry no
# per-game marker at all, and every scoping attempt pulled in the Powerball and
# Mega Millions results sitting next to them. Publishing the wrong winning
# numbers is worse than publishing fewer games.
NC_DRAW_GAMES = [
    ("pick3", "Pick 3", "/pick3", "Pick3", "Fireball", 3),
    ("pick4", "Pick 4", "/pick4", "Pick4", "Fireball", 4),
]


def _nc_year_for(month_day):
    """NC prints 'Sat, Aug 15' with no year. Assume the most recent occurrence."""
    today = datetime.now()
    for year in (today.year, today.year - 1):
        try:
            parsed = datetime.strptime(f"{month_day} {year}", "%b %d %Y")
        except ValueError:
            continue
        if parsed <= today + timedelta(days=2):
            return parsed
    return None


def nc_draw_games():
    """In-state draw games: Pick 3/4, Cash 5, Lucky for Life."""
    games = []
    for game_id, name, path, token, special_label, expected in NC_DRAW_GAMES:
        try:
            html = get(NC_ROOT + path)
        except urllib.error.URLError:
            continue

        draws, seen = [], set()
        # Chunk at each result header so a greedy match can't reach across
        # into a neighbouring result block.
        starts = [m.start() for m in re.finditer(r'class="label-drawdate"', html)]
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(html)
            chunk = html[start:end]
            if f"/{token}-Draw?dn=" not in chunk:
                continue  # this block belongs to some other game on the page

            label_match = re.search(r'class="label-drawdate">([^<]*)</span>', chunk)
            date_match = re.search(r'class="drawdate">(.*?)</span>', chunk, re.S)
            balls_match = re.search(r'<div class="ball-row">(.*?)</div>', chunk, re.S)
            if not (label_match and date_match and balls_match):
                continue
            label = label_match.group(1)
            balls_html = balls_match.group(1)

            date_text = unescape(re.sub(r"<[^>]+>", "", date_match.group(1))).strip()
            month_day = re.search(r"([A-Z][a-z]{2} \d{1,2})", date_text)
            if not month_day:
                continue
            parsed = _nc_year_for(month_day.group(1))
            if not parsed:
                continue

            balls = re.findall(r'class="ball([^"]*)"[^>]*>([^<]+)', balls_html)
            main, special = [], None
            for classes, value in balls:
                digits = re.sub(r"[^0-9]", "", value)
                if not digits:
                    continue
                # A plain ball is class="ball"; every special carries a second
                # class (fireball, luckyball, megaball, millionaireball).
                if classes.strip():
                    special = int(digits)
                else:
                    main.append(int(digits))
            if len(main) != expected:
                continue

            # "Latest Daytime Drawing" -> "Daytime"
            clean_label = re.sub(r"^Latest\s+|\s+Drawing$", "", label.strip()) or None
            key = (parsed.strftime("%Y-%m-%d"), clean_label, tuple(main), special)
            if key in seen:
                continue  # the page renders each result twice, for two layouts
            seen.add(key)

            draws.append(
                {
                    "date": parsed.strftime("%Y-%m-%d"),
                    "numbers": main,
                    "special": special,
                    "label": clean_label,
                }
            )

        if draws:
            games.append(
                {
                    "id": f"NC-{game_id}",
                    "name": name,
                    "specialLabel": special_label,
                    "draws": draws,
                }
            )
    print(f"  NC: {len(games)} in-state draw games", file=sys.stderr)
    return games


AZ_API = "https://api.arizonalottery.com/v2/drawgames/drawings"

# Arizona lists its Pick games twice, once per bet size ("ONE PLAY FOR $1" and
# "TWO PLAYS FOR $1"). Those are the same draw, so they collapse to one game.
AZ_RENAME = {
    "THE PICK": "The Pick",
    "FANTASY 5": "Fantasy 5",
    "TRIPLE TWIST": "Triple Twist",
    "PICK 3 ONE PLAY FOR $1": "Pick 3",
    "PICK 3 TWO PLAYS FOR $1": "Pick 3",
    "PICK 4 ONE PLAY FOR $1": "Pick 4",
    "PICK 4 TWO PLAYS FOR $1": "Pick 4",
}


def az_draw_games():
    """Arizona publishes a clean public JSON API for its draw results."""
    try:
        rows = json.loads(get(AZ_API))
    except (urllib.error.URLError, ValueError) as exc:
        print(f"  AZ: draw API failed ({type(exc).__name__})", file=sys.stderr)
        return []

    games = {}
    for row in rows:
        name = AZ_RENAME.get((row.get("gameName") or "").strip().upper())
        if not name:
            continue  # multi-state games are already covered nationally
        numbers = [int(n) for n in re.findall(r"\d+", row.get("winningNumbers") or "")]
        date = (row.get("drawDate") or "")[:10]
        if not numbers or not date:
            continue
        ball = row.get("winningBall") or 0
        draw = {
            "date": date,
            "numbers": numbers,
            "special": int(ball) if ball else None,
            "multiplier": None,
            "label": None,
        }
        entry = games.setdefault(
            name,
            {"id": f"AZ-{name.lower().replace(' ', '')}", "name": name,
             "specialLabel": None, "states": ["AZ"], "draws": []},
        )
        # Both bet-size variants report the same draw; keep it once.
        if not any(d["date"] == date and d["numbers"] == numbers
                   for d in entry["draws"]):
            entry["draws"].append(draw)

    for entry in games.values():
        entry["draws"].sort(key=lambda d: d["date"], reverse=True)
    print(f"  AZ: {len(games)} in-state draw games", file=sys.stderr)
    return list(games.values())


MI_API = "https://www.michiganlottery.com/api"

# Michigan answers a GraphQL query for winning numbers. Daily 3 and Daily 4 are
# drawn twice a day and come back as drawNumbersMid / drawNumbersEve. Its
# jackpot games (Fantasy 5, Lotto 47) use a different selection shape and are
# not covered here.
MI_GAMES = [("DAILY_3", "Daily 3"), ("DAILY_4", "Daily 4")]

MI_QUERY = """query results($logicalGameIdentifier: String, $drawDate: String) {
  winningNumbers: winningNumbers(
    logicalGameIdentifier: $logicalGameIdentifier
    drawDate: $drawDate
  ) {
    resultsPending
    drawNumbersMid
    drawNumbersEve
    __typename
  }
}"""


def mi_draw_games():
    def query(gid, iso_date):
        payload = json.dumps([{
            "operationName": "results",
            "variables": {"logicalGameIdentifier": gid, "drawDate": iso_date},
            "query": MI_QUERY,
        }]).encode()
        request = urllib.request.Request(
            MI_API, data=payload,
            headers={"User-Agent": UA, "Content-Type": "application/json",
                     "Referer": "https://www.michiganlottery.com/results"},
        )
        with urllib.request.urlopen(request, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        return (body[0].get("data") or {}).get("winningNumbers") or {}

    games = []
    for gid, name in MI_GAMES:
        draws = []
        # The query needs an explicit date, and today's draws have not happened
        # until the evening -- so walk back until a day actually has results.
        for offset in range(4):
            day = datetime.now() - timedelta(days=offset)
            try:
                block = query(gid, day.strftime("%Y-%m-%dT23:29:00.000Z"))
            except Exception as exc:  # noqa: BLE001
                print(f"  MI: {name} failed ({type(exc).__name__})", file=sys.stderr)
                break
            for label, key in (("Midday", "drawNumbersMid"),
                               ("Evening", "drawNumbersEve")):
                nums = block.get(key)
                if nums:
                    draws.append({"date": day.strftime("%Y-%m-%d"),
                                  "numbers": [int(n) for n in nums],
                                  "special": None, "multiplier": None,
                                  "label": label})
            if draws:
                break
        if draws:
            games.append({"id": f"MI-{gid.lower()}", "name": name,
                          "specialLabel": None, "states": ["MI"], "draws": draws})
    print(f"  MI: {len(games)} in-state draw games", file=sys.stderr)
    return games


# ------------------------------------------------------- FL in-state draws

FL_RESULTS_PAGE = "https://www.flalottery.com/winningNumbers"

# In-state games only; the multi-state ones are already covered nationally.
# CASH4LIFE is deliberately absent: Florida's own page says the game ended on
# 21 Feb 2026, and its final draw matches the last row of the retired NY feed.
# EZMATCH and DP are add-ons printed on the same ticket, not separate draws.
FL_GAMES = {
    "LOTTO": "Florida Lotto",
    "JACKPOT TRIPLE PLAY": "Jackpot Triple Play",
    "FANTASY 5": "Fantasy 5",
    "CASH POP": "Cash Pop",
    "PICK 2": "Pick 2",
    "PICK 3": "Pick 3",
    "PICK 4": "Pick 4",
    "PICK 5": "Pick 5",
}


def fl_draw_games():
    """Florida's results come from an Azure gateway that rejects unheadered
    requests, so the page is loaded and its own response read back."""
    body = capture_json_page(FL_RESULTS_PAGE, "getLatestDrawGames")
    if not body:
        print("  FL: results API not captured", file=sys.stderr)
        return []
    try:
        rows = json.loads(body)
    except ValueError:
        print("  FL: results API returned non-JSON", file=sys.stderr)
        return []

    games = {}
    for row in rows:
        name = FL_GAMES.get((row.get("GameName") or "").strip().upper())
        if not name:
            continue
        numbers = [
            int(n["NumberPick"]) for n in (row.get("DrawNumbers") or [])
            if str(n.get("NumberType", "")).startswith("wn")
            and n.get("NumberPick") is not None
        ]
        raw_date = (row.get("DrawDate") or "")[:10]
        try:
            date = datetime.strptime(raw_date, "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue
        if not numbers:
            continue

        entry = games.setdefault(name, {
            "id": f"FL-{name.lower().replace(' ', '')}",
            "name": name, "specialLabel": None, "states": ["FL"], "draws": [],
        })
        # Several games draw more than once a day (Cash Pop five times), and
        # the feed carries each as its own row.
        if not any(d["date"] == date and d["numbers"] == numbers
                   for d in entry["draws"]):
            entry["draws"].append({"date": date, "numbers": numbers,
                                   "special": None, "multiplier": None,
                                   "label": None})

    for entry in games.values():
        entry["draws"].sort(key=lambda d: d["date"], reverse=True)
    print(f"  FL: {len(games)} in-state draw games", file=sys.stderr)
    return list(games.values())


# ------------------------------------------------------- MA in-state draws

MA_API = "https://www.masslottery.com/api/v1/draw-results"

MA_GAMES = {
    "megabucks": ("Megabucks Doubler", None),
    "mass_cash": ("Mass Cash", None),
    "mass_3": ("Mass 3", "Wicked Bonus"),
    "mass_4": ("Mass 4", "Wicked Bonus"),
    "the_numbers_game": ("The Numbers Game", None),
}


def ma_draw_games():
    """Massachusetts publishes a clean JSON results endpoint, no browser needed."""
    try:
        payload = json.loads(get(MA_API))
    except (urllib.error.URLError, ValueError) as exc:
        print(f"  MA: results API failed ({type(exc).__name__})", file=sys.stderr)
        return []

    rows = payload.get("winningNumbers", payload if isinstance(payload, list) else [])
    games = {}
    for row in rows:
        config = MA_GAMES.get(row.get("gameIdentifier"))
        if not config:
            continue
        name, special_label = config
        numbers = [int(n) for n in (row.get("winningNumbers") or [])]
        date = (row.get("drawDate") or "")[:10]
        if not numbers or not date:
            continue

        extras = row.get("extras") or {}
        special = extras.get("wickedbonus")

        entry = games.setdefault(name, {
            "id": f"MA-{row['gameIdentifier']}", "name": name,
            "specialLabel": special_label, "states": ["MA"], "draws": [],
        })
        entry["draws"].append({
            "date": date, "numbers": numbers,
            "special": int(special) if special is not None else None,
            "multiplier": None, "label": None,
        })

    for entry in games.values():
        entry["draws"].sort(key=lambda d: d["date"], reverse=True)
    print(f"  MA: {len(games)} in-state draw games", file=sys.stderr)
    return list(games.values())


# --------------------------------------------- shared draw-games platform
#
# Georgia and New Jersey run the same vendor platform, reachable at
# /api/v2/draw-games/draws/ with a plain GET. One adapter covers both, and any
# other state later found on it.

PLATFORM_HOSTS = {
    "GA": "www.galottery.com",
    "NJ": "www.njlottery.com",
}

# The page to load when a direct fetch is refused. It must be the one that asks
# for every game: the site root only requests whichever game it features.
PLATFORM_PAGES = {
    "GA": "https://www.galottery.com/en-us/winning-numbers.html",
    "NJ": "https://www.njlottery.com/en-us/drawgames.html",
}

# Multi-state games are covered nationally; skip them here so they are not
# listed twice with two different sources.
PLATFORM_SKIP = re.compile(
    r"powerball|mega\s*millions|cash\s*4\s*life|cash4life|"
    r"million(aire)?\s*4\s*life|lucky\s*for\s*life|keno|"
    r"all\s*or\s*nothing|five\s*card", re.I)

# Result tokens carry a prefix for anything that is not a main number:
# PB-23 powerball, MB-24 mega ball, CB-04 cash ball, FB-1 fireball,
# BE-05 bonus, B-30 bonus, M-03 multiplier.
PLATFORM_MULTIPLIER = re.compile(r"^M-(\d+)$", re.I)
PLATFORM_SPECIAL = re.compile(r"^(?:PB|MB|CB|FB|BE|B|LB|SB)-(\d+)$", re.I)

# A feed that still lists a game drawn in 2019 is listing a dead game. Cash4Life
# taught this lesson once already; a date cutoff catches the next one without
# needing to know its name.
PLATFORM_MAX_AGE_DAYS = 45


def platform_draw_games(code):
    host = PLATFORM_HOSTS[code]
    url = f"https://{host}/api/v2/draw-games/draws/?previous-draws=1"
    # These hosts rate-limit repeated calls and answer fine a moment later,
    # so a single failure is not a verdict.
    payload = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": UA, "Referer": f"https://{host}/"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 2:
                # New Jersey serves this happily to its own page but 403s a
                # direct client after a few calls. Letting the page fetch it
                # and reading the answer gets past that without pretending to
                # be something we are not.
                print(f"  {code}: direct fetch blocked ({type(exc).__name__}); "
                      "retrying via the page", file=sys.stderr)
                body = fetch_json_via_browser(url)
                if not body:
                    print(f"  {code}: draw API unavailable", file=sys.stderr)
                    return []
                try:
                    payload = json.loads(body)
                except ValueError:
                    print(f"  {code}: draw API returned non-JSON", file=sys.stderr)
                    return []
                break
            time.sleep(2.5 * (attempt + 1))

    cutoff = datetime.now() - timedelta(days=PLATFORM_MAX_AGE_DAYS)
    games, stale = {}, set()

    for entry in payload.get("draws", []):
        name = (entry.get("gameName") or "").strip()
        if not name or PLATFORM_SKIP.search(name):
            continue
        stamp = entry.get("drawTime")
        if not stamp:
            continue
        when = datetime.fromtimestamp(stamp / 1000)
        if when < cutoff:
            stale.add(name)
            continue

        for result in entry.get("results") or []:
            main, special, multiplier = [], None, None
            for token in result.get("primary") or []:
                token = str(token).strip()
                if not token:
                    continue
                if (m := PLATFORM_MULTIPLIER.match(token)):
                    multiplier = str(int(m.group(1))) if int(m.group(1)) else None
                elif (m := PLATFORM_SPECIAL.match(token)):
                    special = int(m.group(1))
                elif token.isdigit():
                    if len(token) > 2:
                        # A concatenated draw ("958" is a whole Pick 3 result).
                        # New Jersey lists several play-type variants this way,
                        # so only the first is the draw -- merging them turned
                        # a Pick 3 into nine numbers.
                        if not main:
                            main = [int(c) for c in token]
                    else:
                        main.append(int(token))
            if not main:
                continue

            title = name.title() if name.isupper() else name
            game = games.setdefault(title, {
                "id": f"{code}-{re.sub(r'[^a-z0-9]', '', title.lower())}",
                "name": title, "specialLabel": None, "states": [code], "draws": [],
            })
            draw = {"date": when.strftime("%Y-%m-%d"), "numbers": main,
                    "special": special, "multiplier": multiplier,
                    "label": (result.get("drawType") or None)}
            if not any(d["date"] == draw["date"] and d["numbers"] == main
                       for d in game["draws"]):
                game["draws"].append(draw)

    for game in games.values():
        game["draws"].sort(key=lambda d: d["date"], reverse=True)
    note = f", {len(stale)} retired dropped" if stale else ""
    print(f"  {code}: {len(games)} in-state draw games{note}", file=sys.stderr)
    return list(games.values())


def ga_draw_games():
    return platform_draw_games("GA")


def nj_draw_games():
    return platform_draw_games("NJ")


# ------------------------------------------------------- OK in-state draws

OK_DRAWS_URL = "https://www.lottery.ok.gov/draws-search"

# The feed identifies games only by number. These were mapped by matching each
# id's latest draw against results already known to be correct: id 16 returned
# Powerball's numbers, 17 Mega Millions, 22 Millionaire for Life. Those three
# are covered nationally, so only the rest are taken here.
#   (name, count of main numbers, whether DbNumber6 is a real special ball)
OK_GAMES = {
    18: ("Lotto America", 5, True),
    19: ("Cash 5", 5, False),
    20: ("Pick 3", 3, False),
}


def ok_draw_games():
    """Oklahoma answers this to a browser but serves HTML to a plain client."""
    body = fetch_json_via_browser(OK_DRAWS_URL)
    if not body:
        print("  OK: draws endpoint unavailable", file=sys.stderr)
        return []
    try:
        payload = json.loads(body)
    except ValueError:
        print("  OK: draws endpoint returned non-JSON", file=sys.stderr)
        return []

    games = {}
    for row in payload.get("Draws", []):
        config = OK_GAMES.get(row.get("Game_Id"))
        if not config:
            continue
        name, count, has_special = config

        stamp = re.search(r"/Date\((\d+)\)/", row.get("DrawDate") or "")
        if not stamp:
            continue
        date = datetime.fromtimestamp(int(stamp.group(1)) / 1000).strftime("%Y-%m-%d")

        numbers = [row.get(f"DbNumber{i}") for i in range(1, count + 1)]
        if any(n is None for n in numbers):
            continue
        # Unused slots are zero-filled rather than omitted, so a real special
        # ball has to be distinguished from padding.
        special = row.get(f"DbNumber{count + 1}") if has_special else None
        if special in (0, None):
            special = None

        entry = games.setdefault(name, {
            "id": f"OK-{re.sub(r'[^a-z0-9]', '', name.lower())}",
            "name": name, "specialLabel": None, "states": ["OK"], "draws": [],
        })
        draw = {"date": date, "numbers": [int(n) for n in numbers],
                "special": int(special) if special else None,
                "multiplier": None, "label": None}
        if not any(d["date"] == date and d["numbers"] == draw["numbers"]
                   for d in entry["draws"]):
            entry["draws"].append(draw)

    for entry in games.values():
        entry["draws"].sort(key=lambda d: d["date"], reverse=True)
    print(f"  OK: {len(games)} in-state draw games", file=sys.stderr)
    return list(games.values())


# ------------------------------------------------------- RI scratch-off state

RI_TRIGGER_PAGE = "https://www.rilot.com/"
RI_API_MARKER = "lotteryservices.net"


def scrape_ri():
    """Rhode Island's game feed is authorised, and only its home page triggers
    the call — the games and instant-games pages do not.

    Amounts arrive in cents, and it publishes the print run outright, so these
    games need no inference for ticket counts.
    """
    bodies = capture_json_pages(RI_TRIGGER_PAGE, RI_API_MARKER, settle_ms=5000)
    payload = None
    for body in bodies:
        try:
            candidate = json.loads(body)
        except ValueError:
            continue
        if candidate.get("games"):
            payload = candidate
            break
    if not payload:
        print("  RI: game feed not captured", file=sys.stderr)
        return []

    raw = payload["games"]
    print(f"  RI: {len(raw)} games in feed", file=sys.stderr)

    games = []
    for entry in raw:
        # ACTIVE is the only selling state; DISABLED and NOT_ACTIVE are games
        # that have finished or not yet launched.
        if entry.get("validationStatus") != "ACTIVE":
            continue

        tiers = []
        for tier in entry.get("prizeTiers") or []:
            total = tier.get("winningTickets")
            paid = tier.get("paidTickets") or 0
            amount = tier.get("prizeAmount")
            if not total or amount is None:
                continue
            tiers.append({
                "value": amount / 100.0,        # cents
                "odds": None,
                "total": int(total),
                "remaining": max(0, int(total) - int(paid)),
            })
        if not tiers:
            continue

        price = entry.get("ticketPrice")
        games.append({
            "id": f"RI-{entry.get('gameId')}",
            "name": (entry.get("gameName") or "").strip().title(),
            "number": str(entry.get("gameId")),
            "price": price / 100.0 if price else None,
            "topPrize": max(t["value"] for t in tiers),
            "overallOdds": money(entry.get("overallOdds")),
            "ticketsPrintedActual": entry.get("totalTicket") or None,
            "tiers": tiers,
            "url": "https://www.rilot.com/en/games/instant-games.html",
        })

    print(f"  RI: {len(games)} active games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- OH in-state draws

OH_RESULTS = "https://www.ohiolottery.com/winning-numbers"

# Multi-state games are covered nationally; Lucky for Life is retired.
OH_SKIP = re.compile(r"powerball|mega\s*millions|lucky\s*for\s*life|"
                     r"million(aire)?\s*for\s*life|keno", re.I)


def oh_draw_games():
    """Ohio renders its results into the page: each is a list item carrying the
    game name, the date and the numbers."""
    html = render_page(OH_RESULTS, settle_ms=4000)
    if not html:
        print("  OH: results page unavailable", file=sys.stderr)
        return []

    games = {}
    # <li class="... winningNumbersItem ..."> <a>Name</a> <span>date</span>
    #   <ul><li>1</li>...</ul>
    for block in re.findall(r'winningNumbersItem.*?</figure>', html, re.S):
        name_match = re.search(r"<a[^>]*>\s*([^<]+?)\s*</a>", block, re.S)
        date_match = re.search(r"<span[^>]*>\s*(\d{2}/\d{2}/\d{4})\s*</span>", block)
        if not name_match or not date_match:
            continue
        name = unescape(name_match.group(1)).strip()
        if not name or OH_SKIP.search(name):
            continue
        try:
            date = datetime.strptime(date_match.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
        except ValueError:
            continue

        entry = games.setdefault(name, {
            "id": f"OH-{re.sub(r'[^a-z0-9]', '', name.lower())}",
            "name": name, "specialLabel": None, "states": ["OH"], "draws": [],
        })

        # Twice-daily games carry both draws in one block, each <ul> preceded
        # by its own MIDDAY/EVENING label. Reading every <li> in the block at
        # once concatenated them into a six-digit "Pick 3".
        for segment in re.findall(r"<ul[^>]*>.*?</ul>", block, re.S):
            numbers = [int(n) for n in
                       re.findall(r"<li[^>]*>\s*(\d{1,2})\s*</li>", segment)]
            if not numbers:
                continue
            before = block[:block.index(segment)]
            label_match = re.findall(r"<span[^>]*>\s*(MIDDAY|EVENING|DAY|NIGHT)\s*</span>",
                                     before, re.I)
            label = label_match[-1].title() if label_match else None

            if not any(d["date"] == date and d["numbers"] == numbers
                       for d in entry["draws"]):
                entry["draws"].append({"date": date, "numbers": numbers,
                                       "special": None, "multiplier": None,
                                       "label": label})

    for entry in games.values():
        entry["draws"].sort(key=lambda d: d["date"], reverse=True)
    print(f"  OH: {len(games)} in-state draw games", file=sys.stderr)
    return list(games.values())


# ------------------------------------------------------- IL in-state draws

IL_RESULTS = "https://www.illinoislottery.com/results-hub"

# slug -> (display name, count of main numbers, trailing ball is a Fireball)
IL_GAMES = {
    "lotto": ("Illinois Lotto", 6, False),
    "luckydaylotto": ("Lucky Day Lotto", 5, False),
    "pick3": ("Pick 3", 3, True),
    "pick4": ("Pick 4", 4, True),
}

# Only groups carrying a date are real results; the others are the same draw
# repeated by a parent container.
IL_SCRIPT = """
() => {
  const out = [];
  document.querySelectorAll('[class*="results-container--"]').forEach(box => {
    const slug = (box.className.match(/results-container--([a-z0-9-]+)/) || [])[1];
    box.querySelectorAll('[class*="results-content-group"]').forEach(grp => {
      const dateEl = grp.querySelector('[class*="results-content__date"]');
      if (!dateEl) return;
      const balls = [...grp.querySelectorAll('[class*="ball"]')]
        .map(b => (b.textContent || '').trim())
        .filter(t => /^\\d{1,2}$/.test(t));
      if (!balls.length) return;
      // Must be the specific evening icon: [class*="eve"] also matches
      // "level", "event", "seven" and would mislabel draws at random.
      const evening = !!grp.querySelector('[class*="illi-icon-eve"]');
      out.push({slug, date: dateEl.textContent.trim(), balls, evening});
    });
  });
  return out;
}
"""


def il_draw_games():
    rows = evaluate_page(IL_RESULTS, IL_SCRIPT)
    if not rows:
        print("  IL: results page unavailable", file=sys.stderr)
        return []

    games = {}
    for row in rows:
        config = IL_GAMES.get(row.get("slug"))
        if not config:
            continue
        name, count, has_fireball = config

        try:
            date = datetime.strptime(row["date"][:11].strip(),
                                     "%b %d %Y").strftime("%Y-%m-%d")
        except ValueError:
            continue

        balls = [int(b) for b in row.get("balls", [])]
        # Illinois Lotto shows three draws in one group; the first is the game.
        main = balls[:count]
        if len(main) < count:
            continue
        special = balls[count] if has_fireball and len(balls) > count else None

        entry = games.setdefault(name, {
            "id": f"IL-{row['slug']}", "name": name,
            "specialLabel": "Fireball" if has_fireball else None,
            "states": ["IL"], "draws": [],
        })
        draw = {"date": date, "numbers": main, "special": special,
                "multiplier": None,
                "label": ("Evening" if row.get("evening") else "Midday")
                         if has_fireball else None}
        if not any(d["date"] == date and d["numbers"] == main
                   for d in entry["draws"]):
            entry["draws"].append(draw)

    for entry in games.values():
        entry["draws"].sort(key=lambda d: d["date"], reverse=True)
    print(f"  IL: {len(games)} in-state draw games", file=sys.stderr)
    return list(games.values())


# ------------------------------------------------------- NH in-state draws

NH_RESULTS = "https://www.nhlottery.com/winning/winning-numbers"

# name -> (count of main numbers, trailing ball is a real special)
NH_GAMES = {
    "Megabucks": (5, True),
    "Gimme 5": (5, False),
    "Pick 3": (3, False),
    "Pick 4": (4, False),
}

# New Hampshire's numbers live in grouped children with no game name nearby;
# the name is only on an image alt several levels up, and the Day/Evening
# marker only in the surrounding text. Reading the DOM is the sole way in.
NH_SCRIPT = """
() => {
  const out = [];
  document.querySelectorAll('[class*="winning-numbers__numbers"]').forEach(el => {
    let p = el, name = '', dateText = '', around = '';
    for (let i = 0; i < 8 && p; i++) {
      p = p.parentElement; if (!p) break;
      if (!name) {
        const h = p.querySelector('img[alt]');
        if (h && h.alt) name = h.alt.replace(/\\s*game icon\\s*/i, '').trim();
      }
      if (!dateText) {
        const d = p.querySelector('[class*="date"],time');
        if (d) dateText = (d.textContent || '').replace(/\\s+/g, ' ').trim();
      }
      if (!around) {
        const t = (p.innerText || '').replace(/\\s+/g, ' ').trim();
        if (t.length > 8) around = t.slice(0, 120);
      }
      if (name && dateText) break;
    }
    const nums = [...el.querySelectorAll('*')]
      .map(k => (k.textContent || '').trim())
      .filter(t => /^\\d{1,2}$/.test(t));
    out.push({name, dateText, around, nums});
  });
  return out;
}
"""


def nh_draw_games():
    rows = evaluate_page(NH_RESULTS, NH_SCRIPT, settle_ms=8000)
    if not rows:
        print("  NH: results page unavailable", file=sys.stderr)
        return []

    games = {}
    for row in rows:
        name = (row.get("name") or "").strip()
        config = NH_GAMES.get(name)
        if not config:
            continue
        count, has_special = config

        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", row.get("dateText") or "")
        if not date_match:
            continue
        raw = date_match.group(1)
        fmt = "%m/%d/%Y" if len(raw.split("/")[-1]) == 4 else "%m/%d/%y"
        try:
            date = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

        numbers = [int(n) for n in row.get("nums", [])]
        main = numbers[:count]
        if len(main) < count:
            continue
        special = numbers[count] if has_special and len(numbers) > count else None

        # Pick 3 and Pick 4 draw twice a day; the marker is only in the text.
        around = row.get("around") or ""
        label = None
        if re.search(r"\bevening\b", around, re.I):
            label = "Evening"
        elif re.search(r"\bday\b", around, re.I):
            label = "Day"

        entry = games.setdefault(name, {
            "id": f"NH-{re.sub(r'[^a-z0-9]', '', name.lower())}",
            "name": name, "specialLabel": "Megaball" if has_special else None,
            "states": ["NH"], "draws": [],
        })
        if not any(d["date"] == date and d["numbers"] == main
                   for d in entry["draws"]):
            entry["draws"].append({"date": date, "numbers": main,
                                   "special": special, "multiplier": None,
                                   "label": label})

    for entry in games.values():
        entry["draws"].sort(key=lambda d: d["date"], reverse=True)
    print(f"  NH: {len(games)} in-state draw games", file=sys.stderr)
    return list(games.values())


# ------------------------------------------------------- WY in-state draws

# Wyoming's "winning numbers" page is a ticket checker, not a results display —
# it asks for your numbers rather than showing the draw. The latest result for
# each game is on that game's own page instead.
WY_GAMES = {
    "cowboy-draw": ("Cowboy Draw", 5),
    "2by2": ("2by2", 4),
}

WY_SCRIPT = """
() => {
  const el = document.querySelector('[class*="game-detail-hero__balls"]');
  const nums = el ? [...el.children].map(k => (k.textContent||'').trim())
                      .filter(t => /^\\d{1,2}$/.test(t)) : [];
  const body = (document.body.innerText || '').replace(/\\s+/g, ' ');
  return {nums, text: body.slice(0, 3000)};
}
"""


def wy_draw_games():
    games = []
    for slug, (name, count) in WY_GAMES.items():
        result = evaluate_page(f"https://wyolotto.com/games/{slug}", WY_SCRIPT,
                               settle_ms=6000)
        if not result:
            continue
        numbers = [int(n) for n in result.get("nums", [])][:count]
        if len(numbers) < count:
            continue

        # The hero shows the latest draw with its date in the surrounding copy.
        text = result.get("text") or ""
        date = None
        match = re.search(
            r"([A-Z][a-z]{2,8}\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})", text)
        if match:
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y", "%m/%d/%Y"):
                try:
                    date = datetime.strptime(match.group(1).replace(".", ""),
                                             fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
        if not date:
            # Without a date the draw cannot be placed, and a wrong date is
            # worse than no game.
            print(f"  WY: {name} has numbers but no readable date", file=sys.stderr)
            continue

        games.append({
            "id": f"WY-{slug.replace('-', '')}", "name": name,
            "specialLabel": None, "states": ["WY"],
            "draws": [{"date": date, "numbers": numbers, "special": None,
                       "multiplier": None, "label": None}],
        })

    print(f"  WY: {len(games)} in-state draw games", file=sys.stderr)
    return games


MONTHS = {m: n for n, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}

# The month must be spelled like a month. An open-ended [A-Za-z]+ here matched
# the word before any number -- "Winning Numbers for 08/22/2026" parsed as
# month "for", day 08, and consumed those digits, so the real date behind them
# never matched and Texas and Maine reported no date at all.
MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
DAY = r"\d{1,2}"
ANY_DATE = (rf"{MONTH}\.?\s+{DAY}(?:\s*,?\s*\d{{4}})?"
            r"|\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|\d{4}-\d{2}-\d{2}")

# "Next Drawing Monday, August 24" sits beside the result on half these pages,
# and on the day of a draw that date is not in the future -- so any rule based
# on "the latest date that has already happened" picks the wrong one. Cut the
# next-draw notice, and exactly the one date it names, before reading dates.
NEXT_DRAW_RE = re.compile(
    r"next\s+draw(?:ing)?\b[^0-9A-Za-z]{0,8}"
    r"(?:[A-Za-z]{3,9}day,?\s*)?"                 # optional weekday
    rf"(?:{ANY_DATE}|tonight|today)?", re.I)

# These pages run a date straight into the numbers behind it. Kansas prints
# "Aug 22" and then the balls, giving "Aug 22133154576523" -- so the year may
# only follow a real separator, or "1331" becomes the year and the draw lands
# in the fourteenth century. The day itself gets no such guard: it genuinely
# does butt up against the digits. A two-digit year gets none either, because
# South Dakota's "08.22.26" is followed by its balls the same way.
DATE_RE = re.compile(
    rf"(?P<month>{MONTH})\.?\s+(?P<day>{DAY})"
    rf"(?:(?:\s*,\s*|\s+)(?P<year>\d{{4}})(?!\d))?"
    r"|(?P<m>\d{1,2})[/.](?P<d>\d{1,2})[/.](?P<y>\d{4}(?!\d)|\d{2})"
    # Iowa dates its draws "8/24" and leaves the year off entirely. Must come
    # after the full form above, or it would claim the month and day of every
    # complete date and leave the year dangling.
    r"|(?P<m2>\d{1,2})/(?P<d2>\d{1,2})(?![\d/])"
    r"|(?P<iso>\d{4}-\d{2}-\d{2})", re.I)


def date_from_text(text, today=None):
    """The most recent draw date named in a blob of surrounding page copy.

    Written against what these pages actually print, which is messier than it
    looks: months arrive shouted ("SUN/AUG 23"), the year is often left off
    entirely ("Sunday, August 23"), and results pages list many draws at once.
    So: strip the next-draw notice, read every date, drop anything still in the
    future, and take the newest of what remains.

    A draw without a date cannot be placed in time, and a *wrong* date is worse
    than no game -- it shows a stale draw as tonight's result. Callers drop the
    game when this returns None rather than assuming today.
    """
    today = today or datetime.now(timezone.utc).date()
    found = []

    for match in DATE_RE.finditer(NEXT_DRAW_RE.sub(" ", text or "")):
        try:
            if match.group("iso"):
                candidate = datetime.strptime(match.group("iso"), "%Y-%m-%d").date()
            elif match.group("m"):
                year = int(match.group("y"))
                year += 2000 if year < 100 else 0
                candidate = date(year, int(match.group("m")), int(match.group("d")))
            elif match.group("m2"):
                # No year at all: the most recent time this date came round.
                month, day = int(match.group("m2")), int(match.group("d2"))
                candidate = date(today.year, month, day)
                if candidate > today:
                    candidate = date(today.year - 1, month, day)
            else:
                month = MONTHS.get(match.group("month")[:3].lower())
                if not month:
                    continue
                day = int(match.group("day"))
                if match.group("year"):
                    candidate = date(int(match.group("year")), month, day)
                else:
                    # No year printed. Assume the most recent time this date
                    # occurred, which is this year unless that is still ahead.
                    candidate = date(today.year, month, day)
                    if candidate > today:
                        candidate = date(today.year - 1, month, day)
        except ValueError:
            continue
        if candidate <= today:
            found.append(candidate)

    return max(found).strftime("%Y-%m-%d") if found else None


# Find every element whose children are all short numbers, with enough
# surrounding text to date it. Deliberately structural: these ten states share
# no markup and half of them put the balls in elements with no class at all, so
# there is nothing to anchor a selector to. What they do share is the shape.
BALLS_SCRIPT = """
() => {
  const isNum = t => /^\\d{1,2}$/.test((t || '').trim());
  const flat = el => (el.textContent || '').replace(/\\s+/g, ' ').trim();
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    const kids = [...el.children];
    if (kids.length < 3 || kids.length > 24) return;
    const nums = kids.filter(k => isNum(k.textContent));
    if (nums.length < 3 || nums.length < kids.length - 1) return;
    // Text at each level up the tree. The date is rarely a sibling of the
    // balls, and stopping at a fixed depth either misses it or overshoots
    // into the page body, where a tag-manager blob crowds it out.
    const texts = [];
    let ctx = el;
    for (let i = 0; i < 7 && ctx; i++) {
      texts.push(flat(ctx).slice(0, 300));
      ctx = ctx.parentElement;
    }
    out.push({
      nums: nums.map(n => n.textContent.trim()),
      cls: [el.className, el.id, el.parentElement ? el.parentElement.className : '']
             .join(' ').toString().slice(0, 120),
      texts: texts
    });
  });
  return out.slice(0, 30);
}
"""

# Each entry: page URL -> the games that page carries, as (slug, name, count).
# `count` includes any bonus ball, because the page renders it in the same row.
# Several states publish two or three games on one page, so the page is the
# key: one load, several games.
PER_GAME = {
    "CA": [
        ("https://www.calottery.com/en/draw-games/superlotto-plus",
         [("superlotto", "SuperLotto Plus", 5, r"(\d{1,2})\s+Superball|Mega,?\s*#?(\d{1,2})", None)]),
        ("https://www.calottery.com/en/draw-games/fantasy-5",
         [("fantasy5", "Fantasy 5", 5, None, None)]),
        ("https://www.calottery.com/en/draw-games/daily-4",
         [("daily4", "Daily 4", 4, None, None)]),
        ("https://www.calottery.com/en/draw-games/daily-3",
         [("daily3", "Daily 3", 3, None, None)]),
    ],
    "CO": [
        ("https://www.coloradolottery.com/en/games/lotto/",
         [("lotto", "Colorado Lotto+", 6, None, None)]),
        ("https://www.coloradolottery.com/en/games/cash5/",
         [("cash5", "Cash 5", 5, None, None)]),
        ("https://www.coloradolottery.com/en/games/pick3/",
         [("pick3", "Pick 3", 3, None, None)]),
    ],
    "ME": [
        ("https://www.mainelottery.com/games/megabucksplus.shtml",
         [("megabucks", "Megabucks Plus", 6, None, None)]),
        ("https://www.mainelottery.com/games/gimme5.html",
         [("gimme5", "Gimme 5", 5, None, None)]),
    ],
    "MD": [
        ("https://www.mdlottery.com/games/pick-3-pick-4-pick-5/",
         [("pick3", "Pick 3", 3, None, None), ("pick4", "Pick 4", 4, None, None),
          ("pick5", "Pick 5", 5, None, None)]),
        ("https://www.mdlottery.com/games/bonus-match-5/",
         [("bonusmatch5", "Bonus Match 5", 6, None, None)]),
        ("https://www.mdlottery.com/games/multi-match/",
         [("multimatch", "Multi-Match", 6, None, None)]),
    ],
    "PA": [
        ("https://www.palottery.pa.gov/Draw-Games/PICK-2.aspx",
         [("pick2", "PICK 2", 3, None, None)]),
        ("https://www.palottery.pa.gov/Draw-Games/PICK-3.aspx",
         [("pick3", "PICK 3", 4, None, None)]),
        ("https://www.palottery.pa.gov/Draw-Games/PICK-4.aspx",
         [("pick4", "PICK 4", 5, None, None)]),
        ("https://www.palottery.pa.gov/Draw-Games/PICK-5.aspx",
         [("pick5", "PICK 5", 6, None, None)]),
        ("https://www.palottery.pa.gov/Draw-Games/Cash-5.aspx",
         [("cash5", "Cash 5", 5, None, None)]),
        ("https://www.palottery.pa.gov/Draw-Games/Match-6.aspx",
         [("match6", "Match 6", 6, None, None)]),
        ("https://www.palottery.pa.gov/Draw-Games/Treasure-Hunt.aspx",
         [("treasurehunt", "Treasure Hunt", 5, None, None)]),
    ],
    "SC": [
        ("https://www.sceducationlottery.com/Games/Pick3",
         [("pick3", "Pick 3", 4, None, None)]),
        ("https://www.sceducationlottery.com/Games/Pick4",
         [("pick4", "Pick 4", 5, None, None)]),
        ("https://www.sceducationlottery.com/Games",
         [("palmettocash5", "Palmetto Cash 5", 5, None, None)]),
    ],
    "TX": [
        ("https://www.texaslottery.com/export/sites/lottery/Games/Lotto_Texas/index.html",
         [("lottotexas", "Lotto Texas", 6, None, None)]),
        ("https://www.texaslottery.com/export/sites/lottery/Games/Texas_Two_Step/index.html",
         [("twostep", "Texas Two Step", 5, None, None)]),
        ("https://www.texaslottery.com/export/sites/lottery/Games/Cash_Five/index.html",
         [("cash5", "Cash Five", 5, None, None)]),
        ("https://www.texaslottery.com/export/sites/lottery/Games/Pick_3/index.html",
         [("pick3", "Pick 3", 3, None, None)]),
        ("https://www.texaslottery.com/export/sites/lottery/Games/Daily_4/index.html",
         [("daily4", "Daily 4", 4, None, None)]),
    ],
    # Vermont is deliberately absent. Its game pages carry only the site's
    # number generator -- random picks rendered exactly like a result row --
    # and every results URL it advertises 404s, on a page that helpfully
    # renders "404" as three balls. There is no result here to read.
    # Six states publish every game on one results page rather than on the
    # games' own pages. That is the same shape as far as this table is
    # concerned -- one URL, several games -- except that a shared row length
    # no longer identifies a game, so these lean on the name hint.
    "AR": [
        ("https://www.arkansasscholarshiplottery.com/winning-numbers", [
            ("cash3mid", "Cash 3 Midday", 3, None, r"Cash 3 Midday"),
            ("cash3eve", "Cash 3 Evening", 3, None, r"Cash 3 Evening"),
            ("cash4mid", "Cash 4 Midday", 4, None, r"Cash 4 Midday"),
            ("cash4eve", "Cash 4 Evening", 4, None, r"Cash 4 Evening"),
            ("naturalstate", "Natural State Jackpot", 5, None, r"Natural State"),
        ]),
    ],
    "MN": [
        ("https://www.mnlottery.com/winning-numbers", [
            ("gopher5", "Gopher 5", 5, None, r"Gopher 5"),
            ("north5", "Northstar Cash", 5, None, r"North 5|Northstar"),
            ("pick3", "Pick 3", 3, None, r"Pick 3"),
        ]),
    ],
    "IN": [
        ("https://hoosierlottery.com/winning-numbers", [
            # Hoosier Lotto is not here on purpose: the page labels the
            # site-wide Powerball widget with its name, so the only six-number
            # row on offer is Powerball's.
            ("cash5", "CA$H 5", 5, None, r"CA\$H\s*5|Cash 5"),
        ]),
    ],
    "KY": [
        ("https://www.kylottery.com/apps/draw_games/index.html", [
            ("cashball", "Cash Ball 225", 5, None, None),
            ("pick4", "Pick 4", 4, None, None),
            ("pick3", "Pick 3", 3, None, None),
        ]),
    ],
    "SD": [
        ("https://lottery.sd.gov/winning-numbers/",
         [("dakotacash", "Dakota Cash", 5, None, None)]),
    ],
    "DC": [
        ("https://dclottery.com/winning-numbers", [
            ("dc4", "DC-4", 4, None, None),
            ("dc3", "DC-3", 3, None, None),
        ]),
    ],
    # Louisiana is deliberately absent. Its results page names no game beside
    # the numbers, and twenty-five of its rows are historical Powerball draws,
    # so there is nothing to match a game against except the row length -- and
    # two of its games are five numbers.
    # Connecticut was the long holdout. Its results were behind a search form
    # that returned nothing to the DOM -- on ctlottery.org, which is not where
    # the lottery lives any more. The site is ctlottery.com, its games render
    # plainly, and the form never needed solving. Play 3 and Play 4 each draw
    # twice a day and carry a Lucky Ball, so their rows run one longer than
    # the game's name suggests.
    "CT": [
        ("https://ctlottery.com/games/draw-games/lotto",
         [("lotto", "CT Lotto", 6, None, None)]),
        ("https://ctlottery.com/games/draw-games/cash5",
         [("cash5", "Cash5", 5, None, None)]),
        ("https://ctlottery.com/games/draw-games/play4", [
            ("play4day", "Play4 Day", 5, None, r"Drawing\s*DAY:"),
            ("play4night", "Play4 Night", 5, None, r"NIGHT:"),
        ]),
        ("https://ctlottery.com/games/draw-games/play3", [
            ("play3day", "Play3 Day", 4, None, r"Drawing\s*DAY:"),
            ("play3night", "Play3 Night", 4, None, r"NIGHT:"),
        ]),
    ],
    "OR": [
        ("https://www.oregonlottery.org/jackpot/megabucks/",
         [("megabucks", "Megabucks", 6, None, None)]),
        ("https://www.oregonlottery.org/jackpot/win-for-life/",
         [("winforlife", "Win for Life", 4, None, None)]),
        # Pick 4's page prints its whole prize table as worked examples, which
        # look exactly like draws. They carry no date, which is what rules
        # them out.
        ("https://www.oregonlottery.org/jackpot/pick-4/",
         [("pick4", "Pick 4", 4, None, None)]),
    ],
    "MT": [
        ("https://montanalottery.com/montana-cash/",
         [("montanacash", "Montana Cash", 5, None, None)]),
        ("https://montanalottery.com/big-sky-bonus/",
         [("bigskybonus", "Big Sky Bonus", 4, None, None)]),
    ],
    # Iowa lists midday and evening side by side under one heading, so both
    # draws share the surrounding text and only the first can be dated
    # correctly. That first row is the latest draw, which is what is wanted
    # here; splitting them would mean dating the evening draw from the
    # midday's date.
    "IA": [
        ("https://ialottery.com/Pages/WinningNumbers/WinningNumbers_Main.aspx", [
            ("pick4", "Pick 4", 4, None, None),
            ("pick3", "Pick 3", 3, None, None),
        ]),
    ],
    "ID": [
        ("https://www.idaholottery.com/games/draw/idaho-cash",
         [("idahocash", "Idaho Cash", 5, None, None)]),
        ("https://www.idaholottery.com/games/draw/pick-4",
         [("pick4", "Pick 4", 4, None, None)]),
        ("https://www.idaholottery.com/games/draw/pick-3",
         [("pick3", "Pick 3", 3, None, None)]),
    ],
    "MO": [
        ("https://www.molottery.com/show-me-cash/winning-numbers.do",
         [("showmecash", "Show Me Cash", 5, None, None)]),
        ("https://www.molottery.com/pick4/winning-numbers.do",
         [("pick4", "Pick 4", 4, None, None)]),
        ("https://www.molottery.com/pick3/winning-numbers.do",
         [("pick3", "Pick 3", 3, None, None)]),
    ],
    "MS": [
        ("https://www.mslottery.com/games/mm5/",
         [("match5", "Mississippi Match 5", 5, None, None)]),
    ],
    "RI": [
        ("https://www.rilot.com/content/interactive/ilottery/en/winning-numbers/wild-money.html",
         [("wildmoney", "Wild Money", 5, None, None)]),
    ],
    # Louisiana, Virginia and Indiana are deliberately absent. Their game pages
    # render only the site-wide Powerball and Mega Millions widget, never the
    # game's own draw -- so a six-number game like Hoosier Lotto would match
    # the Powerball row and publish it under the wrong name. Better to have no
    # entry than a confidently wrong one.
    "WA": [
        ("https://www.walottery.com/JackpotGames/Lotto.aspx",
         [("lotto", "Lotto", 6, None, None)]),
        ("https://www.walottery.com/JackpotGames/Hit5.aspx",
         [("hit5", "Hit 5", 5, None, None)]),
        ("https://www.walottery.com/JackpotGames/Match4.aspx",
         [("match4", "Match 4", 4, None, None)]),
        ("https://www.walottery.com/JackpotGames/Pick3.aspx",
         [("pick3", "Pick 3", 3, None, None)]),
    ],
    "WI": [
        ("https://wilottery.com/games/megabucks",
         [("megabucks", "Megabucks", 6, None, None)]),
        ("https://wilottery.com/games/supercash",
         [("supercash", "SuperCash!", 6, None, None)]),
        ("https://wilottery.com/games/badger-5", [("badger5", "Badger 5", 5, None, None)]),
        ("https://wilottery.com/games/pick-4", [("pick4", "Pick 4", 4, None, None)]),
        ("https://wilottery.com/games/pick-3", [("pick3", "Pick 3", 3, None, None)]),
    ],
}


_PER_GAME_ROWS = None


def _per_game_rows():
    """Every per-game page, loaded once and in parallel.

    These forty-odd pages span ten states and none of them depends on another,
    so loading them one at a time turned a one-minute job into a ten-minute
    one. The whole batch is fetched on the first call and reused by every
    state's adapter afterwards.
    """
    global _PER_GAME_ROWS
    if _PER_GAME_ROWS is None:
        urls = [url for entries in PER_GAME.values() for url, _ in entries]
        started = time.time()
        _PER_GAME_ROWS = parallel.evaluate_many(urls, BALLS_SCRIPT,
                                                settle_ms=6000, concurrency=6)
        loaded = sum(1 for rows in _PER_GAME_ROWS.values() if rows)
        print(f"  per-game: {loaded}/{len(urls)} pages in "
              f"{time.time() - started:.0f}s", file=sys.stderr)
    return _PER_GAME_ROWS


# Several of these sites offer a "pick numbers for me" widget that renders its
# output exactly like a result row. Vermont's sits on every game page under
# numGenBallContainer, and its numbers are random -- publishing them as winning
# numbers would be worse than publishing nothing.
GENERATOR_RE = re.compile(r"numgen|number-?gen|generator|quick-?pick|random",
                          re.I)


# A latest-draw date more than seven weeks old is a misread, not a result.
# Indiana's page dated a row 2025-08-25 -- a year stale -- because the year was
# not printed and the day had not yet arrived this year, so it rolled back.
# Every game here draws at least weekly, so nothing legitimate lands outside
# this window.
STALE_DAYS = 50


# The draws every state shows anyway. A state page that renders the site-wide
# Powerball widget alongside its own games will offer that row to any
# six-number game asking for one -- Indiana's "Hoosier Lotto" matched the
# Powerball draw this way, name hint and all, and would have shipped it under
# the wrong name. Nothing in-state may repeat a national result.
MULTISTATE_DRAWS: set = set()


def remember_multistate(game):
    for draw in game.get("draws") or []:
        numbers = draw.get("numbers") or []
        if numbers:
            MULTISTATE_DRAWS.add(tuple(numbers))


def _is_sequence(numbers):
    """A run of consecutive numbers is a number picker, not a draw.

    Pennsylvania's Cash Pop page renders its 1-20 selector exactly the way a
    ball row is rendered, and it sits above the results.
    """
    return len(numbers) >= 4 and all(
        b - a == 1 for a, b in zip(numbers, numbers[1:]))


def per_game_draw_games(code):
    """Latest draw for states that publish results on each game's own page.

    Wyoming turned out this way -- its winning-numbers page is a ticket checker
    and the actual numbers live on the game pages. That layout is the rule, not
    the exception, and it sidesteps the search forms and date pickers that made
    the central results pages so hard to read.
    """
    games = []
    for url, entries in PER_GAME[code]:
        rows = _per_game_rows().get(url)
        if not rows:
            # Some pages build their ball rows late enough that the batch pass
            # saw an empty shell. One slower retry costs a few seconds and is
            # the difference between four games and none.
            rows = evaluate_page(url, BALLS_SCRIPT, settle_ms=12000)
        if not rows:
            print(f"  {code}: nothing rendered at {url}", file=sys.stderr)
            continue

        used = set()
        for slug, name, count, pattern, hint in entries:
            undated = generated = stale = borrowed = 0
            for index, row in enumerate(rows):
                if index in used or len(row.get("nums") or []) != count:
                    continue
                if GENERATOR_RE.search(row.get("cls") or ""):
                    generated += 1
                    continue
                # A results page carries every game at once, and several of
                # them share a row length -- Minnesota's North 5 and Gopher 5
                # are both five numbers. Where the page names the game beside
                # the balls, that name is what identifies it, not the count.
                if hint and not any(re.search(hint, text, re.I)
                                    for text in row.get("texts") or []):
                    continue
                numbers = [int(n) for n in row["nums"]]
                if _is_sequence(numbers) or tuple(numbers) in MULTISTATE_DRAWS:
                    borrowed += 1
                    continue
                # Walk outwards until a level names a date. The nearest one
                # usually holds only the digits; the outermost is the whole
                # page, where the real date is buried past anything useful.
                drawn_on = next(
                    (found for text in row.get("texts") or []
                     if (found := date_from_text(text))), None)
                if not drawn_on:
                    undated += 1
                    continue
                age = (datetime.now(timezone.utc).date()
                       - datetime.strptime(drawn_on, "%Y-%m-%d").date()).days
                if age > STALE_DAYS:
                    stale += 1
                    continue
                special = None
                if pattern:
                    match = re.search(pattern, " ".join(row.get("texts") or []))
                    if match:
                        special = int(next(g for g in match.groups() if g))
                used.add(index)
                games.append({
                    "id": f"{code}-{slug}", "name": name,
                    "specialLabel": None, "states": [code],
                    "draws": [{"date": drawn_on, "numbers": numbers,
                               "special": special, "multiplier": None,
                               "label": None}],
                })
                break
            else:
                reason = (f"{undated} row(s) carried no readable date" if undated
                          else f"{generated} generator row(s), no result row"
                          if generated
                          else f"{stale} row(s) dated over {STALE_DAYS}d ago"
                          if stale
                          else f"{borrowed} row(s) were a national draw"
                          if borrowed else f"no {count}-number row")
                print(f"  {code}: {reason} for {name}", file=sys.stderr)

    print(f"  {code}: {len(games)} in-state draw games", file=sys.stderr)
    return games



# ---------------------------------------------------------------- text games
#
# Some states print the draw as running text rather than as one element per
# ball -- Virginia's page reads "Sun 8/23/2026 Winning Numbers 3 13 17 27 37",
# and North Dakota lays 2by2 out as a table of hyphenated pairs. The
# structural detector cannot see any of it, because there is no structure: the
# numbers are words in a sentence. These are matched by a pattern written
# against the page's own wording, with named groups for the date and numbers.

TEXT_SCRIPT = "() => (document.body.innerText || '').replace(/\\s+/g, ' ')"

TEXT_GAMES = {
    "VA": [
        ("https://www.valottery.com/data/draw-games/cash5", [
            ("cash5", "Cash 5", 5,
             r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*Winning Numbers\s*"
             r"(?P<nums>(?:\d{1,2}\s+){4}\d{1,2})(?!\s*\d)", None),
        ]),
        # Virginia's daily games all carry a FIREBALL, and its date is
        # labelled DAY or NIGHT, so the row runs one longer than the name.
        ("https://www.valottery.com/Data/Draw-Games/Pick3", [
            ("pick3", "Pick 3", 4,
             r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*Winning Numbers\s*"
             r"(?:DAY|NIGHT):\s*(?P<nums>(?:\d\s+){3}\d)\s*FIREBALL", None),
        ]),
        ("https://www.valottery.com/Data/Draw-Games/Pick4", [
            ("pick4", "Pick 4", 5,
             r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*Winning Numbers\s*"
             r"(?:DAY|NIGHT):\s*(?P<nums>(?:\d\s+){4}\d)\s*FIREBALL", None),
        ]),
        ("https://www.valottery.com/Data/Draw-Games/Pick5", [
            ("pick5", "Pick 5", 6,
             r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*Winning Numbers\s*"
             r"(?:DAY|NIGHT):\s*(?P<nums>(?:\d\s+){5}\d)\s*FIREBALL", None),
        ]),
        ("https://www.valottery.com/Data/Draw-Games/BankAMillion", [
            ("bankamillion", "Bank a Million", 7,
             r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s*Winning Numbers\s*"
             r"(?P<nums>(?:\d{1,2}\s+){6}\d{1,2})\s*Bonus Ball", None),
        ]),
    ],
    # Louisiana lists every game on every game's page, in the same order, so
    # position identifies nothing and two of its games are five numbers. What
    # does identify them is the prize line printed after each: Pick 5 pays up
    # to $50,000, Pick 4 up to $5,000, Pick 3 up to $500.
    "LA": [
        ("https://louisianalottery.com/draw-games/pick-3/", [
            ("pick5", "Pick 5", 5,
             r"View Latest Draw:\s*(?P<date>[A-Za-z]+ \d{1,2}, \d{4})\s*"
             r"(?P<nums>[\d ]+?)\s*Drawings Every Day Up To \$50,000", None),
            ("pick4", "Pick 4", 4,
             r"View Latest Draw:\s*(?P<date>[A-Za-z]+ \d{1,2}, \d{4})\s*"
             r"(?P<nums>[\d ]+?)\s*Drawings Every Day Up To \$5,000", None),
            ("pick3", "Pick 3", 3,
             r"View Latest Draw:\s*(?P<date>[A-Za-z]+ \d{1,2}, \d{4})\s*"
             r"(?P<nums>[\d ]+?)\s*Drawings Every Day Up To \$500", None),
        ]),
    ],
    "KS": [
        ("https://playonkansas.com/games/draw-games/pick-3", [
            ("pick3day", "Pick 3 Afternoon", 3,
             r"Past Afternoon Draws Date Draw Numbers\s*"
             r"(?P<date>[A-Za-z]+ \d{1,2}, \d{4})\s*(?P<nums>\d \d \d)", None),
            ("pick3eve", "Pick 3 Evening", 3,
             r"Past Evening Draws Date Draw Numbers\s*"
             r"(?P<date>[A-Za-z]+ \d{1,2}, \d{4})\s*(?P<nums>\d \d \d)", None),
        ]),
        ("https://playonkansas.com/games/draw-games/2-by-2", [
            ("2by2", "2by2", 4,
             r"LAST DRAW\s*[A-Za-z]+\.?,?\s*(?P<date>[A-Za-z]+ \d{1,2}, \d{4})"
             r"\s*\$[\d,]+\s*(?P<nums>\d{1,2} \d{1,2} \d{1,2} \d{1,2})", None),
        ]),
    ],
    # Nebraska puts all four of its games on one page, each under its own
    # heading, so the heading is what the pattern anchors to. MyDaY draws a
    # month, a day and a year rather than three numbers in a range, which is
    # why its figures run past 31.
    "NE": [
        ("https://nelottery.com/homeapp/lotto/drawresults/web", [
            ("pick5", "Nebraska Pick 5", 5,
             r"Pick 5 Numbers Date Numbers\s*(?P<date>\d{2}/\d{2}/\d{4})\s*"
             r"(?P<nums>(?:\d{2}, ){4}\d{2})", None),
            ("2by2", "2by2", 4,
             r"2by2 Numbers Date Red White\s*(?P<date>\d{2}/\d{2}/\d{4})\s*"
             r"(?P<nums>\d{2}, \d{2} \d{2}, \d{2})", None),
            ("pick3", "Pick 3", 3,
             r"Pick 3 Numbers Date Numbers\s*(?P<date>\d{2}/\d{2}/\d{4})\s*"
             r"(?P<nums>(?:\d{2}, ){2}\d{2})", None),
            ("myday", "MyDaY", 3,
             r"MyDaY Numbers Date Month Day Year\s*(?P<date>\d{2}/\d{2}/\d{4})"
             r"\s*(?P<nums>\d{2} \d{2} \d{2})", None),
        ]),
    ],
    # West Virginia renders each number twice, once as the accessible label
    # and once as the text, so these say how to pick one out of each pair.
    "WV": [
        ("https://wvlottery.com/games/draw-games/daily-3", [
            ("daily3", "Daily 3", 3,
             r"Last Draw.{0,40}?Draw Date [A-Za-z]+, (?P<date>[A-Za-z]+ \d{1,2}),"
             r".{0,20}?(?P<nums>(?:Draw Number, \d{1,2} \d{1,2} ?){3})",
             r"Draw Number, (\d{1,2}) \d{1,2}"),
        ]),
        ("https://wvlottery.com/games/draw-games/daily-4", [
            ("daily4", "Daily 4", 4,
             r"Last Draw.{0,40}?Draw Date [A-Za-z]+, (?P<date>[A-Za-z]+ \d{1,2}),"
             r".{0,20}?(?P<nums>(?:Draw Number, \d{1,2} \d{1,2} ?){4})",
             r"Draw Number, (\d{1,2}) \d{1,2}"),
        ]),
        ("https://wvlottery.com/games/draw-games/cash-25", [
            ("cash25", "Cash 25", 6,
             r"Last Draw.{0,40}?Draw Date [A-Za-z]+, (?P<date>[A-Za-z]+ \d{1,2}),"
             r".{0,20}?(?P<nums>(?:Draw Number, \d{1,2} \d{1,2} ?){6})",
             r"Draw Number, (\d{1,2}) \d{1,2}"),
        ]),
    ],
    "ND": [
        ("https://www.lottery.nd.gov/public/games/TwoByTwoWinningNumbers", [
            ("2by2", "2by2", 4,
             r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+"
             r"(?P<nums>\d{1,2}-\d{1,2}\s+\d{1,2}-\d{1,2})", None),
        ]),
    ],
}


def text_draw_games(code):
    games = []
    for url, entries in TEXT_GAMES[code]:
        text = _text_pages().get(url)
        if not text:
            text = evaluate_page(url, TEXT_SCRIPT, settle_ms=9000)
        if not text:
            print(f"  {code}: nothing rendered at {url}", file=sys.stderr)
            continue

        for slug, name, count, pattern, num_re in entries:
            match = re.search(pattern, text, re.I)
            if not match:
                print(f"  {code}: {name} not found in page text", file=sys.stderr)
                continue
            # West Virginia prints every number twice -- once as the
            # accessible label, once as the text -- so a game may say how its
            # own numbers are picked out of the matched run.
            numbers = [int(n) for n in re.findall(num_re or r"\d{1,2}",
                                                  match.group("nums"))]
            if len(numbers) != count:
                print(f"  {code}: {name} matched {len(numbers)} numbers, "
                      f"expected {count}", file=sys.stderr)
                continue
            if tuple(numbers) in MULTISTATE_DRAWS:
                print(f"  {code}: {name} matched a national draw", file=sys.stderr)
                continue
            drawn_on = date_from_text(match.group("date"))
            if not drawn_on:
                continue
            age = (datetime.now(timezone.utc).date()
                   - datetime.strptime(drawn_on, "%Y-%m-%d").date()).days
            if age > STALE_DAYS:
                continue
            games.append({
                "id": f"{code}-{slug}", "name": name, "specialLabel": None,
                "states": [code],
                "draws": [{"date": drawn_on, "numbers": numbers,
                           "special": None, "multiplier": None, "label": None}],
            })

    print(f"  {code}: {len(games)} in-state draw games", file=sys.stderr)
    return games


_TEXT_PAGES = None


def _text_pages():
    """Every text-game page, loaded once and in parallel."""
    global _TEXT_PAGES
    if _TEXT_PAGES is None:
        urls = [url for entries in TEXT_GAMES.values() for url, _ in entries]
        _TEXT_PAGES = parallel.evaluate_many(urls, TEXT_SCRIPT, settle_ms=8000,
                                             concurrency=6)
    return _TEXT_PAGES


# New Mexico serves its results from a different host than its website. The
# pages on nmlottery.com are shells: the numbers arrive in an iframe pointed at
# nmlotterydynamic.sks.com, so reading the page body returns furniture and
# nothing else, however long you wait for it. The iframe's own URL answers a
# plain HTTP request with a few hundred bytes of clean markup and needs no
# browser at all -- the fastest source of any state here.
NM_ROOT = "https://nmlotterydynamic.sks.com/rts/games"
NM_GAMES = {
    "roadrunnercash": ("Roadrunner Cash", 5),
    "pick4plus": ("Pick 4 Plus", 4),
    "pick3plus": ("Pick 3 Plus", 3),
}


def nm_draw_games():
    games = []
    for slug, (name, count) in NM_GAMES.items():
        try:
            html = get(f"{NM_ROOT}/{slug}/drawresults.aspx")
        except urllib.error.URLError as exc:
            print(f"  NM: {name} unreachable ({exc})", file=sys.stderr)
            continue

        block = re.search(r'<ul class="winning-numbers">(.*?)</ul>', html, re.S)
        if not block:
            print(f"  NM: {name} published no numbers", file=sys.stderr)
            continue
        numbers = [int(n) for n in re.findall(r"<li>\s*(\d{1,2})\s*</li>",
                                              block.group(1))]
        if len(numbers) != count:
            print(f"  NM: {name} gave {len(numbers)} numbers, expected {count}",
                  file=sys.stderr)
            continue

        date_match = re.search(r'<span class="date">([^<]+)</span>', html)
        drawn_on = date_from_text(date_match.group(1)) if date_match else None
        if not drawn_on:
            print(f"  NM: {name} has numbers but no readable date",
                  file=sys.stderr)
            continue

        games.append({
            "id": f"NM-{slug}", "name": name, "specialLabel": None,
            "states": ["NM"],
            "draws": [{"date": drawn_on, "numbers": numbers, "special": None,
                       "multiplier": None, "label": None}],
        })

    print(f"  NM: {len(games)} in-state draw games", file=sys.stderr)
    return games


def nc_payouts():
    """State-level winner counts per match tier for the latest NC draw.

    Only some states publish these; NC does, keyed to the draw date shown on
    the page, so the app can tie counts to the draw it is already displaying.
    """
    out = {}
    for game_id, path in (("powerball", "/powerball"), ("megamillions", "/mega-millions")):
        try:
            html = get(NC_ROOT + path)
        except urllib.error.URLError:
            continue

        date_match = re.search(r'class="drawdate"[^>]*>([^<]+)', html)
        draw_date = None
        if date_match:
            try:
                parsed = datetime.strptime(
                    date_match.group(1).split(", ", 1)[1].strip(), "%b %d, %Y"
                )
                draw_date = parsed.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Powerball renders Match/Prize/Wins; Mega Millions inserts a Megaplier
        # column. Read the header row so the columns are located, not assumed.
        table = None
        for candidate in re.findall(r"<table.*?</table>", html, re.S):
            headers = [
                re.sub(r"<[^>]+>", "", h).strip().lower()
                for h in re.findall(r"<th[^>]*>(.*?)</th>", candidate, re.S)
            ]
            if "match" in headers and "wins" in headers:
                table = candidate
                prize_col = headers.index("prize")
                wins_col = headers.index("wins")
                break
        if not table:
            continue

        tiers = []
        for row in re.findall(r"<tr>(.*?)</tr>", table, re.S):
            label = re.search(r'aria-label="([^"]+)"', row)
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if not label or len(cells) <= max(prize_col, wins_col):
                continue

            # Base value comes first; <br/>-separated multiplier values follow.
            def first(cell):
                text = re.sub(r"<br\s*/?>.*", "", cell, flags=re.S)
                return unescape(re.sub(r"<[^>]+>", "", text)).strip()

            prize, wins = money(first(cells[prize_col])), money(first(cells[wins_col]))
            if wins is None:
                continue
            tiers.append(
                {"match": label.group(1), "prize": prize, "winners": int(wins)}
            )

        if tiers:
            out[game_id] = {"drawDate": draw_date, "tiers": tiers}
    return out


# ------------------------------------------------------- LA scratch-off state

LA_API = "https://louisianalottery.com/wp-json/wp/v2/instant-game"


def la_game_list():
    games, page = [], 1
    while True:
        rows = json.loads(get(f"{LA_API}?per_page=100&page={page}"))
        if not rows:
            break
        games.extend(
            {"title": unescape(r["title"]["rendered"]), "url": r["link"]} for r in rows
        )
        if len(rows) < 100:
            break
        page += 1
    return games


def la_parse_game(entry):
    html = get(entry["url"])
    # Louisiana prints the value first and its label second, so tokenize the
    # visible text and read backwards from each label.
    tokens = [
        t.strip()
        for t in re.split(r"<[^>]+>", html)
        if t.strip() and len(t.strip()) < 60
    ]

    def before(label):
        for i, tok in enumerate(tokens):
            if tok.lower() == label.lower() and i > 0:
                return tokens[i - 1]
        return None

    tiers = []
    table = re.search(r"<table.*?</table>", html, re.S)
    if table:
        for row in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S):
            cells = [
                unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            if len(cells) < 5:
                continue
            value, odds, total, _claimed, left = cells[:5]
            v, t, r = money(value), money(total), money(left)
            if v is None or t is None or r is None or t <= 0:
                continue
            odds_match = re.search(r"1 in ([\d,.]+)", odds)
            tiers.append(
                {
                    "value": v,
                    "odds": money(odds_match.group(1)) if odds_match else None,
                    "total": int(t),
                    "remaining": int(r),
                }
            )

    if not tiers:
        return None

    # Titles arrive as "1689 - Fire/Ice"; split the game number off the front.
    title = re.sub(r"\s*[-–—]\s*", " - ", entry["title"], count=1)
    num_match = re.match(r"(\d+)\s*-\s*(.+)", title)
    number = num_match.group(1) if num_match else None
    name = (num_match.group(2) if num_match else title).strip()

    odds_text = before("Overall Odds") or ""
    odds_val = re.search(r"1 in ([\d,.]+)", odds_text)

    # Louisiana keeps expired games online with their final prize tables. Those
    # tables look great -- an unclaimed top prize against almost no inventory --
    # but the tickets cannot be bought or redeemed, so they must not be ranked.
    expired = re.search(r"This game expired on ([^<.]+)", html)
    close_date = re.search(r"Close Date:\s*([^<]+?)\s*<", html)
    redeem_date = re.search(r"Final Redemption Date:\s*([^<]+?)\s*<", html)

    return {
        "id": f"LA-{number or name}",
        "name": name,
        "number": number,
        "price": money(before("Ticket Price")),
        "topPrize": money(before("Top Prize")),
        "overallOdds": money(odds_val.group(1)) if odds_val else None,
        "tiers": tiers,
        "url": entry["url"],
        "expired": bool(expired),
        "closeDate": close_date.group(1).strip() if close_date else None,
        "finalRedemption": redeem_date.group(1).strip() if redeem_date else None,
    }


def scrape_la():
    entries = la_game_list()
    print(f"  LA: {len(entries)} games listed", file=sys.stderr)
    games = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(la_parse_game, entries):
            if result:
                games.append(result)
    print(f"  LA: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- NM scratch-off state

NM_URL = "https://www.nmlottery.com/games/scratchers/"


def scrape_nm():
    """New Mexico publishes every active game, with its prize table, on one page."""
    html = get(NM_URL)
    blocks = html.split('<div class="filter-block">')[1:]
    print(f"  NM: {len(blocks)} blocks found", file=sys.stderr)

    games = []
    for block in blocks:
        name_match = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        table_match = re.search(r"<table.*?</table>", block, re.S)
        if not name_match or not table_match:
            continue
        name = unescape(re.sub(r"<[^>]+>", "", name_match.group(1))).strip()
        if not name:
            continue

        tiers = []
        for row in re.findall(r"<tr>(.*?)</tr>", table_match.group(0), re.S):
            cells = [
                unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            if len(cells) < 4:
                continue
            value, odds, total, left = cells[:4]
            v, t, r = money(value), money(total), money(left)
            if v is None or t is None or r is None or t <= 0:
                continue
            tiers.append(
                {"value": v, "odds": money(odds), "total": int(t), "remaining": int(r)}
            )
        if not tiers:
            continue

        top = re.search(r'class="top-prize"[^>]*>.*?Top Prize:\s*([^<]+)', block, re.S)
        price = re.search(r'class="price"[^>]*>\s*([^<]+)', block)
        odds = re.search(r"overall odds of winning[^:]*:\s*1 in ([\d.,]+)", block, re.I)

        games.append(
            {
                "id": f"NM-{name}",
                "name": name,
                "number": None,
                "price": money(unescape(price.group(1))) if price else None,
                "topPrize": money(unescape(top.group(1))) if top else None,
                "overallOdds": money(odds.group(1)) if odds else None,
                "tiers": tiers,
                "url": NM_URL,
            }
        )

    print(f"  NM: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- SC scratch-off state

SC_ROOT = "https://www.sceducationlottery.com"


def sc_game_ids():
    html = get(f"{SC_ROOT}/Games/InstantGames")
    return sorted(set(re.findall(r"/Games/InstantGame\?gameId=(\d+)", html)))


def sc_parse_game(game_id):
    html = get(f"{SC_ROOT}/Games/InstantGame?gameId={game_id}")
    tokens = [
        re.sub(r"\s+", " ", unescape(t)).strip()
        for t in re.split(r"<[^>]+>", html)
        if t.strip()
    ]

    def after(label):
        for i, tok in enumerate(tokens[:-1]):
            if tok.lower().rstrip(":") == label.lower():
                return tokens[i + 1]
        return None

    title = re.search(r"<title>\s*Scratch-Off - (.*?)\s*\(Game #", html, re.S)
    if not title:
        return None
    name = unescape(title.group(1)).strip()

    # South Carolina reports counts and values but no per-tier odds, so the
    # print run has to come from the game's overall odds instead.
    tiers = []
    table = re.search(r"<table.*?</table>", html, re.S)
    if table:
        for row in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S):
            cells = [
                unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            if len(cells) < 4:
                continue
            v, left, total = money(cells[0]), money(cells[1]), money(cells[3])
            if v is None or total is None or left is None or total <= 0:
                continue
            tiers.append(
                {"value": v, "odds": None, "total": int(total), "remaining": int(left)}
            )
    if not tiers:
        return None

    odds_text = after("Overall Odds") or ""
    odds_match = re.search(r"1 in ([\d.,]+)", odds_text)

    return {
        "id": f"SC-{game_id}",
        "name": name,
        "number": game_id,
        "price": money(after("Price")),
        "topPrize": max(t["value"] for t in tiers),
        "overallOdds": money(odds_match.group(1)) if odds_match else None,
        "tiers": tiers,
        "url": f"{SC_ROOT}/Games/InstantGame?gameId={game_id}",
    }


def scrape_sc():
    ids = sc_game_ids()
    print(f"  SC: {len(ids)} games listed", file=sys.stderr)
    games = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(sc_parse_game, ids):
            if result:
                games.append(result)
    print(f"  SC: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- WA scratch-off state

WA_URL = "https://www.walottery.com/scratch"


def scrape_wa():
    """Washington embeds its whole catalogue as JSON, including the print run.

    That last part matters: every other state here forces the run to be inferred
    from published odds, and Washington just states it.
    """
    html = get(WA_URL)
    match = re.search(r"JSON\.parse\('(.*?)'\)\s*[,;}]", html, re.S)
    if not match:
        print("  WA: embedded JSON not found", file=sys.stderr)
        return []

    payload = json.loads(match.group(1).encode().decode("unicode_escape"))
    raw_games = payload.get("Games", [])
    print(f"  WA: {len(raw_games)} games in payload", file=sys.stderr)

    today = datetime.now()
    games = []
    for entry in raw_games:
        tiers = []
        for prize in entry.get("Prizes", []):
            value = money(prize.get("PrizeAmount"))
            total = prize.get("TotalPrizesNumber")
            left = prize.get("PrizesRemainingNumber")
            if value is None or not total or left is None:
                continue
            tiers.append(
                {"value": value, "odds": None, "total": int(total), "remaining": int(left)}
            )
        if not tiers:
            continue

        odds_match = re.search(r"1 in ([\d.,]+)", entry.get("OverallOdds") or "")

        # A past redemption deadline means the game is finished.
        expired = False
        redeem = (entry.get("RedeemEndDate") or "").strip()
        if redeem:
            for fmt in ("%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    expired = datetime.strptime(redeem[:19], fmt) < today
                    break
                except ValueError:
                    continue

        games.append(
            {
                "id": f"WA-{entry.get('Id')}",
                "name": (entry.get("GameName") or "").strip().title(),
                "number": str(entry.get("Id")) if entry.get("Id") else None,
                "price": float(entry["Cost"]) if entry.get("Cost") else None,
                "topPrize": max(t["value"] for t in tiers),
                "overallOdds": money(odds_match.group(1)) if odds_match else None,
                "ticketsPrintedActual": money(entry.get("TicketsPrinted")),
                "tiers": tiers,
                "url": WA_URL,
                "expired": expired,
                "finalRedemption": redeem or None,
            }
        )

    print(f"  WA: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- MS scratch-off state

MS_API = "https://www.mslotteryhome.com/wp-json/wp/v2"


def scrape_ms():
    """Mississippi serves each game's prize table inside its WP REST content.

    No odds are published, so these games get a ratio but no absolute return.
    """
    # Ticket price lives in a taxonomy; resolve the term ids to numbers once.
    prices = {}
    try:
        for term in json.loads(get(f"{MS_API}/gamevalue?per_page=100")):
            value = money(term.get("name"))
            if value:
                prices[term["id"]] = value
    except (urllib.error.URLError, ValueError):
        pass

    # Mississippi keeps ended games in the feed with their final prize tables --
    # 169 of 253 at time of writing. Ranking those would surface dead games with
    # unclaimed top prizes, exactly the Louisiana problem.
    statuses = {}
    try:
        for term in json.loads(get(f"{MS_API}/gamestatus?per_page=100")):
            statuses[term["id"]] = (term.get("name") or "").strip().lower()
    except (urllib.error.URLError, ValueError):
        pass

    # The host is slow and intermittently times out; take what pages we can get
    # rather than losing the whole state to one bad request.
    entries, page = [], 1
    while page <= 10:
        try:
            rows = json.loads(get(f"{MS_API}/instantgames?per_page=50&page={page}"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            print(f"  MS: page {page} failed ({type(exc).__name__})", file=sys.stderr)
            break
        if not rows:
            break
        entries.extend(rows)
        if len(rows) < 50:
            break
        page += 1
    print(f"  MS: {len(entries)} games listed", file=sys.stderr)

    games = []
    for entry in entries:
        html = entry.get("content", {}).get("rendered", "")
        tiers = []
        for row in re.findall(r"<tr>(.*?)</tr>", html, re.S):
            cells = [
                unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            ]
            if len(cells) < 3:
                continue
            value, total, left = money(cells[0]), money(cells[1]), money(cells[2])
            if value is None or total is None or left is None or total <= 0:
                continue
            tiers.append(
                {"value": value, "odds": None, "total": int(total), "remaining": int(left)}
            )
        if not tiers:
            continue

        price = next(
            (prices[t] for t in entry.get("gamevalue", []) if t in prices), None
        )
        status = next(
            (statuses[t] for t in entry.get("gamestatus", []) if t in statuses), None
        )
        games.append(
            {
                "id": f"MS-{entry['id']}",
                "name": unescape(entry.get("title", {}).get("rendered", "")).strip(),
                "number": None,
                "price": price,
                "topPrize": max(t["value"] for t in tiers),
                "overallOdds": None,
                "tiers": tiers,
                "url": entry.get("link"),
                "expired": status == "ended",
                "status": status,
            }
        )

    print(f"  MS: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- IN scratch-off state
# First state requiring a browser: the game list and prize tables are both
# rendered client-side, so plain HTTP sees an empty shell.

IN_INDEX = "https://www.hoosierlottery.com/scratch-offs"


def scrape_in():
    index = render_page(IN_INDEX, settle_ms=2000)
    if not index:
        print("  IN: skipped (no browser)", file=sys.stderr)
        return []

    links, seen = [], set()
    for href in re.findall(r'href="(/games/scratch-off/[^"?#]+)"', index):
        if href not in seen:
            seen.add(href)
            links.append("https://www.hoosierlottery.com" + href)
    print(f"  IN: {len(links)} games listed", file=sys.stderr)

    games = []
    for url in links:
        html = render_page(url, settle_ms=1200)
        if not html:
            continue
        tiers = tiers_from_table(html)
        if not tiers:
            continue

        # Strip scripts and styles first: their contents otherwise match the
        # label patterns below and yield JavaScript fragments as game names.
        body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", "\n", body)

        def label(pattern):
            match = re.search(pattern, text, re.I)
            return unescape(match.group(1)).strip() if match else None

        # Headed by "2629 - $100,000 GOLD BAR".
        heading = re.search(r"^\s*(\d{3,5})\s*-\s*([^\n]{3,60})$", text, re.M)
        name = (heading.group(2).strip() if heading else url.rsplit("/", 1)[-1]).title()
        games.append(
            {
                "id": f"IN-{heading.group(1) if heading else name}",
                "name": name,
                "number": heading.group(1) if heading else None,
                "price": money(label(r"Ticket Price:\s*\$?([\d.,]+)")),
                "topPrize": money(label(r"Top Prize:\s*\$?([\d.,]+)")),
                # Indiana lists only the upper prize tiers -- a $5 game at 1 in
                # 3.98 has hundreds of thousands of small prizes it never shows.
                # Combining the published overall odds with a truncated tier
                # list yields a print run ~10x too small and returns near 450%,
                # so no print run is derived at all. The ratio still works: it
                # measures the published pool draining, consistently within the
                # state, and the board only ever ranks one state at a time.
                "overallOdds": None,
                "partialTiers": True,
                "tiers": tiers,
                "url": url,
            }
        )

    print(f"  IN: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- VA scratch-off state
# Virginia paginates its catalogue entirely client-side: `?page=2` returns the
# first page, so the only way to reach the rest is to press the pager buttons.

VA_ROOT = "https://www.valottery.com"
VA_SEARCH = f"{VA_ROOT}/Scratcher-Search"


VA_PRICES = (1, 2, 3, 5, 10, 20, 30, 50)


def va_game_ids():
    """Enumerate Virginia's catalogue through its price filters.

    The pager is client-side and has to be clicked, which proved flaky: it
    yielded 52 of ~86 games. The price filters are plain URLs and between them
    cover everything -- checked against the category filters (new, closingSoon,
    promotional, extraChances), which added no games the price sweep missed.
    """
    ids = set()
    for price in VA_PRICES:
        html = render_page(f"{VA_SEARCH}?price={price}", settle_ms=2500)
        if not html:
            print(f"  VA: price {price} did not load", file=sys.stderr)
            continue
        found = set(re.findall(r'href="/scratchers/(\d+)"', html))
        print(f"  VA: ${price} -> {len(found)} games (+{len(found - ids)})",
              file=sys.stderr)
        ids |= found

    # Unfiltered first page, in case a game carries no price facet.
    first = render_page(VA_SEARCH, settle_ms=2500)
    if first:
        ids |= set(re.findall(r'href="/scratchers/(\d+)"', first))

    return sorted(ids)


def va_parse_game(game_id):
    url = f"{VA_ROOT}/scratchers/{game_id}"
    html = render_page(url, settle_ms=2000)
    if not html:
        return None
    tiers = tiers_from_table(html)
    if not tiers:
        return None

    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", body)
    text = re.sub(r"[ \t]+", " ", text)

    def after(label, pattern=r"([^\n]+)"):
        match = re.search(rf"{label}\s*\n*\s*{pattern}", text, re.I)
        return unescape(match.group(1)).strip() if match else None

    # "<title>$173,000,000 Extravaganza Scratcher #2143 | Virginia Lottery"
    title = re.search(r"<title>([^<]*)</title>", html, re.S)
    name = f"Game {game_id}"
    if title:
        name = re.sub(
            r"\s*Scratcher\s*#\d+.*$|\s*\|.*$", "", unescape(title.group(1))
        ).strip() or name

    odds_text = after(r"Odds of Winning Overall:\s*1 in", r"([\d.,]+)")

    return {
        "id": f"VA-{game_id}",
        "name": name,
        "number": str(game_id),
        "price": money(after(r"Ticket Price", r"\$?([\d.,]+)")),
        "topPrize": max(t["value"] for t in tiers),
        "overallOdds": money(odds_text) if odds_text else None,
        "tiers": tiers,
        "url": url,
    }


def scrape_va():
    ids = va_game_ids()
    if not ids:
        print("  VA: skipped (no browser)", file=sys.stderr)
        return []
    print(f"  VA: {len(ids)} games listed", file=sys.stderr)

    games = []
    for game_id in ids:
        parsed = va_parse_game(game_id)
        if parsed:
            games.append(parsed)
    print(f"  VA: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- OK scratch-off state

OK_URL = "https://www.lottery.ok.gov/scratchers/remaining-prizes"


def scrape_ok():
    """Oklahoma lists every game and its full prize table on one page.

    It publishes no ticket price and no odds anywhere, so these games carry a
    value ratio but no return percentage or ticket counts -- the ratio needs
    only prize counts, which is exactly what makes this state usable at all.
    """
    html = render_page(OK_URL, settle_ms=2500)
    if not html:
        print("  OK: skipped (no browser)", file=sys.stderr)
        return []

    # Each game is introduced by "#866 MONSTER MONEY" ahead of its table.
    marks = [m for m in re.finditer(r"#(\d+)\s+([A-Z0-9][^<]{2,50})", html)]
    print(f"  OK: {len(marks)} game blocks", file=sys.stderr)

    games = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(html)
        chunk = html[mark.start():end]
        tiers = tiers_from_table(chunk)
        if not tiers:
            continue
        games.append(
            {
                "id": f"OK-{mark.group(1)}",
                "name": unescape(mark.group(2)).strip().title(),
                "number": mark.group(1),
                "price": None,
                "topPrize": max(t["value"] for t in tiers),
                "overallOdds": None,
                "tiers": tiers,
                "url": OK_URL,
            }
        )
    print(f"  OK: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- MD scratch-off state

MD_URL = "https://www.mdlottery.com/games/scratch-offs/"


def scrape_md():
    """Maryland renders every game and prize table onto one page, via JS.

    Blocks are introduced by "<h3>Prizes: <span>Extreme Green</span></h3>", with
    the overall odds stated just above as "Probability of Winning: 1 in 3.14".
    """
    html = render_page(MD_URL, settle_ms=3500)
    if not html:
        print("  MD: skipped (no browser)", file=sys.stderr)
        return []

    marks = list(
        re.finditer(r"<h3[^>]*>\s*Prizes:\s*<span[^>]*>(.*?)</span>\s*</h3>", html, re.S)
    )
    print(f"  MD: {len(marks)} game blocks", file=sys.stderr)

    games = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(html)
        chunk = html[mark.start():end]
        tiers = tiers_from_table(chunk)
        if not tiers:
            continue
        name = unescape(re.sub(r"<[^>]+>", "", mark.group(1))).strip()
        if not name:
            continue

        # Odds are printed above the heading, so look back a little.
        preceding = html[max(0, mark.start() - 1500):mark.start()]
        odds = re.search(r"Probability of Winning:\s*<strong>\s*1 in ([\d.,]+)",
                         preceding, re.I)
        price = re.search(r"\$(\d+)\s*(?:Ticket|Game)|Ticket Price[^\d$]*\$?(\d+)",
                          preceding, re.I)

        games.append(
            {
                "id": f"MD-{name}",
                "name": name,
                "number": None,
                "price": money(price.group(1) or price.group(2)) if price else None,
                "topPrize": max(t["value"] for t in tiers),
                "overallOdds": money(odds.group(1)) if odds else None,
                "tiers": tiers,
                "url": MD_URL,
            }
        )
    print(f"  MD: {len(games)} games parsed", file=sys.stderr)
    return games


# ------------------------------------------------------- CA scratch-off state

CA_ROOT = "https://www.calottery.com"


def scrape_ca():
    """California links games as /scratchers/$20/name-1739 -- price in the URL."""
    index = render_page(f"{CA_ROOT}/scratchers", settle_ms=3000)
    if not index:
        print("  CA: skipped (no browser)", file=sys.stderr)
        return []

    links = sorted(set(re.findall(r'href="(/scratchers/\$\d+/[^"]+)"', index)))
    print(f"  CA: {len(links)} games listed", file=sys.stderr)

    games = []
    for path in links:
        html = render_page(CA_ROOT + path, settle_ms=2000)
        if not html:
            continue
        tiers = tiers_from_table(html)
        if not tiers:
            continue

        price = re.search(r"/scratchers/\$(\d+)/", path)
        number = re.search(r"-(\d+)/?$", path)
        title = re.search(r"<title>([^<]*)</title>", html, re.S)
        name = path.rsplit("/", 1)[-1]
        if title:
            name = re.split(r"\s*\|", unescape(title.group(1)))[0].strip() or name

        games.append(
            {
                "id": f"CA-{number.group(1) if number else name}",
                "name": name,
                "number": number.group(1) if number else None,
                "price": money(price.group(1)) if price else None,
                "topPrize": max(t["value"] for t in tiers),
                "overallOdds": None,
                "tiers": tiers,
                "url": CA_ROOT + path,
            }
        )
    print(f"  CA: {len(games)} games parsed", file=sys.stderr)
    return games


STATES = {
    "NC": {
        "name": "North Carolina",
        "scraper": scrape_nc,
        "payouts": nc_payouts,
        "drawGames": nc_draw_games,
    },
    "LA": {"name": "Louisiana", "scraper": scrape_la, "payouts": None,
           "drawGames": functools.partial(text_draw_games, "LA")},
    "AZ": {"name": "Arizona", "scraper": None, "payouts": None,
           "drawGames": az_draw_games},
    "MI": {"name": "Michigan", "scraper": None, "payouts": None,
           "drawGames": mi_draw_games},
    "FL": {"name": "Florida", "scraper": None, "payouts": None,
           "drawGames": fl_draw_games},
    "MA": {"name": "Massachusetts", "scraper": None, "payouts": None,
           "drawGames": ma_draw_games},
    "GA": {"name": "Georgia", "scraper": None, "payouts": None,
           "drawGames": ga_draw_games},
    "NJ": {"name": "New Jersey", "scraper": None, "payouts": None,
           "drawGames": nj_draw_games},
    "RI": {"name": "Rhode Island", "scraper": scrape_ri, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "RI")},
    "OH": {"name": "Ohio", "scraper": None, "payouts": None,
           "drawGames": oh_draw_games},
    "IL": {"name": "Illinois", "scraper": None, "payouts": None,
           "drawGames": il_draw_games},
    "NH": {"name": "New Hampshire", "scraper": None, "payouts": None,
           "drawGames": nh_draw_games},
    "WY": {"name": "Wyoming", "scraper": None, "payouts": None,
           "drawGames": wy_draw_games},
    "NM": {"name": "New Mexico", "scraper": scrape_nm, "payouts": None,
           "drawGames": nm_draw_games},
    "SC": {
        "name": "South Carolina",
        "scraper": scrape_sc,
        "payouts": None,
        "drawGames": functools.partial(per_game_draw_games, "SC"),
    },
    "WA": {"name": "Washington", "scraper": scrape_wa, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "WA")},
    "MS": {"name": "Mississippi", "scraper": scrape_ms, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "MS")},
    "IN": {"name": "Indiana", "scraper": scrape_in, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "IN")},
    "VA": {"name": "Virginia", "scraper": scrape_va, "payouts": None,
           "drawGames": functools.partial(text_draw_games, "VA")},
    "OK": {"name": "Oklahoma", "scraper": scrape_ok, "payouts": None,
           "drawGames": ok_draw_games},
    "MD": {"name": "Maryland", "scraper": scrape_md, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "MD")},
    "CA": {"name": "California", "scraper": scrape_ca, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "CA")},
    "ID": {"name": "Idaho", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "ID")},
    "MO": {"name": "Missouri", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "MO")},
    "AR": {"name": "Arkansas", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "AR")},
    "MN": {"name": "Minnesota", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "MN")},
    "KY": {"name": "Kentucky", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "KY")},
    "SD": {"name": "South Dakota", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "SD")},
    "DC": {"name": "District of Columbia", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "DC")},
    "CT": {"name": "Connecticut", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "CT")},
    "OR": {"name": "Oregon", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "OR")},
    "MT": {"name": "Montana", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "MT")},
    "IA": {"name": "Iowa", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "IA")},
    "ND": {"name": "North Dakota", "scraper": None, "payouts": None,
           "drawGames": functools.partial(text_draw_games, "ND")},
    "KS": {"name": "Kansas", "scraper": None, "payouts": None,
           "drawGames": functools.partial(text_draw_games, "KS")},
    "NE": {"name": "Nebraska", "scraper": None, "payouts": None,
           "drawGames": functools.partial(text_draw_games, "NE")},
    "WV": {"name": "West Virginia", "scraper": None, "payouts": None,
           "drawGames": functools.partial(text_draw_games, "WV")},
    "CO": {"name": "Colorado", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "CO")},
    "ME": {"name": "Maine", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "ME")},
    "PA": {"name": "Pennsylvania", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "PA")},
    "TX": {"name": "Texas", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "TX")},
    "WI": {"name": "Wisconsin", "scraper": None, "payouts": None,
           "drawGames": functools.partial(per_game_draw_games, "WI")},
}


def keep_known_games(fresh, known):
    """Carry forward a game this run did not return.

    Georgia's draw API is volatile: between draws it briefly stops returning
    the previous result, so a game that is perfectly healthy disappears for a
    scrape or two and takes its last draw with it. Dropping it makes the game
    vanish from the app entirely until the next draw lands.

    A draw already scraped is still a real draw, correctly dated -- it just
    was not re-confirmed this time. Kept only while it is inside the staleness
    window, so a genuinely retired game still ages out rather than lingering
    for ever.
    """
    have = {game["id"] for game in fresh}
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=STALE_DAYS)
    carried = []
    for game in known or []:
        if game.get("id") in have:
            continue
        draws = game.get("draws") or []
        if not draws:
            continue
        try:
            when = datetime.strptime(draws[0]["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError, TypeError):
            continue
        if when >= cutoff:
            carried.append(game)
    return fresh + carried


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Scrape lottery data into Data/lottery.json.",
        epilog="Scraping every state takes a while, mostly waiting on the "
               "browser-rendered ones. Draw results are quick and universal, "
               "so --core alone refreshes what every user sees in seconds.",
    )
    parser.add_argument(
        "--core", action="store_true",
        help="draw games only; skip scratch-offs entirely (fast)",
    )
    parser.add_argument(
        "--only", metavar="CODES",
        help="comma-separated states to refresh, e.g. --only VA,CA. "
             "Everything else is carried over from the previous run.",
    )
    parser.add_argument(
        "--skip", metavar="CODES",
        help="comma-separated states to leave untouched, e.g. --skip VA,CA",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # Refreshing a subset must not discard the rest, so start from whatever the
    # last run produced and overwrite only what is being scraped now.
    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text())
        except (ValueError, OSError):
            previous = {}

    bundle = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "drawGames": [],
        "states": dict(previous.get("states", {})),
    }

    only = {c.strip().upper() for c in args.only.split(",")} if args.only else None
    skip = {c.strip().upper() for c in args.skip.split(",")} if args.skip else set()

    print("draw games:", file=sys.stderr)
    for key, cfg in SODA.items():
        game = fetch_draw_game(key, cfg)
        remember_multistate(game)
        bundle["drawGames"].append(game)
        print(f"  {game['name']}: {len(game['draws'])} draws", file=sys.stderr)

    # In-state draw games are cheap API/page reads, so they belong in the fast
    # path alongside the national ones -- only scratch-off scraping is slow.
    print("in-state draw games:", file=sys.stderr)
    for code, cfg in STATES.items():
        if not cfg["drawGames"] or (only is not None and code not in only) or code in skip:
            continue
        try:
            state_draws = cfg["drawGames"]()
        except Exception as exc:  # noqa: BLE001
            print(f"  {code}: draw games FAILED ({type(exc).__name__})", file=sys.stderr)
            continue
        entry = bundle["states"].setdefault(
            code, {"name": cfg["name"], "scratchers": [], "payouts": {}}
        )
        entry["name"] = cfg["name"]
        merged = keep_known_games(state_draws, entry.get("drawGames"))
        if len(merged) > len(state_draws):
            print(f"  {code}: kept {len(merged) - len(state_draws)} game(s) "
                  "this run did not return", file=sys.stderr)
        entry["drawGames"] = merged

    if args.core:
        print("scratch-offs: skipped (--core)", file=sys.stderr)
        STATES_TO_RUN = {}
    else:
        STATES_TO_RUN = {
            code: cfg for code, cfg in STATES.items()
            if (only is None or code in only) and code not in skip
        }
        carried = [c for c in STATES if c not in STATES_TO_RUN and c in bundle["states"]]
        if carried:
            print(f"scratch-offs: carrying over {', '.join(sorted(carried))}",
                  file=sys.stderr)

    print("scratch-offs:", file=sys.stderr)
    failures = []
    for code, cfg in STATES_TO_RUN.items():
        # One state's flaky host must not cost the whole bundle: a transient
        # connection reset used to abort the run and publish nothing.
        try:
            # Some states contribute draw games only and have no scratch-off
            # adapter; they still need their drawGames collected below.
            scraped = cfg["scraper"]() if cfg["scraper"] else []
            live = [g for g in scraped if not g.get("expired")]
            dropped = len(scraped) - len(live)
            # Enrichment must sit inside the guard too: a bug here used to kill
            # the whole run at Mississippi, discarding six states already
            # scraped, which is exactly what the guard exists to prevent.
            games = [g for g in (enrich(x) for x in live) if g]
        except Exception as exc:  # noqa: BLE001
            print(f"  {code}: FAILED ({type(exc).__name__}: {exc})", file=sys.stderr)
            failures.append(code)
            continue
        games.sort(key=lambda g: g.get("ratio") or 0, reverse=True)
        payouts = cfg["payouts"]() if cfg["payouts"] else {}
        state_draws = (bundle["states"].get(code) or {}).get("drawGames", [])
        bundle["states"][code] = {
            "name": cfg["name"],
            "scratchers": games,
            "payouts": payouts,
            "drawGames": state_draws,
        }
        print(
            f"  {code}: {len(games)} live ({dropped} expired dropped), "
            f"{len(payouts)} payout tables, {len(state_draws)} in-state games",
            file=sys.stderr,
        )

    close_browser()

    if failures:
        print(f"\nstates that failed: {', '.join(failures)}", file=sys.stderr)
        # Keep whatever the previous run captured for a failed state rather than
        # silently shrinking the bundle; validation still guards what ships.
        if OUT.exists():
            try:
                previous = json.loads(OUT.read_text())
                for code in failures:
                    stale = previous.get("states", {}).get(code)
                    if stale:
                        stale["stale"] = True
                        bundle["states"][code] = stale
                        print(f"  {code}: kept previous data", file=sys.stderr)
            except (ValueError, OSError):
                pass

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, indent=1))
    print(f"\nwrote {OUT} ({OUT.stat().st_size:,} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
