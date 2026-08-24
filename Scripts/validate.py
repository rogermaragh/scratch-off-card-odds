#!/usr/bin/env python3
"""Refuse to publish a bundle that looks half-scraped.

A scrape that silently half-succeeds is worse than one that fails loudly: the
app would happily rank a truncated game list. Exits non-zero on any problem.
"""

import json
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent / "Data" / "lottery.json"

# Ratios outside this band mean the print-run estimate has gone wrong.
RATIO_MIN, RATIO_MAX = 0.2, 3.0
# Scratch-off returns are typically 55-75%; anything at or above 1.0 would be a
# positive-expectation ticket, which effectively never survives a full game.
RETURN_MAX_PCT = 130.0


def main():
    data = json.loads(BUNDLE.read_text())
    errors, warnings = [], []

    if not data.get("drawGames"):
        errors.append("no national draw games")
    if not data.get("states"):
        errors.append("no states")

    for game in data.get("drawGames", []):
        if not game.get("draws"):
            errors.append(f"draw game {game.get('id')}: no draws")

    for code, state in data.get("states", {}).items():
        games = state.get("scratchers", [])
        if not games:
            # Some states contribute draw games only (Arizona, Michigan). An
            # entry carrying neither is the real failure.
            if state.get("drawGames"):
                print(f"{code}: draw games only — ok")
            else:
                errors.append(f"{code}: no scratchers and no draw games")
            continue

        # A stray game without a price is a site quirk, not a broken scrape;
        # a lot of them means the price selector stopped matching.
        missing_price = [g for g in games if not g.get("price")]
        if len(missing_price) == len(games):
            # Oklahoma publishes no prices anywhere. That costs the return
            # percentage, not the ranking, so it is a property of the state.
            warnings.append(f"{code}: publishes no ticket prices")
        elif len(missing_price) > max(2, len(games) // 20):
            errors.append(f"{code}: {len(missing_price)} games missing a price")
        elif missing_price:
            warnings.append(f"{code}: {len(missing_price)} games missing a price")

        no_ratio = [g for g in games if g.get("ratio") is None]
        if no_ratio:
            errors.append(f"{code}: {len(no_ratio)} games missing a ratio")

        ratios = [g["ratio"] for g in games if g.get("ratio") is not None]
        if ratios and (min(ratios) < RATIO_MIN or max(ratios) > RATIO_MAX):
            errors.append(
                f"{code}: ratio out of range ({min(ratios):.2f}-{max(ratios):.2f})"
            )

        returns = [g["returnPct"] for g in games if g.get("returnPct") is not None]
        hot = [r for r in returns if r > RETURN_MAX_PCT]
        if hot:
            errors.append(f"{code}: {len(hot)} games claim >{RETURN_MAX_PCT:.0f}% return")

        # Expired games slip past range checks (their ratios look plausible),
        # so assert the filter actually ran wherever a state publishes them.
        if any(g.get("expired") for g in games):
            errors.append(f"{code}: expired games present in output")

        ending = sum(1 for g in games if g.get("endingSoon"))
        if ending > len(games) // 2:
            warnings.append(f"{code}: {ending}/{len(games)} flagged ending soon")

        in_state = len(state.get("drawGames") or [])
        print(f"{code}: {len(games)} games, {in_state} in-state draw games — ok")

    for warning in warnings:
        print(f"warning: {warning}")

    if errors:
        print("\nFAILED:", *errors, sep="\n  ")
        return 1

    print("\nvalidation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
