"""Spec for Kairos free-text parsing.

These cases are authoritative: the Kotlin `EventParser.kt` port must
reproduce every one of them. `NOW` is fixed so results are deterministic.
"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sandbox"))

from parser import parse  # noqa: E402

# Fixed reference point: Friday, 2025-05-16 10:00 local.
NOW = datetime(2025, 5, 16, 10, 0)


def p(text):
    return parse(text, now=NOW)


# --- canonical example -------------------------------------------------

def test_canonical_example():
    r = p("5/23/25 - 6pm - Doctor's Appt")
    assert r["title"] == "Doctor's Appt"
    assert r["start"] == datetime(2025, 5, 23, 18, 0)
    assert r["end"] == datetime(2025, 5, 23, 19, 0)
    assert r["matched"]["date"] and r["matched"]["time"]


# --- numeric dates ---------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("5/23 lunch", datetime(2025, 5, 23, 9, 0)),
    ("5/23/25 lunch", datetime(2025, 5, 23, 9, 0)),
    ("5/23/2025 lunch", datetime(2025, 5, 23, 9, 0)),
    ("05-23-2025 lunch", datetime(2025, 5, 23, 9, 0)),
    ("12.01.2025 lunch", datetime(2025, 12, 1, 9, 0)),
])
def test_numeric_date_formats(text, expected):
    assert p(text)["start"] == expected


def test_numeric_date_year_rollover():
    # 1/5 has already passed (NOW is May) -> next year.
    assert p("1/5 dentist")["start"] == datetime(2026, 1, 5, 9, 0)


def test_numeric_date_same_year_when_future():
    assert p("11/30 turkey")["start"] == datetime(2025, 11, 30, 9, 0)


# --- textual dates -------------------------------------------------

@pytest.mark.parametrize("text", [
    "May 23 doctor",
    "May 23, 2025 doctor",
    "23 May doctor",
    "23rd of May doctor",
    "may 23 doctor",
    "Fri May 23 doctor",
])
def test_textual_date_formats(text):
    assert p(text)["start"].date() == datetime(2025, 5, 23).date()


def test_month_abbrev():
    assert p("Sept 3 fair")["start"] == datetime(2025, 9, 3, 9, 0)
    assert p("Dec 25 xmas")["start"] == datetime(2025, 12, 25, 9, 0)


# --- keyword dates -----------------------------------------------

def test_today():
    assert p("today 3pm standup")["start"] == datetime(2025, 5, 16, 15, 0)


def test_tomorrow():
    assert p("tomorrow 3pm standup")["start"] == datetime(2025, 5, 17, 15, 0)


def test_tonight_defaults_to_evening():
    assert p("tonight drinks")["start"] == datetime(2025, 5, 16, 19, 0)


# --- times --------------------------------------------------------

@pytest.mark.parametrize("text,hh,mm", [
    ("tomorrow 6pm x", 18, 0),
    ("tomorrow 6:30pm x", 18, 30),
    ("tomorrow 6 PM x", 18, 0),
    ("tomorrow 6am x", 6, 0),
    ("tomorrow 12pm x", 12, 0),
    ("tomorrow 12am x", 0, 0),
    ("tomorrow 18:30 x", 18, 30),
    ("tomorrow noon x", 12, 0),
    ("tomorrow midnight x", 0, 0),
])
def test_time_formats(text, hh, mm):
    s = p(text)["start"]
    assert (s.hour, s.minute) == (hh, mm)


def test_default_time_is_9am():
    assert p("5/23 dentist")["start"].hour == 9


def test_default_duration_is_one_hour():
    r = p("5/23 6pm dentist")
    assert (r["end"] - r["start"]).total_seconds() == 3600


# --- order independence ---------------------------------------

def test_tokens_in_any_order():
    a = p("Doctor's Appt 6pm 5/23/25")
    b = p("5/23/25 6pm Doctor's Appt")
    c = p("6pm Doctor's Appt on 5/23/25")
    for r in (a, b, c):
        assert r["start"] == datetime(2025, 5, 23, 18, 0)
        assert "Doctor" in r["title"]


# --- no date: today, or tomorrow if already past ------------

def test_no_date_future_time_today():
    assert p("3pm walk")["start"] == datetime(2025, 5, 16, 15, 0)


def test_no_date_past_time_rolls_to_tomorrow():
    # NOW is 10:00; 8am today already gone.
    assert p("8am gym")["start"] == datetime(2025, 5, 17, 8, 0)


def test_no_date_no_time():
    r = p("water the plants")
    assert r["start"] == datetime(2025, 5, 16, 9, 0)
    assert r["title"] == "water the plants"


# --- title cleanup -----------------------------------------

@pytest.mark.parametrize("text,title", [
    ("5/23 6pm - Doctor's Appt", "Doctor's Appt"),
    ("Doctor's Appt @ 6pm", "Doctor's Appt"),
    ("meeting with Bob tomorrow at 2pm", "meeting with Bob"),
    ("remind me to call mom tomorrow 6pm", "call mom"),
    ("lunch w/ Sarah on May 23", "lunch w/ Sarah"),
    ("   tomorrow    3pm    ", "Untitled event"),
])
def test_title_cleanup(text, title):
    assert p(text)["title"] == title


def test_empty_input():
    r = p("")
    assert r["title"] == "Untitled event"
    assert r["matched"]["date"] is False
    assert r["matched"]["time"] is False


# --- edge cases -------------------------------------------

def test_invalid_numeric_date_ignored():
    # 13/40 is not a date; treat the whole thing as title, default time.
    r = p("13/40 weird")
    assert r["matched"]["date"] is False


def test_feb_29_non_leap_year_rejected():
    r = p("2/29/2025 leap")
    assert r["matched"]["date"] is False


def test_leap_day_valid():
    assert p("2/29/2028 leap")["start"] == datetime(2028, 2, 29, 9, 0)


# =====================================================================
# Stress-test pass — messier real-world inputs. Some assertions lock in
# behavior that is a deliberate compromise, not an ideal; those are
# marked QUIRK and the Kotlin port must match them exactly.
# =====================================================================

# --- bare "at H" hour, no am/pm ------------------------------------
# Deterministic guess: 7-11 -> AM, 12 -> noon, 1-6 -> PM, 13-23 -> as-is.

@pytest.mark.parametrize("text,hh", [
    ("call mom at 5", 17),
    ("standup at 9", 9),
    ("standup @ 9", 9),
    ("flight at 6", 18),
    ("meeting at 8", 8),
    ("thing at 12", 12),
    ("review at 14", 14),
    ("thing at 0", 0),
])
def test_bare_at_hour(text, hh):
    s = p(text)["start"]
    assert (s.hour, s.minute) == (hh, 0)
    assert p(text)["matched"]["time"] is True


def test_bare_at_hour_out_of_range_ignored():
    r = p("call at 25")
    assert r["matched"]["time"] is False
    assert r["title"] == "call at 25"


def test_bare_hour_needs_at_prefix():
    # QUIRK: a lone number with no "at" and no am/pm is not a time.
    r = p("lunch 12")
    assert r["matched"]["time"] is False
    assert r["title"] == "lunch 12"


def test_at_hour_not_triggered_by_ordinal_street():
    r = p("meeting at 5th and Main")
    assert r["matched"]["time"] is False
    assert r["title"] == "meeting at 5th and Main"


# --- am/pm shorthand ---------------------------------------------

@pytest.mark.parametrize("text,hh,mm", [
    ("dinner 6p", 18, 0),
    ("coffee 7a", 7, 0),
    ("call 6 p.m.", 18, 0),
    ("call 6a.m.", 6, 0),
])
def test_ampm_shorthand(text, hh, mm):
    s = p(text)["start"]
    assert (s.hour, s.minute) == (hh, mm)


def test_ampm_shorthand_does_not_eat_words():
    # "6 apples" must not read as 6 AM.
    r = p("buy 6 apples tomorrow")
    assert r["matched"]["time"] is False
    assert "apples" in r["title"]


# --- bare colon time is read as 24-hour ------------------------

def test_bare_colon_time_is_24h():
    # QUIRK: "dinner 6:30" -> 06:30, not 18:30. Add am/pm to disambiguate.
    assert p("dinner 6:30")["start"].hour == 6
    assert p("dinner 6:30pm")["start"].hour == 18


def test_colon_in_title_not_mistaken_for_time():
    # "1:1" / "1:15" style — needs two digits after colon to be a time,
    # and 1:15 IS a valid 24h time, so document that it wins.
    assert p("1:1 with Bob 3pm")["title"].startswith("1:1")
    assert p("1:15 sync")["start"].hour == 1  # QUIRK: reads as 01:15


# --- keyword-date abbreviations -------------------------------

@pytest.mark.parametrize("word", ["tomorrow", "tmrw", "tmr", "2mrw", "tomorow"])
def test_tomorrow_abbreviations(word):
    assert p(f"{word} 3pm x")["start"].date() == datetime(2025, 5, 17).date()


def test_at_symbol_stripped_from_title():
    assert p("meeting w/ Bob @ 2pm tmrw")["title"] == "meeting w/ Bob"


# --- unmodeled time ranges (Phase 3) -------------------------

def test_time_range_takes_start_only():
    # QUIRK: "6pm-9pm" -> starts 18:00, default 1h duration (ends 19:00);
    # the "9pm" is dropped from the title but the end time is NOT honored.
    r = p("6pm-9pm strategy session")
    assert r["start"] == datetime(2025, 5, 16, 18, 0)
    assert r["end"] == datetime(2025, 5, 16, 19, 0)
    assert "9pm" not in r["title"]
    assert r["title"] == "strategy session"


# --- title punctuation -----------------------------------

@pytest.mark.parametrize("text,title", [
    ("Dr. Smith 3pm", "Dr. Smith"),
    ("standup @ 3pm", "standup"),
    ("pick up kids @ 3:15pm", "pick up kids"),
    ("Coffee w/ Dana — tomorrow 10am", "Coffee w/ Dana"),
    ("Team sync (weekly) 5/20 2pm", "Team sync (weekly)"),
])
def test_title_punctuation(text, title):
    assert p(text)["title"] == title


# --- no meaningful title -------------------------------

@pytest.mark.parametrize("text", ["5/20 2pm", "tomorrow at 9", "just noon", "on 5/20"])
def test_titleless_inputs_fall_back(text):
    assert p(text)["title"] == "Untitled event"


# --- invalid dates are left in the title -----------------

@pytest.mark.parametrize("text", ["13/1 nonsense", "2/30 bad", "0/5 bad", "2/29/2027 bad"])
def test_invalid_numeric_dates_left_alone(text):
    r = p(text)
    assert r["matched"]["date"] is False
    assert r["start"].hour == 9


# --- year handling on bare M/D -------------------------

def test_bare_md_today_is_today_not_next_year():
    # 5/16 == NOW's date -> today, not rolled forward.
    assert p("5/16 thing")["start"].date() == datetime(2025, 5, 16).date()


def test_bare_md_yesterday_rolls_forward():
    # 5/15 was yesterday -> next year.
    assert p("5/15 thing")["start"].date() == datetime(2026, 5, 15).date()


def test_explicit_past_year_is_respected():
    # QUIRK: an explicit past year is kept as-is (no roll-forward). The
    # sandbox/UI is responsible for warning about past events.
    assert p("5/15/2020 old thing")["start"].year == 2020


# --- DST boundary: parser stays naive -----------------

def test_dst_gap_time_passed_through_naive():
    # 2026-03-08 02:30 EST doesn't exist (spring forward). The parser
    # returns the naive datetime unchanged; calendar_client attaches the
    # local offset and Google resolves it.
    r = p("3/8/26 2:30am spring forward")
    assert r["start"] == datetime(2026, 3, 8, 2, 30)


# --- order independence, harder --------------------

def test_order_independence_with_noise():
    a = p("Doctor's Appt — 5/23/25 at 6pm — bring insurance card")
    assert a["start"] == datetime(2025, 5, 23, 18, 0)
    assert "Doctor's Appt" in a["title"]
    assert "insurance card" in a["title"]
