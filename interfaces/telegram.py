import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from langgraph.types import Command

from core.graph import graph

logger = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))

# Threads actuellement en attente d'une réponse HITL
_interrupted_threads: set[str] = set()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        logger.warning("Message rejeté — user_id non autorisé : %s", update.effective_user.id)
        return

    thread_id = str(update.effective_user.id)
    config = {"configurable": {"thread_id": thread_id}}
    user_text = update.message.text or ""

    # Si le graphe est en pause (HITL), on reprend avec la réponse
    if thread_id in _interrupted_threads:
        _interrupted_threads.discard(thread_id)
        input_data = Command(resume=user_text)
    else:
        input_data = {"messages": [("user", user_text)]}

    result = await graph.ainvoke(input_data, config=config)

    # Vérifier si le graphe s'est mis en pause (interrupt)
    state = await graph.aget_state(config)
    if state.next:
        # Le graphe est en pause — extraire la question posée par le Context Agent
        _interrupted_threads.add(thread_id)
        for task in state.tasks:
            for intr in getattr(task, "interrupts", []):
                await update.message.reply_text(intr.value)
                return
    else:
        reply = result["messages"][-1].content
        await update.message.reply_text(reply)


def build_app() -> Application:
    app = (
        Application.builder()
        .token(os.getenv("TELEGRAM_TOKEN"))
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
