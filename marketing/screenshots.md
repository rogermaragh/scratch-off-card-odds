# Screenshots

Two commands. The first captures raw device frames, the second wraps them in
App Store caption frames.

```bash
Scripts/shoot-screenshots.sh          # capture
Scripts/caption-screenshots.sh        # caption
```

Upload `AppStoreScreenshots/*-captioned/`. The raw captures stay untouched
alongside them, so re-wording a caption never needs a re-shoot.

---

## Why it is scripted this way

Every screen is reached by **launch argument**, never by simulated taps:

```bash
xcrun simctl launch <udid> com.lottomin.app \
    -shotState VA -shotScreen scratchers -shotTheme dark
```

Tapping through a simulator is neither repeatable nor reviewable. A mistimed
tap lands on the wrong state and nobody notices until the frames are side by
side — and by then the set has to be shot again from the top. Addressing each
screen by argument means a re-shoot months from now produces the same frames.

Three things are pinned for the same reason:

- **State.** The app geolocates on first run, so an unpinned set would
  advertise whichever state the machine taking it happens to sit in.
- **Appearance.** A set begun before sunset and finished after it would
  disagree with itself halfway through.
- **The intro**, when it is asked for at all. It holds on the landed ticket
  rather than playing out, because timing a screenshot into a 1.6-second
  animation is a coin toss — and the frame it loses is the home screen wearing
  the intro's caption, which looks fine until it is next to the others.

The status bar is overridden to 9:41 with full bars, which is what Apple shows
on its own marketing and one less thing that differs between two frames.

## Arguments

| Argument | Effect |
| --- | --- |
| `-shotState XX` | Pin the state, and skip the location prompt |
| `-shotScreen …` | `home`, `scratchers`, `scratcherDetail`, `checker`, `statePicker` |
| `-shotTheme …` | `light` or `dark` |
| `-shotIntro YES` | Show the intro and hold it |
| `-shotPicks 13,31,…` | Pre-fill the ticket checker and land on the result |

All are read through `UserDefaults`, which folds `-key value` launch arguments
over the stored domain — so they override for the life of the process without
writing to the user's own settings. `Sources/Data/Screenshot.swift` is the
whole implementation.

## The set

| Slot | Screen | Why this one |
| --- | --- | --- |
| `01-results` | Virginia home | The busiest state in the data — Powerball, Mega Millions, Millionaire for Life, Cash 5, three Fireball dailies and Bank a Million. A two-game state would undersell it. |
| `02-scratch-offs` | Virginia board | The ranking is the thing no competitor does |
| `03-check-ticket` | NC checker, pre-filled | Lands on a real five-number match, not an empty keypad |
| `04-every-state` | State picker | Shows the breadth claim is true |
| `05-light` | Texas, light | Proves the app is not dark-only |
| `06-prize-tiers` | Scratch-off detail | The depth behind the ranking — every tier, what is left of it, and how the figure was reached |

The detail screen opens the **top-ranked** game rather than one named by id, so
the frame keeps working after the data moves underneath it.

The intro animation is not in the set. It photographs as a lot of empty space
next to five dense frames, and a listing has better uses for a slot. The
`-shotIntro YES` argument still works if it is ever wanted.

To re-shoot one frame:

```bash
SHOTS="03-check-ticket" Scripts/shoot-screenshots.sh
```

## Sizes

LottoMin ships as an iPhone app, so one set covers the listing:

- **6.9-inch** — 1290 × 2796, from iPhone 17 Pro Max

Apple scales that set down for smaller iPhones; there is no separate 6.5-inch
upload any more.

Override the device if that simulator is not installed:

```bash
PHONE_NAME="iPhone 16 Pro Max" Scripts/shoot-screenshots.sh
```

**iPad is refused rather than shot.** Asking for it on an iPhone-only target
produced frames of the iPad desktop with a blank window floating in the middle
— an iPhone-only app opens in a small window there, and the blank-frame guard
does not catch it because a wallpaper compresses to plenty of bytes. The script
now checks `TARGETED_DEVICE_FAMILY` and says so instead. Add device family 2 to
`project.yml` first if an iPad set is ever wanted.

## Captions

Caption text lives in `Scripts/caption-screenshots.sh`, one line per slot:

```
slot|kicker|headline|sub-caption
```

The kicker is the ticket's serial line, so it carries a fact rather than a
slogan. Keep the claims to what the data supports — 42 of the 46 jurisdictions
publish an in-state game and the scratch-off ranking covers 12 — because a
listing that overstates earns refunds and one-star reviews.

Frames are drawn by `Scripts/caption.swift` as ticket stubs: gold monospace
kicker, headline, perforated tear line, screenshot below. It reads a TSV
manifest on stdin, so it can be driven by hand for a one-off:

```bash
printf 'in.png\tout.png\tno. 0008\tHeadline\tSub-caption\n' | swift Scripts/caption.swift
```
