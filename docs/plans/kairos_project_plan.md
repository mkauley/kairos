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
  and the calendar write before committing to Kotlin. Not shipped anywhere.
  Throwaway-quality is fine; correctness of the logic is what matters. Only
  `parser.py` ports forward — `calendar_client.py`'s OAuth path is sandbox
  scaffolding and is **not** the Android approach (see below).
- **Kotlin Android Studio project** — the real product. Two app modules
  (phone + Wear OS) plus a shared library module, in one Gradle project.
  No backend server, no runtime dependency on the Flask app.

### How the Android app writes events (decided 2026-09-02)
Via **`CalendarContract`**, the Android system calendar provider — not the
Google Calendar REST API.

- Insert a row into `CalendarContract.Events`; the device's existing Google
  account sync-adapter pushes it up to Google Calendar automatically.
- No OAuth, no Google Sign-In, no network code, no Google Cloud project for
  the shipping app, no 7-day token expiry. Just the `WRITE_CALENDAR` /
  `READ_CALENDAR` runtime permissions.
- Works the same on phone and Wear OS.
- Constraints we accept: a Google account must already be set up on the
  device, and only locally-synced calendars are reachable. Fine for a
  personal quick-capture tool.

The Google Cloud project / `credentials.json` from Phase 1 stays sandbox-only.

## Status as of this plan
- [x] Parser logic (date/time/title extraction from free text) — written and
  unit-tested in Python (`sandbox/parser.py`, `tests/test_parser.py`, 43
  cases green). Handles `M/D`, `M/D/YY(YY)`, `M.D.YYYY`, `M-D-YYYY`, month
  names ("May 23", "23 May", "23rd of May"), `today`/`tonight`/`tomorrow`,
  `H(:MM)am/pm`, 24h `HH:MM`, `noon`/`midnight`, tokens in any order. Year
  rollover when the bare M/D has already passed. Default 09:00, 1h duration.
  Title = leftover text with leading/trailing filler words stripped.
- [x] Flask app wired up (`sandbox/app.py`, `sandbox/calendar_client.py`,
  `sandbox/templates/index.html`) with `/parse`, `/create`, `/auth`,
  `/whoami` endpoints.
- [x] Google Cloud project + OAuth desktop credentials created
  (`creds/credentials.json` in place, git-ignored).
- [x] `/create` verified end-to-end against the real Google account
  (`master@occult.engineer`, America/New_York): parse → insert → event
  visible in Google Calendar, confirmed by creating and deleting a smoke
  test and a real "doctor appointment" entry.
- [x] Parser stress-test pass (`tests/test_parser.py`, 86 cases + a 3000-input
  fuzz check for no-crash / structure invariants). Validated formats and
  deliberate quirks are listed below — that list is the Kotlin spec.
- [ ] Kotlin project — not started.

### Auth notes (learned during Phase 1)
- The apt `python3-google-auth` is 1.5.1, which has **no
  `Credentials.to_json()`**. `calendar_client._save_token()` writes the
  token file by hand in the shape `from_authorized_user_file` reads back;
  do not switch to `to_json()` without bumping the library.
- `_run_flow()` passes `access_type=offline, prompt=consent` so a refresh
  token always comes back and the browser consent happens exactly once.
  Expired access tokens refresh silently.
- `calendar.events` scope only. It cannot call `calendars.get` /
  `calendarList` (403 "insufficient scopes"); `/whoami` works around this
  by reading calendar `summary`/`timeZone` off the `events.list` response
  and the account email off an event's `organizer`.

### Parser: validated formats & deliberate quirks (the Kotlin spec)

**Dates**
- `M/D`, `M/D/YY`, `M/D/YYYY`; separators `/`, `-`, `.`
- `Month D`, `Month D, YYYY`, `D Month`, `Dth of Month`; 3-letter abbrevs +
  `Sept`
