#!/usr/bin/env python3
"""Hunt for a scrapeable scratch-off source in every remaining state.

For each state it tries a list of candidate paths, and for anything running
WordPress it also probes the REST API, which usually exposes the game list
directly even when the rendered page is JavaScript-only.

Output is a ranked report; states scoring well are worth an adapter.
"""

import concurrent.futures
import json
import re
import sys
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

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
    "MS": "www.mslotteryhome.com",
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
    "WA": "www.walottery.com",
    "WV": "wvlottery.com",
    "WI": "wilottery.com",
    "WY": "wyolotto.com",
}

PATHS = [
    "/scratch-offs",
    "/scratch-off",
    "/scratchers",
    "/scratch",
    "/games/scratch-offs",
    "/games/scratch-off",
    "/games/scratchers",
    "/games/instant-games",
    "/games/instant",
    "/instant-games",
    "/instant",
    "/scratch-tickets",
    "/scratch-its",
    "/scratchoffs",
]

# WordPress post types that tend to hold instant-game records.
WP_TYPES = ["instant-game", "scratch-off", "scratchers", "scratch_off", "game", "instant_games"]


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def score_html(html):
    """Signals that prize data is present in the server-rendered payload."""
    remaining = len(re.findall(r"remaining", html, re.I))
    tables = html.lower().count("<table")
    links = len(set(re.findall(r'href="[^"]*(?:scratch|instant|game)[^"]*[/=]\d+', html, re.I)))
    prizes = len(re.findall(r"\$[\d,]{3,}", html))
    return {
        "remaining": remaining,
        "tables": tables,
        "links": links,
        "prizes": prizes,
        "score": remaining + tables * 5 + links * 2 + min(prizes, 60) // 10,
    }


def probe_wordpress(host):
    """Return usable WP REST post types, if the site runs WordPress."""
    try:
        _, body = fetch(f"https://{host}/wp-json/wp/v2/types", timeout=12)
        types = json.loads(body)
    except Exception:  # noqa: BLE001
        return []
    found = []
    for key in types:
        if any(t in key for t in ("instant", "scratch", "game")):
            try:
                _, rows = fetch(
                    f"https://{host}/wp-json/wp/v2/{types[key].get('rest_base', key)}"
                    f"?per_page=1",
                    timeout=12,
                )
                if json.loads(rows):
                    found.append(types[key].get("rest_base", key))
            except Exception:  # noqa: BLE001
                continue
    return found


def probe_state(item):
    code, host = item
    best = None
    status_seen = set()

    for path in PATHS:
        url = f"https://{host}{path}"
        try:
            status, html = fetch(url)
        except urllib.error.HTTPError as exc:
            status_seen.add(exc.code)
            continue
        except Exception:  # noqa: BLE001
            status_seen.add("err")
            continue

        stats = score_html(html)
        stats.update(url=url, status=status, size=len(html) // 1024)
        if best is None or stats["score"] > best["score"]:
            best = stats

    wp = probe_wordpress(host)
    return code, best, sorted(str(s) for s in status_seen), wp


def main():
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(probe_state, DOMAINS.items()):
            results.append(result)
            code = result[0]
            print(f"  probed {code}", file=sys.stderr)

    results.sort(key=lambda r: (r[1]["score"] if r[1] else -1), reverse=True)

    print(f"\n{'ST':<4}{'score':>6}{'rem':>6}{'tbl':>5}{'lnk':>5}  {'wp-rest':<22}url")
    for code, best, statuses, wp in results:
        if not best:
            print(f"{code:<4}{'-':>6}{'':>6}{'':>5}{'':>5}  {','.join(wp)[:20]:<22}"
                  f"blocked/404 ({','.join(statuses)})")
            continue
        print(
            f"{code:<4}{best['score']:>6}{best['remaining']:>6}{best['tables']:>5}"
            f"{best['links']:>5}  {','.join(wp)[:20]:<22}{best['url']}"
        )


if __name__ == "__main__":
    main()
