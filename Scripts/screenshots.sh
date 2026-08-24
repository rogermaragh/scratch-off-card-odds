#!/usr/bin/env bash
#
# Capture App Store screenshots across devices, appearances and states.
#
# Apple wants one set per display size. Doing that by hand means booting each
# simulator, switching appearance, picking a state and remembering to wait for
# the intro animation — about eighty manual steps for a full set. This does it
# in one command and puts everything in marketing/screenshots/.
#
#   ./Scripts/screenshots.sh                  # default devices, both appearances
#   ./Scripts/screenshots.sh --device "iPhone 17 Pro"
#   ./Scripts/screenshots.sh --states NC,NY   # only these states
#   ./Scripts/screenshots.sh --light          # skip dark mode
#
set -euo pipefail

BUNDLE_ID="com.lottomin.app"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$PROJECT_DIR/marketing/screenshots"

# One per App Store display class. Trimmed automatically to what is installed.
DEFAULT_DEVICES=(
  "iPhone 17 Pro Max"
  "iPhone 17 Pro"
  "iPhone SE (3rd generation)"
)
STATES=("NC" "NY" "AZ")
APPEARANCES=("light" "dark")
DEVICES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device)  DEVICES+=("$2"); shift 2 ;;
    --states)  IFS=',' read -r -a STATES <<< "$2"; shift 2 ;;
    --light)   APPEARANCES=("light"); shift ;;
    --dark)    APPEARANCES=("dark"); shift ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done
[[ ${#DEVICES[@]} -eq 0 ]] && DEVICES=("${DEFAULT_DEVICES[@]}")

log() { printf '  %s\n' "$*"; }

wait_for_app() {
  local udid="$1" tries=0
  until xcrun simctl launch "$udid" "$BUNDLE_ID" >/dev/null 2>&1; do
    ((tries++)); [[ $tries -gt 10 ]] && return 1; sleep 1
  done
  # The intro animation runs ~1.6s. Cold start after an install is slower.
  sleep 4
}

# A blank launch screen compresses to almost nothing, so file size tells us
# whether the app has actually drawn yet. Sleeping a fixed amount and hoping
# produced empty screenshots on cold start.
MIN_PNG_BYTES=120000

shoot() {
  local udid="$1" name="$2" tries=0 size=0
  mkdir -p "$(dirname "$name")"
  while [[ $tries -lt 6 ]]; do
    xcrun simctl io "$udid" screenshot --type=png "$name" >/dev/null 2>&1 || true
    size=$(stat -f%z "$name" 2>/dev/null || echo 0)
    [[ $size -ge $MIN_PNG_BYTES ]] && break
    ((tries++)); sleep 2
  done
  if [[ $size -lt $MIN_PNG_BYTES ]]; then
    log "!! still blank after $tries retries: ${name##*/}"
    return 1
  fi
  log "→ ${name#"$PROJECT_DIR"/} ($((size/1024))KB)"
}

echo "Building once for the simulator…"
# Build into the repo rather than the shared DerivedData. That directory went
# stale once and served a months-old binary under a different bundle id, which
# cost hours of "why is my change not showing".
DD="$PROJECT_DIR/.build-dd"
xcodebuild -project "$PROJECT_DIR/LottoMin.xcodeproj" -scheme LottoMin \
  -destination 'generic/platform=iOS Simulator' -configuration Debug \
  -derivedDataPath "$DD" build \
  >/dev/null 2>&1 || { echo "build failed" >&2; exit 1; }

APP_PATH=$(find "$DD/Build/Products/Debug-iphonesimulator" \
  -maxdepth 1 -name "LottoMin.app" 2>/dev/null | head -1)
[[ -z "$APP_PATH" ]] && { echo "could not locate LottoMin.app" >&2; exit 1; }
echo "App: $APP_PATH"

for device in "${DEVICES[@]}"; do
  udid=$(xcrun simctl list devices available \
    | grep -F "$device (" | head -1 | sed -E 's/.*\(([0-9A-F-]{36})\).*/\1/')
  if [[ -z "$udid" ]]; then
    echo "skip: no simulator named '$device'"
    continue
  fi

  echo
  echo "$device"
  xcrun simctl boot "$udid" >/dev/null 2>&1 || true
  xcrun simctl bootstatus "$udid" -b >/dev/null 2>&1 || true
  # A clean status bar keeps shots consistent and is what Apple shows.
  xcrun simctl status_bar "$udid" override \
    --time "9:41" --batteryState charged --batteryLevel 100 \
    --cellularMode active --cellularBars 4 --wifiMode active --wifiBars 3 \
    >/dev/null 2>&1 || true

  xcrun simctl uninstall "$udid" "$BUNDLE_ID" >/dev/null 2>&1 || true
  xcrun simctl install "$udid" "$APP_PATH" >/dev/null

  slug=$(echo "$device" | tr ' ()' '-' | tr -s '-' | sed 's/-$//')

  for appearance in "${APPEARANCES[@]}"; do
    xcrun simctl ui "$udid" appearance "$appearance" >/dev/null 2>&1 || true
    # The app's own override must follow the system, or it wins.
    xcrun simctl spawn "$udid" defaults write "$BUNDLE_ID" appearanceChoice \
      -string "system" >/dev/null 2>&1 || true

    for state in "${STATES[@]}"; do
      xcrun simctl terminate "$udid" "$BUNDLE_ID" >/dev/null 2>&1 || true
      xcrun simctl spawn "$udid" defaults write "$BUNDLE_ID" selectedStateCode \
        -string "$state" >/dev/null 2>&1 || true
      wait_for_app "$udid" || { log "launch failed ($state)"; continue; }

      shoot "$udid" "$OUT_DIR/$slug/$appearance/01-results-$state.png"
    done
  done

  xcrun simctl status_bar "$udid" clear >/dev/null 2>&1 || true
done

echo
echo "Done. Screenshots in ${OUT_DIR#"$PROJECT_DIR"/}/"
find "$OUT_DIR" -name '*.png' 2>/dev/null | wc -l | xargs echo "Total files:"
