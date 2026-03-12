"""
plugins/broadcast.py  –  Admin broadcast to all saved users

Usage:
  /broadcast  (reply to any message — text, photo, video, document, etc.)
  /broadcast Hello everyone!   (text-only broadcast)

Features:
  • Forwards or copies the replied-to message to every user in DB
  • Live progress updates every 20 users
  • Tracks: sent / failed / blocked (auto-removes blocked users)
  • Can be cancelled with a button
  • Respects FloodWait — sleeps and retries
"""

import asyncio
import logging
import time

from pyrogram import Client, filters
from pyrogram.errors import (
    FloodWait,
    UserIsBlocked,
    InputUserDeactivated,
    PeerIdInvalid,
    UserNotParticipant,
)
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import ADMINS
from database.db import Users

logger = logging.getLogger(__name__)

# ── Runtime state ─────────────────────────────────────────────────────────────
class _BC:
    running: bool = False
    cancel:  bool = False

bc = _BC()


# ─────────────────────────────────────────────────────────────────────────────
#  /broadcast
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_cmd(bot: Client, message: Message):
    if bc.running:
        return await message.reply(
            "⚠️ A broadcast is already running.\n"
            "Use /cancelbroadcast to stop it first."
        )

    # Determine what to send
    to_copy   = message.reply_to_message   # forward this message if present
    text_only = None

    if not to_copy:
        # Text after command: /broadcast Hello world
        if len(message.command) < 2:
            return await message.reply(
                "📢 <b>How to broadcast:</b>\n\n"
                "1. Reply to any message with /broadcast\n"
                "2. Or: <code>/broadcast Your message here</code>"
            )
        text_only = message.text.split(None, 1)[1]

    total_users = await Users.count()
    if total_users == 0:
        return await message.reply("❌ No users in database yet.")

    # Confirm before sending
    preview = (
        f"<b>📢 Broadcast Preview</b>\n\n"
        f"👥 <b>Recipients:</b> <code>{total_users}</code> users\n"
        f"📝 <b>Content:</b> {'Replied message' if to_copy else repr(text_only[:60])}\n\n"
        "Tap <b>Send</b> to start."
    )
    buttons = [[
        InlineKeyboardButton("✅ Send", callback_data="bc_confirm"),
        InlineKeyboardButton("❌ Cancel", callback_data="bc_abort"),
    ]]

    # Stash the source for the callback to use
    bot._bc_source_chat    = message.chat.id
    bot._bc_source_msg_id  = to_copy.id if to_copy else None
    bot._bc_text_only      = text_only
    bot._bc_from_admin     = message.from_user.id

    await message.reply(preview, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────────────────────────────────────────────
#  /cancelbroadcast
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("cancelbroadcast") & filters.user(ADMINS))
async def cancel_broadcast_cmd(bot: Client, message: Message):
    if not bc.running:
        return await message.reply("No broadcast is currently running.")
    bc.cancel = True
    await message.reply("⛔ Cancelling broadcast after current user…")


# ─────────────────────────────────────────────────────────────────────────────
#  Confirm / Abort callbacks
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^bc_(confirm|abort)$") & filters.user(ADMINS))
async def bc_confirm_cb(bot: Client, query: CallbackQuery):
    if query.data == "bc_abort":
        await query.message.edit("❌ Broadcast cancelled.")
        return

    if bc.running:
        await query.answer("Already running!", show_alert=True)
        return

    await query.message.edit(
        "📢 <b>Broadcast started…</b>\n\n⏳ Preparing…",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⛔ Cancel", callback_data="bc_cancel_btn")]]
        )
    )

    # Run broadcast in background so callback returns immediately
    asyncio.create_task(
        _do_broadcast(
            bot,
            query.message,
            source_chat   = getattr(bot, "_bc_source_chat", None),
            source_msg_id = getattr(bot, "_bc_source_msg_id", None),
            text_only     = getattr(bot, "_bc_text_only", None),
        )
    )


@Client.on_callback_query(filters.regex(r"^bc_cancel_btn$") & filters.user(ADMINS))
async def bc_cancel_btn_cb(bot: Client, query: CallbackQuery):
    bc.cancel = True
    await query.answer("⛔ Cancelling…", show_alert=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Core broadcast loop
# ─────────────────────────────────────────────────────────────────────────────

async def _do_broadcast(
    bot: Client,
    status_msg,            # message to edit with live progress
    source_chat: int,
    source_msg_id: int,    # None if text_only
    text_only: str,        # None if copying a message
):
    bc.running = True
    bc.cancel  = False

    sent     = 0
    failed   = 0
    blocked  = 0
    last_edit = 0.0

    user_ids = await Users.get_all_ids()
    total    = len(user_ids)

    try:
        for i, uid in enumerate(user_ids, 1):
            if bc.cancel:
                break

            # ── Send ──────────────────────────────────────────────────────────
            for attempt in range(3):
                try:
                    if text_only:
                        await bot.send_message(uid, text_only)
                    else:
                        await bot.copy_message(
                            chat_id      = uid,
                            from_chat_id = source_chat,
                            message_id   = source_msg_id,
                        )
                    sent += 1
                    break   # success

                except FloodWait as e:
                    wait = e.value + 2
                    logger.warning("FloodWait %ds during broadcast (user %s)", wait, uid)
                    await asyncio.sleep(wait)
                    # retry loop continues

                except (UserIsBlocked, InputUserDeactivated):
                    blocked += 1
                    await Users.remove(uid)   # clean up DB
                    break

                except (PeerIdInvalid, UserNotParticipant):
                    failed += 1
                    break

                except Exception as e:
                    logger.warning("Broadcast error for %s: %s", uid, e)
                    failed += 1
                    break

            # ── Progress update every 20 users (max 1 edit per 3s) ────────────
            now = time.time()
            if (i % 20 == 0 or i == total) and now - last_edit >= 3:
                try:
                    await status_msg.edit_text(
                        _progress_text(i, total, sent, failed, blocked, bc.cancel),
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("⛔ Cancel", callback_data="bc_cancel_btn")]]
                        ) if not bc.cancel else None,
                    )
                    last_edit = time.time()
                except FloodWait:
                    pass   # skip this update, don't cascade
                except Exception:
                    pass

            # Small delay to avoid hammering Telegram (30 msg/s safe limit)
            await asyncio.sleep(0.05)

    finally:
        bc.running = False
        bc.cancel  = False

    # Final report
    try:
        await status_msg.edit_text(
            f"{'⛔ Broadcast cancelled!' if bc.cancel else '✅ Broadcast complete!'}\n\n"
            f"👥 Total users: <code>{total}</code>\n"
            f"✅ Sent: <code>{sent}</code>\n"
            f"🚫 Blocked/Deactivated: <code>{blocked}</code> (removed from DB)\n"
            f"❌ Failed: <code>{failed}</code>"
        )
    except Exception:
        pass


def _progress_text(done, total, sent, failed, blocked, cancelled) -> str:
    pct = int(done / total * 100) if total else 0
    bar_len = 10
    filled  = int(bar_len * done / total) if total else 0
    bar     = "█" * filled + "░" * (bar_len - filled)

    status = "⛔ Cancelling…" if cancelled else "📢 Broadcasting…"
    return (
        f"{status}\n\n"
        f"[{bar}] {pct}%\n"
        f"Done: <code>{done}/{total}</code>\n\n"
        f"✅ Sent: <code>{sent}</code>\n"
        f"🚫 Blocked: <code>{blocked}</code>\n"
        f"❌ Failed: <code>{failed}</code>"
    )
