import os
import logging
from datetime import time as dtime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langgraph.types import Command

from core.graph import graph

logger = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))
_TZ_BRUSSELS = ZoneInfo("Europe/Brussels")

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
        _interrupted_threads.add(thread_id)
        for task in state.tasks:
            for intr in getattr(task, "interrupts", []):
                await update.message.reply_text(intr.value)
                return
    else:
        reply = result["messages"][-1].content
        await update.message.reply_text(reply)


async def review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    from core.graph import run_review
    await update.message.reply_text("⏳ Génération de la revue hebdomadaire…")
    text = await run_review()
    await update.message.reply_text(text)


async def _scheduled_weekly_review(context: ContextTypes.DEFAULT_TYPE) -> None:
    from core.graph import run_review
    text = await run_review()
    await context.bot.send_message(chat_id=ALLOWED_USER_ID, text=text)


def build_app() -> Application:
    app = (
        Application.builder()
        .token(os.getenv("TELEGRAM_TOKEN"))
        .build()
    )
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("review", review_command))

    # Weekly review every Friday at 18:00 Brussels time
    app.job_queue.run_daily(
        _scheduled_weekly_review,
        time=dtime(hour=18, minute=0, tzinfo=_TZ_BRUSSELS),
        days=(4,),  # 0=Monday … 4=Friday
    )
    return app
