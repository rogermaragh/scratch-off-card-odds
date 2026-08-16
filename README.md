# LottoMin

Minimalist iOS lottery app. Draw results on launch, scratch-off games ranked by
how much prize money is actually left in them.

## Running it

```bash
xcodegen generate && open LottoMin.xcodeproj
```

Refresh the data by re-running the scraper, which rewrites `Data/lottery.json`:

```bash
python3 Scripts/scrape.py
```

`Scripts/probe.py` scores candidate state sites for scrapeability — run it
before writing a new adapter.

## Coverage

| State | Games | Notes |
| --- | --- | --- |
| North Carolina | 85 | Also the only state publishing winner counts |
| South Carolina | 59 | No per-tier odds; print run derived from overall odds |
| New Mexico | 55 | Every game and prize table on a single page |
| Louisiana | 44 | 138 expired games filtered out |

Powerball and Mega Millions numbers come from New York's Open Data SODA API
(no key required). North Carolina also contributes Pick 3 and Pick 4, both
drawn twice daily and shown as separate Daytime/Evening rows.

The state picker lists all 46 lottery jurisdictions; the 42 without an adapter
appear greyed out rather than hidden, so coverage is honest on its face.

## Where the data comes from

```
Scripts/scrape.py ──> Data/lottery.json ──> bundled into the app
                                       └──> published to a URL (optional)
```

The app resolves data newest-first: a previously downloaded copy on disk beats
the copy bundled at build time. So it opens instantly and works offline either
way. Set `Config.defaultDataURL` to a published `lottery.json` and the refresh
button appears; leave it empty and the app never touches the network.

Downloads are decoded before the cache is overwritten, so a broken publish
cannot replace a working local copy.

### Publishing

`.github/workflows/scrape.yml` runs the scraper daily, gates it on
`Scripts/validate.py`, and publishes to GitHub Pages using the workflow's own
`GITHUB_TOKEN` — no bucket, no secrets, nothing to pay for. Two steps to turn
it on:

1. In the repo: **Settings → Pages → Source: GitHub Actions** (one time).
2. Point the app at it:

```bash
python3 Scripts/set_data_url.py
```

That derives `https://<owner>.github.io/<repo>/lottery.json` from the git
remote and writes it into `Config.swift`. Pass a URL to use a different host,
or `--clear` to go back to bundled-only.

The validation gate fails the run on zero games, missing prices, ratios outside
0.2–3.0×, implausible returns, or any expired game reaching the output — so a
half-scraped bundle never replaces a good one.

## The ranking

Each game gets a `ratio`: prize money left per remaining ticket, divided by
prize money per ticket when the game launched. Above `1.00×` the game is paying
better than it did at print time.

Getting there needs a number no lottery publishes — how many tickets are left.
It's estimated in two steps:

1. **Print run.** Any tier's published odds times its total prizes implies the
   run. The median across tiers is used, since published odds are rounded.
   States without per-tier odds fall back to overall odds × total prizes.
2. **Tickets left.** Assumed to fall in proportion to prizes claimed. This is
   the standard approximation; it is not a count anyone reports.

The app states this on every game's detail screen rather than presenting the
figure as fact.

### Two traps worth knowing about

**Expired games.** Louisiana keeps closed games online with their final prize
tables. Those tables look extraordinary — an unclaimed top prize against nearly
zero inventory — and ranked straight to the top of the board on the first run.
138 of Louisiana's 182 games are expired. They're filtered on `expired` at the
source, because the CI range check does *not* catch them: the inflated ratios
(max 1.79×) sit comfortably inside a plausible range.

**End-of-life games.** Even among live games, once inventory drops below ~5% the
proportional-sales assumption breaks down and one claim swings the ratio hard.
Those are flagged `endingSoon` and visually de-emphasized instead of trusted.

**Winner counts drifting off their draw.** The two feeds move independently:
NC's site posted the Aug 15 Powerball payout table while NY's numbers feed was
still on Aug 12, so the app briefly showed 12,755 winners next to the wrong
draw's numbers. Winner counts now render only when `payout.drawDate` matches
the draw actually on screen, and silently drop out otherwise.

## Adding a state

Each state needs its own adapter — there's no shared format, and this is where
essentially all the work in a national build lives. Write a scraper returning
game dicts (`name`, `price`, `topPrize`, `overallOdds`, `tiers[]`, and an
`expired` flag if the state publishes dead games), then register it:

```python
STATES = {
    "NC": {"name": "North Carolina", "scraper": scrape_nc, "payouts": nc_payouts},
}
```

`enrich()` and the app handle the rest.

### What probing 32 states found

- **Clean HTML (built)** — NC, SC, NM, LA.
- **Bot-blocked (403)** — Texas, Missouri, Arizona, New Jersey, Tennessee.
- **JS-rendered, needs a headless browser** — Maryland, Georgia, Michigan,
  Kansas, Indiana, Colorado, Kentucky.
- **URL moved or dead (404)** — Iowa, Maine, Minnesota, Nebraska, Rhode Island,
  Vermont, Washington, Wisconsin. Worth re-probing; these are usually a path
  change rather than a real block.

Two gotchas that cost real debugging time here: column layouts differ *within* a
single state (NC's Powerball payout table has three columns, its Mega Millions
table has four — read header rows, never index by position), and HTML entities
will silently corrupt numbers (`&#36;20` parses as `3620` if you strip
non-digits before unescaping).

## Not built

- Winner counts outside North Carolina — most states don't publish them.
- NC Cash 5 and Lucky for Life. Their result blocks carry no per-game marker,
  and every scoping attempt pulled in the adjacent Powerball and Mega Millions
  numbers. Pick 3/4 were only safe because each result links to its own
  `/Pick3-Draw?dn=` detail page. Shipping the wrong winning numbers is worse
  than shipping fewer games.
- In-state draw games for LA, NM, and SC — each needs its own adapter.
