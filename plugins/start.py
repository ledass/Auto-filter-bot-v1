"""
plugins/start.py  –  /start command handler
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

from config import START_MSG, FORCE_SUB_MSG, AUTH_CHANNEL, AUTH_USERS

logger = logging.getLogger(__name__)

# Cache invite link so we don't call the API on every failed sub check
_invite_cache: str = ""


# ─────────────────────────────────────────────────────────────────────────────
#  Force-subscribe helper
# ─────────────────────────────────────────────────────────────────────────────

async def is_subscribed(bot: Client, user_id: int) -> bool:
    """
    Return True if the user is a member of AUTH_CHANNEL.
    Always returns True when AUTH_CHANNEL is not set.
    """
    if not AUTH_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(AUTH_CHANNEL, user_id)
        return member.status not in (
            ChatMemberStatus.BANNED,
            ChatMemberStatus.LEFT,
        )
    except UserNotParticipant:
        return False
    except (PeerIdInvalid, ChannelInvalid, ChannelPrivate) as e:
        # Channel peer not cached yet – log a clear message and fail open
        # so users aren't blocked by a misconfigured AUTH_CHANNEL
        logger.error(
            "AUTH_CHANNEL peer could not be resolved (%s). "
            "Make sure the bot is a member/admin of the channel and "
            "that the ID format is correct (e.g. -100XXXXXXXXXX). "
            "Temporarily allowing user %s.",
            e, user_id
        )
        return True   # fail-open: don't lock out everyone on bad config
    except Exception as e:
        logger.exception("is_subscribed unexpected error: %s", e)
        return True   # fail-open on unknown errors


async def _get_invite(bot: Client) -> str:
    """Return a join link for AUTH_CHANNEL (cached after first call)."""
    global _invite_cache
    if _invite_cache:
        return _invite_cache
    try:
        chat = await bot.get_chat(AUTH_CHANNEL)
        if chat.username:
            _invite_cache = f"https://t.me/{chat.username}"
        else:
            _invite_cache = await bot.export_chat_invite_link(AUTH_CHANNEL)
    except ChatAdminRequired:
        _invite_cache = "https://t.me"   # fallback
    except Exception as e:
        logger.warning("Could not get invite link: %s", e)
        _invite_cache = "https://t.me"
    return _invite_cache


# ─────────────────────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private)
async def start(bot: Client, message: Message):
    user = message.from_user

    # Deep-link: /start subscribe  →  show join prompt regardless
    if len(message.command) > 1 and message.command[1] == "subscribe":
        invite = await _get_invite(bot)
        buttons = [[InlineKeyboardButton("✅ Join Channel", url=invite)]]
        return await message.reply(
            FORCE_SUB_MSG,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    # Force-subscribe check
    if not await is_subscribed(bot, user.id):
        invite = await _get_invite(bot)
        buttons = [[InlineKeyboardButton("✅ Join Channel", url=invite)]]
        return await message.reply(
            FORCE_SUB_MSG,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

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
