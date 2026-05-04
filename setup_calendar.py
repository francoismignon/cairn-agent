"""Lance ce script une seule fois pour autoriser l'accès à Google Calendar."""
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]
BASE_DIR = Path(__file__).parent
CREDS_PATH = BASE_DIR / "credentials" / "credentials.json"
TOKEN_PATH = BASE_DIR / "credentials" / "token.json"

if not CREDS_PATH.exists():
    print(f"❌ credentials.json introuvable dans {CREDS_PATH}")
    exit(1)

flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
creds = flow.run_local_server(port=0)
TOKEN_PATH.write_text(creds.to_json())
print(f"✅ token.json créé dans {TOKEN_PATH}")
print("Tu peux maintenant lancer le bot normalement.")
