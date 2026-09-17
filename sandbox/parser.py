"""Free-text event parsing for Kairos (Flask sandbox).

Turns a loose string like "5/23/25 - 6pm - Doctor's Appt" into a structured
event dict. This module is the spec the Kotlin `EventParser.kt` port must
match, so keep behavior deterministic and the test suite authoritative.

Recognized, in any order:
    date  - M/D, M/D/YY, M/D/YYYY (/, -, or . separators)
          - "May 23", "May 23, 2025", "23 May", "23rd of May"
          - today / tonight / tomorrow
    time  - 6pm, 6:30pm, 6 PM
          - 18:30 (24-hour)
          - noon / midnight

Defaults: start 09:00 if no time found, duration 1 hour.
Leftover text (after stripping the date/time spans) becomes the title.

Public API:
    parse(text, now=None) -> {
        "title": str,          # never empty; "Untitled event" fallback
        "start": datetime,     # naive, local wall-clock
        "end":   datetime,     # start + 1h
        "matched": {           # what was recognized, for the preview UI
            "date": bool, "time": bool,
            "date_text": str | None, "time_text": str | None,
        },
    }
"""

from __future__ import annotations

import calendar as _calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

DEFAULT_HOUR = 9
DEFAULT_DURATION = timedelta(hours=1)

_MONTHS: dict[str, int] = {}
for _num, _name in enumerate(_calendar.month_name):
    if _name:
        _MONTHS[_name.lower()] = _num
for _num, _name in enumerate(_calendar.month_abbr):
    if _name:
        _MONTHS[_name.lower()] = _num
_MONTHS["sept"] = 9

_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))


@dataclass
class _Span:
    start: int
    end: int
    text: str


# --- date ----------------------------------------------------------------

_NUMERIC_DATE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2}|\d{4}))?\b")
_TEXT_DATE_MD = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)
_TEXT_DATE_DM = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_ALT})\.?(?:,?\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)
_KEYWORD_DATE = {
    "today": 0, "tonight": 0,
    "tomorrow": 1, "tomorow": 1, "tmrw": 1, "tmr": 1, "2mrw": 1,
}


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_year(raw: str | None, month: int, day: int, today: date) -> int:
    if raw is not None:
        y = int(raw)
        return 2000 + y if y < 100 else y
    # Bare M/D: this year, unless the date is strictly in the past (today's
    # date still counts as this year), in which case roll to next year.
    candidate = _safe_date(today.year, month, day)
    if candidate is not None and candidate < today:
        return today.year + 1
    return today.year


