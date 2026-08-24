"""Regression tests for the parsing layer.

Every test here corresponds to a bug that actually shipped. Prize tables are
adversarial in a quiet way: they parse into *plausible* numbers when they go
wrong, so nothing throws and the mistake reaches the app looking like data.

Run:  .venv/bin/python -m pytest Tests -q
"""

import sys
from pathlib import Path

import re

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


# --------------------------------------------------------------- draw dates
#
# Ten states publish results on each game's own page, and the date beside those
# numbers is written ten different ways. Each case below is a string copied off
# a live page that the first version of the parser got wrong.

from datetime import date  # noqa: E402

from scrape import date_from_text  # noqa: E402

TODAY = date(2026, 8, 24)


@pytest.mark.parametrize("text,expected", [
    # California shouts the month and abbreviates the weekday onto it.
    ("Fantasy 5 Winning Numbers: SUN/AUG 23, 2026 Draw #11978", "2026-08-23"),
    # Washington shouts it *and* omits the year.
    ("Latest Draw: SUN/AUG 23 20 21 33 36 38", "2026-08-23"),
    # Colorado spells it out, still no year.
    ("Sunday, August 23 Cash 5 Winning Numbers", "2026-08-23"),
    ("08/23/2026", "2026-08-23"),
    ("2026-08-23", "2026-08-23"),
    ("Aug. 23, 2026", "2026-08-23"),
])
def test_date_is_read_however_the_state_writes_it(text, expected):
    assert date_from_text(text, today=TODAY) == expected


def test_next_draw_notice_never_wins():
    """The trap that made Wisconsin show an unplayed draw as a result.

    Every one of these pages advertises the next drawing beside the last
    result. On draw day that date is *today* -- not in the future -- so any
    "most recent date that has already happened" rule picks the wrong one.
    """
    assert date_from_text(
        "Next Drawing Monday, August 24 Sunday, August 23 Cash 5 Winning Numbers",
        today=TODAY) == "2026-08-23"
    # Wisconsin prints only the next draw's date beside the balls, so once
    # that notice is cut there is no date left -- and the game is dropped
    # rather than dated with a draw that has not happened.
    assert date_from_text(
        "Megabucks 11 15 25 37 39 44 Next draw: August 26, 2026",
        today=TODAY) is None
    assert date_from_text("Next Draw: TONIGHT", today=TODAY) is None


def test_future_dates_are_refused():
    """A results page should never yield a draw that has not happened."""
    assert date_from_text("August 30, 2026", today=TODAY) is None


def test_a_year_less_date_rolls_back_rather_than_forward():
    """December on a page read in August means last December."""
    assert date_from_text("December 30", today=TODAY) == "2025-12-30"


def test_the_newest_draw_wins_on_a_results_list():
    """Results pages list many draws; the game shows the latest."""
    assert date_from_text("AUG 21, 2026 ... AUG 23, 2026 ... AUG 22, 2026",
                          today=TODAY) == "2026-08-23"


def test_no_date_means_no_game():
    assert date_from_text("081118192342", today=TODAY) is None
    assert date_from_text("", today=TODAY) is None
    assert date_from_text(None, today=TODAY) is None


# ------------------------------------------------ random numbers are not draws
#
# Most state game pages carry a "pick numbers for me" widget that renders its
# output exactly like a result row. Vermont's sits on every game page, so the
# structural detector found it first and dated it from the page around it --
# random numbers, presented as the winning numbers.

from scrape import GENERATOR_RE  # noqa: E402


@pytest.mark.parametrize("cls", [
    "numGenBallContainer",
    "number-generator-balls",
    "quick-pick-results",
    "randomNumbers",
    "game-generator ball-row",
])
def test_generator_widgets_are_refused(cls):
    assert GENERATOR_RE.search(cls)


@pytest.mark.parametrize("cls", [
    "draw-cards--winning-numbers",
    "winningNumberBalls",
    "drawn-numbers",
    "balls",
    "win-numbers",
    "",
])
def test_real_result_rows_are_kept(cls):
    """The states whose markup does anchor a result must not be swept up."""
    assert not GENERATOR_RE.search(cls)


