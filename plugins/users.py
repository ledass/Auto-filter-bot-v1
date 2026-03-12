"""
plugins/users.py  –  Auto-save every user who interacts with the bot

Registers a high-priority handler (group=-1) that fires on every private
message or callback_query. The handler just upserts the user to MongoDB
and then continues — it never blocks or stops the update.
"""

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

from database.db import Users

logger = logging.getLogger(__name__)


# ── Save on any private message ───────────────────────────────────────────────

@Client.on_message(filters.private & filters.incoming, group=-1)
async def save_user_on_message(bot: Client, message: Message):
    user = message.from_user
    if not user or user.is_bot:
        return
    try:
        is_new = await Users.add(user)
        if is_new:
            logger.info("New user saved: %s (%s)", user.id, user.first_name)
    except Exception as e:
        logger.warning("Failed to save user %s: %s", getattr(user, "id", "?"), e)


# ── Save on callback queries (covers group users who tap inline buttons) ──────

@Client.on_callback_query(group=-1)
async def save_user_on_callback(bot: Client, query: CallbackQuery):
    user = query.from_user
    if not user or user.is_bot:
        return
    try:
        await Users.add(user)
    except Exception as e:
        logger.warning("Failed to save user (cb) %s: %s", getattr(user, "id", "?"), e)