- `today`, `tonight`, `tomorrow` (+ `tmrw`, `tmr`, `2mrw`, `tomorow`)
- Bare `M/D`: current year, but rolls to next year if strictly in the past
  (today's date still counts as this year). An **explicit** past year is
  kept as-is — the UI is responsible for warning about past events.
- Invalid dates (`2/30`, `13/1`, `0/5`, `2/29` non-leap) are not recognized;
  the text stays in the title and the event gets the default time.

**Times**
- `6pm`, `6 pm`, `6:30pm`, `6PM`; shorthand `6p` / `7a` (trailing "m"
  optional)
- 24-hour `HH:MM` (`18:30`)
- `noon` -> 12:00, `midnight` -> 00:00
- Bare hour after `at`/`@` with no am/pm: **7-11 -> AM, 12 -> noon,
  1-6 -> PM, 13-23 -> as-is** ("call mom at 5" = 17:00). Out-of-range
  (`at 25`) is ignored.
- QUIRK: a bare `H:MM` with no am/pm is read as **24-hour**, so
  "dinner 6:30" = 06:30. `1:15` likewise = 01:15.
- QUIRK: a lone number with neither `at` nor am/pm is **not** a time
  ("lunch 12" keeps "12" in the title).
- No time found -> **09:00**. Duration is always **1 hour**.
- `tonight` with no explicit time -> 19:00.

**Time already passed**
- No date given + the parsed time is earlier than "now" -> assume tomorrow.

**Title**
- Whatever text remains after the date/time spans are removed, with leading
  fillers (`on at the a an of for to is this next just add create schedule
  remind[er] [me] [to]`), trailing connectors (`on at the of for to is this
  next from by`), and edge punctuation (`- – — : , . | @`) stripped.
- QUIRK: an unmodeled range ("6pm-9pm strategy") keeps only the start time;
  the stray `9pm` is dropped from the title but the **end time is not
  honored** (still start + 1h). Real range parsing is Phase 3.
- Empty / filler-only result -> `"Untitled event"`.

**DST**
- The parser returns a naive local datetime and does no DST math. A time in
  a spring-forward gap is passed through unchanged; `calendar_client`
  attaches the local offset and Google resolves it.

## Running the sandbox
```bash
cd ~/code/kairos
python3 -m pytest tests/ -q          # parser spec (system python is fine)
cd sandbox && python3 app.py         # http://127.0.0.1:5000
```
Deps installed system-wide via apt (`python3-flask`, `python3-googleapi`,
`python3-google-auth-oauthlib`) — no venv needed. First `/create` opens a
browser for Google consent once and caches `creds/token.json`. Testing-mode
refresh tokens last 7 days.

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
Single Android Studio (Gradle) project, three modules:

```
Kairos/
├── app/                       # phone module (com.android.application)
│   └── .../MainActivity.kt    # Compose: text entry, preview card, confirm
├── wear/                      # Wear OS module (com.android.application)
│   └── .../MainActivity.kt    # Compose for Wear: voice-first, minimal taps
└── shared/                    # library module (com.android.library)
    ├── .../EventParser.kt     # 1:1 port of sandbox/parser.py
    ├── .../ParsedEvent.kt     # data class: title, start, end, matched
    └── .../CalendarWriter.kt  # CalendarContract insert + calendar list
```

Environment / tooling choices:
- **UI:** Jetpack Compose (Material 3 on phone, Wear Compose on watch).
- **Language level:** Kotlin, JDK bundled with Studio.
- **minSdk:** 26 (phone) / 30 (Wear OS 3+). targetSdk: current.
- **No** Google Sign-In, Play Services Auth, or REST client dependencies —
  `CalendarContract` is in the platform.
- Shared module is a plain Android library (needs `Context`/`ContentResolver`
  for `CalendarWriter`; `EventParser` itself is pure Kotlin/JVM and is unit-
  tested with plain JUnit, no instrumentation).

Tasks:
- [ ] Scaffold the project: New Project → "No Activity" or "Empty Activity"
  (phone), then add `wear` and `shared` modules.
- [ ] Port `parser.py` → `EventParser.kt`. Bring every case in
  `tests/test_parser.py` across as JUnit tests with the same fixed `NOW` —
  the port is done when they all pass. Mind the differences: Kotlin `Regex`,
  `java.time.LocalDateTime`/`LocalDate`, `Month` enum.
- [ ] `CalendarWriter.kt`:
  - `listCalendars(context): List<CalendarInfo>` — query
    `CalendarContract.Calendars` (id, display name, account name, owner,
    `CALENDAR_ACCESS_LEVEL >= CAL_ACCESS_CONTRIBUTOR`).
  - `insert(context, calendarId, ParsedEvent): Uri` — insert into
    `CalendarContract.Events` with `DTSTART`/`DTEND` in UTC millis +
    `EVENT_TIMEZONE` = device zone.
  - Runtime permission flow for `WRITE_CALENDAR` / `READ_CALENDAR`.
- [ ] Phone UI (Compose): text field, "Preview" → preview card (title +
  formatted when + which fields were matched) → "Add to calendar". Mirrors
  the Flask frontend's flow. Calendar picker (defaults to primary / first
  writable).
- [ ] Wear UI (Wear Compose): tap → `RemoteInput` / `ACTION_RECOGNIZE_SPEECH`
  voice capture → compact confirm ("heard: … — ✓ / ✗") → insert.
- [ ] Manual test pass: phone emulator (or device) with a Google account
  added; Wear emulator paired, or a real watch.

## Phase 3 — Polish (later, not blocking)
- Editing/deleting events, not just creating.
- Better ambiguity handling (e.g. confirm-before-create when the parser is
  unsure, rather than guessing).
- Real time-range parsing (`6pm-9pm` honoring the end time).
- Home-screen / tile shortcut on Wear OS for one-tap capture.
- If `CalendarContract` proves too limiting (calendars not synced locally,
  etc.), revisit the REST + OAuth path — the parser and UI stay; only
  `CalendarWriter` changes.

## Open questions to resolve during the build
- Confirmation step on the watch: full preview like the phone, or a
  lighter-weight "heard: ... — Confirm?" given screen size?
- What should happen when parsing fails on-device — retry prompt, fallback
  to manual date/time pickers, or both?
- Multiple Google accounts on one device — pick one, or always ask?
