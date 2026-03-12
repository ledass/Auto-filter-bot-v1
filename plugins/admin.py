"""
plugins/admin.py  –  Admin commands + channel indexer (bot-only, no userbot needed)

Indexing flow:
  • Admin sends a t.me link or forwards a message from a channel
  • Bot asks for confirmation → Accept / Reject
  • On accept: bot.get_messages() in batches indexes all media up to that message ID
  • /setskip N  → start indexing from message N
  • Cancel button aborts mid-index
"""

import logging
import asyncio
import re
import os

from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.errors.exceptions.bad_request_400 import (
    ChannelInvalid, ChatAdminRequired,
    UsernameInvalid, UsernameNotModified,
)

from config import ADMINS, CHANNELS, LOG_CHANNEL
from database.db import Media, save_file

logger = logging.getLogger(__name__)
_lock = asyncio.Lock()

# ─────────────────────────────────────────────────────────────────────────────
#  FloodWait-safe wrappers
# ─────────────────────────────────────────────────────────────────────────────

async def safe_edit(msg, text: str, reply_markup=None):
    """Edit a message, handling FloodWait by sleeping then retrying once."""
    for attempt in range(2):
        try:
            kwargs = {"text": text}
            if reply_markup:
                kwargs["reply_markup"] = reply_markup
            return await msg.edit(**kwargs)
        except FloodWait as e:
            if attempt == 0:
                logger.warning("FloodWait %ds on edit – sleeping", e.value)
                await asyncio.sleep(min(e.value, 30))
            else:
                logger.error("FloodWait persists on edit, giving up: %s", e)
        except MessageNotModified:
            pass
        except Exception as e:
            logger.warning("safe_edit error: %s", e)
            break


async def safe_reply(message, text: str, reply_markup=None):
    """Reply to a message, handling FloodWait."""
    for attempt in range(2):
        try:
            return await message.reply(text, reply_markup=reply_markup)
        except FloodWait as e:
            if attempt == 0:
                logger.warning("FloodWait %ds on reply – sleeping", e.value)
                await asyncio.sleep(min(e.value, 30))
            else:
                logger.error("FloodWait persists on reply, giving up: %s", e)
        except Exception as e:
            logger.warning("safe_reply error: %s", e)
            break

logger = logging.getLogger(__name__)
_lock = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────────
#  Shared runtime state (replaces utils.temp)
# ─────────────────────────────────────────────────────────────────────────────

class _State:
    CANCEL:  bool = False
    CURRENT: int  = 0   # skip offset – set via /setskip

state = _State()


