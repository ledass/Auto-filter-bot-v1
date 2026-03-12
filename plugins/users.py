"""
plugins/users.py  –  Auto-save every user + notify LOG_CHANNEL on new /start
"""

import logging
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.errors import FloodWait

from config import LOG_CHANNEL
from database.db import Users

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  /start  →  save user + notify LOG_CHANNEL if new
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private & filters.incoming, group=-1)
async def track_start(bot: Client, message: Message):
    user = message.from_user
    if not user or user.is_bot:
        return
    try:
        is_new = await Users.add(user)
    except Exception as e:
        logger.warning("Failed to save user %s: %s", getattr(user, "id", "?"), e)
        return

    if is_new and LOG_CHANNEL:
        total    = await Users.count()
        username = f"@{user.username}" if user.username else "—"
        name     = f"{user.first_name or ''} {user.last_name or ''}".strip()
        joined   = datetime.now(timezone.utc).strftime("%d %b %Y • %H:%M UTC")

        text = (
            "👤 <b>New User Started Bot!</b>\n\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📛 <b>Name:</b> {name}\n"
            f"🔗 <b>Username:</b> {username}\n"
            f"📅 <b>Joined:</b> {joined}\n\n"
            f"👥 <b>Total Users:</b> <code>{total}</code>"
        )
        try:
            await bot.send_message(LOG_CHANNEL, text)
        except FloodWait as e:
            import asyncio
            await asyncio.sleep(min(e.value, 30))
            try:
                await bot.send_message(LOG_CHANNEL, text)
            except Exception:
                pass
        except Exception as e:
            logger.warning("Could not notify LOG_CHANNEL for new user: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
#  All other private messages  →  silently upsert (update last_seen)
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.private & filters.incoming, group=-1)
async def save_user_on_message(bot: Client, message: Message):
    user = message.from_user
    if not user or user.is_bot:
        return
    try:
        await Users.add(user)
    except Exception as e:
        logger.warning("Failed to save user %s: %s", getattr(user, "id", "?"), e)


# ─────────────────────────────────────────────────────────────────────────────
#  Callback queries  →  silently upsert
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(group=-1)
async def save_user_on_callback(bot: Client, query: CallbackQuery):
    user = query.from_user
    if not user or user.is_bot:
        return
    try:
        await Users.add(user)
    except Exception as e:
        logger.warning("Failed to save user (cb) %s: %s", getattr(user, "id", "?"), e)
