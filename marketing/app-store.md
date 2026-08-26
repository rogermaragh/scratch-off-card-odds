# App Store listing

Copy is written to Apple's field limits. Character counts are noted so you can
edit without silently overflowing.

---

## Name (30 max)

```
LottoMin: Lottery Results
```
`24 / 30`

Alternatives if the name is taken:
- `LottoMin — Lottery Numbers` (26)
- `LottoMin Lottery` (16)

## Subtitle (30 max)

```
Winning numbers, every state
```
`28 / 30`

Alternatives:
- `Draw results and scratch odds` (29)
- `Every state. No sign-up.` (24)

## Promotional text (170 max, editable without review)

```
Winning numbers for all 46 US lottery states — including the in-state games most apps skip — plus scratch-offs ranked by prize money left. No account, no ads.
```
`159 / 170`

Use this field for anything time-sensitive — a big jackpot roll, a newly added
state — since it updates without a new build.

## Keywords (100 max, comma-separated, no spaces)

```
lottery,powerball,mega,millions,scratch,off,ticket,odds,winning,numbers,results,draw,pick,jackpot,scratcher
```
`121 / 100` — **too long, trim before submitting.** Suggested cut:

```
lottery,powerball,megamillions,scratchoff,odds,winning,numbers,results,draw,pick3,pick4,jackpot,scratcher
```
`104 / 100` — still over. Final:

```
lottery,powerball,megamillions,scratchoff,odds,winning,numbers,results,pick3,jackpot,scratcher
```
`93 / 100` ✅

Notes: don't repeat words already in the app name or subtitle — Apple indexes
those separately, so "lottery" and "results" are arguably wasted here. If you
want the space back, drop them and add `cash4life,lotto,fantasy5`.

## Description (4000 max)

```
Every US lottery, one app.

LottoMin shows the latest winning numbers for all 46 states and territories
that run a lottery — Powerball and Mega Millions everywhere, Millionaire for
Life in the 31 states that sell it, and the in-state games most apps leave out.

That last part is the difference. 146 local games across 42 jurisdictions:
Virginia's Pick 3 with its Fireball, Nebraska's MyDaY, Montana's Big Sky Bonus,
Kansas 2by2, Wisconsin's Badger 5. If your state draws it, it is in here.

It opens instantly. No account, no ads, no tracking.

WHICH SCRATCH-OFFS ARE STILL WORTH BUYING

Lotteries publish how many prizes are left in each scratch-off game, but not
what that means. LottoMin does the arithmetic: it compares the prize money
still unclaimed against how much the game held at launch, and ranks every
active game by the result.

Above 1.00x, a game is paying better than it did on day one — the good prizes
haven't been claimed yet. Below it, the top prizes are largely gone and you're
buying into what's left.

817 games ranked across 12 states, refreshed regularly.

WHAT ELSE IS IN THERE

• Winning numbers for every state, updated after each draw
• Check a ticket: tap your numbers once, match them against weeks of results
• Twice-daily games shown as separate midday and evening draws
• Fireballs, Wild Balls, Megaballs and Bonus Balls shown as what they are,
  never mixed into the main numbers
• Winner counts by prize tier, where the state publishes them
• Full prize tables: what's left, out of how many
• Tap your state, or let the app find it once on first launch

BUILT TO BE HONEST

Every scratch-off screen tells you where its numbers came from and which parts
are estimated. Some states publish their exact print run; most don't, so ticket
counts are inferred from published odds and labelled as such. Games that have
ended are filtered out rather than left to look like bargains.

LottoMin is not affiliated with any lottery. It doesn't sell tickets and never
will. Always check winning numbers against your state lottery before claiming
anything.

Must be 18+ (21+ in some states) to play the lottery. If gambling stops being
fun, call 1-800-GAMBLER.
```
`~1,750 / 4000`

## What's New (first release)

```
First release.

• Winning numbers for all 46 US lottery jurisdictions
• 146 in-state games across 42 of them, not just Powerball and Mega Millions
• Scratch-off games ranked by prize money remaining, in 19 states
• Check a ticket against every recent draw
• Light and dark, switchable from any screen
• Works offline
```

## App Privacy answers

Apple's questionnaire, answered for this build:

| Question | Answer |
| --- | --- |
| Do you collect data? | **No** |
| Location | Used on device only, never collected or transmitted |
| Identifiers / analytics / tracking | None |
| Third-party SDKs | None |

The app makes exactly one kind of network request: fetching its own data file.
No user data leaves the device, so the whole questionnaire answers "no data
collected" — which earns the "Data Not Collected" label.

## Age rating

Expect **17+** — Apple rates lottery-adjacent apps under "Simulated Gambling"
or "Contests" even when no money changes hands. Answer the questionnaire
honestly: the app displays real gambling results but offers no play, no
purchase and no simulated gambling.

## Category

- Primary: **Reference** (fits an information utility better than Games, and
  avoids the Games gambling subcategories)
- Secondary: **Utilities**

## Review notes

Paste into App Review Information → Notes:

```
LottoMin is an informational app. It displays publicly published lottery
results and scratch-off prize inventories.

It does NOT:
- sell or enable the purchase of lottery tickets
- accept payment of any kind
- offer play, simulated play, or any game of chance
- require or offer an account

Data comes from state lottery open-data APIs and public results pages. The app
is not affiliated with or endorsed by any lottery. A disclaimer appears on
every screen footer and on each game's detail page.

Location is requested once to select the user's state. It is reverse-geocoded
on device to a two-letter state code and never stored or transmitted.

No login is required. All features are available immediately.
```
