import datetime
import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDS_FILE = os.path.expanduser("~/.ai-os-google-creds.pickle")
CLIENT_SECRET = "credentials.json"

def get_calendar_service():
    """
    Authenticates with Google Calendar API.
    On first run opens browser for OAuth consent.
    Subsequent runs use cached credentials.
    """
    creds = None
    if os.path.exists(CREDS_FILE):
        with open(CREDS_FILE, "rb") as f:
            creds = pickle.load(f)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET):
                print(
                    "  ✗  credentials.json not found.\n"
                    "  To set up Google Calendar:\n"
                    "  1. Go to console.cloud.google.com\n"
                    "  2. Create project → Enable Calendar API\n"
                    "  3. Create OAuth2 credentials → "
                    "Desktop App\n"
                    "  4. Download as credentials.json to "
                    "project root"
                )
                return None
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(CREDS_FILE, "wb") as f:
            pickle.dump(creds, f)
    
    return build("calendar", "v3", credentials=creds)


def create_event(title: str, date_str: str, 
                 time_str: str = "09:00",
                 duration_hours: int = 1,
                 attendee_email: str = None) -> bool:
    """
    Creates a Google Calendar event.
    date_str: "tomorrow", "Monday", or "2025-04-15"
    time_str: "3pm", "15:00", "9:30am"
    """
    service = get_calendar_service()
    if not service:
        return False
    
    # Parse date
    today = datetime.date.today()
    if date_str.lower() == "tomorrow":
        event_date = today + datetime.timedelta(days=1)
    elif date_str.lower() == "today":
        event_date = today
    else:
        # Try day names
        days = ["monday","tuesday","wednesday","thursday",
                "friday","saturday","sunday"]
        if date_str.lower() in days:
            target = days.index(date_str.lower())
            current = today.weekday()
            delta = (target - current) % 7
            if delta == 0:
                delta = 7
            event_date = today + datetime.timedelta(days=delta)
        else:
            try:
                event_date = datetime.date.fromisoformat(
                    date_str)
            except ValueError:
                event_date = today + datetime.timedelta(days=1)
    
    # Parse time
    time_str = time_str.lower().replace(" ", "")
    try:
        if "pm" in time_str:
            t = time_str.replace("pm", "")
            parts = t.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            if hour != 12:
                hour += 12
        elif "am" in time_str:
            t = time_str.replace("am", "")
            parts = t.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            if hour == 12:
                hour = 0
        else:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        hour, minute = 9, 0
    
    start_dt = datetime.datetime.combine(
        event_date, 
        datetime.time(hour, minute)
    )
    end_dt = start_dt + datetime.timedelta(hours=duration_hours)
    
    event_body = {
        "summary": title,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Kolkata"
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Kolkata"
        }
    }
    
    if attendee_email:
        event_body["attendees"] = [
            {"email": attendee_email}
        ]
    
    event = service.events().insert(
        calendarId="primary",
        body=event_body
    ).execute()
    
    print(f"\n  📅  Event created successfully")
    print(f"  Title: {title}")
    print(f"  Date:  {event_date.strftime('%A, %B %d %Y')}")
    print(f"  Time:  {start_dt.strftime('%I:%M %p')}")
    if attendee_email:
        print(f"  Invite sent to: {attendee_email}")
    print(f"  Link:  {event.get('htmlLink', 'N/A')}")
    return True


def list_upcoming_events(days_ahead: int = 1) -> list:
    """
    Lists events in the next N days.
    """
    service = get_calendar_service()
    if not service:
        return []
    
    now = datetime.datetime.utcnow().isoformat() + "Z"
    end = (datetime.datetime.utcnow() + 
           datetime.timedelta(days=days_ahead)
           ).isoformat() + "Z"
    
    result = service.events().list(
        calendarId="primary",
        timeMin=now,
        timeMax=end,
        maxResults=10,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    
    events = result.get("items", [])
    
    if not events:
        label = "today" if days_ahead == 1 else \
                f"the next {days_ahead} days"
        print(f"\n  📅  No events scheduled for {label}")
        return []
    
    label = "today" if days_ahead == 1 else \
            f"next {days_ahead} days"
    print(f"\n  📅  Your schedule — {label}:\n")
    for event in events:
        start = event["start"].get(
            "dateTime", event["start"].get("date"))
        try:
            dt = datetime.datetime.fromisoformat(
                start.replace("Z",""))
            time_str = dt.strftime("%a %b %d · %I:%M %p")
        except Exception:
            time_str = start
        print(f"  ▸  {event['summary']}")
        print(f"     {time_str}\n")
    
    return events


def delete_event(title_keyword: str = None,
                 date_str: str = None) -> bool:
    """
    Deletes the first upcoming event whose title matches
    title_keyword (case-insensitive substring match).
    If title_keyword is empty, lists upcoming events and
    asks the user to confirm which one to delete.
    """
    service = get_calendar_service()
    if not service:
        return False

    # Search window: next 30 days
    now = datetime.datetime.utcnow().isoformat() + "Z"
    end = (datetime.datetime.utcnow() +
           datetime.timedelta(days=30)).isoformat() + "Z"

    result = service.events().list(
        calendarId="primary",
        timeMin=now,
        timeMax=end,
        maxResults=20,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = result.get("items", [])

    if not events:
        print("\n  📅  No upcoming events found to delete.")
        return False

    # Filter by keyword if provided
    if title_keyword:
        keyword = title_keyword.lower()
        matched = [
            e for e in events
            if keyword in e.get("summary", "").lower()
        ]
    else:
        matched = events

    if not matched:
        print(f"\n  ✗  No upcoming events matching "
              f"'{title_keyword}' were found.")
        return False

    # If multiple matches, pick the earliest one and
    # inform the user
    target = matched[0]
    event_id = target["id"]
    event_title = target.get("summary", "Untitled")
    start_raw = target["start"].get(
        "dateTime", target["start"].get("date", ""))
    try:
        dt = datetime.datetime.fromisoformat(
            start_raw.replace("Z", ""))
        time_label = dt.strftime("%A, %B %d %Y · %I:%M %p")
    except Exception:
        time_label = start_raw

    service.events().delete(
        calendarId="primary",
        eventId=event_id
    ).execute()

    print(f"\n  🗑️   Event deleted successfully")
    print(f"  Title: {event_title}")
    print(f"  Was:   {time_label}")
    if len(matched) > 1:
        print(f"\n  ℹ️   {len(matched) - 1} more event(s) matched "
              f"'{title_keyword}' — only the earliest was removed.")
    return True

