# LottoMin — press kit

**One line:** Winning numbers for every US lottery, plus the scratch-off games
that still have prize money left.

**Status:** pre-launch · **Platform:** iOS 17+ · **Price:** free, no ads, no IAP

---

## What it is

LottoMin shows the latest draw results for all 46 US jurisdictions that run a
lottery, and ranks scratch-off games by how much prize money is actually left
in them.

The second part is the interesting one. State lotteries publish how many prizes
remain in each scratch-off game, but not what that means. LottoMin compares the
unclaimed prize money against what the game held at launch and ranks every
active game by the result. Above 1.00x, the game is paying better than it did
on day one.

## Why it exists

The information is public but effectively unusable. It lives in prize tables
scattered across 46 different websites, in a dozen different formats, several
of which only render after JavaScript runs. Reading it the way LottoMin does
means visiting a page per game and doing arithmetic the lottery does not do for
you.

## Numbers

| | |
| --- | --- |
| Jurisdictions with draw results | 46 (all of them) |
| Draw games covered | Powerball and Mega Millions everywhere; Millionaire for Life in 31 |
| In-state games | 146 games across 42 jurisdictions |
| States with scratch-off rankings | 12 |
| Scratch-off games ranked | 817 |
| Account required | none |
| Data collected | none |

## Three things worth writing about

**1. It found retired games still being published.** Cash4Life and Lucky for
Life were both replaced by Millionaire for Life in February 2026. Their data
feeds still respond — Cash4Life's returns results through 21 February — so an
app that trusted the feed would show six-month-old numbers as current.

**2. Expired scratch-offs look like the best deals in the country.** A finished
game with an unclaimed top prize and almost no inventory scores extraordinarily
well on any naive ranking. 138 of Louisiana's 182 games and 169 of
Mississippi's 253 are dead. They are filtered out. Each state hides the flag
somewhere different.

**3. Most of the maths cancels out.** The ranking appears to need the print run
— how many tickets were made — which most states do not publish. It does not:
the print run cancels algebraically out of the ratio. That is what makes states
publishing prize counts but no odds rankable at all.

## Honesty

LottoMin is unofficial and not affiliated with any lottery. It sells nothing.
Every game screen states which of its numbers are published and which are
estimated, and from what. Where a state publishes no odds, the app says the
ticket count is unavailable rather than inventing one.

## Assets

- Screenshots: `marketing/screenshots/` (light and dark, several devices)
- Regenerate: `./Scripts/screenshots.sh`

## Contact

press@lottomin.app
