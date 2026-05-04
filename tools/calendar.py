import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("calendar")

BASE_DIR = Path(__file__).parent.parent
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_PATH = BASE_DIR / "credentials" / "token.json"


def _get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
        else:
            raise RuntimeError(
                "token.json manquant — lance d'abord : uv run python setup_calendar.py"
            )
    return build("calendar", "v3", credentials=creds)


def get_or_create_project_calendar(project_title: str) -> str:
    """Retourne l'ID du calendrier du projet, le crée s'il n'existe pas."""
    try:
        service = _get_service()
        calendars = service.calendarList().list().execute().get("items", [])
        for cal in calendars:
            if cal.get("summary") == project_title:
                logger.info("[Calendar] calendrier existant trouvé : %s", project_title)
                return cal["id"]
        # Crée le calendrier
        new_cal = service.calendars().insert(body={"summary": project_title}).execute()
        logger.info("[Calendar] nouveau calendrier créé : %s", project_title)
        return new_cal["id"]
    except Exception as e:
        logger.warning("[Calendar] échec get_or_create_calendar '%s' : %s", project_title, e)
        return "primary"


def list_events(days_ahead: int = 14) -> list[dict]:
    """Retourne les événements des N prochains jours (calendrier principal)."""
    try:
        from datetime import timezone
        service = _get_service()
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=days_ahead)
        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = []
        for e in result.get("items", []):
            date = e.get("start", {}).get("date") or e.get("start", {}).get("dateTime", "")[:10]
            events.append({"title": e.get("summary", ""), "date": date})
        logger.info("[Calendar] %d événements récupérés", len(events))
        return events
    except Exception as e:
        logger.warning("[Calendar] échec list_events : %s", e)
        return []


def create_event(title: str, date_iso: str, duration_minutes: int = 60,
                 description: str = "", calendar_id: str = "primary") -> str:
    """Crée un événement all-day dans le calendrier spécifié."""
    try:
        service = _get_service()
        end_date = (datetime.fromisoformat(date_iso) + timedelta(days=1)).strftime("%Y-%m-%d")
        body = {
            "summary": title,
            "description": description,
            "start": {"date": date_iso},
            "end": {"date": end_date},
        }
        result = service.events().insert(calendarId=calendar_id, body=body).execute()
        logger.info("[Calendar] événement créé dans '%s' : %s", calendar_id, title)
        return result.get("id", "")
    except Exception as e:
        logger.warning("[Calendar] échec événement '%s' : %s", title, e)
        return ""
