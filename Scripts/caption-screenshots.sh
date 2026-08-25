#!/usr/bin/env bash
#
# Adds App Store caption frames to the raw screenshots.
#
#   Scripts/caption-screenshots.sh
#
# Raw captures stay untouched in 6.9-inch/ and iPad-13-inch/; captioned frames
# — the ones you actually upload — are written to *-captioned/ alongside them,
# so re-captioning never needs a re-shoot.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/AppStoreScreenshots"

# slot|kicker|headline|sub-caption
#
# The kicker is the ticket's serial line, so it carries a fact rather than a
# slogan. Claims here are the ones the data actually supports — 42 of the 46
# jurisdictions publish an in-state game, and the scratch-off ranking covers 12
# — because a listing that overstates gets refunds and one-star reviews.
FRAMES=(
  "01-results|no. 0001 · 46 jurisdictions|Every draw, every state|Powerball and Mega Millions everywhere, plus the local games most apps skip"
  "02-scratch-offs|no. 0002 · ranked by value left|Which scratch-off still has prizes|Prize money left per ticket, against how the game started"
  "03-check-ticket|no. 0003 · every recent draw|Check a ticket in seconds|Tap your numbers once, match them against weeks of results"
  "04-every-state|no. 0004 · 46 jurisdictions|Your state, found automatically|Or pick any other in two taps"
  "05-light|no. 0005 · light and dark|Readable in any light|One tap from anywhere in the app"
  "06-intro|no. 0006 · unofficial results|A ticket that prints itself|Always verify with your state lottery"
  # Dormant until the capture exists — the loop skips a slot whose source is
  # missing, so this captions itself the moment the screen is shot.
  "07-scratcher-detail|no. 0007 · every prize tier|See what is actually left|Top prizes, remaining counts, and the odds behind them"
)

manifest=""
for dir in 6.9-inch iPad-13-inch; do
  [ -d "$OUT/$dir" ] || continue
  mkdir -p "$OUT/$dir-captioned"
  for frame in "${FRAMES[@]}"; do
    IFS='|' read -r slot kicker headline sub <<<"$frame"
    src="$OUT/$dir/$slot.png"
    [ -f "$src" ] || continue
    manifest+="$src	$OUT/$dir-captioned/$slot.png	$kicker	$headline	$sub"$'\n'
  done
done

[ -n "$manifest" ] || { echo "no captures found — run shoot-screenshots.sh first" >&2; exit 1; }
printf '%s' "$manifest" | swift "$ROOT/Scripts/caption.swift"
