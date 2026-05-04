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
from tools.memory import append_to_user_profile

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
    needs_research: bool | None
    research_query: str | None
    research_result: str | None
    debate_log: list[str] | None  # survit aux interrupts mid-débat
    pending_user_question: str | None  # question du Synthesizer en attente


# ── Manager ────────────────────────────────────────────────────────────────────

_MANAGER_JSON_INSTRUCTIONS = """
## Format de réponse OBLIGATOIRE
Réponds uniquement avec ce JSON (rien d'autre avant ou après) :
{
  "action": "capture" ou "complete" ou "respond",
  "capture_content": "texte exact à capturer si action=capture, sinon chaîne vide",
  "completed_title": "titre ou mots-clés de la tâche terminée si action=complete, sinon chaîne vide",
  "reply": "ta réponse si action=respond, sinon chaîne vide",
  "user_note": "info personnelle à retenir sur l'utilisateur (préférences, infos famille, contexte) — chaîne vide si rien de nouveau",
  "needs_research": true ou false,
  "research_query": "requête de recherche précise en français si needs_research=true, sinon chaîne vide"
}

Déclenche needs_research=true si la capture implique : construction, bricolage, achat de
matériaux, comparaison de prix, prestataire à trouver, ou info pratique locale.
En cas de doute, préfère true — une recherche de trop vaut mieux qu'une planification à l'aveugle.
Exemples : "construire une cabane" → true (modèles, prix matériaux près de Mons)
           "installer une clôture" → true (prix, fournisseurs)
           "appeler le plombier" → false
           "acheter du pain" → false

Si l'utilisateur partage une information personnelle (prénom, famille, lieu, préférence, contrainte),
écris-la dans user_note sous forme d'une phrase courte. Sinon laisse user_note vide.
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
        user_note = data.get("user_note", "")
        needs_research = bool(data.get("needs_research", False))
        research_query = data.get("research_query", "")
    except Exception:
        action, capture_content, completed_title, reply, user_note = "respond", "", "", response.content, ""
        needs_research, research_query = False, ""

    if user_note:
        try:
            append_to_user_profile(user_note)
            logger.info("[Manager] user_note sauvegardé : %s", user_note)
        except Exception as e:
            logger.warning("[Manager] échec sauvegarde user_note : %s", e)

    logger.info("[Manager] action=%s needs_research=%s query=%s", action, needs_research, research_query or "—")

    if action == "capture" and capture_content:
        return Command(
            goto="collector",
            update={
                "messages": [AIMessage(content=reply)],
                "pending_capture": capture_content,
                "needs_research": needs_research,
                "research_query": research_query if needs_research else None,
                "research_result": None,
            },
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
    from tools.tasks_google import complete_task_by_title as gtasks_complete
    completed_title = state.get("completed_title") or ""
    task_title = ""
    project_id = None
    project_title = None
    replan = False

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
                project_title = project["title"]
                replan = True

    gtasks_complete(task_title)

    if replan and project_title:
        logger.info("[Complete] projet '%s' sans next action — relance Organize+Plan", project_title)
        clarified = {
            "type": "project",
            "title": project_title,
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
  "needs_user_input": true ou false,
  "user_question": "question précise à poser à l'utilisateur si needs_user_input=true, sinon chaîne vide",
  "continue_debate": true ou false,
  "type": "project" ou "action" ou "someday" ou "delete" ou "reference",
  "title": "titre clair du projet ou de l'action (pas un verbe GTD ici, juste le sujet)",
  "description": "une phrase de contexte utile pour planifier (vide si type=delete)",
  "explanation": "phrase courte à envoyer à l'utilisateur",
  "research_query_refined": "requête de recherche web affinée avec tout ce qu'on a appris pendant le débat, ou chaîne vide si pas de recherche utile"
}

Règles :
- "project" = nécessite plus d'une étape pour être fait
- "action" = faisable en une seule étape (< 2h)
- "someday" = bonne idée mais pas maintenant
- "delete" = pas actionnable, inutile
- "reference" = info à garder sans action associée
- Si needs_user_input=true : continue_debate doit être true, pose UNE seule question (la plus bloquante)
- Ne demande une info que si elle est vraiment indispensable pour décider du type ou du titre
- research_query_refined : si le débat a révélé des informations (matériaux précis, contraintes, lieu), affine la requête. Si le besoin de recherche est tombé (l'utilisateur a déjà les infos), laisse vide
"""


