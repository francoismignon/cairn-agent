from datetime import date
from langchain_core.tools import tool
from core.db import get_conn


@tool
def collect_to_inbox(content: str) -> str:
    """Capture un item dans l'inbox sans jugement ni reformulation."""
    with get_conn() as conn:
        conn.execute("INSERT INTO inbox (content) VALUES (?)", (content,))
    return "Capturé."


@tool
def get_todays_tasks() -> str:
    """Retourne les tâches next_action planifiées pour aujourd'hui (max 4)."""
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT title, context FROM tasks
               WHERE status = 'next_action'
               AND (scheduled_date = ? OR scheduled_date IS NULL)
               ORDER BY scheduled_date IS NULL, id
               LIMIT 4""",
            (today,),
        ).fetchall()
    if not rows:
        return "Aucune tâche planifiée pour aujourd'hui."
    lines = []
    for r in rows:
        line = r["title"]
        if r["context"]:
            line += f" [{r['context']}]"
        lines.append(line)
    return "\n".join(lines)


@tool
def complete_task(title: str) -> str:
    """Marque une tâche comme terminée (correspondance partielle sur le titre)."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE tasks SET status = 'done', completed_at = CURRENT_TIMESTAMP
               WHERE title LIKE ? AND status != 'done'""",
            (f"%{title}%",),
        )
    return "Tâche terminée."


@tool
def defer_task(title: str) -> str:
    """Remet une tâche dans le backlog — supprime la date planifiée."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET scheduled_date = NULL WHERE title LIKE ? AND status = 'next_action'",
            (f"%{title}%",),
        )
    return "Tâche remise dans le backlog."
