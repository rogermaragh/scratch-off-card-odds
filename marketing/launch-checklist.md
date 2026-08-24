# Launch checklist

Ordered by what blocks what. Items marked **done** are already in the repo.

## 1. Things that will get you rejected if missed

- [ ] **Bundle ID matches App Store Connect.** Currently `com.lottomin.app`
      (`project.yml` → `PRODUCT_BUNDLE_IDENTIFIER`). This drifted once already —
      the generated project said `com.rogermaragh.lottomin` while `project.yml`
      said otherwise. Check both before archiving:
      ```bash
      grep -o 'PRODUCT_BUNDLE_IDENTIFIER = [^;]*' LottoMin.xcodeproj/project.pbxproj | sort -u
      ```
- [ ] **Age rating questionnaire.** Expect 17+. Answer honestly: the app shows
      real gambling results but offers no play, purchase or simulated gambling.
- [ ] **Review notes.** Paste the block from `app-store.md` → Review notes. A
      lottery app with no explanation is a guaranteed round-trip with review.
- [x] **Privacy policy URL.** `privacy.md` — host it and paste the URL.
- [x] **No IAP, no account, no ticket sales.** Guideline 5.3.3 forbids selling
      lottery tickets in-app. The app does none of this; keep it that way.
- [ ] **Support URL.** Required field. `support.md` is written; host it.

## 2. Assets

- [x] **App icon** — `Scripts/make_icon.py` writes the 1024 into the asset
      catalog. Regenerate any time: `python3 Scripts/make_icon.py --preview`.
- [ ] **Screenshots** — `./Scripts/screenshots.sh` captures light and dark
      across devices. Apple needs at least the 6.9" set; others are optional
      and inherited. Check the output before uploading: the script guards
      against blank frames but not against a bad data day.
- [ ] **App preview video** (optional). The intro animation and the flip tiles
      are the obvious 15 seconds.

## 3. Data and correctness

- [x] **Validation gate** — `Scripts/validate.py` fails on zero games, missing
      prices, implausible ratios or any expired game reaching output.
- [ ] **Fresh scrape immediately before archiving.** Bundled data is what
      offline users see first:
      ```bash
      python3 Scripts/scrape.py && python3 Scripts/split.py && python3 Scripts/validate.py
      ```
- [ ] **Spot-check two states against their official sites.** Do this by hand,
      every release. It has caught real bugs: a `$51` prize that did not exist,
      odds reading "1 in 1.00", and a retired game still being published.
- [ ] **Turn on hosting** so data refreshes without an App Store update:
      1. Repo → Settings → Pages → Source: GitHub Actions
      2. `python3 Scripts/set_data_url.py`
      3. Rebuild. The refresh button appears once a URL is set.

## 4. Before you hit submit

- [ ] Run on a real device, not just the simulator. Location behaves
      differently, and the colour field is worth checking on OLED.
- [ ] Test with Location denied — the picker must still work.
- [ ] Test in Airplane Mode — bundled data must still render.
- [ ] Test with Reduce Motion on — drift and shimmer should stop, colour stays.
- [ ] Test at the largest Dynamic Type size.

## 5. Known gaps to disclose or fix first

These are honest limits, not bugs. Decide whether to ship with them:

- In-state games exist for **4 of 46** jurisdictions (NY, AZ, MI, NC). Every
  other state shows multi-state games only, with an on-screen note saying so.
- Scratch-off rankings cover **11 states**. Others show "no prize data
  published for this state".
- Some states publish no ticket price (Maryland, Oklahoma), so those games
  rank on value but show no return percentage.
- Pennsylvania and Idaho publish prize data too incomplete to rank at all.
