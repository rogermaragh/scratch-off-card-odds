#!/usr/bin/env python3
"""Split the scraped bundle into a fast core plus per-state scratch-off files.

The app should be useful in every state on first launch. Draw results are the
part that exists everywhere -- Powerball and Mega Millions are sold in all 45
lottery states plus DC -- so they go in a small `core.json` that always loads.

Scratch-off inventories only exist for the states with an adapter, are far
larger, and are the slow part of a scrape. They get one file each, fetched only
when someone actually opens that state's board.

    python3 Scripts/split.py            # rewrite core.json + scratchers/*.json
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "Data"
BUNDLE = DATA / "lottery.json"
CORE = DATA / "core.json"
SCRATCHERS = DATA / "scratchers"

# Every US jurisdiction that runs a lottery. Powerball and Mega Millions are
# sold in all of them, so each one has something worth showing even with no
# scratch-off adapter.
JURISDICTIONS = {
    "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


def split(bundle):
    """Return (core, {code: scratcher_file}) from a scraped bundle."""
    scraped = bundle.get("states", {})

    core = {
        "generatedAt": bundle.get("generatedAt"),
        "drawGames": bundle.get("drawGames", []),
        "states": {},
    }
    files = {}

    for code, name in sorted(JURISDICTIONS.items(), key=lambda kv: kv[1]):
        state = scraped.get(code, {})
        games = state.get("scratchers", [])

        ratios = [g["ratio"] for g in games if g.get("ratio")]
        core["states"][code] = {
            "name": name,
            # Drives the app's ambient colour: how well the best game in this
            # state is currently paying. Kept in the core so the home screen can
            # tint itself without pulling the whole scratch-off file.
            "bestRatio": round(max(ratios), 3) if ratios else None,
            # The core carries only the summary the home screen needs; the
            # games themselves live in the per-state file.
            "scratcherCount": len(games),
            "payouts": state.get("payouts") or {},
            "drawGames": state.get("drawGames") or [],
            # So the app can say how old *this state's* prize data is, rather
            # than how recently anything at all was published.
            "scratchersScrapedAt": state.get("scratchersScrapedAt"),
        }
        if games:
            files[code] = {
                # The scratchers' own age, falling back to the bundle's for a
                # state scraped before this field existed.
                "generatedAt": (state.get("scratchersScrapedAt")
                                or bundle.get("generatedAt")),
                "state": code,
                "name": name,
                "scratchers": games,
            }

    return core, files


def main():
    if not BUNDLE.exists():
        print(f"no bundle at {BUNDLE}", file=sys.stderr)
        return 1

    core, files = split(json.loads(BUNDLE.read_text()))

    CORE.write_text(json.dumps(core, separators=(",", ":")))
    if SCRATCHERS.exists():
        shutil.rmtree(SCRATCHERS)
    SCRATCHERS.mkdir(parents=True)
    for code, payload in files.items():
        (SCRATCHERS / f"{code}.json").write_text(
            json.dumps(payload, separators=(",", ":"))
        )

    covered = len(files)
    print(f"core.json: {CORE.stat().st_size // 1024} KB, "
          f"{len(core['states'])} jurisdictions, {covered} with scratch-offs")
    for code in sorted(files):
        size = (SCRATCHERS / f"{code}.json").stat().st_size // 1024
        print(f"  {code}: {len(files[code]['scratchers']):>3} games, {size} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
