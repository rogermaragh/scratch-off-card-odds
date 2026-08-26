
## Why not OCR the prize pages?

A reasonable idea, and it was tested rather than argued about. It does not
help, for two separate reasons.

**Nothing is rendered as an image.** Every remaining state's prize data was
checked for images and canvases large enough to hold a table. The only large
image found anywhere was New Hampshire's picture of the ticket. The numbers
are already text in the DOM, so OCR would be a lossy way to read what can be
read exactly — and misread digits are the one failure this project has no
defence against. A wrong `8` for a `3` produces a plausible ranking with no
structural signal that anything is off, unlike every other bug found here,
which announced itself as an impossible payout or a national draw under a
local name.

**The missing column is missing at the source, in every format.** The states
that cannot be ranked are not hiding the original counts in a picture. They do
not publish them:

| State | What they publish | Where it was confirmed |
|---|---|---|
| Pennsylvania | `Top Six Prizes \| Wins Remaining` | their own "view all" print page |
| New York | 1st and 2nd prize levels, remaining only | the HTML *and* the official game-report PDF |
| Idaho | `Prize \| Remaining` | per-game tables |
| Montana | `WIN \| PRIZE \| ODDS` — no counts at all | the scratch-games index |

New York's PDF is worth singling out, because a PDF is where you would expect
to need OCR. It extracts as clean text, and what the text says is that the
report only covers the top two prize levels. The format was never the problem.

Per-tier odds do not close the gap either — they give the launch value per
ticket but not the print run, and tickets remaining still depends on it.
