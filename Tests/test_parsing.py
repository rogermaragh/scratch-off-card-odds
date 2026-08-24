"""Regression tests for the parsing layer.

Every test here corresponds to a bug that actually shipped. Prize tables are
adversarial in a quiet way: they parse into *plausible* numbers when they go
wrong, so nothing throws and the mistake reaches the app looking like data.

Run:  .venv/bin/python -m pytest Tests -q
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Scripts"))

from scrape import enrich, money, odds_after_in, tiers_from_table  # noqa: E402


# --------------------------------------------------------------------- money


@pytest.mark.parametrize("text,expected", [
    ("$5,000,000", 5_000_000),
    ("$20", 20),
    ("1,182,816", 1_182_816),
    ("3.79", 3.79),
    ("$2.50 per play", 2.50),
    ("55 of 105", 55),          # combined cells read the first figure
    ("", None),
    ("no digits here", None),
    (None, None),
])
def test_money_reads_the_first_number(text, expected):
    assert money(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("$5*", 5),                 # asterisk footnote marker
    ("$5 1", 5),                # dangling footnote number
    ("$5†", 5),
    ("$100 (see note 2)", 100),
])
def test_money_ignores_footnotes(text, expected):
    """The $51 bug.

    money() used to strip every non-digit and concatenate what was left, so a
    "$5" cell followed by a footnote marker "1" became 51. That invented a $51
    prize at 1-in-13 odds behind 1.18 million tickets, which inflated one
    California game's payout to 139% -- impossible, and the only reason anyone
    noticed.
    """
    assert money(text) == expected


# ---------------------------------------------------------------------- odds


@pytest.mark.parametrize("text,expected", [
    ("1 in 3.01", 3.01),
    ("1 in 13.22", 13.22),
    ("1 IN 4.5", 4.5),
    ("1 in 1,213,145", 1_213_145),
    ("3.79", 3.79),             # already bare
    (None, None),
])
def test_odds_takes_the_figure_after_in(text, expected):
    """The 1-in-1.00 bug.

    "1 in 3.01" fed to money() correctly returns the first number -- the
    literal 1 -- so every North Carolina game reported odds of 1 in 1.00,
    meaning "every ticket wins".
    """
    assert odds_after_in(text) == expected


# -------------------------------------------------------------- prize tables


def table(headers, rows):
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><tr>{head}</tr>{body}</table>"


def test_columns_are_found_by_header_not_position():
    """NC's Powerball table has three columns; its Mega Millions table has four.

    Indexing by position put prize values in the winners column.
    """
    a = table(["Value", "Odds 1 in", "Total", "Remaining"],
              [["$500", "1,070.96", "1,362", "1,317"]])
    b = table(["Prize", "Total", "Remaining"],
              [["$500", "1,362", "1,317"]])
    for html in (a, b):
        tiers = tiers_from_table(html)
        assert tiers == [{"value": 500.0, "odds": tiers[0]["odds"],
                          "total": 1362, "remaining": 1317}]


def test_start_is_recognised_as_the_total_column():
    """Maryland labels the original count "Start", which no keyword matched."""
    html = table(["Prize Amount", "Start", "Remaining"],
                 [["$100", "500", "200"]])
    assert tiers_from_table(html) == [
        {"value": 100.0, "odds": None, "total": 500, "remaining": 200}
    ]


def test_combined_remaining_of_total_cell():
    """California packs both counts into one cell: "55 of 105"."""
    html = table(["Prizes", "Odds 1 in", "Prizes Remaining"],
                 [["$5,000", "291,730", "55 of 105"]])
    assert tiers_from_table(html) == [
        {"value": 5000.0, "odds": 291730.0, "total": 105, "remaining": 55}
    ]


def test_table_without_original_counts_is_rejected():
    """Pennsylvania publishes only "Top Six Prizes | Wins Remaining".

    There is no ratio to compute from that, and pretending otherwise would rank
    games on a number that does not exist.
    """
    html = table(["Top Six Prizes", "Wins Remaining"], [["$500", "12"]])
    assert tiers_from_table(html) == []


def test_zero_total_rows_are_dropped():
    html = table(["Prize", "Total", "Remaining"], [["$5", "0", "0"]])
    assert tiers_from_table(html) == []


# -------------------------------------------------------------------- enrich


def game(tiers, **kw):
    return {"tiers": tiers, **kw}


def test_ratio_needs_no_print_run():
    """The print run cancels out of the ratio, which is what makes states that
    publish counts but no odds (Mississippi) rankable at all."""
    tiers = [{"value": 100.0, "odds": None, "total": 100, "remaining": 50}]
    result = enrich(game(tiers, price=5.0))
    assert result["ratio"] == 1.0
    assert result["printRunSource"] is None
    assert result["evNow"] is None          # absolute figures need the run


def test_no_odds_game_does_not_crash():
    """enrich() referenced ev_now outside the branch that defines it, so any
    state publishing no odds raised UnboundLocalError mid-run and took six
    already-scraped states down with it."""
    tiers = [{"value": 50.0, "odds": None, "total": 10, "remaining": 4}]
    result = enrich(game(tiers, price=2.0))
    assert result is not None
    assert result["netPerTicket"] is None


def test_published_print_run_is_preferred():
    """Washington states its print run outright; nothing should be inferred."""
    tiers = [{"value": 100.0, "odds": 1000.0, "total": 10, "remaining": 5}]
    result = enrich(game(tiers, price=5.0, ticketsPrintedActual=12_345))
    assert result["printRunSource"] == "published"
    assert result["ticketsPrinted"] == 12_345


def test_net_per_ticket_is_value_minus_price():
    tiers = [{"value": 10.0, "odds": 2.0, "total": 100, "remaining": 100}]
    result = enrich(game(tiers, price=4.0))
    assert result["evNow"] == pytest.approx(5.0)
    assert result["netPerTicket"] == pytest.approx(1.0)


def test_nearly_exhausted_game_is_flagged():
    """Below ~5% inventory the proportional-sales assumption stops holding and
    one claim swings the ratio hard, so the figure is flagged not trusted."""
    tiers = [{"value": 100.0, "odds": 10.0, "total": 1000, "remaining": 10}]
    assert enrich(game(tiers, price=1.0))["endingSoon"] is True


def test_fully_claimed_game_is_dropped():
    tiers = [{"value": 100.0, "odds": 10.0, "total": 1000, "remaining": 0}]
    assert enrich(game(tiers, price=1.0)) is None


def test_returns_above_one_hundred_percent_are_possible_but_rare():
    """Sanity anchor for the validator's threshold: a normal scratch-off returns
    roughly 55-75%, so anything near 139% means a parsing fault, not a bargain."""
    tiers = [{"value": 10.0, "odds": 2.0, "total": 1000, "remaining": 700}]
    result = enrich(game(tiers, price=5.0))
    assert 0 < result["returnPct"] < 200


# ------------------------------------------------- ticket matching semantics
#
# The app matches picks against a draw by consuming each drawn number once,
# rather than intersecting sets. Daily games draw repeats -- Pick 3 can come up
# 5-5-8 -- and set logic would score a single 5 as matching both.

def match_count(picks, drawn):
    pool = list(drawn)
    hits = 0
    for pick in picks:
        if pick in pool:
            pool.remove(pick)
            hits += 1
    return hits


def test_repeated_numbers_are_consumed_once():
    assert match_count([5], [5, 5, 8]) == 1
    assert match_count([5, 5], [5, 5, 8]) == 2
    assert match_count([5, 5, 5], [5, 5, 8]) == 2


def test_full_and_partial_matches():
    drawn = [13, 31, 54, 57, 65]
    assert match_count([13, 31, 54, 57, 65], drawn) == 5
    assert match_count([13, 31, 99, 98, 97], drawn) == 2
    assert match_count([1, 2, 3, 4, 6], drawn) == 0


def extend(current, digit, limit):
    """Mirrors the keypad rule: append a digit only if it stays in range."""
    if current is None or current == 0:
        return digit
    combined = current * 10 + digit
    return combined if combined <= limit else digit


def test_entry_respects_the_games_range():
    # Powerball goes to 69: 1 then 3 is 13.
    assert extend(1, 3, 69) == 13
    # Pick 3 tops out at 9: 1 then 9 must restart, not become 19.
    assert extend(1, 9, 9) == 9
    # Out of range restarts rather than clamping to a number never drawn.
    assert extend(6, 9, 69) == 69
    assert extend(7, 5, 69) == 5
