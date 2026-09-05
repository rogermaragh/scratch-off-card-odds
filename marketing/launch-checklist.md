# Launch checklist

Ordered by what blocks what. Items marked **done** are already in the repo, and
are listed rather than deleted so a later reader can tell "handled" from
"forgotten".

App: **Scratch Off Card Odds** · bundle `com.scratchoffcardodds.app` · iPhone
only, iOS 17+.

---

## 1. The one that ruins the app quietly

The data URL is **set** to `https://rogermaragh.github.io/scratch-off-card-odds/`,
but nothing serves it yet — the repo has not been pushed and Pages is not
enabled. Until both are true the app believes it has an update source, tries on
every launch, and fails silently, because automatic refreshes deliberately do
not report errors. It has also lost the honest "this build has no update
source" wording, since as far as it knows it has one.

**So do not archive a build until the URL below returns 200.**

- [ ] **Push the repo.** The remote is already set.
      ```bash
      git push -u origin main
      ```
- [ ] **Enable Pages.** Settings → Pages → Source: **GitHub Actions**.
- [ ] **Run the scrape workflow once** (Actions → Scrape lottery data → Run
      workflow) so there is something published. The first full run takes
      about 35 minutes.
- [ ] **Confirm it serves**, which is the check that matters:
      ```bash
      curl -sI https://rogermaragh.github.io/scratch-off-card-odds/core.json | head -1
      ```
- [ ] **Confirm the app uses it.** Launch and look for the refresh control in
      the toolbar — it renders only when a URL is configured — then check the
      staleness banner is gone, which can only happen if a download replaced
      the bundled copy.

## 2. Things that will get you rejected if missed

- [ ] **Register the bundle ID** `com.scratchoffcardodds.app` in App Store
      Connect. It can never be changed after the first release.
- [ ] **Check the generated project agrees with `project.yml`.** This has
      drifted **twice**, and the failure is nasty: the app installs and then
      simply refuses to open, with no crash log, because the id being launched
      is not the id that was built.
      ```bash
      xcodegen generate
      plutil -extract CFBundleIdentifier raw \
        .build-dd/Build/Products/Debug-iphonesimulator/ScratchOffCardOdds.app/Info.plist
      ```
      `Scripts/shoot-screenshots.sh` already regenerates and reads the id from
      the built app, so a clean screenshot run is itself a check.
- [ ] **Age rating questionnaire.** Expect 17+. Answer honestly: the app shows
      real gambling results but offers no play, purchase or simulated
      gambling.
- [ ] **Review notes.** Paste the block from `app-store.md`. A lottery app with
      no explanation is a guaranteed round-trip with review. Say plainly that
      it sells nothing, is unofficial, and only republishes public results.
- [ ] **Support URL.** Required field. `support.md` is written; host it.
- [ ] **Privacy policy URL.** `privacy.md` is written; host it.
- [x] **No IAP, no account, no ticket sales.** Guideline 5.3.3 forbids selling
      lottery tickets in-app. The app does none of this; keep it that way.
- [x] **No official-affiliation claim.** Every ticket in the app is stamped
      "unofficial", and the disclaimer sits under every screen.

## 3. Store listing

- [x] **Name** (21/30), **subtitle** (28/30), **keywords** (94/100),
      description and promotional text — all in `app-store.md`, written to
      Apple's field limits with counts noted.
- [x] **Screenshots** — six frames, rendered at **both** sizes App Store
      Connect accepts, because it rejects the whole upload if one frame is off
      by a pixel:

      | Slot | Size | Directory |
      |---|---|---|
      | 6.9-inch | 1290 × 2796 | `AppStoreScreenshots/6.9-inch-captioned/` |
      | 6.5-inch | 1284 × 2778 | `AppStoreScreenshots/6.5-inch-captioned/` |

      Upload whichever the slot asks for. The captures come from whatever
      simulator is installed; each set is *composited* at its target size
      rather than resized afterwards, so the device shot keeps its own
      proportions instead of being stretched a fraction to fit.
      ```bash
      Scripts/shoot-screenshots.sh          # raw captures
      Scripts/caption-screenshots.sh        # captioned frames
      ```
      Every screen is reached by launch argument rather than by tapping, so a
      re-shoot reproduces the same frames. **Look at the output before
      uploading**: the script guards against blank frames, not against a bad
      data day. It has twice produced a real screen under the wrong caption.
