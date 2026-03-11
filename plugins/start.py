"""
plugins/start.py  –  /start command + deep-link file delivery
"""

import logging

from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    CallbackQuery,
)
from pyrogram.errors import (
    UserNotParticipant,
    ChatAdminRequired,
    PeerIdInvalid,
    ChannelInvalid,
    ChannelPrivate,
)

from config import START_MSG, FORCE_SUB_MSG, AUTH_CHANNEL

logger = logging.getLogger(__name__)

_invite_cache: str = ""


# ─────────────────────────────────────────────────────────────────────────────
#  Shared helpers (imported by search.py, admin.py, inline.py)
# ─────────────────────────────────────────────────────────────────────────────

async def is_subscribed(bot: Client, user_id: int) -> bool:
    if not AUTH_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(AUTH_CHANNEL, user_id)
        return member.status not in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT)
    except UserNotParticipant:
        return False
    except (PeerIdInvalid, ChannelInvalid, ChannelPrivate) as e:
        logger.error(
            "AUTH_CHANNEL peer unresolved (%s). Allowing user %s.", e, user_id
        )
        return True
    except Exception as e:
        logger.exception("is_subscribed error: %s", e)
        return True


async def _get_invite(bot: Client) -> str:
    global _invite_cache
    if _invite_cache:
        return _invite_cache
    try:
        chat = await bot.get_chat(AUTH_CHANNEL)
        _invite_cache = (
            f"https://t.me/{chat.username}" if chat.username
            else await bot.export_chat_invite_link(AUTH_CHANNEL)
        )
    except ChatAdminRequired:
        _invite_cache = "https://t.me"
    except Exception as e:
        logger.warning("Could not get invite link: %s", e)
        _invite_cache = "https://t.me"
    return _invite_cache


# ─────────────────────────────────────────────────────────────────────────────
#  /start  –  plain start  OR  deep-link file delivery
#
#  Deep-link format:  /start <file_id>
#  Sent by group search buttons:  t.me/bot?start=<file_id>
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private)
async def start(bot: Client, message: Message):
    user = message.from_user
    args = message.command[1] if len(message.command) > 1 else None

    # ── Deep-link: /start subscribe ──────────────────────────────────────────
    if args == "subscribe":
        invite  = await _get_invite(bot)
        buttons = [[InlineKeyboardButton("✅ Join Channel", url=invite)]]
        return await message.reply(FORCE_SUB_MSG, reply_markup=InlineKeyboardMarkup(buttons))

    # ── Deep-link: /start <file_id>  →  send the file ────────────────────────
    if args and args not in ("start", "help"):
        # Force-subscribe check before sending file
        if not await is_subscribed(bot, user.id):
            invite  = await _get_invite(bot)
            buttons = [[InlineKeyboardButton("✅ Join Channel", url=invite)]]
            return await message.reply(
                FORCE_SUB_MSG + "\n\n<i>After joining, tap the file button again.</i>",
                reply_markup=InlineKeyboardMarkup(buttons),
            )

        # Import here to avoid circular import
        from plugins.search import send_file_to_user
        await message.reply("📤 <b>Fetching your file…</b>")
        await send_file_to_user(bot, user.id, args)
        return

    # ── Normal /start ─────────────────────────────────────────────────────────
    if not await is_subscribed(bot, user.id):
        invite  = await _get_invite(bot)
        buttons = [[InlineKeyboardButton("✅ Join Channel", url=invite)]]
        return await message.reply(FORCE_SUB_MSG, reply_markup=InlineKeyboardMarkup(buttons))

    buttons = [
        [
            InlineKeyboardButton("🔍 Search Here", switch_inline_query_current_chat=""),
            InlineKeyboardButton("🌐 Go Inline",   switch_inline_query=""),
        ],
        [InlineKeyboardButton("❓ How to Use", callback_data="help")],
    ]
    text = START_MSG.format(
        mention    = user.mention,
        username   = bot.username.lstrip("@"),
        first_name = user.first_name,
    )
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────────────────────────────────────────────
#  Help / Back callbacks
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^help$"))
async def help_cb(bot: Client, query: CallbackQuery):
    text = (
        "📖 <b>How to Use</b>\n\n"
        "1️⃣ <b>In this chat:</b> just type a movie/file name.\n"
        "2️⃣ <b>In any group:</b> type the name → tap a result → I'll send it here in PM!\n"
        "3️⃣ Use <b>◀ PREV</b> / <b>NEXT ▶</b> to browse pages.\n\n"
        "🔎 <b>Filter by type:</b> <code>movie name | video</code>\n"
        "🌐 <b>Inline mode:</b> <code>@{username} name</code> in any chat.\n\n"
        "⚠️ <b>Files auto-delete after a few minutes</b> — forward to "
        "<a href='https://t.me/me'>Saved Messages</a> to keep them!"
    ).format(username=bot.username.lstrip("@"))
    await query.message.edit(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_start")]]),
    )


@Client.on_callback_query(filters.regex(r"^back_start$"))
async def back_start_cb(bot: Client, query: CallbackQuery):
    user = query.from_user
    buttons = [
        [
            InlineKeyboardButton("🔍 Search Here", switch_inline_query_current_chat=""),
            InlineKeyboardButton("🌐 Go Inline",   switch_inline_query=""),
        ],
        [InlineKeyboardButton("❓ How to Use", callback_data="help")],
    ]
    text = START_MSG.format(
        mention    = user.mention,
        username   = bot.username.lstrip("@"),
        first_name = user.first_name,
    )
    await query.message.edit(text, reply_markup=InlineKeyboardMarkup(buttons))
