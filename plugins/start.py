"""
plugins/start.py  –  /start command handler
"""

import logging

from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)
from pyrogram.errors import UserNotParticipant

from config import START_MSG, FORCE_SUB_MSG, AUTH_CHANNEL, AUTH_USERS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Force-subscribe helper
# ─────────────────────────────────────────────────────────────────────────────

async def is_subscribed(bot: Client, user_id: int) -> bool:
    """Return True if user is a member of AUTH_CHANNEL (or if no channel set)."""
    if not AUTH_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(AUTH_CHANNEL, user_id)
        return member.status.name not in ("BANNED", "LEFT", "RESTRICTED")
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.exception("is_subscribed error: %s", e)
        return False  # fail-closed


# ─────────────────────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private)
async def start(bot: Client, message: Message):
    user = message.from_user

    # Force-subscribe check
    if not await is_subscribed(bot, user.id):
        channel = await bot.get_chat(AUTH_CHANNEL)
        invite = (
            f"https://t.me/{channel.username}"
            if channel.username
            else await bot.export_chat_invite_link(AUTH_CHANNEL)
        )
        buttons = [[InlineKeyboardButton("✅ Join Channel", url=invite)]]
        await message.reply(
            FORCE_SUB_MSG,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # Deep-link: /start subscribe
    if len(message.command) > 1 and message.command[1] == "subscribe":
        await message.reply(FORCE_SUB_MSG)
        return

    buttons = [
        [
            InlineKeyboardButton("🔍 Search Here", switch_inline_query_current_chat=""),
            InlineKeyboardButton("🌐 Go Inline", switch_inline_query=""),
        ],
        [InlineKeyboardButton("❓ How to Use", callback_data="help")],
    ]
    text = START_MSG.format(
        mention=user.mention,
        username=bot.username.lstrip("@"),
        first_name=user.first_name,
    )
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────────────────────────────────────────────
#  Help callback
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^help$"))
async def help_cb(bot: Client, query: CallbackQuery):
    text = (
        "📖 <b>How to Use</b>\n\n"
        "1️⃣ Just <b>type any movie/file name</b> in this chat.\n"
        "2️⃣ The bot shows results as buttons – tap to get the file!\n"
        "3️⃣ Use <b>◀ Prev</b> / <b>Next ▶</b> to browse pages.\n\n"
        "🔎 <b>Filter by type:</b> <code>movie name | video</code>\n"
        "🌐 <b>Inline mode:</b> type <code>@{username} name</code> anywhere."
    ).format(username=bot.username.lstrip("@"))
    back = [[InlineKeyboardButton("⬅️ Back", callback_data="back_start")]]
    await query.message.edit(text, reply_markup=InlineKeyboardMarkup(back))


@Client.on_callback_query(filters.regex(r"^back_start$"))
async def back_start_cb(bot: Client, query: CallbackQuery):
    user = query.from_user
    buttons = [
        [
            InlineKeyboardButton("🔍 Search Here", switch_inline_query_current_chat=""),
            InlineKeyboardButton("🌐 Go Inline", switch_inline_query=""),
        ],
        [InlineKeyboardButton("❓ How to Use", callback_data="help")],
    ]
    text = START_MSG.format(
        mention=user.mention,
        username=bot.username.lstrip("@"),
        first_name=user.first_name,
    )
    await query.message.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
