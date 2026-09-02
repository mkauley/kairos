# Kairos — Project Plan

> *Kairos* (καιρός): the opportune moment. Say the words, and the moment
> takes its place on the calendar.

## What this is
A quick-capture calendar app. User types or speaks a loose event string
(`5/23/25 - 6pm - Doctor's Appt`) and it lands on their Google Calendar
without the usual tap-through-the-UI flow. Target platforms: Android phone
and Wear OS watch.

## Architecture decision
Two separate, independent codebases. No shared backend.

- **Python/Flask app** — local-only sandbox for validating the parsing logic
  and the Google Calendar API integration before committing to Kotlin. Not
  shipped anywhere. Throwaway-quality is fine; correctness of the logic is
  what matters.
- **Kotlin Android Studio project** — the real product. Two modules (phone +
  Wear OS) in one project, each calling the Google Calendar API directly.
  No backend server, no dependency on the Flask app at runtime.

Rationale: the parsing logic is small and self-contained, and Google Calendar
OAuth is designed for client-side use, so a middle server adds a hop and a
hosting burden with no real benefit here.

## Status as of this plan
- [x] Parser logic (date/time/title extraction from free text) — written and
  unit-tested in Python (`parser.py`). Handles `M/D`, `M/D/YY(YY)`, month
  names, `today`/`tomorrow`, `H:MMam/pm`, `noon`/`midnight`, in any order.
- [x] Flask app wired up (`app.py`, `calendar_client.py`, `templates/index.html`)
  with `/parse` and `/create` endpoints.
- [ ] `/create` not yet tested against a real Google account (needs OAuth
  `credentials.json` from Google Cloud Console).
- [ ] Kotlin project — not started.

## Phase 1 — Validate in Python (current)
Goal: prove the logic and the Google API calls work before porting anything.

1. Set up Google Cloud project, enable Calendar API, create OAuth **Desktop
   app** credentials, save as `credentials.json`.
2. Run the Flask app locally, create a handful of real events through it.
3. Stress-test the parser against messier inputs (ambiguous phrasing,
   missing pieces, edge cases like year rollover, DST) and fix as needed.
4. Treat `parser.py`'s test cases as the spec the Kotlin port has to match.

Deliverable: a list of validated input formats and edge cases, plus any
parser fixes, to carry into Phase 2.

## Phase 2 — Kotlin project scaffold
Single Android Studio project, two modules:

```
Kairos/
├── app/                  # phone module
│   ├── MainActivity.kt   # text entry, preview, confirm
│   └── ...
├── wear/                 # Wear OS module
│   ├── MainActivity.kt   # voice-first entry, minimal taps
│   └── ...
└── shared/               # module shared by app + wear
    ├── EventParser.kt    # Kotlin port of parser.py
    └── CalendarClient.kt # Google Calendar API calls, OAuth
```

Tasks:
- [ ] Scaffold the three modules in Android Studio.
- [ ] Port `parser.py` → `EventParser.kt`, carrying over the Phase 1 test
  cases (regex date/time extraction, title cleanup, default 1hr duration,
  default 9am if no time found).
- [ ] Wire up Google Sign-In / Credential Manager for OAuth on Android.
- [ ] `CalendarClient.kt` — create event via Calendar API, shared by both
  modules.
- [ ] Phone UI: text field, preview card, confirm button (mirrors the Flask
  frontend's flow).
- [ ] Wear UI: voice-first capture (tap to speak, on-watch confirm), since
  typing on a watch isn't viable.
- [ ] Manual test pass on a phone and a watch (or emulator).

## Phase 3 — Polish (later, not blocking)
- Editing/deleting events, not just creating.
- Handling multiple calendars, not just `primary`.
- Better ambiguity handling (e.g. confirm-before-create when the parser is
  unsure, rather than guessing).
- Home-screen / tile shortcut on Wear OS for one-tap capture.

## Open questions to resolve during the build
- Confirmation step on the watch: full preview like the phone, or a
  lighter-weight "heard: ... — Confirm?" given screen size?
- What should happen when parsing fails on-device — retry prompt, fallback
  to manual date/time pickers, or both?
- Multiple Google accounts on one device — pick one, or always ask?
