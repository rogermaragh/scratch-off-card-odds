#!/usr/bin/env python3
"""Fetch lottery data and emit the normalized JSON bundle the app reads.

Draw games come from New York's open-data SODA endpoints (no key required).
Scratch-off inventories are scraped per state; each state needs its own
adapter because no two lottery sites agree on anything.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
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

SODA = {
    "powerball": {
        "resource": "d6yy-54nr",
        "name": "Powerball",
        "special_label": "Powerball",
        "special_in_numbers": True,
    },
    "megamillions": {
        "resource": "5xaw-6ayf",
        "name": "Mega Millions",
        "special_label": "Mega Ball",
        "special_in_numbers": False,
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
        nums = [int(n) for n in row.get("winning_numbers", "").split()]
        if cfg["special_in_numbers"]:
            if len(nums) < 6:
                continue
            main, special = nums[:5], nums[5]
        else:
            special_raw = row.get("mega_ball")
            if not special_raw or len(nums) < 5:
                continue
            main, special = nums[:5], int(special_raw)
        draws.append(
            {
                "date": row["draw_date"][:10],
                "numbers": main,
                "special": special,
                "multiplier": row.get("multiplier"),
            }
        )
    return {
        "id": key,
        "name": cfg["name"],
        "specialLabel": cfg["special_label"],
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
        "overallOdds": money(label("Overall Odds")),
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
    "LA": {"name": "Louisiana", "scraper": scrape_la, "payouts": None, "drawGames": None},
    "NM": {"name": "New Mexico", "scraper": scrape_nm, "payouts": None, "drawGames": None},
    "SC": {
        "name": "South Carolina",
        "scraper": scrape_sc,
        "payouts": None,
        "drawGames": None,
    },
    "WA": {"name": "Washington", "scraper": scrape_wa, "payouts": None, "drawGames": None},
    "MS": {"name": "Mississippi", "scraper": scrape_ms, "payouts": None, "drawGames": None},
    "IN": {"name": "Indiana", "scraper": scrape_in, "payouts": None, "drawGames": None},
    "VA": {"name": "Virginia", "scraper": scrape_va, "payouts": None, "drawGames": None},
    "OK": {"name": "Oklahoma", "scraper": scrape_ok, "payouts": None, "drawGames": None},
    "MD": {"name": "Maryland", "scraper": scrape_md, "payouts": None, "drawGames": None},
    "CA": {"name": "California", "scraper": scrape_ca, "payouts": None, "drawGames": None},
}


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
        bundle["drawGames"].append(game)
        print(f"  {game['name']}: {len(game['draws'])} draws", file=sys.stderr)

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
            scraped = cfg["scraper"]()
        except Exception as exc:  # noqa: BLE001
            print(f"  {code}: FAILED ({type(exc).__name__}: {exc})", file=sys.stderr)
            failures.append(code)
            continue
        live = [g for g in scraped if not g.get("expired")]
        dropped = len(scraped) - len(live)
        games = [g for g in (enrich(x) for x in live) if g]
        games.sort(key=lambda g: g.get("ratio") or 0, reverse=True)
        payouts = cfg["payouts"]() if cfg["payouts"] else {}
        state_draws = cfg["drawGames"]() if cfg["drawGames"] else []
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
