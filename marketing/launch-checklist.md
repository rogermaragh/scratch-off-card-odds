# Launch checklist

## Before the first build upload

- [ ] Set a real bundle identifier and team in `project.yml`
- [ ] Register the App ID; enable no capabilities beyond location-when-in-use
- [ ] Replace the placeholder app icon (currently none — **this blocks upload**)
- [ ] Bump `MARKETING_VERSION` to `1.0`
- [ ] Publish data and point the app at it:
      `python3 Scripts/set_data_url.py`
- [ ] Enable GitHub Pages: **Settings → Pages → Source: GitHub Actions**
- [ ] Run the workflow once manually and confirm `core.json` is reachable
- [ ] Confirm a fresh install with no network still shows results (bundled copy)

## App Store Connect

- [ ] Copy listing text from `marketing/app-store.md`
- [ ] Trim keywords to under 100 characters (the draft notes which cut to use)
- [ ] Host `marketing/privacy.md` at a public URL; add it as the privacy policy
- [ ] Answer App Privacy as **Data Not Collected**
- [ ] Category: Reference (primary), Utilities (secondary)
- [ ] Paste the review notes from `app-store.md` — they pre-empt the gambling
      question, which is the most likely reason this app gets held
- [ ] Upload screenshots for every required display size

## Guideline 5.3 (gaming, gambling, lotteries)

This is the review risk worth preparing for. The app should pass because it is
purely informational, but make the case explicitly:

- [ ] Confirm the app cannot buy tickets, take payment, or simulate play
- [ ] Confirm the "unofficial — verify with your state lottery" disclaimer is
      visible on the home footer and every game detail screen
- [ ] Expect a 17+ age rating and do not contest it
- [ ] If rejected, the usual remedy is clarifying that no gambling occurs in
      the app; have the review notes ready to resubmit unchanged

## Legal and data

- [ ] Re-read the terms of use for each scraped state — several prohibit
      automated access, and that is a real, unresolved risk of this approach
- [ ] Decide whether to attribute sources publicly in-app (currently linked
      per game via "Official game page")
- [ ] Add a responsible-gambling line (1-800-GAMBLER) — already in the
      description, consider putting it in the app too

## After launch

- [ ] Watch the daily workflow for a week; scrapers break when sites change
- [ ] Re-run `Scripts/discover.py` and `Scripts/draws_api.py` quarterly — new
      states become reachable when sites are rebuilt
- [ ] Keep an eye on games retiring: the Cash4Life lesson is that a feed can
      keep answering long after the game is dead