def clarify_node(state: State) -> Command:
    item = state.get("pending_capture") or ""
    extra = state.get("extra_context") or ""
    if extra:
        item = f"{item}\n\n{extra}"

    # Restaure le débat depuis le state (survit aux interrupts via clarify_ask)
    debate_log: list[str] = list(state.get("debate_log") or [])
    completed = sum(1 for l in debate_log if l.startswith("── round "))
    start_round = completed + 1

    user_ctx = _load_user_context()
    logger.info("── DÉBUT/REPRISE CLARIFY ── item : %s (round %d/3)", item, start_round)

    final: dict | None = None

    for round_num in range(start_round, 4):
        round_lines: list[str] = []
        logger.info("┌─ Round %d", round_num)

        # 3 agents de position
        for path, label in [
            ("clarify/minimaliste", "Minimaliste"),
            ("clarify/exhaustif", "Exhaustif"),
            ("clarify/realiste", "Réaliste"),
        ]:
            soul = _load_soul(path) + f"\n{user_ctx}\n" + _POSITION_JSON
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
        da_ctx = f"Item : {item}\n\n{user_ctx}\n\nPositions round {round_num} :\n" + "\n".join(round_lines)
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
        synth_ctx = f"Item original : {item}\n\n{user_ctx}\n\nDébat complet :\n" + "\n".join(debate_log)
        synth_resp = _invoke_with_retry(
            _get_llm(0.2),
            [SystemMessage(content=_load_soul("shared/synthesizer") + _SYNTHESIZER_JSON),
             HumanMessage(content=synth_ctx)],
        )
        try:
            d = _parse_json(synth_resp.content)
            needs_user_input = bool(d.get("needs_user_input", False))
            user_question = d.get("user_question", "")
            research_query_refined = d.get("research_query_refined", "")
            final = {
                "continue_debate":        d.get("continue_debate", False),
                "type":                   d.get("type", "action"),
                "title":                  d.get("title", item),
                "description":            d.get("description", ""),
                "explanation":            d.get("explanation", ""),
                "research_query_refined": research_query_refined,
            }
        except Exception:
            needs_user_input, user_question, research_query_refined = False, "", ""
            final = {"continue_debate": False, "type": "action",
                     "title": item, "description": "", "explanation": "Capturé tel quel.",
                     "research_query_refined": ""}

        logger.info("└─ [Synthesizer] type=%s continue=%s user_input=%s — %s",
                    final["type"], final["continue_debate"], needs_user_input, final["explanation"])

        # Pause mid-débat si le Synthesizer a besoin d'une info utilisateur (pas au round 3)
        if needs_user_input and user_question and round_num < 3:
            logger.info("[Clarify] pause — question pour l'utilisateur : %s", user_question)
            return Command(
                goto="clarify_ask",
                update={
                    "debate_log": debate_log,
                    "pending_user_question": user_question,
                },
            )

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
            update={"messages": [AIMessage(content=explanation)], "clarified": None, "debate_log": None},
        )

    # Sinon → Researcher (si demandé) ou directement Organize+Plan
    needs_research = state.get("needs_research") or False
    # Mettre à jour la query de recherche avec ce qu'on a appris pendant le débat
    refined_query = (final or {}).get("research_query_refined", "")
    if refined_query:
        logger.info("[Clarify] query recherche affinée → %s", refined_query)
    # Si le Synthesizer a vidé la query, annuler la recherche
    if needs_research and not refined_query and final:
        refined_query = state.get("research_query") or ""
    needs_research = needs_research and bool(refined_query)
    goto = "researcher" if needs_research else "organize_plan"
    return Command(
        goto=goto,
        update={
            "messages": [AIMessage(content="…")],
            "clarified": clarified,
            "debate_log": None,
            "research_query": refined_query or state.get("research_query"),
        },
    )


