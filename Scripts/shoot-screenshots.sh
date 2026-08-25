#!/usr/bin/env bash
#
# Regenerates the App Store screenshot set from a clean launch of each screen.
#
#   Scripts/shoot-screenshots.sh           # 6.9" iPhone set (default)
#   Scripts/shoot-screenshots.sh pad       # iPad, once the target supports it
#   SHOTS="01-results 03-check-ticket" Scripts/shoot-screenshots.sh phone
#
# Screens are reached through the app's launch arguments rather than by
# simulated taps, so a run is deterministic and repeatable. The waits are short
# because the data ships in the bundle — nothing here is waiting on a network.
set -euo pipefail

BUNDLE=com.lottomin.app
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/AppStoreScreenshots"
DD="$ROOT/.build-dd"

PHONE_NAME="${PHONE_NAME:-iPhone 17 Pro Max}"
PAD_NAME="${PAD_NAME:-iPad Pro 13-inch (M5)}"

# Pinned on every launch, because both would otherwise drift between shots.
#
# The state is pinned because the app geolocates on first run: a set shot on
# this machine would otherwise advertise whichever state the machine is sitting
# in, and a re-shoot elsewhere would silently produce a different app.
#
# Appearance is pinned per shot rather than left on "system", so a set begun
# before sunset and finished after it does not disagree with itself halfway
# through.
#
# Both are read straight from UserDefaults, which folds `-key value` launch
# arguments over the stored domain — so these override for the life of the
# process without touching the user's own settings.

# name|seconds to wait|launch arguments
#
# Virginia leads because it is the busiest state in the data: Powerball, Mega
# Millions, Millionaire for Life, Cash 5, three daily games each carrying a
# Fireball, and Bank a Million — the widest row in the app. A state with two
# games would undersell the whole thing.
SHOT_LIST=(
  "01-results|5|-shotState VA -shotTheme dark"
  "02-scratch-offs|6|-shotState VA -shotScreen scratchers -shotTheme dark"
  "03-check-ticket|5|-shotState NC -shotScreen checker -shotTheme dark -shotPicks 13,31,54,57,65"
  "04-every-state|5|-shotState CA -shotScreen statePicker -shotTheme dark"
  "05-light|5|-shotState TX -shotTheme light"
  "06-intro|4|-shotState NY -shotIntro YES -shotTheme dark"
  # Dormant until captured by hand: the scratch-off detail needs a tap, which
  # this script deliberately cannot do. The loop skips a slot whose launch
  # arguments are empty, so it starts working the moment the screen is
  # addressable by argument.
  "07-scratcher-detail|5|"
)

# Resolves a device name to the UDID of a single concrete device. Duplicate
# simulator names are common, and `simctl ... booted` silently picks the wrong
# one when more than one device is up — so everything here is UDID-addressed.
udid_for() {
  xcrun simctl list devices available -j \
    | python3 -c "
import json,sys
name=sys.argv[1]
data=json.load(sys.stdin)['devices']
hits=[d for v in data.values() for d in v if d['name']==name]
if not hits:
    sys.exit('No simulator named '+name)
booted=[d for d in hits if d['state']=='Booted']
print((booted or hits)[0]['udid'])
" "$1"
}

echo "▸ building"
# Built into the repo rather than shared DerivedData. That directory went stale
# once and served a months-old binary under a different bundle id, which cost
# hours of "why is my change not showing".
xcodebuild -project "$ROOT/LottoMin.xcodeproj" -scheme LottoMin \
  -destination 'generic/platform=iOS Simulator' -configuration Debug \
  -derivedDataPath "$DD" build >/dev/null 2>&1 \
  || { echo "build failed" >&2; exit 1; }
APP="$DD/Build/Products/Debug-iphonesimulator/LottoMin.app"
[ -d "$APP" ] || { echo "no app at $APP" >&2; exit 1; }

# A blank launch screen compresses to almost nothing, so file size tells us
# whether the app has drawn yet. Sleeping a fixed amount and hoping produced
# empty frames on cold start.
MIN_BYTES=90000

