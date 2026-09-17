"""Google Calendar access for the Kairos sandbox.

Desktop-app OAuth: first call opens a browser, then caches the token in
`creds/token.json`. Only the `calendar.events` scope is requested.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

_ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS_FILE = _ROOT / "creds" / "credentials.json"
TOKEN_FILE = _ROOT / "creds" / "token.json"

# Local wall-clock zone, resolved once. Google wants an IANA name or an
# explicit offset; we send the offset the OS reports.
_LOCAL_TZ = _dt.datetime.now().astimezone().tzinfo


def _save_token(creds: Credentials) -> None:
    """Serialize a token file that `from_authorized_user_file` can reload.

    google-auth 1.5.x (the apt build) has no `Credentials.to_json()`, so we
    write the fields by hand. Newer versions read this same shape.
    """
    TOKEN_FILE.write_text(json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }, indent=2))


def _run_flow() -> Credentials:
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Missing {CREDENTIALS_FILE}. Download the OAuth desktop-app "
            "client JSON from Google Cloud Console and save it there."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    # access_type=offline + prompt=consent guarantees a refresh_token comes
    # back, so this browser round-trip only ever happens once.
    return flow.run_local_server(port=0, access_type="offline", prompt="consent")


def _load_credentials() -> Credentials:
    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except (ValueError, KeyError):
            creds = None

    if creds and creds.valid:
        return creds

    # Have a refresh token but the access token is stale/absent -> refresh
    # silently. Only fall back to the browser if that fails.
    if creds and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception:  # noqa: BLE001 - refresh token revoked/expired
            creds = None

    creds = _run_flow()
    _save_token(creds)
    return creds


def _service():
    return build("calendar", "v3", credentials=_load_credentials(), cache_discovery=False)


def _rfc3339(dt: _dt.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_LOCAL_TZ)
    return dt.isoformat()


def create_event(title: str, start: _dt.datetime, end: _dt.datetime,
                 calendar_id: str = "primary") -> dict:
    """Insert a timed event. Returns {id, htmlLink, summary, start, end}."""
    body = {
        "summary": title,
        "start": {"dateTime": _rfc3339(start)},
        "end": {"dateTime": _rfc3339(end)},
    }
    created = _service().events().insert(calendarId=calendar_id, body=body).execute()
    return {
        "id": created["id"],
        "htmlLink": created.get("htmlLink"),
        "summary": created.get("summary"),
        "start": created["start"].get("dateTime"),
        "end": created["end"].get("dateTime"),
    }


def check_auth() -> bool:
    """Force the OAuth flow now (used by the sandbox's /auth route)."""
    _load_credentials()
    return True


def whoami(calendar_id: str = "primary") -> dict:
    """Which account/calendar are we actually writing to, and what's on it.

    Stays within the `calendar.events` scope: the events.list response
    carries the calendar `summary` and `timeZone`, and each event's
    `organizer.email` (where `self` is true) is the account address.
    """
    svc = _service()
    now = _dt.datetime.now(tz=_LOCAL_TZ)
    resp = svc.events().list(
        calendarId=calendar_id,
        timeMin=(now - _dt.timedelta(days=2)).isoformat(),
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    events = resp.get("items", [])

    # Also list by most-recently-modified, ignoring start date, so an event
    # the parser put on a wrong (past or far-future) date still shows up.
    recent = svc.events().list(
        calendarId=calendar_id,
        maxResults=10,
        orderBy="updated",
    ).execute().get("items", [])

    account = None
    for e in events + recent:
        org = e.get("organizer") or {}
        if org.get("self") and org.get("email"):
            account = org["email"]
            break

    def _fmt(e):
        return {
            "summary": e.get("summary"),
            "start": e["start"].get("dateTime") or e["start"].get("date"),
            "created": e.get("created"),
            "updated": e.get("updated"),
            "htmlLink": e.get("htmlLink"),
        }

    return {
        "account_email": account,
        "calendar_summary": resp.get("summary"),
        "calendar_timezone": resp.get("timeZone"),
        "server_now": now.isoformat(),
        "event_count": len(events),
        "upcoming": [_fmt(e) for e in events],
        "recently_modified": [_fmt(e) for e in recent],
    }