# ─────────────────────────────────────────────────────────────────────────────
#  /setskip  –  set message offset before indexing
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("setskip") & filters.user(ADMINS))
async def set_skip(bot: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply(
            f"Usage: <code>/setskip 1000</code>\n\n"
            f"Current skip: <code>{state.CURRENT}</code>"
        )
    try:
        state.CURRENT = int(message.command[1])
        await message.reply(f"✅ Skip set to <code>{state.CURRENT}</code>")
    except ValueError:
        await message.reply("⚠️ Skip number must be an integer.")


# ─────────────────────────────────────────────────────────────────────────────
#  Forwarded message or t.me link  →  ask to index
# ─────────────────────────────────────────────────────────────────────────────

_LINK_RE = re.compile(
    r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$"
)


@Client.on_message(
    (
        filters.forwarded
        | (filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z_0-9]+)/(\d+)$") & filters.text)
    )
    & filters.private
    & filters.incoming
)
async def send_for_index(bot: Client, message: Message):
    # ── Parse chat_id + last_msg_id ──────────────────────────────────────────
    if message.text:
        match = _LINK_RE.match(message.text.strip())
        if not match:
            return await message.reply("❌ Invalid link.")
        chat_id     = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = message.forward_from_message_id
        chat_id     = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    # ── Validate the chat is accessible ─────────────────────────────────────
    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply(
            "⚠️ This is a private channel/group.\n"
            "Make me an <b>admin</b> there first, then try again."
        )
    except (UsernameInvalid, UsernameNotModified):
        return await message.reply("❌ Invalid link or username.")
    except Exception as e:
        logger.exception(e)
        return await message.reply(f"Error: <code>{e}</code>")

    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except Exception:
        return await message.reply(
            "⚠️ Could not fetch that message.\n"
            "Make sure I am an admin in the channel/group."
        )

    if k.empty:
        return await message.reply("⚠️ That message is empty or deleted.")

    # ── Admin: direct confirm ────────────────────────────────────────────────
    if message.from_user.id in ADMINS:
        buttons = [[
            InlineKeyboardButton(
                "✅ Yes, Index",
                callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}"
            ),
            InlineKeyboardButton("❌ No", callback_data="close_data"),
        ]]
        return await message.reply(
            f"🗂 <b>Index this channel/group?</b>\n\n"
            f"Chat: <code>{chat_id}</code>\n"
            f"Up to message ID: <code>{last_msg_id}</code>\n"
            f"Skip first: <code>{state.CURRENT}</code> messages",
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    # ── Non-admin: submit to LOG_CHANNEL for moderator approval ─────────────
    if not LOG_CHANNEL:
        return await message.reply("⚠️ Bot is not configured to accept index requests from non-admins.")

    if isinstance(chat_id, int):
        try:
            link = (await bot.create_chat_invite_link(chat_id)).invite_link
        except ChatAdminRequired:
            return await message.reply(
                "⚠️ I need <b>invite link</b> permission in that chat."
            )
    else:
        link = f"@{chat_id}"

    buttons = [[
        InlineKeyboardButton(
            "✅ Accept",
            callback_data=f"index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}"
        ),
        InlineKeyboardButton(
            "❌ Reject",
            callback_data=f"index#reject#{chat_id}#{message.id}#{message.from_user.id}"
        ),
    ]]
    await bot.send_message(
        LOG_CHANNEL,
        f"#IndexRequest\n\n"
        f"From: {message.from_user.mention} (<code>{message.from_user.id}</code>)\n"
        f"Chat: <code>{chat_id}</code>\n"
        f"Last Msg ID: <code>{last_msg_id}</code>\n"
        f"Link: {link}",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    await message.reply(
        "✅ Submitted! Waiting for a moderator to approve your request."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Callback: index#accept / index#reject / index_cancel
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^index"))
async def index_callback(bot: Client, query: CallbackQuery):

    # Cancel mid-index
    if query.data == "index_cancel":
        state.CANCEL = True
        return await query.answer("⛔ Cancelling…", show_alert=True)

    _, action, chat, last_msg_id, from_user = query.data.split("#")
    from_user_id = int(from_user)

    # Reject
    if action == "reject":
        await query.message.delete()
        await bot.send_message(
            from_user_id,
            f"❌ Your index request for <code>{chat}</code> was declined by a moderator.",
            reply_to_message_id=int(last_msg_id),
        )
        return

    # Already running?
    if _lock.locked():
        return await query.answer("⏳ Another index is already running. Please wait.", show_alert=True)

    await query.answer("⏳ Starting…", show_alert=True)

    # Notify non-admin submitter
    if from_user_id not in ADMINS:
        try:
            await bot.send_message(
                from_user_id,
                f"✅ Your index request for <code>{chat}</code> was accepted and indexing has started!",
                reply_to_message_id=int(last_msg_id),
            )
        except Exception:
            pass

    await query.message.edit(
        "⏳ <b>Indexing started…</b>",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⛔ Cancel", callback_data="index_cancel")]]
        ),
    )

    try:
        chat = int(chat)
    except ValueError:
        pass

    await _index_to_db(int(last_msg_id), chat, query.message, bot)


# ─────────────────────────────────────────────────────────────────────────────
#  Close button
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^close_data$"))
async def close_cb(bot: Client, query: CallbackQuery):
    await query.message.delete()


# ─────────────────────────────────────────────────────────────────────────────
#  Core indexing loop  (bot.iter_messages – no userbot needed)
# ─────────────────────────────────────────────────────────────────────────────

async def _index_to_db(last_msg_id: int, chat, msg, bot: Client):
    total_files = 0
    duplicate   = 0
    errors      = 0
    deleted     = 0
    no_media    = 0
    unsupported = 0
    current     = state.CURRENT   # messages processed counter

    # Pyrogram v2 has no iter_messages – fetch in batches of 200 by ID.
    # We iterate from last_msg_id down to state.CURRENT (skip offset).
    BATCH = 200
    # Track last edit time to avoid editing too frequently (min 5s between edits)
    import time
    last_edit_ts = 0.0

    async with _lock:
        try:
            state.CANCEL = False

            # Build ID ranges: last_msg_id → state.CURRENT+1 (inclusive)
            start = last_msg_id
            stop  = max(0, state.CURRENT)

            while start > stop:
                if state.CANCEL:
                    await safe_edit(
                        msg,
                        "⛔ <b>Indexing cancelled!</b>\n\n"
                        + _stats(total_files, duplicate, deleted, no_media, unsupported, errors)
                    )
                    return

                # Build a batch of IDs (high → low)
                batch_end = max(stop, start - BATCH)
                ids       = list(range(start, batch_end, -1))
                start     = batch_end

                # Fetch batch
                try:
                    messages = await bot.get_messages(chat, ids)
                except FloodWait as e:
                    wait = e.value + 2
                    logger.warning("FloodWait %ds on get_messages – sleeping", wait)
                    await asyncio.sleep(wait)
                    try:
                        messages = await bot.get_messages(chat, ids)
                    except Exception as e2:
                        logger.error("Retry failed: %s", e2)
                        errors += len(ids)
                        continue
                except Exception as e:
                    logger.exception("get_messages error: %s", e)
                    errors += len(ids)
                    continue

                for message in messages:
                    if state.CANCEL:
                        await safe_edit(
                            msg,
                            "⛔ <b>Indexing cancelled!</b>\n\n"
                            + _stats(total_files, duplicate, deleted, no_media, unsupported, errors)
                        )
                        return

                    current += 1

                    if not message or message.empty:
                        deleted += 1
                        continue
                    if not message.media:
                        no_media += 1
                        continue
                    if message.media not in (
                        enums.MessageMediaType.VIDEO,
                        enums.MessageMediaType.AUDIO,
                        enums.MessageMediaType.DOCUMENT,
                    ):
                        unsupported += 1
                        continue

                    media = getattr(message, message.media.value, None)
                    if not media:
                        unsupported += 1
                        continue

                    media.file_type = message.media.value
                    media.caption   = message.caption

                    saved = await save_file(media)
                    if saved:
                        total_files += 1
                    else:
                        duplicate += 1

                # Update progress once per batch (≤1 edit per ~200 messages)
                # and only if at least 5 seconds have passed since last edit
                now = time.time()
                if now - last_edit_ts >= 5:
                    await safe_edit(
                        msg,
                        f"⏳ <b>Indexing…</b>\n\n"
                        f"Fetched: <code>{current}</code>\n"
                        + _stats(total_files, duplicate, deleted, no_media, unsupported, errors),
                        reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton("⛔ Cancel", callback_data="index_cancel")]]
                        ),
                    )
                    last_edit_ts = time.time()

        except Exception as e:
            logger.exception("Index error: %s", e)
            await safe_edit(msg, f"❌ Error: <code>{e}</code>")
            return

        await safe_edit(
            msg,
            "✅ <b>Indexing complete!</b>\n\n"
            + _stats(total_files, duplicate, deleted, no_media, unsupported, errors)
        )


