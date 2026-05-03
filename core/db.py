import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "agentperso.db"


DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inbox (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                content      TEXT    NOT NULL,
                captured_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed    BOOLEAN  DEFAULT FALSE
            );

            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                status      TEXT DEFAULT 'active',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                title             TEXT NOT NULL,
                context           TEXT,
                status            TEXT DEFAULT 'next_action',
                project_id        INTEGER REFERENCES projects(id),
                scheduled_date    DATE,
                estimated_minutes INTEGER,
                created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at      DATETIME
            );
        """)
