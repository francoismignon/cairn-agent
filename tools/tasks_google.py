import logging
from pathlib import Path

logger = logging.getLogger("tasks_google")

BASE_DIR = Path(__file__).parent.parent
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]
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
                "token.json manquant ou invalide — lance : uv run python setup_calendar.py"
            )
    return build("tasks", "v1", credentials=creds)


def get_or_create_task_list(title: str) -> str:
    """Retourne l'ID de la liste de tâches, la crée si elle n'existe pas."""
    try:
        service = _get_service()
        lists = service.tasklists().list().execute().get("items", [])
        for lst in lists:
            if lst.get("title") == title:
                logger.info("[Tasks] liste existante : %s", title)
                return lst["id"]
        result = service.tasklists().insert(body={"title": title}).execute()
        logger.info("[Tasks] nouvelle liste créée : %s", title)
        return result["id"]
    except Exception as e:
        logger.warning("[Tasks] échec get_or_create_task_list '%s' : %s", title, e)
        return "@default"


def create_task(title: str, task_list_id: str, notes: str = "", due_date: str = "") -> str:
    """Crée une tâche dans la liste spécifiée. due_date format : YYYY-MM-DD."""
    try:
        service = _get_service()
        body: dict = {"title": title, "notes": notes}
        if due_date:
            body["due"] = f"{due_date}T00:00:00.000Z"
        result = service.tasks().insert(
            tasklist=task_list_id,
            body=body,
        ).execute()
        logger.info("[Tasks] tâche créée : %s", title)
        return result.get("id", "")
    except Exception as e:
        logger.warning("[Tasks] échec création tâche '%s' : %s", title, e)
        return ""


def complete_task_by_title(title: str) -> bool:
    """Cherche une tâche dans toutes les listes et la marque comme complétée."""
    try:
        service = _get_service()
        lists = service.tasklists().list().execute().get("items", [])
        for lst in lists:
            tasks = service.tasks().list(
                tasklist=lst["id"], showCompleted=False
            ).execute().get("items", [])
            for task in tasks:
                if task.get("title") == title:
                    service.tasks().update(
                        tasklist=lst["id"],
                        task=task["id"],
                        body={**task, "status": "completed"},
                    ).execute()
                    logger.info("[Tasks] tâche complétée : %s (liste: %s)",
                                title, lst.get("title"))
                    return True
    except Exception as e:
        logger.warning("[Tasks] échec complétion '%s' : %s", title, e)
    return False
