import logging
from dotenv import load_dotenv

load_dotenv()

from core.db import init_db
from interfaces.telegram import build_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

if __name__ == "__main__":
    init_db()
    app = build_app()
    app.run_polling()