def test_a_date_running_into_the_numbers_behind_it():
    """Kansas prints the date and the balls with nothing between them.

    "Last Draw: Saturday, Aug 22" followed by 133154576523 reads as
    "Aug 22133154576523". Without a guard on what may follow the day, the year
    group swallows "1331" and the draw is dated to the fourteenth century.
    """
    assert date_from_text("Last Draw: Saturday, Aug 22133154576523",
                          today=TODAY) == "2026-08-22"


def test_dot_separated_dates():
    """South Dakota writes 08.23.26 where everyone else writes a slash."""
    assert date_from_text("Winning Numbers: 08.23.26", today=TODAY) == "2026-08-23"
    assert date_from_text("Winning Numbers: 08.22.2620233642504",
                          today=TODAY) == "2026-08-22"


def test_a_state_may_not_republish_a_national_draw():
    """Indiana's page labels the site-wide Powerball widget "Hoosier Lotto".

    The name hint matched, the count matched, the date was real -- and the
    numbers were Powerball's. Any in-state row identical to a national draw is
    refused, whatever the page calls it.
    """
    import scrape
    scrape.MULTISTATE_DRAWS.clear()
    scrape.remember_multistate(
        {"draws": [{"numbers": [13, 31, 54, 57, 65, 23]}]})
    assert (13, 31, 54, 57, 65, 23) in scrape.MULTISTATE_DRAWS
    assert (12, 22, 40, 42, 44) not in scrape.MULTISTATE_DRAWS
    scrape.MULTISTATE_DRAWS.clear()


@pytest.mark.parametrize("text,expected", [
    ("8/24 MID-DAY 7 5 6", "2026-08-24"),      # Iowa omits the year entirely
    ("8/23 EVENING 5 9 6", "2026-08-23"),
    ("12/30 results", "2025-12-30"),           # rolls back rather than forward
])
def test_dates_with_no_year_at_all(text, expected):
    assert date_from_text(text, today=TODAY) == expected


def test_a_bare_month_day_never_steals_a_full_date():
    """The short form must not claim the front of a complete date."""
    assert date_from_text("08/23/2026", today=TODAY) == "2026-08-23"
    assert date_from_text("08.23.26", today=TODAY) == "2026-08-23"


def test_odds_are_not_dates():
    """"1 in 10,000" and similar must not parse as a day and month."""
    assert date_from_text("odds 1 in 10,000", today=TODAY) is None


# ------------------------------------------------------- config well-formedness
#
# Both game tables are hand-written and long. A short entry does not fail until
# the scrape reaches that state, minutes in, where the per-state guard turns it
# into one skipped state and a one-line message -- Virginia went missing exactly
# this way. Shape belongs in the tests, where it costs nothing to check.

def test_per_game_entries_are_well_formed():
    import scrape
    for code, pages in scrape.PER_GAME.items():
        for url, entries in pages:
            assert url.startswith("https://"), f"{code}: {url}"
            for entry in entries:
                assert len(entry) == 5, f"{code}: {entry[:2]}"
                slug, name, count, special, hint = entry
                assert slug and name and 3 <= count <= 24, f"{code}: {entry[:2]}"
                for pattern in (special, hint):
                    if pattern:
                        re.compile(pattern)


def test_text_game_entries_are_well_formed():
    import scrape
    for code, pages in scrape.TEXT_GAMES.items():
        for url, entries in pages:
            assert url.startswith("https://"), f"{code}: {url}"
            for entry in entries:
                assert len(entry) == 5, f"{code}: {entry[:2]}"
                slug, name, count, pattern, num_re = entry
                assert slug and name and 3 <= count <= 24, f"{code}: {entry[:2]}"
                compiled = re.compile(pattern, re.I)
                assert "date" in compiled.groupindex, f"{code}/{slug}: no date group"
                assert "nums" in compiled.groupindex, f"{code}/{slug}: no nums group"
                if num_re:
                    assert re.compile(num_re).groups == 1, f"{code}/{slug}"


def test_every_configured_state_is_wired_into_the_table():
    """A game table entry with no STATES row never runs at all."""
    import scrape
    for code in list(scrape.PER_GAME) + list(scrape.TEXT_GAMES):
        assert code in scrape.STATES, f"{code} is configured but never called"