def _stats(files, dup, deleted, no_media, unsupported, errors) -> str:
    return (
        f"💾 Saved: <code>{files}</code>\n"
        f"🔁 Duplicates skipped: <code>{dup}</code>\n"
        f"🗑 Deleted messages: <code>{deleted}</code>\n"
        f"📭 No media: <code>{no_media + unsupported}</code> "
        f"(unsupported: <code>{unsupported}</code>)\n"
        f"❗ Errors: <code>{errors}</code>"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Other admin commands
# ─────────────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("total") & filters.user(ADMINS))
async def total_files(bot: Client, message: Message):
    msg = await safe_reply(message, "⏳ Counting…")
    if not msg:
        return
    try:
        n = await Media.count_documents()
        await safe_edit(msg, f"📦 <b>Total files in database:</b> <code>{n}</code>")
    except Exception as e:
        await safe_edit(msg, f"Error: <code>{e}</code>")


@Client.on_message(filters.command("channel") & filters.user(ADMINS))
async def channel_info(bot: Client, message: Message):
    if not CHANNELS:
        return await safe_reply(message, "No channels configured.")
    lines = ["📑 <b>Watched Channels</b>\n"]
    for ch in CHANNELS:
        try:
            chat = await bot.get_chat(ch)
            name = "@" + chat.username if chat.username else chat.title or str(ch)
        except Exception:
            name = str(ch)
        lines.append(f"• {name}")
    lines.append(f"\n<b>Total:</b> {len(CHANNELS)}")
    text = "\n".join(lines)
    if len(text) < 4096:
        await safe_reply(message, text)
    else:
        path = "/tmp/channels.txt"
        with open(path, "w") as f:
            f.write(text)
        try:
            await message.reply_document(path)
        except FloodWait as e:
            await asyncio.sleep(min(e.value, 30))
            await message.reply_document(path)
        finally:
            os.remove(path)


@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_file_cmd(bot: Client, message: Message):
    reply = message.reply_to_message
    if not (reply and reply.media):
        return await safe_reply(message, "⚠️ Reply to a media file with /delete.")
    msg = await safe_reply(message, "⏳ Processing…")
    if not msg:
        return
    for ftype in ("document", "video", "audio"):
        media = getattr(reply, ftype, None)
        if media:
            result = await Media.delete_one({"file_name": media.file_name, "file_size": media.file_size})
            if result.deleted_count:
                return await safe_edit(msg, "✅ Removed from database.")
            return await safe_edit(msg, "❌ File not found in database.")
    await safe_edit(msg, "⚠️ Unsupported file type.")


@Client.on_message(filters.command(["logs", "logger"]) & filters.user(ADMINS))
async def send_logs(bot: Client, message: Message):
    try:
        await message.reply_document("TelegramBot.log")
    except FloodWait as e:
        await asyncio.sleep(min(e.value, 30))
        try:
            await message.reply_document("TelegramBot.log")
        except Exception as e2:
            await safe_reply(message, f"FloodWait active, try again later: <code>{e2}</code>")
    except FileNotFoundError:
        await safe_reply(message, "No log file found.")
    except Exception as e:
        await safe_reply(message, str(e))