def clarify_ask_node(state: State) -> Command:
    """Pause mid-débat : pose la question du Synthesizer à l'utilisateur via interrupt()."""
    question = state.get("pending_user_question") or ""
    logger.info("[Clarify Ask] interrupt — %s", question)
    answer = interrupt(question)
    logger.info("[Clarify Ask] réponse reçue — %s", answer)
    debate_log = list(state.get("debate_log") or [])
    debate_log.append(f"[Question posée à l'utilisateur] {question}")
    debate_log.append(f"[Réponse de l'utilisateur] {answer}")
    return Command(
        goto="clarify",
        update={"debate_log": debate_log, "pending_user_question": None},
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
        "Identifie les informations manquantes dans USER.md qui sont indispensables "
        "pour comprendre la nature et le périmètre de cet item (projet ou action simple ? "
        "quelles contraintes physiques ou logistiques ?). "
        "Si USER.md contient déjà tout ce qu'il faut, needs_info=false.\n\n"
        "INTERDIT de demander : niveau d'énergie du jour, disponibilités agenda, "
        "préférences de sessions de travail — ces aspects sont gérés par Organize+Plan.\n\n"
        "Si needs_info=true, pose au maximum 2 questions, uniquement sur ce qui aide "
        "à comprendre l'item lui-même (ressources disponibles, contraintes physiques, objectif concret)."
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


# ── Researcher ────────────────────────────────────────────────────────────────

def researcher_node(state: State) -> Command:
    query = state.get("research_query") or ""
    if not query:
        return Command(goto="organize_plan", update={"research_result": None})

    soul = _load_soul("researcher")
    llm = ChatOpenAI(
        model="perplexity/sonar",
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.3,
    )
    resp = _invoke_with_retry(
        llm,
        [SystemMessage(content=soul), HumanMessage(content=query)],
    )
    logger.info("[Researcher] résultat : %s…", resp.content[:150])
    return Command(goto="research_review", update={"research_result": resp.content})


# ── Research Review ───────────────────────────────────────────────────────────

def research_review_node(state: State) -> Command:
    """Présente les résultats de recherche à l'utilisateur et attend sa validation."""
    research = state.get("research_result") or ""
    message = f"Voici ce que j'ai trouvé :\n\n{research}\n\n---\nEst-ce que ça correspond à ce que tu cherches ? Tu peux valider, corriger ou ajouter des précisions."
    logger.info("[Research Review] interrupt — présentation des résultats")
    feedback = interrupt(message)
    logger.info("[Research Review] feedback reçu — %s", feedback)
    enriched = f"{research}\n\nFeedback utilisateur : {feedback}"
    return Command(goto="organize_plan", update={"research_result": enriched})


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
      "title": "Verbe + action concrète",
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
- IMPORTANT : si l'heure actuelle est après 18h, n'assigne AUCUNE tâche à day_offset=0 (trop tard dans la journée) — commence à day_offset=1
- Utilise les magasins/ressources locaux mentionnés dans le profil utilisateur, pas des chaînes génériques
"""


def organize_plan_node(state: State) -> Command:
    clarified = state.get("clarified") or {}
    title = clarified.get("title", "")
    description = clarified.get("description", "")
    item_type = clarified.get("type", "action")
    row_id = clarified.get("row_id")
    extra = state.get("extra_context") or ""

    from datetime import datetime
    now = datetime.now()
    research = state.get("research_result") or ""
    context = (
        f"Titre : {title}\nType : {item_type}\nDescription : {description}\n"
        f"Contexte utilisateur : {extra}\n"
        f"Date et heure actuelles : {now.strftime('%Y-%m-%d %H:%M')} (heure de Bruxelles)"
    )
    if research:
        context += f"\n\nRésultats de recherche :\n{research}"

    # Injecter le planning existant pour éviter les conflits
    from tools.calendar import list_events
    cal_events = list_events(days_ahead=14)
    with get_conn() as conn:
        upcoming = conn.execute(
            """SELECT title, scheduled_date, context FROM tasks
               WHERE status = 'next_action'
               ORDER BY scheduled_date IS NULL, scheduled_date LIMIT 10""",
        ).fetchall()
    planning_ctx = ""
    if upcoming:
        lines = [f"- {r['title']}" + (f" (prévu : {r['scheduled_date']})" if r["scheduled_date"] else "") for r in upcoming]
        planning_ctx += "## Tâches déjà planifiées\n" + "\n".join(lines)
    if cal_events:
        lines = [f"- {e['date']} : {e['title']}" for e in cal_events]
        planning_ctx += "\n\n## Événements agenda (14 prochains jours)\n" + "\n".join(lines)
    if planning_ctx:
        context += f"\n\n{planning_ctx}"

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

    # Écriture des tâches en base + Google Tasks
    from datetime import timedelta
    from tools.tasks_google import create_task, get_or_create_task_list
    today = date.today()
    list_name = title if item_type == "project" else "Tâches ponctuelles"
    task_list_id = get_or_create_task_list(list_name)
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
            create_task(
                title=t["title"],
                task_list_id=task_list_id,
                notes=description,
                due_date=scheduled,
            )

    explanation = final["explanation"] if final else "Planifié."
    logger.info("── FIN ORGANIZE+PLAN ── tâches enregistrées + Calendar")
    return Command(
        goto=END,
        update={"messages": [AIMessage(content=explanation)], "clarified": None},
    )


# ── Weekly Reviewer ───────────────────────────────────────────────────────────

async def run_review() -> str:
    """Génère la weekly review GTD — standalone, sans passer par le graphe."""
    from datetime import timedelta
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    today = date.today().isoformat()

    with get_conn() as conn:
        done_tasks = conn.execute(
            "SELECT title FROM tasks WHERE status='done' AND completed_at >= ? ORDER BY completed_at",
            (week_ago,),
        ).fetchall()
        pending_tasks = conn.execute(
            "SELECT title, context, scheduled_date FROM tasks WHERE status='next_action'"
            " ORDER BY scheduled_date IS NULL, scheduled_date",
        ).fetchall()
        someday_tasks = conn.execute(
            "SELECT title FROM tasks WHERE status='someday'",
        ).fetchall()
        active_projects = conn.execute(
            """SELECT p.title, COUNT(t.id) as task_count
               FROM projects p
               LEFT JOIN tasks t ON t.project_id = p.id AND t.status = 'next_action'
               GROUP BY p.id""",
        ).fetchall()
        inbox_items = conn.execute(
            "SELECT content FROM inbox WHERE processed=FALSE ORDER BY captured_at",
        ).fetchall()

    parts: list[str] = []
    done_text = "\n".join(f"- {r['title']}" for r in done_tasks) or "Aucune."
    parts.append(f"## Tâches terminées cette semaine\n{done_text}")

    if pending_tasks:
        parts.append("## Next actions en attente\n" + "\n".join(
            f"- {r['title']}" + (f" (prévu : {r['scheduled_date']})" if r["scheduled_date"] else "")
            for r in pending_tasks
        ))

    if active_projects:
        parts.append("## Projets actifs\n" + "\n".join(
            f"- {r['title']} ({r['task_count']} next action{'s' if r['task_count'] != 1 else ''})"
            for r in active_projects
        ))

    if someday_tasks:
        parts.append("## Someday/Maybe\n" + "\n".join(f"- {r['title']}" for r in someday_tasks))

    if inbox_items:
        parts.append("## Inbox non traitée\n" + "\n".join(f"- {r['content']}" for r in inbox_items))

    soul = _load_soul("reviewer").replace("{USER_NAME}", "François")
    prompt = f"{soul}\n\nDate d'aujourd'hui : {today}\n\n" + "\n\n".join(parts) + "\n\nGénère la revue de la semaine."

    resp = await _get_llm(0.3).ainvoke([SystemMessage(content=prompt)])
    logger.info("[Reviewer] revue générée")
    return resp.content


# ── Graph ──────────────────────────────────────────────────────────────────────

graph = (
    StateGraph(State)
    .add_node("manager", manager_node)
    .add_node("collector", collector_node)
    .add_node("context_agent", context_agent_node)
    .add_node("clarify", clarify_node)
    .add_node("clarify_ask", clarify_ask_node)
    .add_node("organize_plan", organize_plan_node)
    .add_node("researcher", researcher_node)
    .add_node("research_review", research_review_node)
    .add_node("complete", complete_node)
    .add_edge(START, "manager")
    .add_edge("collector", "context_agent")
    .compile(checkpointer=MemorySaver())
)