# --------------------------------------------- games that come and go
#
# Georgia's draw API stops returning the previous result for a while between
# draws, so a healthy game disappears for a scrape or two. Dropping it makes
# the game vanish from the app until the next draw lands.

def test_a_game_missing_this_run_is_carried_forward():
    import scrape
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
    known = [{"id": "GA-georgiafive", "name": "Georgia Five",
              "draws": [{"date": recent, "numbers": [0, 0, 5, 2, 6]}]}]
    merged = scrape.keep_known_games([], known)
    assert [g["id"] for g in merged] == ["GA-georgiafive"]


def test_a_fresh_result_wins_over_the_kept_one():
    import scrape
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc).date() - timedelta(days=2)).isoformat()
    fresh = [{"id": "GA-georgiafive", "name": "Georgia Five",
              "draws": [{"date": recent, "numbers": [1, 2, 3, 4, 5]}]}]
    known = [{"id": "GA-georgiafive", "name": "Georgia Five",
              "draws": [{"date": recent, "numbers": [0, 0, 5, 2, 6]}]}]
    merged = scrape.keep_known_games(fresh, known)
    assert len(merged) == 1
    assert merged[0]["draws"][0]["numbers"] == [1, 2, 3, 4, 5]


def test_a_retired_game_still_ages_out():
    """Carrying games forward must not resurrect one that has ended."""
    import scrape
    known = [{"id": "GA-jumbolotto", "name": "Jumbo Lotto",
              "draws": [{"date": "2024-11-14", "numbers": [12, 34, 36, 41, 42, 43]}]}]
    assert scrape.keep_known_games([], known) == []


def test_a_game_with_no_draws_is_not_carried():
    import scrape
    assert scrape.keep_known_games([], [{"id": "X", "draws": []}]) == []


def test_a_state_in_both_tables_uses_the_combined_reader():
    """Montana publishes one game as ball elements and one as text.

    Wiring it to either reader alone silently drops the other game -- and
    drops it the quiet way, as one fewer game rather than an error.
    """
    import functools

    import scrape
    for code in set(scrape.PER_GAME) & set(scrape.TEXT_GAMES):
        entry = scrape.STATES[code]["drawGames"]
        assert isinstance(entry, functools.partial), code
        assert entry.func is scrape.combined_draw_games, (
            f"{code} is in both game tables but reads with "
            f"{entry.func.__name__}")


def test_special_ball_is_split_off_the_main_numbers():
    import scrape
    game = {"id": "VA-pick4", "draws": [
        {"date": "2026-08-24", "numbers": [9, 6, 6, 9, 5], "special": None}]}
    result = scrape.split_special(game)
    assert result["draws"][0]["numbers"] == [9, 6, 6, 9]
    assert result["draws"][0]["special"] == 5
    assert result["specialLabel"] == "Fireball"


def test_a_game_with_no_extra_ball_is_untouched():
    import scrape
    game = {"id": "VA-cash5", "draws": [
        {"date": "2026-08-24", "numbers": [3, 13, 17, 27, 37], "special": None}]}
    assert scrape.split_special(game)["draws"][0]["numbers"] == [3, 13, 17, 27, 37]


def test_a_row_of_the_wrong_length_is_left_alone():
    """If a page changes shape, do not carve a number off the main draw."""
    import scrape
    game = {"id": "VA-pick4", "draws": [
        {"date": "2026-08-24", "numbers": [9, 6, 6, 9], "special": None}]}
    assert scrape.split_special(game)["draws"][0]["numbers"] == [9, 6, 6, 9]
    assert scrape.split_special(game)["draws"][0]["special"] is None


def test_every_special_ball_rule_names_a_real_game():
    """A rule keyed to a game id that no longer exists never fires."""
    import scrape
    ids = {f"{code}-{slug}"
           for table in (scrape.PER_GAME, scrape.TEXT_GAMES)
           for code, pages in table.items()
           for _, entries in pages
           for slug, *_ in entries}
    missing = sorted(set(scrape.SPECIAL_BALLS) - ids)
    assert not missing, f"special-ball rules for unknown games: {missing}"
