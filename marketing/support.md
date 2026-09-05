# ScratchOffCardOdds Support

Questions, answered plainly. If yours isn't here: **support@scratchoffcardodds.app**

---

## Are these the official winning numbers?

No. ScratchOffCardOdds is not affiliated with any lottery. Numbers come from state
lottery open data and public results pages, and can lag a draw or carry a
mistake. **Always check your ticket against your state lottery before claiming
anything.** Every screen says so for a reason.

## Why does my state only show Powerball and Mega Millions?

Because those are the two games sold in every US lottery jurisdiction, and most
states' own games need a separate data source that isn't built yet.

Right now in-state games work for New York, Arizona, Michigan and North
Carolina. If your state shows only the multi-state games, the app tells you
directly — it isn't claiming your state has nothing else.

## Why does my state only show Powerball and Mega Millions?

Four jurisdictions have no in-state games in the app, and each for its own
reason:

- **Vermont** does not publish its results anywhere machine-readable. Its game
  pages show only a "pick numbers for me" generator, and the results pages it
  links to are dead.
- **Tennessee** puts a bot check in front of its results, which is not
  something worth working around.
- **Delaware**'s site refuses connections entirely.
- **New York** does have its games — Take 5, Numbers, Win 4, Pick 10 and NY
  Lotto — they are simply listed with the national games rather than under the
  state.

Everywhere else — 42 jurisdictions, 146 games — the local draws are there.

## What is the highlighted number at the end of a row?

The extra ball your state draws separately, and the caption under the row names
it: a Fireball in Virginia and South Carolina, a Wild Ball in Pennsylvania and
Connecticut, a Megaball in Maine, a Bonus Ball in Maryland and Texas, a Lucky
Ball in Montana, the Powerball itself.

It is deliberately not mixed in with the main numbers, because it is not one of
them. A Virginia Pick 4 draws four digits and a Fireball — showing five digits
in a row would mean matching a ticket against a number that is not part of the
main draw.

## Why can't I see scratch-off rankings for my state?

Ranking scratch-offs needs two numbers per prize tier: how many existed at
launch, and how many are left. Not every lottery publishes both.

- **12 states publish enough**: California, Indiana, Louisiana, Maryland,
  Mississippi, New Mexico, North Carolina, Oklahoma, Rhode Island, South
  Carolina, Virginia, Washington.
- **Some publish too little.** Pennsylvania gives only "top six prizes" and
  Idaho only "percent sold", neither of which supports a ranking.
- The rest simply aren't built yet.

## What does the ×1.21 number mean?

It compares prize money still unclaimed per remaining ticket against the same
figure when the game launched.

- **Above 1.00×** — the good prizes haven't been claimed yet, so the game is
  paying better than it did on day one.
- **Below 1.00×** — the big prizes are largely gone.

It is **not** a prediction and not a chance of winning. It is a comparison of a
game against its own starting point.

## Is a game above 1.00× a good bet?

No. Essentially every lottery game returns less than it costs — look at the
"Net" figure on any game and it will be negative. A high ratio means a game is
better *than it was*, not that it is profitable. The lottery is entertainment,
priced accordingly.

## Why does "Tickets left" look like a guess?

Because it is one, and the app says so on every game. Lotteries publish prizes
remaining, not tickets remaining. The app estimates tickets from published odds
and assumes they sell in proportion to prizes claimed.

Where a state publishes its actual print run — Washington does — the app uses
the real number and says so.

## Why do some games show no price or return?

Maryland and Oklahoma publish prize tables but no ticket price anywhere. Those
games still rank, because the ranking doesn't need a price, but there's no
return percentage to show.

## Does the app track me?

No. No account, no analytics, no advertising, no third-party SDK. If you allow
location, it's used once, converted to a two-letter state code on your device,
and the coordinates are discarded. Nothing is transmitted. See the privacy
policy for detail.

## Why does the app ask for my location?

Only to pick your state on first launch. Decline and nothing is lost — choose
your state from the list instead.

## Does it work offline?

Yes. The app ships with a full copy of its data, so it opens and works with no
connection. If a refresh URL is configured, it updates in the background and
falls back to the bundled copy when offline.

## Can I buy tickets in the app?

No, and that will not change. ScratchOffCardOdds displays information. It takes no
payment and sells nothing.

## The numbers look wrong

Please tell us — **support@scratchoffcardodds.app** — with the state, the game and the
date. Data bugs are the failure mode that matters most here, and past reports
have caught real ones.

---

**Play responsibly.** You must be 18+ (21+ in some states). If gambling stops
being fun, call **1-800-GAMBLER** or visit
[ncpgambling.org](https://www.ncpgambling.org).

### Which states can be ranked, and why the rest cannot

The ranking compares prize money left per ticket against the same figure when
the game launched. That needs two numbers for every prize tier: how many were
printed, and how many are left.

Most states publish the second. A good many never publish the first, and it
cannot be recovered from what they do publish — Idaho lists `Prize | Remaining`,
Montana lists `WIN | PRIZE | ODDS`, Pennsylvania lists its top six prizes and
the wins left against them. Per-tier odds do not close the gap either: they
give the launch value per ticket but not the print run, and tickets remaining
still depends on it.

So those states show draw results and no ranking. Publishing a number we cannot
stand behind would be worse than publishing none.
