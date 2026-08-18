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
| North Carolina | 85 | Winner counts, plus Pick 3/4 twice daily |
| Virginia | 85 | Enumerated via price filters; pager is click-only |
| Mississippi | 84 | WP REST; 169 of 253 games are "Ended" and filtered |
| Indiana | 82 | Browser-rendered |
| South Carolina | 60 | No per-tier odds; print run from overall odds |
| Washington | 59 | Embedded JSON with the **actual** print run |
| New Mexico | 55 | Every game and prize table on one page |
| Louisiana | 47 | 138 expired games filtered out |
| Oklahoma | 42 | Full prize tables, but no price or odds published |

599 live games across nine states.

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

Usefully, **the print run cancels out of that ratio**:

```
ratio = (value_left / (printed × frac_left)) ÷ (value_start / printed)
      =  value_left / (frac_left × value_start)
```

So the headline ranking needs only prize counts — which is what unlocked
Mississippi, a state publishing counts but no odds at all. The print run is
needed solely for the absolute figures (tickets left, % return), and comes
from, in order of preference:

1. **Published outright.** Washington states its print run; nothing is inferred.
2. **Per-tier odds.** Odds × total prizes at each tier, taking the median since
   published odds are rounded.
3. **Overall odds.** Coarser fallback for states like South Carolina.
4. **Unavailable.** Mississippi shows a ratio but no ticket counts or return.

Tickets remaining then assumes tickets sell in proportion to prizes claimed —
an estimate, not a count anyone reports. Every game's detail screen names which
of the four cases it falls under rather than presenting one number as fact.

### Two traps worth knowing about

**Expired games — this bites in every state that has them.** Louisiana keeps
closed games online with their final prize tables. Those tables look
extraordinary — an unclaimed top prize against nearly zero inventory — and
ranked straight to the top of the board on the first run. 138 of Louisiana's
182 are expired. Mississippi repeated the trick exactly: **169 of its 253 games
are "Ended"**, and the first version of that adapter happily ranked them.

Each state hides the flag somewhere different (Louisiana in page text,
Mississippi in a `gamestatus` taxonomy, Washington in `RedeemEndDate`), so
**check for it before trusting a new adapter**. The CI range check does *not*
catch this: the inflated ratios sit comfortably inside a plausible range.

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

### What probing all 46 jurisdictions found

Three scripts, in increasing order of what they actually prove:

- `Scripts/discover.py` — plain HTTP, 14 candidate paths per state.
- `Scripts/browse_probe.py` — the same sweep through headless Chromium,
  concurrent, writing JSONL as it goes.
- `Scripts/capability.py` — follows a game link and asks the only question that
  decides usability: **does a page carry original prize counts *and* remaining
  counts?**

That last distinction is the important one. Loading a page is not the same as
the page containing what the ranking needs, and the browser only fixes the
first problem.

- **Built (9)** — NC, VA, MS, IN, SC, WA, NM, LA, OK.
- **Reachable but the data isn't published (2 confirmed)** — Pennsylvania
  publishes `Top Six Prizes | Wins Remaining`; Idaho publishes `Percent Sold |
  Top Prizes Remaining | High Tier Prizes Remaining`. Neither gives original
  per-tier counts, so no ratio exists to compute. **No amount of browser
  automation creates data a lottery does not publish.**
- **Unlocked by the browser, adapter not yet written (~10)** — AZ, MD, MA, MN,
  IL, KS, MI, FL, MT, NH all render usable-looking pages once JavaScript runs;
  several were 403 or 404 over plain HTTP. Each still needs its own link
  pattern worked out — `capability.py`'s guessed regexes matched nothing for
  them, which is a fact about my guesses, not about the sites.
- **Untested for data completeness (~19)** — reachable to some degree, not yet
  put through `capability.py`.

Going from nine states to all of them is no longer blocked on infrastructure.
It is now a per-state grind of finding each site's game-link pattern, plus an
irreducible subset that simply never publishes full prize tables.

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

## Controls

The odds board deliberately avoids stock iOS controls. Sort and price filter
are a `TypeStrip` / `ValueStrip` pair: no chrome, no segmented background —
type weight and a matched-geometry rule carry the selection, and the rule
slides between options. Visible type is small, so each option is padded to the
44pt minimum hit area and carries `.isSelected` for VoiceOver.