def _find_date(text: str, today: date) -> tuple[_Span, date] | None:
    m = _NUMERIC_DATE.search(text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        d = _safe_date(_resolve_year(m.group(3), month, day, today), month, day)
        if d:
            return _Span(m.start(), m.end(), m.group(0)), d

    for rx, order in ((_TEXT_DATE_MD, "md"), (_TEXT_DATE_DM, "dm")):
        m = rx.search(text)
        if not m:
            continue
        if order == "md":
            month, day, year_raw = _MONTHS[m.group(1).lower()], int(m.group(2)), m.group(3)
        else:
            day, month, year_raw = int(m.group(1)), _MONTHS[m.group(2).lower()], m.group(3)
        d = _safe_date(_resolve_year(year_raw, month, day, today), month, day)
        if d:
            return _Span(m.start(), m.end(), m.group(0)), d

    lowered = text.lower()
    for word, delta in _KEYWORD_DATE.items():
        m = re.search(rf"\b{word}\b", lowered)
        if m:
            return _Span(m.start(), m.end(), word), today + timedelta(days=delta)
    return None


# --- time ----------------------------------------------------------------

# "6pm", "6 pm", "6:30pm", "6p", "6 a.m." - the trailing "m" is optional so
# the common "6p"/"7a" shorthand still parses.
_CLOCK_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m?\.?\b", re.IGNORECASE)
_MILITARY_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
# bare hour after "at"/"@" with no am/pm - "call mom at 5", "standup @ 9"
_AT_HOUR = re.compile(r"(?:\bat\s+|@\s*)(\d{1,2})(?![:\d\w])", re.IGNORECASE)
_KEYWORD_TIME = {"noon": (12, 0), "midnight": (0, 0)}


def _bare_hour_to_24(h: int) -> int | None:
    """Deterministic am/pm guess for a bare hour: 7-11 -> AM, 12-6 -> PM."""
    if h == 0:
        return 0
    if h == 12:
        return 12
    if 1 <= h <= 6:
        return h + 12
    if 7 <= h <= 11:
        return h
    if 13 <= h <= 23:
        return h
    return None


def _find_time(text: str) -> tuple[_Span, int, int] | None:
    lowered = text.lower()
    for word, (hh, mm) in _KEYWORD_TIME.items():
        m = re.search(rf"\b{word}\b", lowered)
        if m:
            return _Span(m.start(), m.end(), word), hh, mm

    m = _CLOCK_TIME.search(text)
    if m:
        hour = int(m.group(1)) % 12
        if m.group(3).lower() == "p":
            hour += 12
        minute = int(m.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return _Span(m.start(), m.end(), m.group(0)), hour, minute

    m = _MILITARY_TIME.search(text)
    if m:
        return _Span(m.start(), m.end(), m.group(0)), int(m.group(1)), int(m.group(2))

    m = _AT_HOUR.search(text)
    if m:
        hh = _bare_hour_to_24(int(m.group(1)))
        if hh is not None:
            return _Span(m.start(), m.end(), m.group(0)), hh, 0
    return None


# --- title -------------------------------------------------------------

_EDGE_JUNK = re.compile(r"^[\s\-–—:,.|@]+|[\s\-–—:,.|@]+$")
_LEADING_FILLER = re.compile(
    r"^(?:on|at|the|a|an|of|for|to|is|this|next|just|add|create|schedule|"
    r"remind(?:er)?(?:\s+me)?(?:\s+to)?)(?:\s+|$)",
    re.IGNORECASE,
)
# Connector words left dangling once a date/time span is cut from the middle
# or end of the string ("meeting with Bob tomorrow at 2pm" -> "... Bob at").
_TRAILING_FILLER = re.compile(
    r"\s+(?:on|at|the|of|for|to|is|this|next|from|by)$",
    re.IGNORECASE,
)
# A second time token left behind by a range the parser doesn't model yet
# ("6pm-9pm strategy" -> only "6pm" is consumed; drop the stray "9pm").
_STRAY_TIME = re.compile(
    r"(?<![\w:])\d{1,2}(?::\d{2})?\s*[ap]\.?m?\.?(?![\w])",
    re.IGNORECASE,
)


def _strip_spans(text: str, spans: list[_Span]) -> str:
    if not spans:
        return text
    pieces, cursor = [], 0
    for s in sorted(spans, key=lambda x: x.start):
        pieces.append(text[cursor:s.start])
        cursor = s.end
    pieces.append(text[cursor:])
    return " ".join(p.strip() for p in pieces if p.strip())


def _extract_title(text: str, spans: list[_Span], had_time: bool) -> str:
    cleaned = _strip_spans(text, spans)
    if had_time:
        cleaned = _STRAY_TIME.sub("", cleaned)
    cleaned = _EDGE_JUNK.sub("", cleaned)
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _LEADING_FILLER.sub("", cleaned)
        cleaned = _TRAILING_FILLER.sub("", cleaned)
        cleaned = _EDGE_JUNK.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or "Untitled event"


# --- entry point -----------------------------------------------------

def parse(text: str, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    today = now.date()
    raw = (text or "").strip()

    spans: list[_Span] = []

    date_hit = _find_date(raw, today)
    time_hit = _find_time(raw)

    if date_hit:
        spans.append(date_hit[0])
        event_date = date_hit[1]
    else:
        event_date = today

    if time_hit:
        spans.append(time_hit[0])
        hour, minute = time_hit[1], time_hit[2]
    elif date_hit and date_hit[0].text == "tonight":
        hour, minute = 19, 0
    else:
        hour, minute = DEFAULT_HOUR, 0

    start = datetime(event_date.year, event_date.month, event_date.day, hour, minute)

    # No date given and the time already passed today -> assume tomorrow.
    if not date_hit and time_hit and start < now - timedelta(minutes=1):
        start += timedelta(days=1)

    end = start + DEFAULT_DURATION
    title = _extract_title(raw, spans, had_time=bool(time_hit))

    return {
        "title": title,
        "start": start,
        "end": end,
        "matched": {
            "date": bool(date_hit),
            "time": bool(time_hit),
            "date_text": date_hit[0].text if date_hit else None,
            "time_text": time_hit[0].text if time_hit else None,
        },
    }
