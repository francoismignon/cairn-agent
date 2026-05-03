import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from core.graph import manager

logger = logging.getLogger(__name__)

ALLOWED_USER_ID = int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ALLOWED_USER_ID:
        logger.warning("Message rejeté — user_id non autorisé : %s", update.effective_user.id)
        return

    user_text = update.message.text or ""
    config = {"configurable": {"thread_id": str(update.effective_user.id)}}

    result = await manager.ainvoke(
        {"messages": [("user", user_text)]},
        config=config,
    )
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