shoot_set() {
  local name="$1" outdir="$2" width="$3" height="$4"
  local udid; udid="$(udid_for "$name")"

  echo "▸ $name  ($udid)"
  xcrun simctl boot "$udid" 2>/dev/null || true
  xcrun simctl bootstatus "$udid" -b >/dev/null 2>&1 || true
  # The status bar Apple shows on its own marketing, and one less thing that
  # differs between two frames of the same set.
  xcrun simctl status_bar "$udid" override --time "9:41" \
    --batteryState charged --batteryLevel 100 \
    --cellularMode active --cellularBars 4 --wifiMode active --wifiBars 3 \
    >/dev/null 2>&1 || true
  xcrun simctl uninstall "$udid" "$BUNDLE" >/dev/null 2>&1 || true
  xcrun simctl install "$udid" "$APP"
  mkdir -p "$outdir"

  for entry in "${SHOT_LIST[@]}"; do
    local shot="${entry%%|*}"; local rest="${entry#*|}"
    local wait="${rest%%|*}"; local args="${rest#*|}"
    if [ -n "${SHOTS:-}" ] && [[ " $SHOTS " != *" $shot "* ]]; then continue; fi
    [ -n "$args" ] || { echo "  · $shot (skipped: capture by hand)"; continue; }

    echo "  · $shot (${wait}s)"
    xcrun simctl terminate "$udid" "$BUNDLE" >/dev/null 2>&1 || true
    # shellcheck disable=SC2086
    xcrun simctl launch "$udid" "$BUNDLE" $args >/dev/null
    sleep "$wait"

    local tries=0 size=0
    while [ "$tries" -lt 5 ]; do
      xcrun simctl io "$udid" screenshot "$outdir/$shot.png" >/dev/null 2>&1 || true
      size=$(stat -f%z "$outdir/$shot.png" 2>/dev/null || echo 0)
      [ "$size" -ge "$MIN_BYTES" ] && break
      tries=$((tries + 1)); sleep 2
    done
    if [ "$size" -lt "$MIN_BYTES" ]; then
      echo "    !! still blank after $tries retries"
      continue
    fi
    sips -z "$height" "$width" "$outdir/$shot.png" >/dev/null
  done
  xcrun simctl terminate "$udid" "$BUNDLE" >/dev/null 2>&1 || true
  xcrun simctl status_bar "$udid" clear >/dev/null 2>&1 || true
}

# LottoMin ships as an iPhone app (TARGETED_DEVICE_FAMILY 1), so there is no
# iPad set to shoot and the App Store does not ask for one. Left in rather than
# deleted because it caught a real problem: run against an iPad simulator, an
# iPhone-only app opens in a small window over the desktop, and what comes back
# is the wallpaper with a blank sheet in the middle. The size guard does not
# notice, because a wallpaper compresses to plenty of bytes. Adding iPad to the
# target is the fix; shooting it before then only produces frames that look
# broken on the listing.
ipad_supported() {
  grep -q 'TARGETED_DEVICE_FAMILY: *"[^"]*2' "$ROOT/project.yml"
}

case "${1:-phone}" in
  phone) shoot_set "$PHONE_NAME" "$OUT/6.9-inch" 1290 2796 ;;
  pad|both)
    if ! ipad_supported; then
      echo "This build is iPhone-only (TARGETED_DEVICE_FAMILY 1), so an iPad" >&2
      echo "set would capture the desktop, not the app. Add device family 2" >&2
      echo "to project.yml first." >&2
      [ "${1:-}" = "pad" ] && exit 1
    else
      shoot_set "$PAD_NAME" "$OUT/iPad-13-inch" 2064 2752
    fi
    [ "${1:-}" = "both" ] && shoot_set "$PHONE_NAME" "$OUT/6.9-inch" 1290 2796
    ;;
  *) echo "usage: $0 [phone|pad|both]" >&2; exit 1 ;;
esac
echo "✓ done → $OUT"
