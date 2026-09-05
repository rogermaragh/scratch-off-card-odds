# App Store listing

Copy is written to Apple's field limits. Character counts are noted so you can
edit without silently overflowing.

---

## Name (30 max)

```
Scratch Off Card Odds
```
`21 / 30`

The name describes the scratch-off half, which is the smaller half — the
ranking covers 19 states where draw results cover all 46. That is a deliberate
trade for search: "scratch off odds" is a high-intent query and far less
contested than "lotto", where this app would land behind every official state
app. The subtitle carries the draw-results half, so the pair says what the
name alone does not.

One caveat to hold in mind when reading reviews: the app ranks by *value left*
— prize money still in the game per ticket — and deliberately does not publish
a recalculated "current odds" figure, because that reduces to the state's
published odds by construction. Anyone arriving from "odds" expecting
recalculated odds is expecting something the app declines to invent.

Alternatives if the name is taken:
- `Scratch Off Odds & Lottery` (26)
- `Scratch Card Odds: Lottery` (26)

## Subtitle (30 max)

```
Winning numbers, every state
```
`28 / 30`

Alternatives:
- `Prizes left, every state` (24)
- `Draw results and scratch odds` (29)

## Promotional text (170 max, editable without review)

```
Winning numbers for all 46 US lottery states — including the in-state games most apps skip — plus scratch-offs ranked by prize money left. No account, no ads.
```
`159 / 170`

Use this field for anything time-sensitive — a big jackpot roll, a newly added
state — since it updates without a new build.

## Keywords (100 max, comma-separated, no spaces)

```
powerball,megamillions,lottery,results,scratcher,pick3,pick4,jackpot,cash4life,lotto,unclaimed
```
`94 / 100` ✅

Apple indexes the name and subtitle separately, so anything already in either
is wasted here. "Scratch Off Card Odds" and "Winning numbers, every state"
cover *scratch*, *off*, *card*, *odds*, *winning*, *numbers* and *state* — so
this field buys back the draw-game words the old name used to carry, plus the
specific game names.

`unclaimed` earns its nine characters: it is the word the states themselves use
for the prizes this app ranks, so it is what someone already looking for this
will type.

## Description (4000 max)

```
Every US lottery, one app.

ScratchOffCardOdds shows the latest winning numbers for all 46 states and territories
that run a lottery — Powerball and Mega Millions everywhere, Millionaire for
Life in the 31 states that sell it, and the in-state games most apps leave out.

That last part is the difference. 146 local games across 42 jurisdictions:
Virginia's Pick 3 with its Fireball, Nebraska's MyDaY, Montana's Big Sky Bonus,
Kansas 2by2, Wisconsin's Badger 5. If your state draws it, it is in here.

It opens instantly. No account, no ads, no tracking.

WHICH SCRATCH-OFFS ARE STILL WORTH BUYING

Lotteries publish how many prizes are left in each scratch-off game, but not
what that means. ScratchOffCardOdds does the arithmetic: it compares the prize money
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

ScratchOffCardOdds is not affiliated with any lottery. It doesn't sell tickets and never
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
ScratchOffCardOdds is an informational app. It displays publicly published lottery
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