- [x] **App icon** — `Scripts/make_icon.py` writes the 1024 into the asset
      catalog. Regenerate any time: `python3 Scripts/make_icon.py --preview`.
- [ ] **App preview video** (optional). The intro animation and the flip tiles
      are the obvious fifteen seconds. `-shotIntro YES` holds the intro on its
      landed ticket rather than playing it out.

## 4. Data and correctness

- [x] **Validation gate** — `Scripts/validate.py` fails on zero games, missing
      ratios, implausible ratios, expired games reaching output, and returns
      that are impossible rather than merely unusual.
- [x] **84 tests**, each one a bug that actually shipped. They gate the scrape
      in CI rather than trailing it, because parsing faults here produce
      plausible wrong numbers rather than errors.
- [ ] **Confirm the scheduled scrape is green** before submitting. Full scrape
      daily at 08:45 UTC, draw games again at 21:15 UTC. A failed run publishes
      nothing, and the app will say how old its data is rather than hide it.
- [ ] **Fresh scrape immediately before archiving.** Bundled data is what a new
      install sees before its first refresh:
      ```bash
      .venv/bin/python -m pytest Tests -q
      .venv/bin/python Scripts/scrape.py        # ~33 min for everything
      .venv/bin/python Scripts/validate.py
      .venv/bin/python Scripts/split.py
      ```
      `--core` refreshes draw results only, in about two minutes.
- [ ] **Spot-check two states against their official sites.** By hand, every
      release. This has caught a `$51` prize that did not exist, odds reading
      "1 in 1.00", a retired game ranked first, Powerball published under
      "Hoosier Lotto", and a state's number generator published as results.

## 5. Before you hit submit

- [ ] Run on a real device, not just the simulator. Location behaves
      differently, and the colour field is worth seeing on OLED.
- [ ] Test with Location denied — the picker must still work.
- [ ] Test in Airplane Mode — bundled data must still render, and the failed
      refresh must stay silent rather than showing an error.
- [ ] Test with Reduce Motion on — drift and shimmer stop, colour stays.
- [ ] Test at the largest Dynamic Type size.
- [ ] Check the staleness banner wording by launching with old bundled data.

## 6. Known limits — decide whether to ship with them

These are honest boundaries, not unfinished work. Most were established by
checking rather than assuming, and the reasoning is in `docs/data-sources.md`.

**Draw games: 42 of 46 jurisdictions, 146 in-state games.** The four without:

| | |
|---|---|
| **New York** | Needs no per-state entry — its games are national-list games |
| **Vermont** | Publishes no results at all; its game pages carry only a number generator and every results URL 404s |
| **Tennessee** | Behind a Cloudflare bot check, which is not something to work around |
| **Delaware** | Refuses connections outright, browser and command line alike |

**Scratch-off rankings: 19 states, 1,189 games.** The rest show "no prize data
published for this state", which is usually the literal truth:

- **Pennsylvania, New York, Idaho, Montana, Ohio** publish what is *left*
  without what *started*. The ranking needs both, and no arithmetic recovers
  one from the other — per-tier odds do not close it either. Confirmed against
  their own "view all" pages and, for New York, its official report PDF.
- **Colorado, Illinois, Minnesota, Wisconsin** look the same way; less
  thoroughly confirmed.
- **Oklahoma dropped from 42 games to 12** when it moved to `oklottery.com`.
  The new site simply lists fewer, and has no remaining-prizes page.
- **Maryland** publishes no ticket prices, so its games rank on value left but
  show no return percentage.

**Two more worth knowing:**

- Tickets-remaining is an *estimate*, assuming tickets sell in proportion to
  prizes claimed. No lottery publishes the real figure. The app says so on
  every detail screen, and the estimate is least reliable on nearly-exhausted
  games, which are flagged.
- A handful of games return above 100% because their top prizes went unclaimed
  while the game sold through. That is real and it is the point of the app —
  but the App Store frame deliberately opens an ordinary game instead, because
  a listing image advertising a profitable lottery ticket is a different thing
  from the same number inside the app.
