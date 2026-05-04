import json
import logging
import os
import re
import time
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from langgraph.checkpoint.memory import MemorySaver

from core.db import get_conn

BASE_DIR = Path(__file__).parent.parent
logger = logging.getLogger("clarify")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_soul(agent_path: str) -> str:
    return (BASE_DIR / "agents" / agent_path / "SOUL.md").read_text()


def _load_user_context() -> str:
    user = (BASE_DIR / "memory" / "USER.md").read_text()
    memory = (BASE_DIR / "memory" / "MEMORY.md").read_text()
    return f"\n\n## Profil utilisateur\n{user}\n\n## Mémoire des agents\n{memory}"


def _get_llm(temperature: float = 0.3) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=temperature,
    )


def _invoke_with_retry(chain, messages, retries: int = 2, delay: float = 2.0):
    for attempt in range(retries):
        try:
            return chain.invoke(messages)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning("LLM call failed (%s), retry in %.0fs…", e, delay)
                time.sleep(delay)
            else:
                raise


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"Pas de JSON trouvé dans : {text[:200]}")


def _todays_tasks_text() -> str:
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT title, context FROM tasks
               WHERE status = 'next_action'
               AND (scheduled_date = ? OR scheduled_date IS NULL)
               ORDER BY scheduled_date IS NULL, id LIMIT 4""",
            (today,),
        ).fetchall()
    if not rows:
        return "Aucune tâche planifiée."
    return "\n".join(
        f"- {r['title']}" + (f" [{r['context']}]" if r["context"] else "")
        for r in rows
    )


# ── State ──────────────────────────────────────────────────────────────────────

class State(TypedDict):
    messages: Annotated[list, add_messages]
    pending_capture: str | None
    extra_context: str | None
    clarified: dict | None  # output de Clarify → input d'Organize+Plan
    completed_title: str | None  # tâche que l'utilisateur vient de terminer


# ── Manager ────────────────────────────────────────────────────────────────────

_MANAGER_JSON_INSTRUCTIONS = """
## Format de réponse OBLIGATOIRE
Réponds uniquement avec ce JSON (rien d'autre avant ou après) :
{
  "action": "capture" ou "complete" ou "respond",
  "capture_content": "texte exact à capturer si action=capture, sinon chaîne vide",
  "completed_title": "titre ou mots-clés de la tâche terminée si action=complete, sinon chaîne vide",
  "reply": "ta réponse si action=respond, sinon chaîne vide"
}
"""


def manager_node(state: State) -> Command:
    soul = _load_soul("manager")
    tasks_ctx = f"\n\n## Tâches du jour en base\n{_todays_tasks_text()}"
    user_ctx = _load_user_context()
    system = soul + user_ctx + tasks_ctx + _MANAGER_JSON_INSTRUCTIONS

    response = _invoke_with_retry(
        _get_llm(),
        [SystemMessage(content=system)] + state["messages"],
    )
    try:
        data = _parse_json(response.content)
        action = data.get("action", "respond")
        capture_content = data.get("capture_content", "")
        completed_title = data.get("completed_title", "")
        reply = data.get("reply", response.content)
    except Exception:
        action, capture_content, completed_title, reply = "respond", "", "", response.content

    if action == "capture" and capture_content:
        return Command(
            goto="collector",
            update={"messages": [AIMessage(content=reply)], "pending_capture": capture_content},
        )
    if action == "complete" and completed_title:
        return Command(
            goto="complete",
            update={"completed_title": completed_title},
        )
    return Command(goto=END, update={"messages": [AIMessage(content=reply)]})


# ── Collector ──────────────────────────────────────────────────────────────────

def collector_node(state: State) -> Command:
    content = state.get("pending_capture") or ""
    with get_conn() as conn:
        conn.execute("INSERT INTO inbox (content) VALUES (?)", (content,))
    return Command(goto="context_agent", update={})


# ── Complete ───────────────────────────────────────────────────────────────────

def complete_node(state: State) -> Command:
    completed_title = state.get("completed_title") or ""

    with get_conn() as conn:
        task = conn.execute(
            """SELECT id, title, project_id FROM tasks
               WHERE status = 'next_action' AND title LIKE ? LIMIT 1""",
            (f"%{completed_title}%",),
        ).fetchone()

        if not task:
            return Command(
                goto=END,
                update={"messages": [AIMessage(content=f"Tâche '{completed_title}' introuvable dans les next actions.")]},
            )

        task_id = task["id"]
        project_id = task["project_id"]
        task_title = task["title"]

        conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task_id,),
        )
        logger.info("[Complete] tâche #%d marquée done : %s", task_id, task_title)

        if project_id:
            project = conn.execute(
                "SELECT title FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
            remaining = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE project_id = ? AND status = 'next_action'",
                (project_id,),
            ).fetchone()["cnt"]

            if remaining == 0 and project:
                logger.info("[Complete] projet #%d sans next action — relance Organize+Plan", project_id)
                clarified = {
                    "type": "project",
                    "title": project["title"],
                    "description": "Continuation — prochaine étape après tâche terminée.",
                    "explanation": "",
                    "row_id": project_id,
                }
                return Command(
                    goto="organize_plan",
                    update={
                        "messages": [AIMessage(content=f"✓ {task_title}")],
                        "clarified": clarified,
                        "extra_context": None,
                    },
                )

    return Command(
        goto=END,
        update={"messages": [AIMessage(content=f"✓ {task_title} — noté.")]},
    )


# ── Clarify committee ──────────────────────────────────────────────────────────

_POSITION_JSON = """
Réponds uniquement avec ce JSON :
{"position": "ta position en 2-4 phrases"}
"""

_SYNTHESIZER_JSON = """
Réponds uniquement avec ce JSON :
{
  "continue_debate": true ou false,
  "type": "project" ou "action" ou "someday" ou "delete" ou "reference",
  "title": "titre clair du projet ou de l'action (pas un verbe GTD ici, juste le sujet)",
  "description": "une phrase de contexte utile pour planifier (vide si type=delete)",
  "explanation": "phrase courte à envoyer à l'utilisateur"
}

Règles :
- "project" = nécessite plus d'une étape pour être fait
- "action" = faisable en une seule étape (< 2h)
- "someday" = bonne idée mais pas maintenant
- "delete" = pas actionnable, inutile
- "reference" = info à garder sans action associée
"""


def clarify_node(state: State) -> Command:
    item = state.get("pending_capture") or ""
    debate_log: list[str] = []

    final: SynthesizerDecision | None = None

    extra = state.get("extra_context") or ""
    if extra:
        item = f"{item}\n\n{extra}"
    logger.info("── DÉBUT CLARIFY ── item : %s", item)

    for round_num in range(1, 4):
        round_lines: list[str] = []
        logger.info("┌─ Round %d", round_num)

        # 3 agents de position
        for path, label in [
            ("clarify/minimaliste", "Minimaliste"),
            ("clarify/exhaustif", "Exhaustif"),
            ("clarify/realiste", "Réaliste"),
        ]:
            soul = _load_soul(path) + _POSITION_JSON
            ctx = f"Item à clarifier : {item}\n\nDébat jusqu'ici :\n" + "\n".join(debate_log)
            resp = _invoke_with_retry(
                _get_llm(0.5),
                [SystemMessage(content=soul), HumanMessage(content=ctx)],
            )
            try:
                pos = _parse_json(resp.content).get("position", resp.content)
            except Exception:
                pos = resp.content
            round_lines.append(f"[{label}] {pos}")
            logger.info("│  [%s] %s", label, pos)

        # Devil's Advocate
        da_ctx = f"Item : {item}\n\nPositions round {round_num} :\n" + "\n".join(round_lines)
        da_reply = _invoke_with_retry(
            _get_llm(0.7),
            [SystemMessage(content=_load_soul("shared/devils_advocate")),
             HumanMessage(content=da_ctx)],
        )
        round_lines.append(f"[Devil's Advocate] {da_reply.content}")
        logger.info("│  [Devil's Advocate] %s", da_reply.content)
        debate_log.extend(round_lines)
        debate_log.append(f"── round {round_num} ──")

        # Synthesizer
        synth_ctx = f"Item original : {item}\n\nDébat complet :\n" + "\n".join(debate_log)
        synth_resp = _invoke_with_retry(
            _get_llm(0.2),
            [SystemMessage(content=_load_soul("shared/synthesizer") + _SYNTHESIZER_JSON),
             HumanMessage(content=synth_ctx)],
        )
        try:
            d = _parse_json(synth_resp.content)
            final = {
                "continue_debate": d.get("continue_debate", False),
                "type":            d.get("type", "action"),
                "title":           d.get("title", item),
                "description":     d.get("description", ""),
                "explanation":     d.get("explanation", ""),
            }
        except Exception:
            final = {"continue_debate": False, "type": "action",
                     "title": item, "description": "", "explanation": "Capturé tel quel."}

        logger.info("└─ [Synthesizer] type=%s continue=%s — %s",
                    final["type"], final["continue_debate"], final["explanation"])
        if not final["continue_debate"] or final["type"] in ("delete", "someday", "reference"):
            break

    # Écriture en base selon le type
    row_id = None
    with get_conn() as conn:
        conn.execute(
            "UPDATE inbox SET processed = TRUE WHERE content = ? AND processed = FALSE",
            (item,),
        )
        t = final["type"] if final else "action"
        title = final["title"] if final else item

        if t == "project":
            cur = conn.execute(
                "INSERT INTO projects (title) VALUES (?)", (title,)
            )
            row_id = cur.lastrowid
        elif t == "action":
            cur = conn.execute(
                "INSERT INTO tasks (title) VALUES (?)", (title,)
            )
            row_id = cur.lastrowid
        elif t == "someday":
            conn.execute(
                "INSERT INTO tasks (title, status) VALUES (?, 'someday')", (title,)
            )
        # delete / reference → juste marquer processed, rien à créer

    explanation = final["explanation"] if final else "Traité."
    clarified = {**final, "row_id": row_id} if final else None

    # Fin si pas actionnable
    if not final or final["type"] in ("delete", "someday", "reference"):
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=explanation)], "clarified": None},
        )

    # Sinon → Organize+Plan
    return Command(
        goto="organize_plan",
        update={"messages": [AIMessage(content="…")], "clarified": clarified},
    )


# ── Context Agent ──────────────────────────────────────────────────────────────

_CONTEXT_AGENT_JSON = """
Réponds uniquement avec ce JSON :
{
  "needs_info": true ou false,
  "questions": "toutes tes questions en un seul message naturel à envoyer à l'utilisateur, ou chaîne vide si needs_info=false"
}
"""


def context_agent_node(state: State) -> Command:
    item = state.get("pending_capture") or ""
    user_ctx = _load_user_context()
    soul = _load_soul("organize_plan/context_agent")

    prompt = (
        f"{soul}\n{user_ctx}\n{_CONTEXT_AGENT_JSON}\n\n"
        f"Item capturé : {item}\n\n"
        "Identifie TOUTES les informations manquantes dans USER.md qui sont pertinentes "
        "pour clarifier et planifier cet item correctement. "
        "Si USER.md contient déjà tout ce qu'il faut, needs_info=false.\n\n"
        "Si needs_info=true, formate les questions en liste à puces markdown (- question)."
    )
    resp = _invoke_with_retry(_get_llm(0.3), [SystemMessage(content=prompt)])

    try:
        d = _parse_json(resp.content)
        needs_info = d.get("needs_info", False)
        questions = d.get("questions", "")
    except Exception:
        needs_info = False
        questions = ""

    if needs_info and questions:
        logger.info("[Context Agent] questions posées : %s", questions)
        # Pause le graphe, envoie les questions à l'utilisateur, attend sa réponse
        answer = interrupt(questions)
        logger.info("[Context Agent] réponse reçue : %s", answer)
        return Command(goto="clarify", update={"extra_context": f"Contexte fourni par l'utilisateur : {answer}"})

    return Command(goto="clarify", update={"extra_context": None})


# ── Organize+Plan committee ────────────────────────────────────────────────────

_OP_POSITION_JSON = """
Réponds uniquement avec ce JSON :
{"position": "ta proposition de décomposition ou planification en 2-4 phrases"}
"""

_OP_SYNTHESIZER_JSON = """
Réponds uniquement avec ce JSON :
{
  "tasks": [
    {
      "title": "Verbe + action concrète (ex: Acheter pinceaux chez Leroy Merlin)",
      "context": "@téléphone ou @ordi ou @dehors ou @maison ou @énergie-faible",
      "estimated_minutes": nombre entier,
      "day_offset": 0
    }
  ],
  "explanation": "résumé en une phrase pour l'utilisateur"
}

Règles :
- day_offset 0 = aujourd'hui, 1 = demain, 2 = après-demain, etc.
- Maximum 4 tâches par jour (day_offset identique)
- Chaque tâche commence par un verbe d'action
- Respecter la deadline si mentionnée dans le contexte
"""


def organize_plan_node(state: State) -> Command:
    clarified = state.get("clarified") or {}
    title = clarified.get("title", "")
    description = clarified.get("description", "")
    item_type = clarified.get("type", "action")
    row_id = clarified.get("row_id")
    extra = state.get("extra_context") or ""

    context = f"Titre : {title}\nType : {item_type}\nDescription : {description}\nContexte utilisateur : {extra}"
    user_ctx = _load_user_context()
    debate_log: list[str] = []
    final: dict | None = None

    logger.info("── DÉBUT ORGANIZE+PLAN ── %s", title)

    for round_num in range(1, 4):
        round_lines: list[str] = []
        logger.info("┌─ Round %d", round_num)

        for path, label in [
            ("organize_plan/urgentiste", "Urgentiste"),
            ("organize_plan/sprinter", "Sprinter"),
        ]:
            soul = _load_soul(path) + f"\n{user_ctx}\n{_OP_POSITION_JSON}"
            ctx = f"{context}\n\nDébat jusqu'ici :\n" + "\n".join(debate_log)
            resp = _invoke_with_retry(
                _get_llm(0.5),
                [SystemMessage(content=soul), HumanMessage(content=ctx)],
            )
            try:
                pos = _parse_json(resp.content).get("position", resp.content)
            except Exception:
                pos = resp.content
            round_lines.append(f"[{label}] {pos}")
            logger.info("│  [%s] %s", label, pos)

        da_ctx = f"Projet/action : {title}\n\nPositions :\n" + "\n".join(round_lines)
        da_reply = _invoke_with_retry(
            _get_llm(0.7),
            [SystemMessage(content=_load_soul("shared/devils_advocate")),
             HumanMessage(content=da_ctx)],
        )
        round_lines.append(f"[Devil's Advocate] {da_reply.content}")
        logger.info("│  [Devil's Advocate] %s", da_reply.content)
        debate_log.extend(round_lines)
        debate_log.append(f"── round {round_num} ──")

        synth_ctx = f"Projet/action : {title}\n{context}\n\nDébat :\n" + "\n".join(debate_log)
        synth_resp = _invoke_with_retry(
            _get_llm(0.2),
            [SystemMessage(content=_load_soul("shared/synthesizer") + _OP_SYNTHESIZER_JSON),
             HumanMessage(content=synth_ctx)],
        )
        try:
            d = _parse_json(synth_resp.content)
            final = {"tasks": d.get("tasks", []), "explanation": d.get("explanation", "")}
        except Exception:
            final = {"tasks": [{"title": title, "context": "", "estimated_minutes": 0, "day_offset": 0}],
                     "explanation": "Planifié tel quel."}

        logger.info("└─ [Synthesizer] %d tâches — %s", len(final["tasks"]), final["explanation"])
        break  # 1 round suffit pour Organize+Plan en Phase 1

    # Écriture des tâches en base
    from datetime import timedelta
    today = date.today()
    with get_conn() as conn:
        for t in (final["tasks"] if final else []):
            scheduled = (today + timedelta(days=t.get("day_offset", 0))).isoformat()
            conn.execute(
                """INSERT INTO tasks (title, context, estimated_minutes, scheduled_date, project_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (t["title"],
                 t.get("context") or None,
                 t.get("estimated_minutes") or None,
                 scheduled,
                 row_id if item_type == "project" else None),
            )

    explanation = final["explanation"] if final else "Planifié."
    logger.info("── FIN ORGANIZE+PLAN ── tâches enregistrées")
    return Command(
        goto=END,
        update={"messages": [AIMessage(content=explanation)], "clarified": None},
    )


# ── Graph ──────────────────────────────────────────────────────────────────────

graph = (
    StateGraph(State)
    .add_node("manager", manager_node)
    .add_node("collector", collector_node)
    .add_node("context_agent", context_agent_node)
    .add_node("clarify", clarify_node)
    .add_node("organize_plan", organize_plan_node)
    .add_edge(START, "manager")
    .add_edge("collector", "context_agent")
    .compile(checkpointer=MemorySaver())
)
