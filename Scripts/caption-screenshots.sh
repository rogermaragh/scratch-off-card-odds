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
# jurisdictions publish an in-state game, and the scratch-off ranking covers 19
# — because a listing that overstates gets refunds and one-star reviews.
FRAMES=(
  "01-results|no. 0001 · 46 jurisdictions|Every draw, every state|Powerball and Mega Millions everywhere, plus the local games most apps skip"
  "02-scratch-offs|no. 0002 · ranked by value left|Which tickets still pay|Prize money left per ticket, against how the game started"
  "03-check-ticket|no. 0003 · every recent draw|Check a ticket in seconds|Tap your numbers once, match them against weeks of results"
  "04-every-state|no. 0004 · 46 jurisdictions|Your state, found for you|Or pick any other in two taps"
  "05-light|no. 0005 · light and dark|Readable in any light|One tap from anywhere in the app"
  "06-prize-tiers|no. 0006 · every prize tier|See exactly what is left|Top prizes, remaining counts, and where each number came from"
)

# App Store Connect wants exact pixel sizes per display class, and rejects the
# whole upload if one frame is off. The captures come from whichever simulator
# is installed -- a 6.9" device here -- so each set is composited at the size
# its slot expects rather than resized afterwards.
#
#   6.9-inch  1290x2796   iPhone 16/17 Pro Max
#   6.5-inch  1284x2778   the slot that rejected 1290x2796
#
# Apple accepts 1242x2688 for 6.5" as well; 1284x2778 is the one that matches
# these captures most closely, so the device shot is scaled least.
SIZES=(
  "6.9-inch|1290x2796"
  "6.5-inch|1284x2778"
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

for entry in "${SIZES[@]}"; do
  label="${entry%%|*}"; size="${entry#*|}"
  echo "▸ $label ($size)"
  # Rewrite the destination for this size, leaving the sources alone.
  printf '%s' "$manifest" \
    | sed -E "s#[^/]*-captioned/#${label}-captioned/#" \
    | while IFS=$'\t' read -r src dst rest; do mkdir -p "$(dirname "$dst")"; done
  printf '%s' "$manifest" \
    | sed -E "s#[^/]*-captioned/#${label}-captioned/#" \
    | CAPTION_SIZE="$size" swift "$ROOT/Scripts/caption.swift"
done
